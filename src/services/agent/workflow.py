"""
Bounded agentic workflow orchestration for DevPilot.

Implements two cooperating classes:

  GuardedToolDispatcher
    A pure-async execution firewall that wraps every tool call with:
      1.  Phase boundary enforcement  (PHASE_VIOLATION)
      2.  Pydantic v2 runtime argument validation  (VALIDATION_ERROR)
      3.  asyncio.wait_for timeout isolation  (TIMEOUT)
      4.  Exception fallback blocks  (EXECUTION_ERROR)
    Every outcome – success or failure – is returned as a (payload, log) pair.
    The dispatcher never raises; it always produces a structured result so the
    agent loop can reflect errors back into the LLM context and self-correct.

  BoundedAgent
    A finite-state machine that drives the four-phase workflow:

        SEARCH  ->  INSPECT  ->  SUMMARIZE  ->  PROPOSE

    Bounded by MAX_ITERATIONS = 5.  Phases only advance on SUCCESS; on any
    non-SUCCESS outcome the LLM receives the structured error payload so it can
    adjust its next tool call (self-correction within the iteration budget).

    The PROPOSE phase is handled differently from the three tool phases:
    no tool call occurs; instead the agent synthesises an AgentProposal from
    the accumulated context using the LLM service, then wraps everything in
    a WorkflowReport and returns it to the caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.agent.schemas import (
    AgentProposal,
    InspectInput,
    SearchInput,
    SummarizeInput,
    ToolExecutionLog,
    ToolExecutionStatus,
    WorkflowPhase,
    WorkflowReport,
)
from src.services.agent.tools import inspect_chunk, search_project, summarize_text
from src.services.llm import LLMService, get_llm_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ordered phase sequence enforced by the state machine
PHASE_SEQUENCE: list[WorkflowPhase] = [
    WorkflowPhase.SEARCH,
    WorkflowPhase.INSPECT,
    WorkflowPhase.SUMMARIZE,
    WorkflowPhase.PROPOSE,
]

# Maps each tool-call phase to its (validation_schema, async_callable, human_name)
# The callable signatures are the inner *keyword* arguments accepted after
# (project_id, session) are injected by the dispatcher.
_TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "search_project": {
        "phase": WorkflowPhase.SEARCH,
        "schema": SearchInput,
        # query is the only schema-validated arg; project_id + session injected
        "arg_key": "query",
    },
    "inspect_chunk": {
        "phase": WorkflowPhase.INSPECT,
        "schema": InspectInput,
        "arg_key": "chunk_id",
    },
    "summarize_text": {
        "phase": WorkflowPhase.SUMMARIZE,
        "schema": SummarizeInput,
        "arg_key": "text",
    },
}

# LLM proposal synthesis prompt (PROPOSE phase — no tool call)
_PROPOSE_SYSTEM_PROMPT = """You are DevPilot AI, a senior engineering analyst.
You have just completed a structured research workflow:
  SEARCH: retrieved relevant document chunks from the project corpus.
  INSPECT: read the full text of the most relevant chunk.
  SUMMARIZE: distilled the key technical findings.

Your task now is to synthesise everything into a structured JSON proposal.
Respond ONLY with a valid JSON object matching this exact schema (no markdown, no prose):

{
  "title": "<concise descriptive title, 5-15 words>",
  "executive_summary": "<2-4 sentence synthesis of findings>",
  "action_items": ["<item 1>", "<item 2>", "<item 3>"],
  "confidence_score": <float between 0.0 and 1.0>
}

