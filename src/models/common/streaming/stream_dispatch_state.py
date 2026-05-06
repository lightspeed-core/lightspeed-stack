"""State models for streaming dispatch."""

from dataclasses import dataclass, field
from typing import Optional

from llama_stack_api import OpenAIResponseObject

from models.common.turn_summary import ToolCallSummary, ToolResultSummary


@dataclass(slots=True)
class StreamDispatchState:
    """Streaming reducer state built incrementally from chunk events."""

    chunk_id: int = 0
    text_parts: list[str] = field(default_factory=list)
    llm_response: str = ""
    tool_calls: list[ToolCallSummary] = field(default_factory=list)
    tool_results: list[ToolResultSummary] = field(default_factory=list)
    mcp_calls: dict[int, tuple[str, str]] = field(default_factory=dict)
    latest_response_object: Optional[OpenAIResponseObject] = None


@dataclass(slots=True)
class ChunkDispatchResult:
    """Result returned by chunk handlers."""

    state: StreamDispatchState
    events: list[str] = field(default_factory=list)
