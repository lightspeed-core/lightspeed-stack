"""Reducer state for pydantic-ai stream event dispatch."""

from dataclasses import dataclass, field

from models.common.turn_summary import ToolCallSummary, ToolResultSummary


@dataclass(slots=True)
class PydanticAiDispatchState:  # pylint: disable=too-many-instance-attributes
    """Streaming reducer state built incrementally from pydantic-ai events."""

    chunk_id: int = 0
    text_parts: list[str] = field(default_factory=list)
    llm_response: str = ""
    tool_calls: list[ToolCallSummary] = field(default_factory=list)
    tool_results: list[ToolResultSummary] = field(default_factory=list)
    tool_round: int = 1
    saw_tool_results_since_last_model_step: bool = False
    emitted_tool_call_ids: set[str] = field(default_factory=set)
    emitted_tool_result_ids: set[str] = field(default_factory=set)
