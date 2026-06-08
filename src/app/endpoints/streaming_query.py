"""Streaming query handler using Responses API."""

import asyncio
import datetime
from collections.abc import AsyncIterator
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api import (
    OpenAIResponseObject,
    OpenAIResponseObjectStream,
)
from llama_stack_api import (
    OpenAIResponseObjectStreamResponseMcpCallArgumentsDone as MCPArgsDoneChunk,
)
from llama_stack_api import (
    OpenAIResponseObjectStreamResponseOutputItemAdded as OutputItemAddedChunk,
)
from llama_stack_api import (
    OpenAIResponseObjectStreamResponseOutputItemDone as OutputItemDoneChunk,
)
from llama_stack_api import (
    OpenAIResponseObjectStreamResponseOutputTextDelta as TextDeltaChunk,
)
from llama_stack_api import (
    OpenAIResponseObjectStreamResponseOutputTextDone as TextDoneChunk,
)
from llama_stack_api import (
    OpenAIResponseOutputMessageMCPCall as MCPCall,
)
from llama_stack_client import (
    APIConnectionError,
)
from llama_stack_client import (
    APIStatusError as LLSApiStatusError,
)
from openai._exceptions import APIStatusError as OpenAIAPIStatusError
from typing_extensions import deprecated

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import (
    ENDPOINT_PATH_STREAMING_QUERY,
    INTERRUPTED_RESPONSE_MESSAGE,
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
    LLM_TURN_COMPLETE_EVENT,
    MEDIA_TYPE_EVENT_STREAM,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
)
from log import get_logger
from metrics import recording
from models.api.requests import QueryRequest
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.api.responses.successful import StreamingQueryResponse
from models.common.responses.contexts import ResponseGeneratorContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from models.common.turn_summary import TurnSummary
from models.config import Action
from utils.agents.streaming import (
    generate_agent_response,
    retrieve_agent_response_generator,
)
from utils.conversation_compaction import (
    CompactionResult,
    CompactionStartedEvent,
    apply_compaction,
    configured_conversation_cache,
    needs_compaction_path,
    store_compacted_turn,
)
from utils.conversations import append_turn_items_to_conversation
from utils.endpoints import (
    check_configuration_loaded,
    validate_and_retrieve_conversation,
)
from utils.mcp_headers import McpHeaders, mcp_headers_dependency
from utils.mcp_oauth_probe import check_mcp_auth
from utils.query import (
    consume_query_tokens,
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    is_context_length_error,
    prepare_input,
    store_query_results,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    build_mcp_tool_call_from_arguments_done,
    build_tool_call_summary,
    build_tool_result_from_mcp_output_item_done,
    deduplicate_referenced_documents,
    extract_token_usage,
    extract_vector_store_ids_from_tools,
    get_topic_summary,
    parse_rag_chunks,
    parse_referenced_documents,
    prepare_responses_params,
)
from utils.shields import (
    run_shield_moderation,
    validate_shield_ids_override,
)
from utils.stream_interrupts import (
    deregister_stream,
    persist_interrupted_turn,
    register_interrupt_callback,
)
from utils.streaming_sse import (
    http_exception_stream_event,
    shield_violation_generator,
    stream_compaction_event,
    stream_end_event,
    stream_event,
    stream_http_error_event,
    stream_interrupted_event,
    stream_start_event,
)
from utils.suid import get_suid, normalize_conversation_id
from utils.vector_search import build_rag_context

logger = get_logger(__name__)
router = APIRouter(tags=["streaming_query"])

# Tracks background topic summary tasks for graceful shutdown.
_background_topic_summary_tasks: list[asyncio.Task[None]] = []

streaming_query_responses: dict[int | str, dict[str, Any]] = {
    200: StreamingQueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["conversation read", "endpoint", "model override"]
    ),
    404: NotFoundResponse.openapi_response(
        examples=["conversation", "model", "provider"]
    ),
    413: PromptTooLongResponse.openapi_response(examples=["context window exceeded"]),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}


