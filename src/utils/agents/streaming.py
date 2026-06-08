"""Agent streaming helpers for the streaming_query flow."""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import AsyncIterator
from functools import singledispatch
from typing import Any, Final, Optional, TypeAlias, cast

from fastapi import HTTPException
from llama_stack_client import APIConnectionError, APIStatusError
from pydantic_ai import Agent, AgentRunError, AgentRunResultEvent, ToolReturnPart
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    NativeToolCallPart,
    NativeToolReturnPart,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)

from configuration import configuration
from constants import INTERRUPTED_RESPONSE_MESSAGE, MEDIA_TYPE_JSON
from log import get_logger
from models.common.agents import (
    AgentTurnAccumulator,
    EndStreamPayload,
    ErrorStreamPayload,
    InterruptedStreamPayload,
    StartStreamPayload,
    StreamEventPayload,
    TokenStreamPayload,
    ToolCallStreamPayload,
    ToolResultStreamPayload,
    TurnCompleteStreamPayload,
)
from models.common.responses import ResponseInput
from models.common.responses.contexts import ResponseGeneratorContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import TurnSummary
from utils.agents.query import (
    AgentFinishReason,
    extract_agent_token_usage,
    get_agent_finish_reason,
    get_finish_reason_error,
    map_agent_inference_error,
)
from utils.agents.tool_processor import (
    process_function_tool_call,
    process_function_tool_result,
    process_native_tool_call,
    process_native_tool_result,
)
from utils.conversations import append_turn_items_to_conversation
from utils.pydantic_ai import build_agent
from utils.query import consume_query_tokens, store_query_results
from utils.quota import get_available_quotas
from utils.responses import (
    deduplicate_referenced_documents,
    maybe_get_topic_summary,
)
from utils.stream_interrupts import (
    deregister_stream,
    persist_interrupted_turn,
    register_interrupt_callback,
)
from utils.streaming_sse import shield_violation_generator

AgentDispatchEvent: TypeAlias = AgentStreamEvent | AgentRunResultEvent

logger = get_logger(__name__)

DEFAULT_REFUSAL_RESPONSE: Final[str] = (
    "I cannot process this request due to policy restrictions."
)


async def retrieve_agent_response_generator(
    responses_params: ResponsesApiParams,
    context: ResponseGeneratorContext,
    endpoint_path: str,
    original_input: Optional[ResponseInput] = None,
) -> tuple[AsyncIterator[str], TurnSummary]:
    """Return the SSE generator and mutable turn summary for an agent run.

    Args:
        responses_params: Prepared Responses API parameters.
        context: Streaming request context and moderation result.
        endpoint_path: Endpoint path used for metric labeling.
        original_input: In compacted mode, the original user input before the
            explicit-input rewrite. Used to persist the completed turn with its
            structured input (preserving attachments); ``None`` otherwise.

    Returns:
        Tuple of SSE async iterator and mutable turn summary.
    """
    turn_summary = TurnSummary()
    try:
        if context.moderation_result.decision == "blocked":
            turn_summary.llm_response = context.moderation_result.message
            turn_summary.id = context.moderation_result.moderation_id
            await append_turn_items_to_conversation(
                context.client,
                responses_params.conversation,
                original_input or responses_params.input,
                [context.moderation_result.refusal_response],
            )
            media_type = context.query_request.media_type or MEDIA_TYPE_JSON
            return (
                shield_violation_generator(
                    context.moderation_result.message,
                    media_type,
                ),
                turn_summary,
            )

        agent = build_agent(
            context.client, responses_params, configuration.skills, original_input
        )

        return (
            agent_response_generator(
                agent,
                responses_params,
                context,
                turn_summary,
                endpoint_path,
            ),
            turn_summary,
        )
    except (AgentRunError, APIStatusError, APIConnectionError, RuntimeError) as exc:
        response = map_agent_inference_error(exc, responses_params.model)
        raise HTTPException(**response.model_dump()) from exc


