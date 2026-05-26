"""Unit tests for pydantic-ai stream event dispatchers."""

import json
from types import SimpleNamespace
from typing import Literal, cast

from pydantic_ai.messages import (
    ModelResponse,
    ModelResponseState,
    NativeToolReturnPart,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturnPart,
)
from pydantic_ai.native_tools import MCPServerTool, WebSearchTool

from models.common.turn_summary import MCPListToolsSummary, ToolInfoSummary
from utils.streaming.pydantic_ai_dispatch_state import PydanticAiDispatchState
from utils.streaming.pydantic_ai_event_dispatchers import (
    dispatch_stream_event,
    process_turn_complete_event,
)
from utils.streaming.pydantic_ai_tool_summaries import (
    function_tool_call_summary,
    function_tool_result_summary,
    tool_result_summary,
)


def test_function_tool_call_summary() -> None:
    """Function calls use call_id, name, args, and type=function_call."""
    part = ToolCallPart("search", '{"query": "x"}', tool_call_id="call_abc")
    summary = function_tool_call_summary(part)
    assert summary is not None
    assert summary.id == "call_abc"
    assert summary.name == "search"
    assert summary.args == {"query": "x"}
    assert summary.type == "function_call"


def test_tool_result_summary_function_call_output() -> None:
    """Client function returns mirror Open Responses function_call_output."""
    part = ToolReturnPart(
        tool_name="search",
        content={"hits": 1},
        tool_call_id="call_fn_1",
    )
    summary = function_tool_result_summary(part, tool_round=1)
    assert summary.type == "function_call_output"
    assert summary.id == "call_fn_1"
    assert json.loads(summary.content) == {"hits": 1}


def test_tool_result_summary_web_search_sources() -> None:
    """Web search results serialize optional citation sources as JSON."""
    sources = [{"url": "https://example.com", "title": "Example"}]
    part = NativeToolReturnPart(
        tool_name=WebSearchTool.kind,
        tool_call_id="ws_1",
        content={"status": "completed", "sources": sources},
    )
    summary = tool_result_summary(part, tool_round=1)
    assert summary.type == "web_search_call"
    assert json.loads(summary.content) == {"sources": sources}


def test_tool_result_summary_web_search_without_sources() -> None:
    """Web search results without sources use empty content."""
    part = NativeToolReturnPart(
        tool_name=WebSearchTool.kind,
        tool_call_id="ws_1",
        content={"status": "completed"},
    )
    summary = tool_result_summary(part, tool_round=1)
    assert summary.content == ""


def test_tool_result_summary_mcp_list_tools_content_shape() -> None:
    """MCP list-tools results serialize MCPListToolsSummary."""
    label = "my-server"
    part = NativeToolReturnPart(
        tool_name=f"{MCPServerTool.kind}:{label}",
        tool_call_id="mcp_list_1",
        content={
            "tools": [
                {
                    "name": "tool_a",
                    "description": "desc",
                    "input_schema": {"type": "object"},
                }
            ]
        },
    )
    summary = tool_result_summary(part, tool_round=2)
    assert summary.type == "mcp_list_tools"
    assert summary.round == 2
    parsed = json.loads(summary.content)
    expected = MCPListToolsSummary(
        server_label=label,
        tools=[
            ToolInfoSummary(
                name="tool_a",
                description="desc",
                input_schema={"type": "object"},
            )
        ],
    ).model_dump()
    assert parsed == expected


def test_tool_result_summary_mcp_list_tools_error_returns_failure() -> None:
    """MCP list-tools errors map to failure status with empty content."""
    label = "my-server"
    part = NativeToolReturnPart(
        tool_name=f"{MCPServerTool.kind}:{label}",
        tool_call_id="mcp_list_1",
        content={"tools": [], "error": "backend unavailable"},
    )
    summary = tool_result_summary(part, tool_round=2)
    assert summary.type == "mcp_list_tools"
    assert summary.status == "failure"
    assert summary.content == ""