@router.post(
    "/streaming_query",
    response_class=StreamingResponse,
    responses=streaming_query_responses,
    summary="Streaming Query Endpoint Handler",
)
@authorize(Action.STREAMING_QUERY)
async def streaming_query_endpoint_handler(  # pylint: disable=too-many-locals
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: McpHeaders = Depends(mcp_headers_dependency),
) -> StreamingResponse:
    """
    Handle request to the /streaming_query endpoint using Responses API.

    Returns a streaming response using Server-Sent Events (SSE) format with
    content type text/event-stream.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - query_request: Request to the LLM.
    - auth: Auth context tuple resolved from the authentication dependency.
    - mcp_headers: Headers that should be passed to MCP servers.

    ### Returns:
    - SSE-formatted events for the query lifecycle.

    ### Raises:
    - HTTPException:
    - 401: Unauthorized - Missing or invalid credentials
    - 403: Forbidden - Insufficient permissions or model override not allowed
    - 404: Not Found - Conversation, model, or provider not found
    - 413: Prompt too long - Prompt exceeded model's context window size
    - 422: Unprocessable Entity - Request validation failed
    - 429: Quota limit exceeded - The token quota for model or user has been exceeded
    - 500: Internal Server Error - Configuration not loaded or other server errors
    - 503: Service Unavailable - Unable to connect to Llama Stack backend
    """
    check_configuration_loaded(configuration)

    user_id, _user_name, _skip_userid_check, token = auth
    started_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Check MCP Auth
    await check_mcp_auth(configuration, mcp_headers, token, request.headers)

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(
        query_request.model, query_request.provider, request.state.authorized_actions
    )

    # Validate shield_ids override if provided
    validate_shield_ids_override(query_request, configuration)

    # Validate attachments if provided
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    # Retrieve conversation if conversation_id is provided
    user_conversation = None
    if query_request.conversation_id:
        logger.debug(
            "Conversation ID specified in query: %s", query_request.conversation_id
        )
        normalized_conv_id = normalize_conversation_id(query_request.conversation_id)
        user_conversation = validate_and_retrieve_conversation(
            normalized_conv_id=normalized_conv_id,
            user_id=user_id,
            others_allowed=Action.READ_OTHERS_CONVERSATIONS
            in request.state.authorized_actions,
        )

    client = AsyncLlamaStackClientHolder().get_client()

    # Moderation input is the raw user content (query + attachments) without injected RAG
    # context, to avoid false positives from retrieved document content.
    moderation_input = prepare_input(query_request)
    endpoint_path = ENDPOINT_PATH_STREAMING_QUERY
    moderation_result = await run_shield_moderation(
        client, moderation_input, endpoint_path, query_request.shield_ids
    )

    # Build RAG context from Inline RAG sources
    inline_rag_context = await build_rag_context(
        client,
        moderation_result.decision,
        query_request.query,
        query_request.vector_store_ids,
        query_request.solr,
    )

    # Prepare API request parameters
    responses_params = await prepare_responses_params(
        client=client,
        query_request=query_request,
        user_conversation=user_conversation,
        token=token,
        mcp_headers=mcp_headers,
        stream=True,
        store=True,
        request_headers=request.headers,
        inline_rag_context=inline_rag_context.context_text,
    )

    # Handle Azure token refresh if needed
    if (
        responses_params.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await AsyncLlamaStackClientHolder().update_azure_token()

    request_id = get_suid()

    # Create context with index identification mapping for RAG source resolution
    context = ResponseGeneratorContext(
        conversation_id=normalize_conversation_id(responses_params.conversation),
        request_id=request_id,
        model_id=responses_params.model,
        user_id=user_id,
        skip_userid_check=_skip_userid_check,
        query_request=query_request,
        started_at=started_at,
        client=client,
        moderation_result=moderation_result,
        vector_store_ids=extract_vector_store_ids_from_tools(responses_params.tools),
        rag_id_mapping=configuration.rag_id_mapping,
        inline_rag_context=inline_rag_context,
    )

    # Update metrics for the LLM call
    provider_id, model_id = extract_provider_and_model_from_model_id(
        responses_params.model
    )
    recording.record_llm_call(provider_id, model_id, endpoint_path)

    response_media_type = (
        MEDIA_TYPE_TEXT
        if query_request.media_type == MEDIA_TYPE_TEXT
        else MEDIA_TYPE_EVENT_STREAM
    )

    # Only conversations that actually compact (already have a summary marker,
    # or would trigger one now) take the compaction-aware path, where the
    # response is created inside the SSE stream so the progress event can be
    # flushed before the summarization LLM call. Every other request keeps the
    # unchanged path: the response stream is created here, so create-time errors
    # surface as HTTP responses exactly as before.
    if await needs_compaction_path(
        context.client,
        responses_params,
        configuration.inference,
        configuration.compaction,
    ):
        return StreamingResponse(
            generate_response_with_compaction(
                context=context,
                responses_params=responses_params,
                endpoint_path=endpoint_path,
            ),
            media_type=response_media_type,
        )

    generator, turn_summary = await retrieve_agent_response_generator(
        responses_params=responses_params,
        context=context,
        endpoint_path=endpoint_path,
        original_input=None,
    )

    # Combine inline RAG results (BYOK + Solr) with tool-based results
    if context.moderation_result.decision == "passed":
        turn_summary.referenced_documents = deduplicate_referenced_documents(
            inline_rag_context.referenced_documents + turn_summary.referenced_documents
        )

    return StreamingResponse(
        generate_agent_response(
            generator=generator,
            context=context,
            responses_params=responses_params,
            turn_summary=turn_summary,
            background_topic_summary_tasks=_background_topic_summary_tasks,
            emit_start=True,
            original_input=None,
        ),
        media_type=response_media_type,
    )


@deprecated(
    "Deprecated in favor of utils.agents.streaming.retrieve_agent_response_generator.",
    stacklevel=2,
)
async def retrieve_response_generator(
    responses_params: ResponsesApiParams,
    context: ResponseGeneratorContext,
    endpoint_path: str,
) -> tuple[AsyncIterator[str], TurnSummary]:
    """
    Retrieve the appropriate response generator.

    Handles shield moderation check and retrieves response.
    Returns the generator (shield violation or response generator) and turn_summary.
    Fills turn_summary attributes for token usage, referenced documents, and tool calls.

    Args:
        responses_params: The Responses API parameters
        context: The response generator context
        endpoint_path: API endpoint path used for metric labeling.
    Returns:
        tuple[AsyncIterator[str], TurnSummary]: The response generator and turn summary

    """
    turn_summary = TurnSummary()
    try:
        if context.moderation_result.decision == "blocked":
            turn_summary.llm_response = context.moderation_result.message
            turn_summary.id = context.moderation_result.moderation_id
            # In compacted mode the conversation parameter was omitted, so the
            # refusal turn (with the original input) is persisted by
            # generate_response; storing it here too would duplicate it.
            if not responses_params.omit_conversation:
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
        # Retrieve response stream (may raise exceptions)
        response = await context.client.responses.create(
            **responses_params.model_dump(exclude_none=True)
        )
        # Store pre-RAG documents for later merging with tool-based RAG
        return (
            response_generator(
                response,
                context,
                turn_summary,
                endpoint_path,
            ),
            turn_summary,
        )
    # Handle know LLS client errors only at stream creation time and shield execution
    except RuntimeError as e:  # library mode wraps 413 into runtime error
        if is_context_length_error(str(e)):
            error_response = PromptTooLongResponse(model=responses_params.model)
            raise HTTPException(**error_response.model_dump()) from e
        raise e
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e

    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        error_response = handle_known_apistatus_errors(e, responses_params.model)
        raise HTTPException(**error_response.model_dump()) from e


async def shutdown_background_topic_summary_tasks() -> None:
    """Cancel and await outstanding background topic summary tasks on shutdown.

    Ensures graceful shutdown so in-flight topic summary generation can be
    cleaned up. Called from the application lifespan shutdown phase.
    """
    tasks = list(_background_topic_summary_tasks)
    if not tasks:
        return
    logger.debug(
        "Shutting down %d outstanding background topic summary task(s)",
        len(tasks),
    )
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def generate_response_with_compaction(
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    endpoint_path: str,
) -> AsyncIterator[str]:
    """Stream a response for a conversation that requires compaction.

    Used only when :func:`needs_compaction_path` is true. Compaction and the
    response creation happen inside the SSE stream so the ``compaction`` event
    is flushed to the client *before* the summarization LLM call (R12). Errors
    raised while compacting or creating the response are surfaced as SSE error
    events (the stream has already started, so an HTTP status is no longer
    possible).

    Args:
        context: The response generator context.
        responses_params: The base Responses API parameters.
        endpoint_path: API endpoint path used for metric labeling.

    Yields:
        SSE-formatted strings.
    """
    media_type = context.query_request.media_type or MEDIA_TYPE_JSON
    yield stream_start_event(
        conversation_id=context.conversation_id,
        request_id=context.request_id,
    )

    compacted_original_input: Optional[ResponseInput] = None
    try:
        async for item in apply_compaction(
            context.client,
            responses_params,
            configuration.inference,
            configuration.compaction,
            emit_events=True,
            cache=configured_conversation_cache(),
            user_id=context.user_id,
            skip_user_id_check=context.skip_userid_check,
        ):
            if isinstance(item, CompactionStartedEvent):
                yield stream_compaction_event(context.conversation_id)
            elif isinstance(item, CompactionResult):
                responses_params = item.params
                compacted_original_input = item.original_input

        generator, turn_summary = await retrieve_agent_response_generator(
            responses_params=responses_params,
            context=context,
            endpoint_path=endpoint_path,
            original_input=compacted_original_input,
        )
    except HTTPException as e:
        yield http_exception_stream_event(e)
        return
    except RuntimeError as e:  # library mode wraps 413 into runtime error
        error_response = (
            PromptTooLongResponse(model=responses_params.model)
            if is_context_length_error(str(e))
            else InternalServerErrorResponse.generic()
        )
        yield stream_http_error_event(error_response, media_type)
        return
    except APIConnectionError as e:
        yield stream_http_error_event(
            ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e)),
            media_type,
        )
        return
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        yield stream_http_error_event(
            handle_known_apistatus_errors(e, responses_params.model), media_type
        )
        return

    # Combine inline RAG results (BYOK + Solr) with tool-based results
    if context.moderation_result.decision == "passed":
        turn_summary.referenced_documents = deduplicate_referenced_documents(
            context.inline_rag_context.referenced_documents
            + turn_summary.referenced_documents
        )

    # The start event was already emitted above; delegate the rest (re-yield,
    # finalization, compacted-turn storage) to the shared generator.
    async for event in generate_agent_response(
        generator,
        context,
        responses_params,
        turn_summary,
        background_topic_summary_tasks=_background_topic_summary_tasks,
        emit_start=False,
        original_input=compacted_original_input,
    ):
        yield event


