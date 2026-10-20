"""
Agent service schemas for the DevPilot bounded agentic workflow.

This module defines the full type surface for the SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE
phase-gated agent loop. All tool input schemas enforce strict Pydantic v2 runtime validation
before any tool function executes. Output schemas produce a structured WorkflowReport for
consumption by the API layer and tests.

Design principles:
  - Mirrors DevPilot's existing BaseSchema / ConfigDict(from_attributes=True) convention.
  - Uses Pydantic v2 field constraints (min_length, max_length, ge, le, pattern) as the
    primary validation layer — no separate validator methods required.
  - Enum members use str mixin so they serialise as plain strings in JSON responses.
  - All runtime-generated objects (ToolExecutionLog, WorkflowReport) are read-only after
    creation; model_config enforces from_attributes=True for ORM compat.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Workflow Phase State Machine
# ---------------------------------------------------------------------------


class WorkflowPhase(str, Enum):
    """Ordered phase identifiers enforcing SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE progression.

    The agent controller must only allow the phase-specific tool to be called
    during each phase; any out-of-order invocation raises a PHASE_VIOLATION error.
    """

    SEARCH = "SEARCH"
    INSPECT = "INSPECT"
    SUMMARIZE = "SUMMARIZE"
    PROPOSE = "PROPOSE"


# ---------------------------------------------------------------------------
# Tool Ingress Validation Schemas
# ---------------------------------------------------------------------------


class SearchInput(BaseModel):
    """Validated input for the ``search_chunks`` tool (SEARCH phase).

    Enforces a non-trivial minimum query length to prevent degenerate BM25
    single-character queries from saturating the retrieval pipeline.
    """

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    query: str = Field(
        ...,
        min_length=3,
        max_length=512,
        description=(
            "Natural-language search query. Must contain at least 3 characters. "
            "Drives hybrid retrieval (dense + BM25 + RRF) against the project corpus."
        ),
    )


class InspectInput(BaseModel):
    """Validated input for the ``inspect_chunk`` tool (INSPECT phase).

    Accepts either:
      - A canonical UUID4 string:  ``xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx``
      - A bare 32-char hex string: ``xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx``

    Both formats are used in the DevPilot corpus depending on how the chunk_id
    was stored (UUID column with/without hyphens).
    """

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    chunk_id: str = Field(
        ...,
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
            r"|^[0-9a-fA-F]{32}$"
        ),
        description=(
            "Document chunk identifier. Accepts canonical UUID4 format "
            "(e.g. '3fa85f64-5717-4562-b3fc-2c963f66afa6') or 32-char hex string."
        ),
    )


class SummarizeInput(BaseModel):
    """Validated input for the ``summarize_chunk`` tool (SUMMARIZE phase).

    The 20-character minimum prevents the model from attempting to summarize
    single-word or near-empty text that would produce meaningless proposals.
    """

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    text: str = Field(
        ...,
        min_length=20,
        max_length=16_000,
        description=(
            "Full extracted text content to condense. Must be at least 20 characters. "
            "Typically sourced directly from inspect_chunk output."
        ),
    )


# ---------------------------------------------------------------------------
# Execution Telemetry Schemas
# ---------------------------------------------------------------------------


class ToolExecutionStatus(str, Enum):
    """Categorised outcome status for each tool invocation attempt.

    SUCCESS          - Tool returned a valid result; phase may advance.
    VALIDATION_ERROR - LLM-supplied arguments failed Pydantic ingress validation.
    TIMEOUT          - Tool coroutine exceeded the per-tool asyncio timeout.
    EXECUTION_ERROR  - Tool raised an unexpected runtime exception.
    PHASE_VIOLATION  - Tool was called in the wrong workflow phase.
    """

    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TIMEOUT = "TIMEOUT"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    PHASE_VIOLATION = "PHASE_VIOLATION"


class ToolExecutionLog(BaseModel):
    """Immutable telemetry record for a single tool invocation attempt.

    One log entry is emitted per tool call, regardless of success or failure.
    Validation errors include the structured Pydantic error detail list so the
    LLM can inspect schema violations and self-correct on the next iteration.
    """

    model_config = ConfigDict(from_attributes=True)

    iteration: int = Field(
        ...,
        ge=1,
        description="1-indexed loop iteration counter within the bounded workflow.",
    )
    phase: WorkflowPhase = Field(
        ...,
        description="Active workflow phase at the time of this tool call.",
    )
    tool_name: str = Field(
        ...,
        description="Name of the tool that was invoked (e.g. 'search_chunks').",
    )
    raw_arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw JSON-decoded arguments as received from the LLM before validation.",
    )
    validated_inputs: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Pydantic-validated, normalised inputs passed to the tool implementation. "
            "None when status is VALIDATION_ERROR or PHASE_VIOLATION."
        ),
    )
    status: ToolExecutionStatus = Field(
        ...,
        description="Final outcome category of this tool invocation.",
    )
    runtime_seconds: float = Field(
        ...,
        ge=0.0,
        description="Wall-clock execution time in seconds measured with time.perf_counter().",
    )
    output_or_error: Any = Field(
        ...,
        description=(
            "Successful tool output (dict) or structured error payload (dict with "
            "'status', 'message', and optional 'details' keys) returned back to the LLM."
        ),
    )


# ---------------------------------------------------------------------------
# Deliverable Schemas
# ---------------------------------------------------------------------------


class AgentProposal(BaseModel):
    """Structured final deliverable synthesised during the PROPOSE phase.

    Designed for direct serialisation to the API response body. The confidence_score
    is agent-assigned (0.0 to 1.0) based on how well the retrieved evidence supports
    the proposed action items.
    """

    model_config = ConfigDict(from_attributes=True)

    title: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Concise, descriptive title for the proposed plan or finding.",
    )
    executive_summary: str = Field(
        ...,
        min_length=10,
        description=(
            "High-level synthesis of evidence gathered across SEARCH, INSPECT, "
            "and SUMMARIZE phases that supports the proposed action items."
        ),
    )
    action_items: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Ordered list of concrete, implementable recommendations derived "
            "from the retrieved and summarised project context."
        ),
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Agent confidence rating between 0.0 (uncertain) and 1.0 (highly confident) "
            "reflecting evidence coverage across the retrieved corpus."
        ),
    )


class WorkflowReport(BaseModel):
    """Complete, immutable report returned at the end of a bounded agent run.

    Captures both the deliverable (final_proposal) and the full audit trail
    (execution_logs) for observability, testing, and debugging.

    status values:
      COMPLETED              - All 4 phases completed; final_proposal is present.
      MAX_ITERATIONS_REACHED - Loop cap hit before PROPOSE phase could complete.
      TERMINATED_ON_ERROR    - Unrecoverable error forced early exit.
    """

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(
        ...,
        description=(
            "Terminal run status: 'COMPLETED', 'MAX_ITERATIONS_REACHED', or "
            "'TERMINATED_ON_ERROR'."
        ),
    )
    total_iterations: int = Field(
        ...,
        ge=0,
        description="Total number of agent loop iterations executed (bounded by MAX_ITERATIONS).",
    )
    total_runtime_seconds: float = Field(
        ...,
        ge=0.0,
        description="End-to-end wall-clock time in seconds for the complete workflow run.",
    )
    phase_history: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered sequence of WorkflowPhase values visited during the run, "
            "e.g. ['SEARCH', 'INSPECT', 'SUMMARIZE', 'PROPOSE']. "
            "May contain duplicates when a phase is retried after a validation error."
        ),
    )
    execution_logs: list[ToolExecutionLog] = Field(
        default_factory=list,
        description=(
            "Complete ordered list of ToolExecutionLog entries, one per tool call attempt. "
            "Includes both successful and failed invocations for full audit traceability."
        ),
    )
    final_proposal: AgentProposal | None = Field(
        default=None,
        description=(
            "Structured proposal produced during the PROPOSE phase. "
            "None when status is not COMPLETED."
        ),
    )
