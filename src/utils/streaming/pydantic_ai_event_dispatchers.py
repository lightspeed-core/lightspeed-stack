"""Dispatchers for pydantic-ai agent/model stream events."""

from __future__ import annotations

from functools import singledispatch
from typing import Any, Optional

from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelResponse,
    ModelResponsePart,
    ModelResponsePartDelta,
    NativeToolCallPart,
    NativeToolReturnPart,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.result import StreamedRunResult

from log import get_logger
from models.api.responses.error import (
    InternalServerErrorResponse,
    PromptTooLongResponse,
)
from models.common.streaming import (
    ErrorStreamPayload,
    LlmTokenChunkData,
    LlmTokenStreamPayload,
    LlmToolCallStreamPayload,
    LlmToolResultStreamPayload,
    LlmTurnCompleteStreamPayload,
    StreamLlmEventPayload,
)
from models.common.streaming.stream_payloads import ErrorEventData
from models.common.turn_summary import ToolResultSummary
from utils.query import is_context_length_error
from utils.streaming.pydantic_ai_dispatch_state import PydanticAiDispatchState
from utils.streaming.pydantic_ai_tool_summaries import (
    function_tool_call_summary,
    function_tool_result_summary,
    tool_call_summary,
    tool_result_summary,
)

logger = get_logger(__name__)


def _maybe_advance_tool_round(state: PydanticAiDispatchState) -> None:
    """Bumps the tool round when the model resumes after tool results.

    Args:
        state: Mutable dispatch reducer state.
    """
    if not state.saw_tool_results_since_last_model_step:
        return
    state.tool_round += 1
    state.saw_tool_results_since_last_model_step = False


def process_token(
    state: PydanticAiDispatchState,
    text: str,
) -> StreamLlmEventPayload:
    """Appends text to state and builds a token stream payload.

    Args:
        state: Mutable dispatch reducer state.
        text: Token text to append and emit.

    Returns:
        Token stream payload containing the emitted token chunk.
    """
    state.text_parts.append(text)
    payload = LlmTokenStreamPayload(
        data=LlmTokenChunkData(id=state.chunk_id, token=text),
    )
    state.chunk_id += 1
    return payload


def process_tool_call(
    state: PydanticAiDispatchState,
    part: ToolCallPart | NativeToolCallPart,
) -> Optional[StreamLlmEventPayload]:
    """Builds a tool-call payload from completed tool call parts.

    Args:
        state: Mutable dispatch reducer state.
        part: Function or native tool call part.

    Returns:
        Tool-call payload when a new call is emitted, otherwise None.
    """
    if part.tool_call_id in state.emitted_tool_call_ids:
        return None
    summary = (
        tool_call_summary(part)
        if isinstance(part, NativeToolCallPart)
        else function_tool_call_summary(part)
    )
    if summary is None:
        return None
    state.emitted_tool_call_ids.add(part.tool_call_id)
    state.tool_calls.append(summary)
    return LlmToolCallStreamPayload(data=summary)


def process_tool_result(
    state: PydanticAiDispatchState,
    summary: ToolResultSummary,
) -> LlmToolResultStreamPayload:
    """Records a tool result and builds its SSE payload.

    Args:
        state: Mutable dispatch reducer state.
        summary: Tool result summary to store and emit.

    Returns:
        Tool-result payload for SSE serialization.
    """
    state.emitted_tool_result_ids.add(summary.id)
    state.tool_results.append(summary)
    state.saw_tool_results_since_last_model_step = True
    return LlmToolResultStreamPayload(data=summary)


# ---------------------------------------------------------------------------
# Part handlers (nested singledispatch)
# ---------------------------------------------------------------------------