@deprecated(
    "Deprecated in favor of utils.agents.streaming.generate_agent_response.",
    stacklevel=2,
)
async def generate_response(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
    generator: AsyncIterator[str],
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
    emit_start: bool = True,
    compacted: bool = False,
    original_input: Optional[ResponseInput] = None,
) -> AsyncIterator[str]:
    """Wrap a generator with cleanup logic.

    Re-yields events from the generator, handles errors, and ensures
    persistence and token consumption after completion.  When the
    stream is interrupted via ``CancelledError``, the user query and
    an interrupted response are persisted to the conversation, but
    token consumption is skipped (no usage data is available).

    Args:
        generator: The base generator to wrap
        context: The response generator context
        responses_params: The Responses API parameters
        turn_summary: TurnSummary populated during streaming
        emit_start: Whether to emit the SSE start event. False when the caller
            (the compaction-aware wrapper) has already emitted it.
        compacted: Whether the conversation is in compacted mode. When True the
            conversation parameter was not sent to Llama Stack, so the completed
            turn is appended to the conversation here rather than being stored
            automatically.
        original_input: In compacted mode, the original user input before the
            explicit-input rewrite. Used to persist the completed turn with its
            structured input (preserving attachments); ``None`` otherwise.

    Yields:
        SSE-formatted strings from the wrapped generator
    """
    persist_guard = register_interrupt_callback(
        context,
        responses_params,
        turn_summary,
        _background_topic_summary_tasks,
        original_input,
    )

    stream_completed = False
    try:
        if emit_start:
            yield stream_start_event(
                conversation_id=context.conversation_id,
                request_id=context.request_id,
            )

        # Re-yield all events from the generator
        async for event in generator:
            yield event

        stream_completed = True

    # Handle known LLS client errors during response generation time
    except RuntimeError as e:  # library mode wraps 413 into runtime error
        error_response = (
            PromptTooLongResponse(model=responses_params.model)
            if is_context_length_error(str(e))
            else InternalServerErrorResponse.generic()
        )
        yield stream_http_error_event(error_response, context.query_request.media_type)
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        yield stream_http_error_event(error_response, context.query_request.media_type)
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        error_response = handle_known_apistatus_errors(e, responses_params.model)
        yield stream_http_error_event(error_response, context.query_request.media_type)
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
                _background_topic_summary_tasks,
                original_input,
            )
        yield stream_interrupted_event(context.request_id)
    finally:
        deregister_stream(context.request_id)

    if not stream_completed:
        return

    # Post-stream side effects: only run when streaming finished successfully

    # Get topic summary for new conversations if needed
    topic_summary = None
    if not context.query_request.conversation_id:
        should_generate = context.query_request.generate_topic_summary
        if should_generate:
            logger.debug("Generating topic summary for new conversation")
            topic_summary = await get_topic_summary(
                context.query_request.query,
                context.client,
                responses_params.model,
            )

    # Consume tokens
    logger.info("Consuming tokens")
    consume_query_tokens(
        user_id=context.user_id,
        model_id=responses_params.model,
        token_usage=turn_summary.token_usage,
    )
    # Get available quotas
    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=context.user_id
    )

    yield stream_end_event(
        turn_summary.token_usage,
        available_quotas,
        turn_summary.referenced_documents,
        context.query_request.media_type or MEDIA_TYPE_JSON,
    )
    completed_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # In compacted mode the conversation parameter was not sent, so Llama Stack
    # did not persist this turn. Append it ourselves to keep the recent-turn
    # buffer and audit history intact for the next request.
    if compacted:
        try:
            await store_compacted_turn(
                context.client,
                responses_params.conversation,
                (
                    original_input
                    if original_input is not None
                    else context.query_request.query
                ),
                [],  # field was removed from TurnSummary
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Failed to append compacted turn to conversation for request %s",
                context.request_id,
            )

    # Store query results (transcript, conversation details, cache)
    logger.info("Storing query results")
    store_query_results(
        user_id=context.user_id,
        conversation_id=context.conversation_id,
        model=responses_params.model,
        completed_at=completed_at,
        started_at=context.started_at,
        summary=turn_summary,
        query=context.query_request.query,
        attachments=context.query_request.attachments,
        skip_userid_check=context.skip_userid_check,
        topic_summary=topic_summary,
    )