Base the confidence_score on how well the retrieved evidence supports the proposal.
Do NOT add fields outside the schema. Do NOT wrap in markdown code fences."""


# ---------------------------------------------------------------------------
# GuardedToolDispatcher
# ---------------------------------------------------------------------------


class GuardedToolDispatcher:
    """Async execution firewall wrapping every tool invocation with four layers of protection.

    Execution order for each call:
      1. Tool existence check
      2. Phase boundary enforcement
      3. Pydantic v2 schema validation of raw arguments
      4. asyncio.wait_for timeout-bounded execution
      5. General exception catch-all

    Every outcome returns ``(result_payload, ToolExecutionLog)``.  The caller
    (BoundedAgent) appends the payload to the LLM message history and the log
    to the WorkflowReport — the dispatcher itself never raises.

    Args:
        per_tool_timeout: Seconds before a running tool coroutine is cancelled.
                          Default 3.0 s matches the spec requirement.
    """

    def __init__(self, per_tool_timeout: float = 3.0) -> None:
        self.per_tool_timeout = per_tool_timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_validation_error_payload(
        tool_name: str,
        errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Serialise a Pydantic ValidationError into an LLM-readable dict."""
        return {
            "status": "validation_error",
            "tool": tool_name,
            "message": (
                f"Argument validation failed for tool '{tool_name}'. "
                "Fix the argument and retry."
            ),
            "details": [
                {
                    "field": ".".join(str(p) for p in err["loc"]),
                    "error": err["msg"],
                    "type": err["type"],
                }
                for err in errors
            ],
        }

    @staticmethod
    def _build_error_payload(
        status: str,
        tool_name: str,
        message: str,
    ) -> dict[str, Any]:
        """Serialise a generic (timeout / execution) error into an LLM-readable dict."""
        return {
            "status": status,
            "tool": tool_name,
            "message": message,
        }

    # ------------------------------------------------------------------
    # Public dispatch interface
    # ------------------------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        raw_arguments: dict[str, Any],
        current_phase: WorkflowPhase,
        iteration: int,
        *,
        project_id: UUID,
        session: AsyncSession,
    ) -> tuple[dict[str, Any], ToolExecutionLog]:
        """Dispatch a single tool call through all four guard layers.

        Args:
            tool_name:      Exact name of the tool as declared in ``_TOOL_REGISTRY``.
            raw_arguments:  JSON-decoded dict from the LLM tool-call arguments string.
            current_phase:  Active workflow phase at call time.
            iteration:      1-based loop iteration counter for the telemetry log.
            project_id:     Project UUID injected into session-backed tools.
            session:        Active AsyncSession injected into session-backed tools.

        Returns:
            Tuple of (payload, ToolExecutionLog).
            payload is either a success result dict or a structured error dict.
            The caller must *never* raise on a non-SUCCESS log status; it should
            instead inject the payload into LLM context and continue looping.
        """
        t_start = time.perf_counter()
        validated_inputs: dict[str, Any] | None = None

        # ── Guard 1: Tool existence ────────────────────────────────────────
        if tool_name not in _TOOL_REGISTRY:
            runtime = time.perf_counter() - t_start
            payload = self._build_error_payload(
                "execution_error",
                tool_name,
                f"Unknown tool '{tool_name}'. Valid tools: {list(_TOOL_REGISTRY)}.",
            )
            log = ToolExecutionLog(
                iteration=iteration,
                phase=current_phase,
                tool_name=tool_name,
                raw_arguments=raw_arguments,
                status=ToolExecutionStatus.EXECUTION_ERROR,
                runtime_seconds=round(runtime, 6),
                output_or_error=payload,
            )
            logger.warning("GuardedDispatcher: unknown tool '%s'", tool_name)
            return payload, log

        meta = _TOOL_REGISTRY[tool_name]

        # ── Guard 2: Phase boundary enforcement ────────────────────────────
        expected_phase: WorkflowPhase = meta["phase"]
        if expected_phase != current_phase:
            runtime = time.perf_counter() - t_start
            payload = self._build_error_payload(
                "phase_violation",
                tool_name,
                (
                    f"Tool '{tool_name}' belongs to phase '{expected_phase.value}' "
                    f"but was called during phase '{current_phase.value}'. "
                    f"You must call the '{current_phase.value.lower()}' phase tool."
                ),
            )
            log = ToolExecutionLog(
                iteration=iteration,
                phase=current_phase,
                tool_name=tool_name,
                raw_arguments=raw_arguments,
                status=ToolExecutionStatus.PHASE_VIOLATION,
                runtime_seconds=round(runtime, 6),
                output_or_error=payload,
            )
            logger.warning(
                "GuardedDispatcher: phase violation — tool=%s expected=%s got=%s",
                tool_name, expected_phase.value, current_phase.value,
            )
            return payload, log

        # ── Guard 3: Pydantic v2 argument validation ───────────────────────
        schema: type[BaseModel] = meta["schema"]
        try:
            validated_model = schema.model_validate(raw_arguments)
            validated_inputs = validated_model.model_dump()
        except ValidationError as val_err:
            runtime = time.perf_counter() - t_start
            payload = self._build_validation_error_payload(
                tool_name, val_err.errors()
            )
            log = ToolExecutionLog(
                iteration=iteration,
                phase=current_phase,
                tool_name=tool_name,
                raw_arguments=raw_arguments,
                status=ToolExecutionStatus.VALIDATION_ERROR,
                runtime_seconds=round(runtime, 6),
                output_or_error=payload,
            )
            logger.info(
                "GuardedDispatcher: validation error on '%s': %s",
                tool_name, val_err.errors(),
            )
            return payload, log

        # ── Guard 4a: Build coroutine from validated inputs ───────────────
        # Inject project_id + session for session-backed tools;
        # summarize_text is session-agnostic (pure text transformation).
        if tool_name == "search_project":
            coro = search_project(
                query=validated_inputs["query"],
                project_id=project_id,
                session=session,
            )
        elif tool_name == "inspect_chunk":
            coro = inspect_chunk(
                chunk_id=validated_inputs["chunk_id"],
                project_id=project_id,
                session=session,
            )
        else:  # summarize_text
            coro = summarize_text(text=validated_inputs["text"])

        # ── Guard 4b: Timeout-bounded execution ───────────────────────────
        try:
            result: dict[str, Any] = await asyncio.wait_for(
                coro, timeout=self.per_tool_timeout
            )
            runtime = time.perf_counter() - t_start
            payload = {"status": "success", "data": result}
            log = ToolExecutionLog(
                iteration=iteration,
                phase=current_phase,
                tool_name=tool_name,
                raw_arguments=raw_arguments,
                validated_inputs=validated_inputs,
                status=ToolExecutionStatus.SUCCESS,
                runtime_seconds=round(runtime, 6),
                output_or_error=result,
            )
            logger.info(
                "GuardedDispatcher: %s SUCCESS in %.3fs",
                tool_name, runtime,
            )
            return payload, log

        except TimeoutError:
            runtime = time.perf_counter() - t_start
            payload = self._build_error_payload(
                "timeout",
                tool_name,
                (
                    f"Tool '{tool_name}' exceeded the {self.per_tool_timeout}s timeout. "
                    "The operation was cancelled. Retry with a narrower query."
                ),
            )
            log = ToolExecutionLog(
                iteration=iteration,
                phase=current_phase,
                tool_name=tool_name,
                raw_arguments=raw_arguments,
                validated_inputs=validated_inputs,
                status=ToolExecutionStatus.TIMEOUT,
                runtime_seconds=round(runtime, 6),
                output_or_error=payload,
            )
            logger.warning(
                "GuardedDispatcher: TIMEOUT on '%s' after %.2fs",
                tool_name, runtime,
            )
            return payload, log

        except Exception as exc:
            runtime = time.perf_counter() - t_start
            payload = self._build_error_payload(
                "execution_error",
                tool_name,
                f"Tool '{tool_name}' raised {type(exc).__name__}: {exc}",
            )
            log = ToolExecutionLog(
                iteration=iteration,
                phase=current_phase,
                tool_name=tool_name,
                raw_arguments=raw_arguments,
                validated_inputs=validated_inputs,
                status=ToolExecutionStatus.EXECUTION_ERROR,
                runtime_seconds=round(runtime, 6),
                output_or_error=payload,
            )
            logger.error(
                "GuardedDispatcher: EXECUTION_ERROR on '%s': %s",
                tool_name, exc, exc_info=True,
            )
            return payload, log


