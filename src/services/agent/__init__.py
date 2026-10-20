"""
DevPilot Agent Service Module.

Implements a bounded agentic workflow (SEARCH -> INSPECT -> SUMMARIZE -> PROPOSE)
with strict Pydantic v2 runtime validation, per-tool timeout isolation, and
structured WorkflowReport output for integration with the DevPilot RAG pipeline.
"""

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
from src.services.agent.workflow import BoundedAgent, GuardedToolDispatcher

__all__ = [
    # Schemas
    "WorkflowPhase",
    "SearchInput",
    "InspectInput",
    "SummarizeInput",
    "ToolExecutionStatus",
    "ToolExecutionLog",
    "AgentProposal",
    "WorkflowReport",
    # Tools
    "search_project",
    "inspect_chunk",
    "summarize_text",
    # Workflow
    "GuardedToolDispatcher",
    "BoundedAgent",
]