@deprecated(
    "Deprecated in favor of utils.agents.streaming.agent_response_generator.",
    stacklevel=2,
)
async def response_generator(  # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    turn_response: AsyncIterator[OpenAIResponseObjectStream],
    context: ResponseGeneratorContext,
    turn_summary: TurnSummary,
    endpoint_path: str,
) -> AsyncIterator[str]:
    """Generate SSE formatted streaming response.

    Processes streaming chunks from Llama Stack and converts them to
    Server-Sent Events (SSE) format. Uses handler functions to process
    different event types and populate turn_summary during streaming.

    Args:
        turn_response: The streaming response from Llama Stack
        context: The response generator context
        turn_summary: TurnSummary to populate during streaming
        endpoint_path: API endpoint path used for metric labeling.

    Yields:
        SSE-formatted strings for tokens, tool calls, tool results,
        turn completion, and error events.
    """
    chunk_id = 0
    media_type = context.query_request.media_type or MEDIA_TYPE_JSON
    text_parts: list[str] = []
    mcp_calls: dict[int, tuple[str, str]] = (
        {}
    )  # output_index -> (mcp_call_id, mcp_call_name)
    latest_response_object: Optional[OpenAIResponseObject] = None

    logger.debug("Starting streaming response (Responses API) processing")

    async for chunk in turn_response:
        event_type = getattr(chunk, "type", None)
        logger.debug("Processing chunk %d, type: %s", chunk_id, event_type)

        # Content part started - emit an empty token to kick off UI streaming
        if event_type == "response.content_part.added":
            yield stream_event(
                {
                    "id": chunk_id,
                    "token": "",
                },
                LLM_TOKEN_EVENT,
                media_type,
            )
            chunk_id += 1

        # Store MCP call item info for later lookup when arguments.done event occurs
        elif event_type == "response.output_item.added":
            item_added_chunk = cast(OutputItemAddedChunk, chunk)
            if item_added_chunk.item.type == "mcp_call":
                mcp_call_item = cast(MCPCall, item_added_chunk.item)
                mcp_calls[item_added_chunk.output_index] = (
                    mcp_call_item.id,
                    mcp_call_item.name,
                )

        # Text streaming - emit token delta
        elif event_type == "response.output_text.delta":
            delta_chunk = cast(TextDeltaChunk, chunk)
            text_parts.append(delta_chunk.delta)
            yield stream_event(
                {
                    "id": chunk_id,
                    "token": delta_chunk.delta,
                },
                LLM_TOKEN_EVENT,
                media_type,
            )
            chunk_id += 1

        # Final text of the output (capture, but emit at response.completed)
        elif event_type == "response.output_text.done":
            text_done_chunk = cast(TextDoneChunk, chunk)
            turn_summary.llm_response = text_done_chunk.text

        # Emit tool call when MCP call arguments are done
        elif event_type == "response.mcp_call.arguments.done":
            mcp_arguments_done_chunk = cast(MCPArgsDoneChunk, chunk)
            tool_call = build_mcp_tool_call_from_arguments_done(
                mcp_arguments_done_chunk.output_index,
                mcp_arguments_done_chunk.arguments,
                mcp_calls,
            )
            if tool_call:
                turn_summary.tool_calls.append(tool_call)
                yield stream_event(
                    tool_call.model_dump(),
                    LLM_TOOL_CALL_EVENT,
                    media_type,
                )

        # Process tool calls and results when output items are done
        # For mcp_call, only emit result (call was already emitted when arguments.done)
        # For other types, emit both call and result
        elif event_type == "response.output_item.done":
            output_item_done_chunk = cast(OutputItemDoneChunk, chunk)
            item_type = output_item_done_chunk.item.type
            # Skip message items as they are parsed separately
            if item_type == "message":
                continue

            output_index = output_item_done_chunk.output_index

            # For mcp_call, only emit result if call was already emitted when arguments.done
            # (indicated by output_index not being in mcp_calls dict)
            # If output_index is in dict, process in else branch (emit both call and result)
            if item_type == "mcp_call" and output_index not in mcp_calls:
                # Call was already emitted during arguments.done, only emit result
                mcp_call_item = cast(MCPCall, output_item_done_chunk.item)
                tool_result = build_tool_result_from_mcp_output_item_done(mcp_call_item)
                turn_summary.tool_results.append(tool_result)
                yield stream_event(
                    tool_result.model_dump(),
                    LLM_TOOL_RESULT_EVENT,
                    media_type,
                )
            else:
                # For all other types (and mcp_call when arguments.done didn't happen),
                # emit both call and result together
                tool_call, tool_result = build_tool_call_summary(
                    output_item_done_chunk.item
                )
                if tool_call:
                    turn_summary.tool_calls.append(tool_call)
                    yield stream_event(
                        tool_call.model_dump(),
                        LLM_TOOL_CALL_EVENT,
                        media_type,
                    )
                if tool_result:
                    turn_summary.tool_results.append(tool_result)
                    yield stream_event(
                        tool_result.model_dump(),
                        LLM_TOOL_RESULT_EVENT,
                        media_type,
                    )

        # Completed response - capture final text and response object
        elif event_type == "response.completed":
            latest_response_object = cast(
                OpenAIResponseObject,
                getattr(chunk, "response"),  # noqa: B009
            )
            turn_summary.llm_response = turn_summary.llm_response or "".join(text_parts)
            yield stream_event(
                {
                    "id": chunk_id,
                    "token": turn_summary.llm_response,
                },
                LLM_TURN_COMPLETE_EVENT,
                media_type,
            )
            chunk_id += 1

        # Incomplete or failed response - emit error
        elif event_type in ("response.incomplete", "response.failed"):
            latest_response_object = cast(
                OpenAIResponseObject,
                getattr(chunk, "response"),  # noqa: B009
            )
            error_message = (
                latest_response_object.error.message
                if latest_response_object.error
                else "An unexpected error occurred while processing the request."
            )
            error_response = (
                PromptTooLongResponse(model=context.model_id)
                if is_context_length_error(error_message)
                else InternalServerErrorResponse.query_failed(error_message)
            )
            yield stream_http_error_event(error_response, media_type)

    logger.debug(
        "Streaming complete - Tool calls: %d, Response chars: %d",
        len(turn_summary.tool_calls),
        len(turn_summary.llm_response),
    )

    # Extract token usage and referenced documents from the final response object
    if not latest_response_object:
        return

    turn_summary.token_usage = extract_token_usage(
        latest_response_object.usage, context.model_id, endpoint_path
    )
    # Parse tool-based referenced documents from the final response object
    tool_rag_docs = parse_referenced_documents(
        latest_response_object,
        vector_store_ids=context.vector_store_ids,
        rag_id_mapping=context.rag_id_mapping,
    )
    # Combine inline RAG results (BYOK + Solr) with tool-based results
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        context.inline_rag_context.referenced_documents + tool_rag_docs
    )
    tool_rag_chunks = parse_rag_chunks(
        latest_response_object,
        vector_store_ids=context.vector_store_ids,
        rag_id_mapping=context.rag_id_mapping,
    )
    turn_summary.rag_chunks = context.inline_rag_context.rag_chunks + tool_rag_chunks