def test_dispatch_advances_tool_round() -> None:
    """Round increments when a new model step follows tool results."""
    from pydantic_ai.messages import TextPart

    state = PydanticAiDispatchState()
    web_return = NativeToolReturnPart(
        tool_name=WebSearchTool.kind,
        tool_call_id="ws_1",
        content={"status": "completed"},
    )
    dispatch_stream_event(PartStartEvent(index=0, part=web_return), state)
    assert state.saw_tool_results_since_last_model_step is True
    assert state.tool_round == 1

    dispatch_stream_event(
        PartStartEvent(index=1, part=TextPart("hello")),
        state,
    )
    assert state.tool_round == 2


def test_part_start_tool_call_does_not_emit_sse() -> None:
    """Tool calls are ignored on ``PartStartEvent``."""
    part = ToolCallPart("search", '{"query": "x"}', tool_call_id="call_abc")
    assert (
        dispatch_stream_event(
            PartStartEvent(index=0, part=part),
            PydanticAiDispatchState(),
        )
        is None
    )


def test_part_end_tool_call_emits_sse() -> None:
    """Completed tool calls emit on ``PartEndEvent``."""
    part = ToolCallPart("search", '{"query": "x"}', tool_call_id="call_abc")
    state = PydanticAiDispatchState()
    payload = dispatch_stream_event(PartEndEvent(index=0, part=part), state)
    assert payload is not None
    assert payload.event == "tool_call"
    assert state.emitted_tool_call_ids == {"call_abc"}


def test_tool_call_delta_does_not_emit_sse() -> None:
    """Tool argument deltas are ignored; final calls emit on ``PartEnd``."""
    assert (
        dispatch_stream_event(
            PartDeltaEvent(index=0, delta=ToolCallPartDelta(args_delta='{"q": "x"}')),
            PydanticAiDispatchState(),
        )
        is None
    )


def test_part_start_native_return_emits_tool_result() -> None:
    """Builtin tool results emit on ``PartStartEvent`` for the return part."""
    part = NativeToolReturnPart(
        tool_name=WebSearchTool.kind,
        tool_call_id="ws_1",
        content={"status": "completed"},
    )
    payload = dispatch_stream_event(
        PartStartEvent(index=0, part=part),
        PydanticAiDispatchState(),
    )
    assert payload is not None
    assert payload.event == "tool_result"


def test_text_part_start_emits_empty_token() -> None:
    """Text part start emits an empty token like ``ContentPartAddedChunk``."""
    from pydantic_ai.messages import TextPart

    state = PydanticAiDispatchState()
    payload = dispatch_stream_event(
        PartStartEvent(index=0, part=TextPart("hello")),
        state,
    )
    assert payload is not None
    assert payload.event == "token"
    assert payload.data.token == ""
    assert state.chunk_id == 1

    delta_payload = dispatch_stream_event(
        PartDeltaEvent(index=0, delta=TextPartDelta("hello")),
        state,
    )
    assert delta_payload is not None
    assert delta_payload.event == "token"
    assert delta_payload.data.token == "hello"


def _mock_stream(
    *,
    state: Literal["complete", "incomplete", "interrupted"] = "complete",
    cancelled: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        cancelled=cancelled,
        response=ModelResponse(
            parts=[],
            model_name="gpt-4",
            state=cast(ModelResponseState, state),
        ),
    )


def test_turn_complete_dispatcher_on_success() -> None:
    """Successful streams emit turn_complete with assembled llm_response text."""
    state = PydanticAiDispatchState(
        text_parts=["Hello", " world"],
        chunk_id=3,
    )
    payload = process_turn_complete_event(
        state,
        _mock_stream(state="complete"),
        "openai/gpt-4",
    )
    assert state.llm_response == "Hello world"
    assert payload.event == "turn_complete"
    assert payload.data.token == "Hello world"


def test_turn_complete_dispatcher_on_incomplete_stream() -> None:
    """Incomplete or interrupted streams emit error SSE."""
    state = PydanticAiDispatchState(text_parts=["partial"])
    payload = process_turn_complete_event(
        state,
        _mock_stream(state="incomplete"),
        "openai/gpt-4",
    )
    assert state.llm_response == ""
    assert payload.event == "error"


def test_turn_complete_dispatcher_on_cancelled_stream() -> None:
    """Cancelled streams emit error SSE."""
    payload = process_turn_complete_event(
        PydanticAiDispatchState(),
        _mock_stream(state="interrupted", cancelled=True),
        "openai/gpt-4",
    )
    assert payload.event == "error"
