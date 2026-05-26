"""Pydantic-ai streaming helpers for the streaming_query flow."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException
from llama_stack_client import APIConnectionError
from llama_stack_client import APIStatusError as LLSApiStatusError
from openai._exceptions import APIStatusError as OpenAIAPIStatusError
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponseStreamEvent
from pydantic_ai.result import StreamedRunResult
from pydantic_ai.usage import RunUsage

from app.endpoints.streaming_query import (
    append_turn_items_to_conversation,
    shield_violation_generator,
)
from constants import MEDIA_TYPE_JSON
from log import get_logger
from metrics import recording
from models.api.responses.error import (
    PromptTooLongResponse,
    ServiceUnavailableResponse,
)
from models.common.responses.contexts import ResponseGeneratorContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import TurnSummary
from utils.query import (
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    is_context_length_error,
)
from utils.responses import (
    deduplicate_referenced_documents,
    extract_text_from_response_items,
)
from utils.streaming.event_serializers import serialize_event
from utils.streaming.pydantic_ai_dispatch_state import PydanticAiDispatchState
from utils.streaming.pydantic_ai_event_dispatchers import (
    dispatch_stream_event,
    process_turn_complete_event,
)
from utils.streaming.pydantic_ai_tool_summaries import (
    parse_tool_rag_chunks_from_agent_messages,
    parse_tool_referenced_documents_from_agent_messages,
)
from utils.token_counter import TokenCounter

logger = get_logger(__name__)


def build_agent_from_responses_params(
    _responses_params: ResponsesApiParams,
    _context: ResponseGeneratorContext,
) -> Agent[Any, str]:
    """Builds a pydantic-ai agent from prepared Responses API inputs.

    Args:
        _responses_params: Prepared Responses API parameters for the turn.
        _context: Streaming query context for building the agent.

    Returns:
        Agent configured for the requested run.

    Raises:
        NotImplementedError: Agent construction is not implemented yet.
    """
    raise NotImplementedError(
        "build_agent_from_responses_params is not implemented yet"
    )


async def retrieve_response_generator_pydantic_ai(
    responses_params: ResponsesApiParams,
    context: ResponseGeneratorContext,
    endpoint_path: str,
) -> tuple[AsyncIterator[str], TurnSummary]:
    """Returns the SSE generator and mutable turn summary for a pydantic-ai run.

    Args:
        responses_params: Prepared Responses API parameters.
        context: Streaming request context and moderation result.
        endpoint_path: Endpoint path used for metric labeling.

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
                responses_params.input,
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

        agent = build_agent_from_responses_params(responses_params, context)

        return (
            pydantic_ai_response_generator(
                agent,
                responses_params,
                context,
                turn_summary,
                endpoint_path,
            ),
            turn_summary,
        )
    except RuntimeError as exc:
        if is_context_length_error(str(exc)):
            raise HTTPException(
                **PromptTooLongResponse(model=responses_params.model).model_dump()
            ) from exc
        raise
    except APIConnectionError as exc:
        raise HTTPException(
            **ServiceUnavailableResponse(
                backend_name="pydantic-ai",
                cause=str(exc),
            ).model_dump()
        ) from exc
    except (LLSApiStatusError, OpenAIAPIStatusError) as exc:
        raise HTTPException(
            **handle_known_apistatus_errors(exc, responses_params.model).model_dump()
        ) from exc


