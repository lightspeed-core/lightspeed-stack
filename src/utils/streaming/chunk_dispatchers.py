"""Dispatchers for streaming response chunks."""

from dataclasses import replace
from functools import singledispatch
from typing import cast

from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseCompleted as CompletedChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseContentPartAdded as ContentPartAddedChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseFailed as FailedChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseIncomplete as IncompleteChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseMcpCallArgumentsDone as MCPArgsDoneChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemAdded as OutputItemAddedChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemAddedItemOpenAIResponseOutputMessageMcpCall as MCPCall,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputItemDone as OutputItemDoneChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputTextDelta as TextDeltaChunk,
)
from llama_stack_client.types.response_object_stream import (
    OpenAIResponseObjectStreamResponseOutputTextDone as TextDoneChunk,
)
from llama_stack_client.types.response_object_stream import (
    ResponseObjectStream,
)

from log import get_logger
from models.api.responses.error import (
    InternalServerErrorResponse,
    PromptTooLongResponse,
)
from models.common.turn_summary import ToolCallSummary
from utils.query import is_context_length_error
from utils.responses import parse_arguments_string
from utils.streaming.event_serializers import (
    serialize_event,
)
from utils.streaming.output_item_dispatchers import dispatch_output_item_done
from utils.streaming.state import ChunkDispatchResult, StreamDispatchState
from utils.streaming.stream_payloads import (
    ErrorEventData,
    ErrorStreamPayload,
    LlmTokenChunkData,
    LlmTokenStreamPayload,
    LlmToolCallStreamPayload,
    LlmTurnCompleteStreamPayload,
)

logger = get_logger(__name__)


@singledispatch
def dispatch_stream_chunk(
    chunk: ResponseObjectStream,
    state: StreamDispatchState,
    _media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Fallback dispatcher for unknown chunk types."""
    logger.debug(
        "Ignoring unsupported chunk type=%s",
        getattr(chunk, "type", None),
    )
    return ChunkDispatchResult(state=state)


@dispatch_stream_chunk.register
def _(
    _chunk: ContentPartAddedChunk,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Handle content part start by emitting an empty token."""
    payload = LlmTokenStreamPayload(
        data=LlmTokenChunkData(id=state.chunk_id, token=""),
    )
    return ChunkDispatchResult(
        state=replace(state, chunk_id=state.chunk_id + 1),
        events=[serialize_event(payload, media_type)],
    )


@dispatch_stream_chunk.register
def _(
    chunk: OutputItemAddedChunk,
    state: StreamDispatchState,
    _media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Track MCP call metadata for arguments.done events."""
    if chunk.item.type != "mcp_call":
        return ChunkDispatchResult(state=state)

    mcp_call_item = cast(MCPCall, chunk.item)
    next_mcp_calls = {
        **state.mcp_calls,
        chunk.output_index: (mcp_call_item.id, mcp_call_item.name),
    }
    return ChunkDispatchResult(state=replace(state, mcp_calls=next_mcp_calls))


@dispatch_stream_chunk.register
def _(
    chunk: TextDeltaChunk,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Handle token delta chunks."""
    state.text_parts.append(chunk.delta)
    payload = LlmTokenStreamPayload(
        data=LlmTokenChunkData(id=state.chunk_id, token=chunk.delta)
    )
    return ChunkDispatchResult(
        state=replace(state, chunk_id=state.chunk_id + 1),
        events=[serialize_event(payload, media_type)],
    )


@dispatch_stream_chunk.register
def _(
    chunk: TextDoneChunk,
    state: StreamDispatchState,
    _media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Store final generated text from output_text.done."""
    return ChunkDispatchResult(state=replace(state, llm_response=chunk.text))


@dispatch_stream_chunk.register
def _(
    chunk: MCPArgsDoneChunk,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Emit MCP tool call when arguments are complete."""
    next_mcp_calls = dict(state.mcp_calls)
    item_info = next_mcp_calls.pop(chunk.output_index, None)
    if item_info is None:
        return ChunkDispatchResult(state=replace(state, mcp_calls=next_mcp_calls))

    item_id, item_name = item_info
    tool_call = ToolCallSummary(
        id=item_id,
        name=item_name,
        args=parse_arguments_string(chunk.arguments),
        type="mcp_call",
    )
    payload = LlmToolCallStreamPayload(data=tool_call)
    return ChunkDispatchResult(
        state=replace(
            state,
            mcp_calls=next_mcp_calls,
            tool_calls=[*state.tool_calls, tool_call],
        ),
        events=[serialize_event(payload, media_type)],
    )


@dispatch_stream_chunk.register
def _(
    chunk: OutputItemDoneChunk,
    state: StreamDispatchState,
    media_type: str,
    model_id: str,
) -> ChunkDispatchResult:
    """Handle output item completion for tool calls and results."""
    return dispatch_output_item_done(
        chunk.item,
        chunk.output_index,
        state,
        media_type,
        model_id,
    )


@dispatch_stream_chunk.register
def _(
    chunk: CompletedChunk,
    state: StreamDispatchState,
    media_type: str,
    _model_id: str,
) -> ChunkDispatchResult:
    """Handle successful response completion."""
    final_text = state.llm_response or "".join(state.text_parts)
    payload = LlmTurnCompleteStreamPayload(
        data=LlmTokenChunkData(id=state.chunk_id, token=final_text),
    )
    return ChunkDispatchResult(
        state=replace(
            state,
            chunk_id=state.chunk_id + 1,
            latest_response_object=chunk.response,
            llm_response=final_text,
        ),
        events=[serialize_event(payload, media_type)],
    )


@dispatch_stream_chunk.register
def _(
    chunk: IncompleteChunk | FailedChunk,
    state: StreamDispatchState,
    media_type: str,
    model_id: str,
) -> ChunkDispatchResult:
    """Handle incomplete or failed response."""
    error_message = (
        chunk.response.error.message
        if chunk.response.error is not None
        else "An unexpected error occurred while processing the request."
    )
    error_response = (
        PromptTooLongResponse(model=model_id)
        if is_context_length_error(error_message)
        else InternalServerErrorResponse.query_failed(error_message)
    )
    payload = ErrorStreamPayload(
        data=ErrorEventData(
            status_code=error_response.status_code,
            response=error_response.detail.response,
            cause=error_response.detail.cause,  # pylint: disable=no-member
        ),
    )
    return ChunkDispatchResult(
        state=replace(state, latest_response_object=chunk.response),
        events=[serialize_event(payload, media_type)],
    )