@singledispatch
def dispatch_part_on_start(  # type: ignore[return]
    part: ModelResponsePart,
    _state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Handles model-part start events with a default no-op mapping.

    Args:
        part: Model response part for this start event.
        _state: Mutable dispatch reducer state.

    Returns:
        None when the part kind is not mapped to an SSE payload.
    """
    logger.debug("Ignoring part start kind=%s", part.part_kind)


@dispatch_part_on_start.register
def _(
    _part: TextPart,
    state: PydanticAiDispatchState,
) -> StreamLlmEventPayload:
    """Emit an empty token when a text part starts (``ContentPartAddedChunk`` parity)."""
    _maybe_advance_tool_round(state)
    return process_token(state, "")


@dispatch_part_on_start.register
def _(
    _part: ToolCallPart | NativeToolCallPart,
    state: PydanticAiDispatchState,
) -> None:
    """Advance tool round after results; tool calls emit on ``PartEnd``."""
    _maybe_advance_tool_round(state)


@dispatch_part_on_start.register
def _(
    part: NativeToolReturnPart,
    state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Emit builtin tool results (pydantic-ai does not emit ``PartEnd`` for returns)."""
    if part.tool_call_id in state.emitted_tool_result_ids:
        return None
    return process_tool_result(
        state,
        tool_result_summary(part, state.tool_round),
    )


@singledispatch
def dispatch_part_delta(  # type: ignore[return]
    delta: ModelResponsePartDelta,
    _state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Handles part-delta events with a default no-op mapping.

    Args:
        delta: Model response part delta for this event.
        _state: Mutable dispatch reducer state.

    Returns:
        None when the delta kind is not mapped to an SSE payload.
    """
    logger.debug("Ignoring part delta kind=%s", delta.part_delta_kind)


@dispatch_part_delta.register
def _(
    delta: TextPartDelta,
    state: PydanticAiDispatchState,
) -> StreamLlmEventPayload:
    """Emits a token payload for incremental text deltas."""
    return process_token(state, delta.content_delta)


@singledispatch
def dispatch_part_on_end(  # type: ignore[return]
    part: ModelResponsePart,
    _state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Handles model-part end events with a default no-op mapping.

    Args:
        part: Model response part for this end event.
        _state: Mutable dispatch reducer state.

    Returns:
        None when the part kind is not mapped to an SSE payload.
    """
    logger.debug("Ignoring part end kind=%s", part.part_kind)


@dispatch_part_on_end.register
def _(
    part: TextPart,
    state: PydanticAiDispatchState,
) -> None:
    """Stores the final text part content on dispatch state."""
    state.llm_response = part.content


@dispatch_part_on_end.register
def _(
    part: ToolCallPart | NativeToolCallPart,
    state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Emit completed tool calls when the model part boundary closes."""
    _maybe_advance_tool_round(state)
    return process_tool_call(state, part)


# ---------------------------------------------------------------------------
# Top-level agent stream event dispatch
# ---------------------------------------------------------------------------


@singledispatch
def dispatch_stream_event(  # type: ignore[return]
    event: AgentStreamEvent,
    _state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Handles stream events with a default no-op mapping.

    Args:
        event: Agent stream event produced by pydantic-ai.
        _state: Mutable dispatch reducer state.

    Returns:
        None when the event kind is not mapped to an SSE payload.
    """
    logger.debug("Ignoring event kind=%s", event.event_kind)


@dispatch_stream_event.register
def _(
    event: PartStartEvent,
    state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Dispatches a part-start stream event to part handlers."""
    return dispatch_part_on_start(event.part, state)


@dispatch_stream_event.register
def _(
    event: PartDeltaEvent,
    state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Dispatches a part-delta stream event to part handlers."""
    return dispatch_part_delta(event.delta, state)


@dispatch_stream_event.register
def _(
    event: PartEndEvent,
    state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Dispatches a part-end stream event to part handlers."""
    return dispatch_part_on_end(event.part, state)


@dispatch_stream_event.register
def _(
    event: FunctionToolCallEvent,
    state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Processes a function tool call event into a tool_call payload."""
    return process_tool_call(state, event.part)


@dispatch_stream_event.register
def _(
    event: FunctionToolResultEvent,
    state: PydanticAiDispatchState,
) -> Optional[StreamLlmEventPayload]:
    """Emit client function tool results from agent stream events."""
    part = event.part
    if not isinstance(part, ToolReturnPart):
        return None
    if part.tool_call_id in state.emitted_tool_result_ids:
        return None
    return process_tool_result(
        state,
        function_tool_result_summary(part, state.tool_round),
    )


def _stream_succeeded(stream: StreamedRunResult[Any, Any]) -> bool:
    """Returns whether a streamed run completed without cancellation.

    Args:
        stream: Streamed run result to evaluate.

    Returns:
        True when the stream is not cancelled and ended in complete state.
    """
    if stream.cancelled:
        return False
    return stream.response.state == "complete"


def _stream_failure_message(response: ModelResponse) -> str:
    """Builds a user-facing error message for an unsuccessful model stream.

    Args:
        response: Final model response for the stream.

    Returns:
        Best-effort human-readable failure message.
    """
    provider_finish = (response.provider_details or {}).get("finish_reason")
    if isinstance(provider_finish, str) and provider_finish.strip():
        return provider_finish
    if response.finish_reason == "content_filter":
        return "The model refused to generate a response due to content policy."
    if response.state == "interrupted":
        return "The response was interrupted before completion."
    if response.state == "incomplete":
        return "The response ended before completion."
    return "An unexpected error occurred while processing the request."


def process_turn_complete_event(
    state: PydanticAiDispatchState,
    stream: StreamedRunResult[Any, Any],
    model_id: str,
) -> StreamLlmEventPayload:
    """Builds turn-complete or error payload after stream termination.

    Args:
        state: Mutable dispatch reducer state.
        stream: Streamed run result to finalize.
        model_id: Model identifier used for error response shaping.

    Returns:
        Turn-complete payload on success, otherwise error payload.
    """
    response = stream.response
    if not _stream_succeeded(stream):
        error_message = _stream_failure_message(response)
        error_response = (
            PromptTooLongResponse(model=model_id)
            if is_context_length_error(error_message)
            else InternalServerErrorResponse.query_failed(error_message)
        )
        return ErrorStreamPayload(
            data=ErrorEventData(
                status_code=error_response.status_code,
                response=error_response.detail.response,
                cause=error_response.detail.cause,  # pylint: disable=no-member
            ),
        )

    final_text = state.llm_response or "".join(state.text_parts)
    state.llm_response = final_text
    payload = LlmTurnCompleteStreamPayload(
        data=LlmTokenChunkData(id=state.chunk_id, token=final_text),
    )
    state.chunk_id += 1
    return payload