async def pydantic_ai_response_generator(
    agent: Agent[Any, str],
    responses_params: ResponsesApiParams,
    context: ResponseGeneratorContext,
    turn_summary: TurnSummary,
    endpoint_path: str,
) -> AsyncIterator[str]:
    """Streams SSE events from a pydantic-ai run and updates the turn summary.

    Args:
        agent: Pydantic-ai agent to execute.
        responses_params: Prepared Responses API parameters.
        context: Streaming request context.
        turn_summary: Mutable summary to fill while streaming.
        endpoint_path: Endpoint path used for metric labeling.

    Yields:
        Serialized SSE event strings.
    """
    media_type = context.query_request.media_type or MEDIA_TYPE_JSON
    model_id = context.model_id
    dispatch_state = PydanticAiDispatchState()
    prompt = (
        responses_params.input
        if isinstance(responses_params.input, str)
        else extract_text_from_response_items(responses_params.input)
    )

    logger.debug("Starting pydantic-ai streaming response processing")
    async with agent.run_stream(prompt) as stream:
        async for event in stream_event_iterator(stream):
            payload = dispatch_stream_event(event, dispatch_state)
            if payload is not None:
                yield serialize_event(payload, media_type)

        payload = process_turn_complete_event(dispatch_state, stream, model_id)
        yield serialize_event(payload, media_type)

        turn_summary.llm_response = dispatch_state.llm_response
        turn_summary.tool_calls.extend(dispatch_state.tool_calls)
        turn_summary.tool_results.extend(dispatch_state.tool_results)
        finalize_stream_turn(
            turn_summary,
            stream_result=stream,
            context=context,
            model_id=responses_params.model,
            endpoint_path=endpoint_path,
        )

    logger.debug(
        "Pydantic-ai streaming complete - Tool calls: %d, Response chars: %d",
        len(turn_summary.tool_calls),
        len(turn_summary.llm_response),
    )


def extract_agent_token_usage(
    usage: RunUsage,
    model: str,
    endpoint_path: str,
) -> TokenCounter:
    """Builds token usage for a completed agent run and records related metrics.

    Args:
        usage: Run usage reported by pydantic-ai.
        model: Model identifier in provider/model format.
        endpoint_path: Endpoint path used for metric labeling.

    Returns:
        Aggregated token usage counter for the run.
    """
    provider_id, model_id = extract_provider_and_model_from_model_id(model)
    token_counter = TokenCounter(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        llm_calls=max(usage.requests, 1),
    )
    logger.debug(
        "Extracted token usage from pydantic-ai run: input=%d, output=%d, requests=%d",
        token_counter.input_tokens,
        token_counter.output_tokens,
        usage.requests,
    )
    recording.record_llm_token_usage(
        provider_id,
        model_id,
        token_counter.input_tokens,
        token_counter.output_tokens,
        endpoint_path,
    )
    recording.record_llm_call(provider_id, model_id, endpoint_path)
    return token_counter


async def stream_event_iterator(
    stream_result: StreamedRunResult[Any, str],
) -> AsyncIterator[ModelResponseStreamEvent]:
    """Yields model stream events from a streamed pydantic-ai run result.

    Args:
        stream_result: Streamed run result produced by pydantic-ai.

    Yields:
        Model response stream events from the underlying agent stream.
    """
    agent_stream = stream_result._stream_response  # pylint: disable=protected-access
    if agent_stream is None:
        return
    async for event in agent_stream:
        yield event


def finalize_stream_turn(
    turn_summary: TurnSummary,
    *,
    stream_result: StreamedRunResult[Any, str],
    context: ResponseGeneratorContext,
    model_id: str,
    endpoint_path: str,
) -> None:
    """Fills final turn summary fields from a completed streamed agent run.

    Args:
        turn_summary: Mutable turn summary populated during streaming.
        stream_result: Completed streamed run result from pydantic-ai.
        context: Streaming request context with RAG metadata inputs.
        model_id: Model identifier in provider/model format.
        endpoint_path: Endpoint path used for metric labeling.
    """
    turn_summary.id = stream_result.run_id
    turn_summary.token_usage = extract_agent_token_usage(
        stream_result.usage,
        model_id,
        endpoint_path,
    )
    new_messages = stream_result.new_messages()
    tool_rag_chunks = parse_tool_rag_chunks_from_agent_messages(
        new_messages,
        vector_store_ids=context.vector_store_ids,
        rag_id_mapping=context.rag_id_mapping,
    )
    tool_rag_docs = parse_tool_referenced_documents_from_agent_messages(
        new_messages,
        vector_store_ids=context.vector_store_ids,
        rag_id_mapping=context.rag_id_mapping,
    )
    turn_summary.rag_chunks = context.inline_rag_context.rag_chunks + tool_rag_chunks
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        context.inline_rag_context.referenced_documents + tool_rag_docs
    )