# ---------------------------------------------------------------------------
# BoundedAgent — finite state machine driver
# ---------------------------------------------------------------------------


class BoundedAgent:
    """Phase-gated agentic workflow: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE.

    The agent drives a simple finite state machine (FSM):
      - Exactly one tool is available per phase (declared in ``_TOOL_REGISTRY``).
      - The dispatcher validates arguments and executes the tool within a timeout.
      - On SUCCESS the FSM advances to the next phase.
      - On any non-SUCCESS the error payload is injected into LLM context so the
        model can self-correct on the next iteration, staying in the same phase.
      - The loop terminates when all four phases complete (COMPLETED) or the
        MAX_ITERATIONS cap is hit (MAX_ITERATIONS_REACHED).

    The PROPOSE phase does not execute a tool.  Instead the agent calls the LLM
    with the full accumulated context and parses the JSON response into an
    ``AgentProposal``.  If parsing fails a minimal fallback proposal is used.

    Args:
        project_id:          UUID of the project being analysed.
        session:             Async DB session; passed through to tool calls.
        llm_service:         Optional pre-configured LLMService.  Defaults to the
                             application-wide singleton (``get_llm_service()``).
        per_tool_timeout:    Per-tool asyncio timeout in seconds (default 3.0 s).
        max_iterations:      Hard loop cap (default 5).
    """

    MAX_ITERATIONS: int = 5

    def __init__(
        self,
        project_id: UUID,
        session: AsyncSession,
        *,
        llm_service: LLMService | None = None,
        per_tool_timeout: float = 3.0,
        max_iterations: int = 5,
    ) -> None:
        self.project_id = project_id
        self.session = session
        self.llm_service: LLMService = llm_service or get_llm_service()
        self.dispatcher = GuardedToolDispatcher(per_tool_timeout=per_tool_timeout)
        self.max_iterations = max_iterations

    # ------------------------------------------------------------------
    # LLM interaction helpers
    # ------------------------------------------------------------------

    def _build_initial_messages(self, goal: str) -> list[dict[str, Any]]:
        """Construct the opening system + user message pair."""
        return [
            {
                "role": "system",
                "content": (
                    "You are DevPilot AI, a bounded technical research agent. "
                    "You operate in four strict phases: SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE. "
                    "Each phase exposes exactly one tool. Always call the tool for the active phase. "
                    "Do NOT call tools from a different phase. "
                    "If a tool returns an error, correct your arguments and call it again."
                ),
            },
            {"role": "user", "content": goal},
        ]

    def _phase_tool_instruction(self, phase: WorkflowPhase) -> str:
        """Return a brief instruction injected before each phase's tool call."""
        instructions = {
            WorkflowPhase.SEARCH: (
                "Phase SEARCH: call search_project with a focused query string "
                "to retrieve relevant document chunks."
            ),
            WorkflowPhase.INSPECT: (
                "Phase INSPECT: call inspect_chunk with the chunk_id of the most "
                "relevant chunk returned by search_project."
            ),
            WorkflowPhase.SUMMARIZE: (
                "Phase SUMMARIZE: call summarize_text with the full content field "
                "from the inspect_chunk result."
            ),
            WorkflowPhase.PROPOSE: (
                "Phase PROPOSE: synthesise all gathered evidence into a structured "
                "proposal. Respond with only a JSON object matching the schema."
            ),
        }
        return instructions[phase]

    async def _call_llm_for_tool(
        self,
        messages: list[dict[str, Any]],
        phase: WorkflowPhase,
    ) -> dict[str, Any]:
        """Ask the LLM to emit a tool call for the current phase.

        In mock / test mode the LLM service does not produce tool calls, so we
        synthesise a deterministic tool call from the accumulated context to keep
        the FSM running without a real LLM key.

        Returns:
            dict with at least ``"tool_name"`` and ``"arguments"`` keys.
        """
        if self.llm_service._use_mock:
            return self._mock_tool_call(messages, phase)

        # Real path: call the LLM and parse its response.
        # We use generate_grounded_answer as a generic completion primitive
        # (it makes one HTTP call and returns the raw answer text).
        instruction = self._phase_tool_instruction(phase)
        tool_prompt = (
            f"{instruction}\n\n"
            "Respond ONLY with a valid JSON object: "
            "{\"tool_name\": \"<tool>\", \"arguments\": {<key>: <value>}}"
        )
        context_chunks = [
            {"content": m["content"], "index": i + 1, "filename": "context"}
            for i, m in enumerate(messages)
            if m.get("role") != "system" and m.get("content")
        ]
        try:
            raw, _ = await self.llm_service.generate_grounded_answer(
                query=tool_prompt,
                context_chunks=context_chunks,
                temperature=0.0,
            )
            data = json.loads(raw)
            if "tool_name" in data and "arguments" in data:
                return data
        except Exception as exc:
            logger.warning("LLM tool-call parse error: %s. Falling back to mock.", exc)

        # Graceful fallback to mock if the real LLM returns unparseable output
        return self._mock_tool_call(messages, phase)

    def _mock_tool_call(
        self,
        messages: list[dict[str, Any]],
        phase: WorkflowPhase,
    ) -> dict[str, Any]:
        """Generate a deterministic tool call from accumulated context messages.

        Extracts artefacts produced by previous successful tool calls so each
        phase correctly feeds from the prior phase's output.
        """
        # Collect the most recent tool result payload from the message history
        last_tool_result: dict[str, Any] = {}
        for msg in reversed(messages):
            if msg.get("role") == "tool":
                try:
                    payload = json.loads(msg["content"])
                    if payload.get("status") == "success" and "data" in payload:
                        last_tool_result = payload["data"]
                        break
                except (json.JSONDecodeError, KeyError):
                    pass

        if phase == WorkflowPhase.SEARCH:
            # Extract goal from initial user message
            goal = next(
                (m["content"] for m in messages if m.get("role") == "user"), "project"
            )
            query = " ".join(goal.split()[:8])  # first 8 words as query
            return {
                "tool_name": "search_project",
                "arguments": {"query": query},
            }

        elif phase == WorkflowPhase.INSPECT:
            # Pick the first chunk_id from the search result
            chunks = last_tool_result.get("chunks", [])
            if chunks:
                chunk_id = str(chunks[0].get("chunk_id", ""))
                if chunk_id:
                    return {
                        "tool_name": "inspect_chunk",
                        "arguments": {"chunk_id": chunk_id},
                    }
            # Fallback: inject an obviously invalid id so validation error fires
            # and the LLM can self-correct (loop won't stall; error is reflected back)
            return {
                "tool_name": "inspect_chunk",
                "arguments": {"chunk_id": "00000000-0000-4000-8000-000000000000"},
            }

        elif phase == WorkflowPhase.SUMMARIZE:
            content = last_tool_result.get("content", "")
            if not content:
                content = "No content available from the inspected chunk."
            # Pad to meet the 20-char minimum if needed
            if len(content) < 20:
                content = content + " " * (20 - len(content))
            return {
                "tool_name": "summarize_text",
                "arguments": {"text": content},
            }

        # PROPOSE has no tool call — handled separately by _run_propose_phase
        raise ValueError(f"_mock_tool_call called for unsupported phase: {phase}")

    async def _call_llm_for_proposal(
        self,
        messages: list[dict[str, Any]],
    ) -> AgentProposal:
        """Synthesise a structured AgentProposal from the full accumulated context.

        Uses the LLM for a JSON-formatted response; falls back to a deterministic
        proposal extracted from the context messages if the LLM is in mock mode
        or JSON parsing fails.

        Returns:
            A validated ``AgentProposal`` instance.
        """
        if self.llm_service._use_mock:
            return self._build_mock_proposal(messages)

        # Build condensed context string from assistant/tool messages
        context_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content") or ""
            if role in ("assistant", "tool") and content:
                context_parts.append(content[:800])  # cap per-message length

        context_summary = "\n---\n".join(context_parts) or "No context gathered."

        try:
            raw, _ = await self.llm_service.generate_grounded_answer(
                query=_PROPOSE_SYSTEM_PROMPT,
                context_chunks=[
                    {"content": context_summary, "index": 1, "filename": "workflow_context"}
                ],
                temperature=0.0,
            )
            # Strip markdown code fences if the LLM wrapped the JSON
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(raw)
            proposal = AgentProposal.model_validate(data)
            logger.info("BoundedAgent: LLM proposal parsed successfully.")
            return proposal
        except Exception as exc:
            logger.warning(
                "BoundedAgent: proposal parse error (%s). Using mock fallback.", exc
            )
            return self._build_mock_proposal(messages)

    def _build_mock_proposal(self, messages: list[dict[str, Any]]) -> AgentProposal:
        """Build a deterministic AgentProposal from accumulated context messages.

        Extracts summary text and search query from prior tool results to produce
        a plausible (but generic) proposal without an LLM call.
        """
        summary_text = ""
        search_query = ""

        for msg in reversed(messages):
            if msg.get("role") != "tool":
                continue
            try:
                payload = json.loads(msg["content"])
                data = payload.get("data", {})
                if "summary" in data and not summary_text:
                    summary_text = data["summary"]
                if "query" in data and not search_query:
                    search_query = data["query"]
            except (json.JSONDecodeError, KeyError):
                pass

        executive_summary = (
            summary_text
            or "Analysis of the project corpus was completed via hybrid retrieval, "
               "full chunk inspection, and extractive summarisation."
        )
        title = (
            f"Technical Analysis: {search_query.title()}"
            if search_query
            else "DevPilot Project Analysis"
        )

        return AgentProposal(
            title=title,
            executive_summary=executive_summary,
            action_items=[
                "Review the retrieved document chunks for completeness.",
                "Validate findings against the project's current implementation.",
                "Address identified gaps in the technical documentation.",
            ],
            confidence_score=0.75,
        )

    # ------------------------------------------------------------------
    # Phase runners
    # ------------------------------------------------------------------

    async def _run_tool_phase(
        self,
        phase: WorkflowPhase,
        messages: list[dict[str, Any]],
        execution_logs: list[ToolExecutionLog],
        phase_history: list[str],
        iteration_ref: list[int],
    ) -> bool:
        """Execute one iteration of a tool-based phase (SEARCH / INSPECT / SUMMARIZE).

        Asks the LLM for a tool call, dispatches it through the guardrail firewall,
        appends the result to ``messages`` and ``execution_logs``, and returns
        ``True`` if the phase should advance (i.e. tool call succeeded).

        Args:
            phase:          Active workflow phase.
            messages:       Mutable LLM conversation history (modified in place).
            execution_logs: Mutable telemetry log list (appended in place).
            phase_history:  Mutable phase trace list (appended in place).
            iteration_ref:  Single-element list acting as a mutable int reference
                            (Python doesn't have pass-by-reference for ints).

        Returns:
            True  → phase succeeded, advance FSM.
            False → tool error / iteration cap reached, stay in phase or exit.
        """
        iteration = iteration_ref[0]
        phase_history.append(phase.value)
        logger.info("BoundedAgent: iteration=%d phase=%s", iteration, phase.value)

        # Ask LLM for a tool call
        tool_response = await self._call_llm_for_tool(messages, phase)
        tool_name: str = tool_response.get("tool_name", "")
        raw_args: dict[str, Any] = tool_response.get("arguments", {})

        # Append assistant turn with the tool call intent
        messages.append({
            "role": "assistant",
            "content": f"[Phase {phase.value}] Calling {tool_name} with {raw_args}",
        })

        # Dispatch through the guarded firewall
        payload, log = await self.dispatcher.execute(
            tool_name=tool_name,
            raw_arguments=raw_args,
            current_phase=phase,
            iteration=iteration,
            project_id=self.project_id,
            session=self.session,
        )
        execution_logs.append(log)

        # Inject result / error into LLM context as a tool response message
        messages.append({
            "role": "tool",
            "content": json.dumps(payload, default=str),
        })

        logger.info(
            "BoundedAgent: %s -> %s (%.3fs)",
            tool_name, log.status.value, log.runtime_seconds,
        )

        return log.status == ToolExecutionStatus.SUCCESS

    async def _run_propose_phase(
        self,
        messages: list[dict[str, Any]],
        phase_history: list[str],
        iteration_ref: list[int],
    ) -> AgentProposal:
        """Execute the PROPOSE phase: synthesise an AgentProposal from full context.

        No tool is called here.  The LLM (or mock fallback) is asked directly
        to produce structured JSON matching the AgentProposal schema.

        Returns:
            A validated ``AgentProposal`` instance.
        """
        phase_history.append(WorkflowPhase.PROPOSE.value)
        logger.info(
            "BoundedAgent: iteration=%d phase=PROPOSE (synthesis)",
            iteration_ref[0],
        )
        messages.append({
            "role": "assistant",
            "content": "[Phase PROPOSE] Synthesising structured proposal from workflow context.",
        })
        return await self._call_llm_for_proposal(messages)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        goal: str | None = None,
        *,
        user_goal: str | None = None,
    ) -> WorkflowReport:
        """Execute the full bounded agentic workflow for the given goal.

        Drives the FSM through SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE,
        bounded by ``self.max_iterations``.

        Args:
            goal: Plain-English research objective (or user_goal).
            user_goal: Keyword alias for goal.

        Returns:
            A fully populated ``WorkflowReport`` capturing both the
            ``final_proposal`` and the step-by-step ``execution_logs`` audit trail.
        """
        resolved_goal = user_goal or goal
        if not resolved_goal:
            raise ValueError("A research goal (goal or user_goal) must be provided.")

        wall_start = time.perf_counter()

        messages = self._build_initial_messages(resolved_goal)
        execution_logs: list[ToolExecutionLog] = []
        phase_history: list[str] = []
        final_proposal: AgentProposal | None = None

        # Mutable iteration counter as a single-element list (so helpers can mutate it)
        iteration_ref: list[int] = [0]

        # Indices into PHASE_SEQUENCE; PROPOSE is handled separately
        tool_phase_count = len(PHASE_SEQUENCE) - 1  # SEARCH, INSPECT, SUMMARIZE
        phase_index = 0  # index into PHASE_SEQUENCE

        logger.info(
            "BoundedAgent.run: project=%s goal=%r max_iter=%d",
            self.project_id, goal, self.max_iterations,
        )

        while iteration_ref[0] < self.max_iterations:
            iteration_ref[0] += 1
            current_phase = PHASE_SEQUENCE[phase_index]

            # ── PROPOSE phase: no tool call, direct synthesis ──────────────
            if current_phase == WorkflowPhase.PROPOSE:
                final_proposal = await self._run_propose_phase(
                    messages, phase_history, iteration_ref
                )
                phase_index += 1  # past the end → loop will not re-enter
                break

            # ── Tool phase: SEARCH / INSPECT / SUMMARIZE ───────────────────
            succeeded = await self._run_tool_phase(
                phase=current_phase,
                messages=messages,
                execution_logs=execution_logs,
                phase_history=phase_history,
                iteration_ref=iteration_ref,
            )

            if succeeded:
                phase_index += 1
                # Check if we've exhausted all tool phases and should PROPOSE next
                if phase_index == tool_phase_count:
                    # Advance into PROPOSE on the next iteration
                    pass
            else:
                logger.info(
                    "BoundedAgent: phase %s did not advance (non-SUCCESS), retrying.",
                    current_phase.value,
                )
                # Stay in current phase; loop cap will catch runaway failures

        # ── Terminal status determination ──────────────────────────────────
        if final_proposal is not None:
            status = "COMPLETED"
        elif iteration_ref[0] >= self.max_iterations:
            status = "MAX_ITERATIONS_REACHED"
        else:
            status = "TERMINATED_ON_ERROR"

        total_runtime = round(time.perf_counter() - wall_start, 6)

        logger.info(
            "BoundedAgent.run: DONE status=%s iterations=%d runtime=%.3fs",
            status, iteration_ref[0], total_runtime,
        )

        return WorkflowReport(
            status=status,
            total_iterations=iteration_ref[0],
            total_runtime_seconds=total_runtime,
            phase_history=phase_history,
            execution_logs=execution_logs,
            final_proposal=final_proposal,
        )