async def generate_agent_response(
    generator: AsyncIterator[str],
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
    background_topic_summary_tasks: list[asyncio.Task[None]],
    emit_start: bool = True,
    original_input: Optional[ResponseInput] = None,
) -> AsyncIterator[str]:
    """Wrap an agent SSE generator with cleanup logic.

    Re-yields events from the generator, handles errors, and ensures
    persistence and token consumption after completion.

    Args:
        generator: The base agent SSE generator to wrap.
        context: The response generator context.
        responses_params: The Responses API parameters.
        turn_summary: TurnSummary populated during streaming.
        background_topic_summary_tasks: Mutable list tracking fire-and-forget
            topic summary tasks for graceful shutdown.
        emit_start: Whether to emit the SSE start event. False when the caller
            (the compaction-aware wrapper) has already emitted it.
        original_input: In compacted mode, the original user input before the
            explicit-input rewrite. Used to persist the completed turn with its
            structured input (preserving attachments); ``None`` otherwise.
    Yields:
        SSE-formatted strings from the wrapped generator.
    """
    media_type = context.query_request.media_type or MEDIA_TYPE_JSON
    persist_guard = register_interrupt_callback(
        context,
        responses_params,
        turn_summary,
        background_topic_summary_tasks,
        original_input,
    )
    stream_completed = False
    if emit_start:
        yield serialize_event(
            StartStreamPayload.create(
                conversation_id=context.conversation_id,
                request_id=context.request_id,
            ),
            media_type,
        )
    try:
        async for event in generator:
            yield event

        stream_completed = True

    except (AgentRunError, APIStatusError, APIConnectionError, RuntimeError) as exc:
        error_response = map_agent_inference_error(exc, responses_params.model)
        yield serialize_event(
            ErrorStreamPayload.from_error_response(error_response),
            media_type,
        )
    except asyncio.CancelledError:
        logger.info("Streaming request %s interrupted by user", context.request_id)
        current_task = asyncio.current_task()
        if current_task is not None:
            current_task.uncancel()
        if not persist_guard[0]:
            persist_guard[0] = True
            turn_summary.llm_response = INTERRUPTED_RESPONSE_MESSAGE
            await persist_interrupted_turn(
                context,
                responses_params,
                turn_summary,
                background_topic_summary_tasks,
                original_input,
            )
        yield serialize_event(
            InterruptedStreamPayload.create(request_id=context.request_id),
            media_type,
        )
    finally:
        deregister_stream(context.request_id)

    if not stream_completed:
        return

    should_generate_topic_summary = (
        context.query_request.conversation_id is None
        and bool(context.query_request.generate_topic_summary)
    )
    topic_summary = await maybe_get_topic_summary(
        generate_topic_summary=should_generate_topic_summary,
        input_text=context.query_request.query,
        client=context.client,
        model_id=responses_params.model,
    )
    logger.info("Consuming tokens")
    consume_query_tokens(
        user_id=context.user_id,
        model_id=responses_params.model,
        token_usage=turn_summary.token_usage,
    )
    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters,
        user_id=context.user_id,
    )
    end_payload = EndStreamPayload.create(
        referenced_documents=turn_summary.referenced_documents,
        input_tokens=turn_summary.token_usage.input_tokens,
        output_tokens=turn_summary.token_usage.output_tokens,
        available_quotas=available_quotas,
    )
    yield serialize_event(end_payload, media_type)

    completed_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info("Storing query results")
    store_query_results(
        user_id=context.user_id,
        conversation_id=context.conversation_id,
        model=responses_params.model,
        completed_at=completed_at,
        started_at=context.started_at,
        summary=turn_summary,
        query=context.query_request.query,
        skip_userid_check=context.skip_userid_check,
        topic_summary=topic_summary,
    )
    logger.info("Agent streaming complete")


async def agent_response_generator(
    agent: Agent[Any, str],
    responses_params: ResponsesApiParams,
    context: ResponseGeneratorContext,
    turn_summary: TurnSummary,
    endpoint_path: str,
) -> AsyncIterator[str]:
    """Stream SSE events from an agent run and update the turn summary.

    Args:
        agent: Agent to execute.
        responses_params: Prepared Responses API parameters.
        context: Streaming request context.
        turn_summary: Mutable summary to fill while streaming.
        endpoint_path: Endpoint path used for metric labeling.

    Yields:
        Serialized SSE event strings.
    """
    media_type = context.query_request.media_type or MEDIA_TYPE_JSON
    dispatch_state = AgentTurnAccumulator(
        vector_store_ids=context.vector_store_ids,
        rag_id_mapping=context.rag_id_mapping,
        turn_summary=turn_summary,
    )
    prompt = cast(str, responses_params.input)  # query is always a string

    logger.debug("Starting agent streaming response processing")
    async with agent.run_stream_events(prompt) as stream:
        async for event in stream:
            if payload := dispatch_stream_event(event, dispatch_state):
                yield serialize_event(payload, media_type)

    if dispatch_state.run_result is None:
        logger.error("No final result received from agent run")
        return

    run_result = dispatch_state.run_result
    turn_summary.token_usage = extract_agent_token_usage(
        run_result.usage,
        responses_params.model,
        endpoint_path,
    )

    finish_reason = get_agent_finish_reason(run_result.response)
    if finish_reason != AgentFinishReason.SUCCESS:
        error_response = get_finish_reason_error(finish_reason, responses_params.model)
        yield serialize_event(
            ErrorStreamPayload.from_error_response(error_response),
            media_type,
        )

    turn_summary.referenced_documents = deduplicate_referenced_documents(
        context.inline_rag_context.referenced_documents
        + turn_summary.referenced_documents
    )
    turn_summary.rag_chunks = (
        context.inline_rag_context.rag_chunks + turn_summary.rag_chunks
    )


def serialize_event(
    payload: StreamEventPayload,
    media_type: str = MEDIA_TYPE_JSON,
) -> str:
    """Serialize an LLM stream payload (token, tool, turn complete) for the client."""
    if media_type == MEDIA_TYPE_JSON:
        return payload.serialize_json()
    return payload.serialize_text()


