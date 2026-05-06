"""Dispatchers for response output items."""

import json
from dataclasses import replace
from functools import singledispatch
from typing import Any, Optional

from llama_stack_api.openai_responses import (
    OpenAIResponseInputFunctionToolCallOutput as FunctionToolCallOutput,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMCPApprovalResponse as MCPApprovalResponse,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDoneItemOpenAIResponseMcpApprovalRequest as MCPApprovalRequest,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDoneItemOpenAIResponseMessage as ResponseMessage,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDoneItemOpenAIResponseOutputMessageFileSearchToolCall as FileSearchCall,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDoneItemOpenAIResponseOutputMessageFunctionToolCall as FunctionCall,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDoneItemOpenAIResponseOutputMessageMcpCall as MCPCall,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDoneItemOpenAIResponseOutputMessageMcpListTools as MCPListTools,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDoneItemOpenAIResponseOutputMessageWebSearchToolCall as WebSearchCall,
)

from constants import DEFAULT_RAG_TOOL
from log import get_logger
from models.common.responses.types import ResponseItem
from models.common.turn_summary import (
    MCPListToolsSummary,
    ToolCallSummary,
    ToolInfoSummary,
    ToolResultSummary,
)
from utils.responses import parse_arguments_string
from utils.streaming.event_serializers import serialize_event
from utils.streaming.state import ChunkDispatchResult, StreamDispatchState
from utils.streaming.stream_payloads import (
    LlmToolCallStreamPayload,
    LlmToolResultStreamPayload,
)

logger = get_logger(__name__)


def _serialize_tool_summary_events(
    media_type: str,
    tool_call: Optional[ToolCallSummary],
    tool_result: Optional[ToolResultSummary],
) -> list[str]:
    """Serialize tool summaries to SSE event strings (no state updates)."""
    events: list[str] = []
    if tool_call:
        events.append(
            serialize_event(LlmToolCallStreamPayload(data=tool_call), media_type)
        )
    if tool_result:
        events.append(
            serialize_event(LlmToolResultStreamPayload(data=tool_result), media_type)
        )
    return events


def _stringify_function_tool_output(output: str | list[Any]) -> str:
    """Coerce API function_call_output content to a string (matches summary models)."""
    if isinstance(output, str):
        return output
    return json.dumps([part.model_dump() for part in output])


@singledispatch
def dispatch_output_item_done(
    item: ResponseItem,
    _output_index: int,
    state: StreamDispatchState,
    _media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Dispatch output_item.done processing by concrete output item class."""
    logger.debug("Ignoring unsupported output item class=%s", type(item).__name__)
    return ChunkDispatchResult(state=state)


@dispatch_output_item_done.register
def _(
    _item: ResponseMessage,
    _output_index: int,
    state: StreamDispatchState,
    _media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Skip message output items (they are parsed elsewhere)."""
    return ChunkDispatchResult(state=state)


@dispatch_output_item_done.register
def _(
    item: FunctionCall,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit function call summary only."""
    tool_call = ToolCallSummary(
        id=item.call_id,
        name=item.name,
        args=parse_arguments_string(item.arguments),
        type="function_call",
    )
    return ChunkDispatchResult(
        state=replace(state, tool_calls=[*state.tool_calls, tool_call]),
        events=_serialize_tool_summary_events(media_type, tool_call, None),
    )


@dispatch_output_item_done.register
def _(
    item: FunctionToolCallOutput,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit function tool output as tool result only."""
    tool_result = ToolResultSummary(
        id=item.call_id,
        status=item.status or "success",
        content=_stringify_function_tool_output(item.output),
        type="function_call_output",
    )
    return ChunkDispatchResult(
        state=replace(state, tool_results=[*state.tool_results, tool_result]),
        events=_serialize_tool_summary_events(media_type, None, tool_result),
    )


@dispatch_output_item_done.register
def _(
    item: FileSearchCall,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit both call and result for file search call."""
    response_payload: Optional[dict[str, Any]] = None
    if item.results is not None:
        response_payload = {"results": [result.model_dump() for result in item.results]}

    tool_call = ToolCallSummary(
        id=item.id,
        name=DEFAULT_RAG_TOOL,
        args={"queries": item.queries},
        type="file_search_call",
    )
    tool_result = ToolResultSummary(
        id=item.id,
        status=item.status,
        content=json.dumps(response_payload) if response_payload else "",
        type="file_search_call",
    )
    return ChunkDispatchResult(
        state=replace(
            state,
            tool_calls=[*state.tool_calls, tool_call],
            tool_results=[*state.tool_results, tool_result],
        ),
        events=_serialize_tool_summary_events(media_type, tool_call, tool_result),
    )


@dispatch_output_item_done.register
def _(
    item: WebSearchCall,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit both call and result for web search call."""
    tool_call = ToolCallSummary(
        id=item.id,
        name="web_search",
        args={},
        type="web_search_call",
    )
    tool_result = ToolResultSummary(
        id=item.id,
        status=item.status,
        content="",
        type="web_search_call",
    )
    return ChunkDispatchResult(
        state=replace(
            state,
            tool_calls=[*state.tool_calls, tool_call],
            tool_results=[*state.tool_results, tool_result],
        ),
        events=_serialize_tool_summary_events(media_type, tool_call, tool_result),
    )


@dispatch_output_item_done.register
def _(
    item: MCPCall,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Handle MCP call output item completion."""
    content = item.error or (item.output or "")
    tool_result = ToolResultSummary(
        id=item.id,
        status="success" if item.error is None else "failure",
        content=content,
        type="mcp_call",
    )
    return ChunkDispatchResult(
        state=replace(state, tool_results=[*state.tool_results, tool_result]),
        events=_serialize_tool_summary_events(media_type, None, tool_result),
    )


@dispatch_output_item_done.register
def _(
    item: MCPListTools,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit both call and result for MCP list tools events."""
    tool_call = ToolCallSummary(
        id=item.id,
        name="mcp_list_tools",
        args={"server_label": item.server_label},
        type="mcp_list_tools",
    )
    tools_info = [
        ToolInfoSummary(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
        )
        for tool in item.tools
    ]
    tool_result = ToolResultSummary(
        id=item.id,
        status="success",
        content=json.dumps(
            MCPListToolsSummary(
                server_label=item.server_label,
                tools=tools_info,
            ).model_dump()
        ),
        type="mcp_list_tools",
    )
    return ChunkDispatchResult(
        state=replace(
            state,
            tool_calls=[*state.tool_calls, tool_call],
            tool_results=[*state.tool_results, tool_result],
        ),
        events=_serialize_tool_summary_events(media_type, tool_call, tool_result),
    )


@dispatch_output_item_done.register
def _(
    item: MCPApprovalRequest,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit approval request as tool call only."""
    tool_call = ToolCallSummary(
        id=item.id,
        name=item.name,
        args=parse_arguments_string(item.arguments),
        type="mcp_approval_request",
    )
    return ChunkDispatchResult(
        state=replace(state, tool_calls=[*state.tool_calls, tool_call]),
        events=_serialize_tool_summary_events(media_type, tool_call, None),
    )


@dispatch_output_item_done.register
def _(
    item: MCPApprovalResponse,
    _output_index: int,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit approval response as tool result only."""
    tool_result = ToolResultSummary(
        id=item.approval_request_id,
        status="success" if item.approve else "denied",
        content=json.dumps({"reason": item.reason} if item.reason else {}),
        type="mcp_approval_response",
    )
    return ChunkDispatchResult(
        state=replace(state, tool_results=[*state.tool_results, tool_result]),
        events=_serialize_tool_summary_events(media_type, None, tool_result),
    )