def _process_token(
    state: AgentTurnAccumulator,
    text: str,
) -> StreamEventPayload:
    """Append text to state and build a token stream payload.

    Args:
        state: Mutable dispatch reducer state.
        text: Token text to append and emit.

    Returns:
        Token stream payload containing the emitted token chunk.
    """
    state.text_parts.append(text)
    payload = TokenStreamPayload.create(
        chunk_id=state.chunk_id,
        token=text,
    )
    state.chunk_id += 1
    return payload


@singledispatch
def dispatch_stream_event(
    event: AgentDispatchEvent,
    _state: AgentTurnAccumulator,
) -> Optional[StreamEventPayload]:
    """Map a pydantic-ai stream event to an SSE payload.

    Args:
        event: Agent stream event emitted by the runtime.
        _state: Mutable accumulator for stream processing.

    Returns:
        None when the event does not map to an SSE payload.
    """
    logger.debug("Ignoring event kind=%s", event.event_kind)
    return None


@dispatch_stream_event.register
def _(
    event: AgentRunResultEvent,
    state: AgentTurnAccumulator,
) -> Optional[StreamEventPayload]:
    """Handle final run result event and emit completion payload.

    Args:
        event: Final run result event.
        state: Mutable accumulator for stream processing.

    Returns:
        Completion stream payload.
    """
    state.run_result = event.result
    state.turn_summary.id = state.run_result.response.provider_response_id or ""
    if state.run_result.response.finish_reason == "content_filter":
        provider_details = state.run_result.response.provider_details or {}
        final_text = (
            provider_details.get("refusal_response") or DEFAULT_REFUSAL_RESPONSE
        )
    else:
        final_text = state.run_result.response.text or "".join(state.text_parts)

    payload = TurnCompleteStreamPayload.create(
        chunk_id=state.chunk_id,
        token=final_text,
    )
    state.chunk_id += 1
    return payload


@dispatch_stream_event.register
def _(
    event: PartStartEvent,
    state: AgentTurnAccumulator,
) -> Optional[StreamEventPayload]:
    """Handle start of a model response part.

    Args:
        event: Part start event.
        state: Mutable accumulator for stream processing.

    Returns:
        Optional stream payload emitted at part start.
    """
    part = event.part
    if isinstance(part, TextPart):
        state.increment_round_if_pending()
        return _process_token(state, part.content)

    if isinstance(part, NativeToolReturnPart):
        if tool_result := process_native_tool_result(state, part):
            return ToolResultStreamPayload(data=tool_result)
        return None

    logger.debug("Ignoring part start kind=%s", part.part_kind)
    return None


@dispatch_stream_event.register
def _(
    event: PartDeltaEvent,
    state: AgentTurnAccumulator,
) -> Optional[StreamEventPayload]:
    """Handle incremental updates to a model response part.

    Args:
        event: Part delta event.
        state: Mutable accumulator for stream processing.

    Returns:
        Optional stream payload emitted for the delta.
    """
    delta = event.delta
    if isinstance(delta, TextPartDelta):
        return _process_token(state, delta.content_delta)

    logger.debug("Ignoring part delta kind=%s", delta.part_delta_kind)
    return None


@dispatch_stream_event.register
def _(
    event: PartEndEvent,
    state: AgentTurnAccumulator,
) -> Optional[StreamEventPayload]:
    """Handle completion of a model response part.

    Args:
        event: Part end event.
        state: Mutable accumulator for stream processing.

    Returns:
        Optional stream payload emitted at part end.
    """
    part = event.part
    if isinstance(part, TextPart):
        state.turn_summary.llm_response += (
            part.content or "".join(state.text_parts) + "\n\n"
        )
        state.text_parts.clear()
        return None

    if isinstance(part, NativeToolCallPart):
        if summary := process_native_tool_call(state, part):
            return ToolCallStreamPayload(data=summary)
        return None

    logger.debug("Ignoring part end kind=%s", part.part_kind)
    return None


@dispatch_stream_event.register
def _(
    event: FunctionToolCallEvent,
    state: AgentTurnAccumulator,
) -> Optional[StreamEventPayload]:
    """Handle function tool call event.

    Args:
        event: Function tool call event.
        state: Mutable accumulator for stream processing.

    Returns:
        Tool call stream payload or None.
    """
    if summary := process_function_tool_call(state, event.part):
        return ToolCallStreamPayload(data=summary)
    return None


@dispatch_stream_event.register
def _(
    event: FunctionToolResultEvent,
    state: AgentTurnAccumulator,
) -> Optional[StreamEventPayload]:
    """Handle function tool result event.

    Args:
        event: Function tool result event.
        state: Mutable accumulator for stream processing.

    Returns:
        Tool result stream payload or None.
    """
    part = event.part
    if not isinstance(part, ToolReturnPart):
        return None

    if result := process_function_tool_result(state, part):
        return ToolResultStreamPayload(data=result)
    return None
