"""Streaming query handler using Responses API."""

# pylint: disable=too-many-lines

import asyncio
import datetime
from collections.abc import AsyncIterator
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_client import (
    APIConnectionError,
)
from llama_stack_client import (
    APIStatusError as LLSApiStatusError,
)
from llama_stack_client.types.response_object_stream import (
    ResponseObjectStream as OpenAIResponseObjectStream,
)
from openai._exceptions import APIStatusError as OpenAIAPIStatusError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import (
    ENDPOINT_PATH_STREAMING_QUERY,
    INTERRUPTED_RESPONSE_MESSAGE,
    MEDIA_TYPE_EVENT_STREAM,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
    TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS,
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
from models.common.streaming import (
    LlmTokenChunkData,
    LlmTokenStreamPayload,
    StreamDispatchState,
)
from models.common.turn_summary import TurnSummary
from models.config import Action
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
    update_azure_token,
    update_conversation_topic_summary,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    deduplicate_referenced_documents,
    extract_token_usage,
    extract_vector_store_ids_from_tools,
    get_topic_summary,
    parse_rag_chunks,
    parse_referenced_documents,
    prepare_responses_params,
)
from utils.shields import (
    append_turn_to_conversation,
    run_shield_moderation,
    validate_shield_ids_override,
)
from utils.stream_interrupts import get_stream_interrupt_registry
from utils.streaming.chunk_dispatchers import dispatch_stream_chunk
from utils.streaming.event_serializers import (
    serialize_end_event,
    serialize_event,
    serialize_http_error_event,
    serialize_interrupted_event,
    serialize_start_event,
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
        client = await update_azure_token(client)

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

    generator, turn_summary = await retrieve_response_generator(
        responses_params=responses_params,
        context=context,
        endpoint_path=endpoint_path,
    )

    # Combine inline RAG results (BYOK + Solr) with tool-based results
    if context.moderation_result.decision == "passed":
        turn_summary.referenced_documents = deduplicate_referenced_documents(
            inline_rag_context.referenced_documents + turn_summary.referenced_documents
        )

    response_media_type = (
        MEDIA_TYPE_TEXT
        if query_request.media_type == MEDIA_TYPE_TEXT
        else MEDIA_TYPE_EVENT_STREAM
    )

    return StreamingResponse(
        generate_response(
            generator=generator,
            context=context,
            responses_params=responses_params,
            turn_summary=turn_summary,
        ),
        media_type=response_media_type,
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


async def _background_update_topic_summary(
    context: ResponseGeneratorContext,
    model: str,
) -> None:
    """Generate topic summary and update DB/cache in the background.

    Runs as a fire-and-forget task after an interrupted turn is persisted.
    All errors are caught and logged.
    """
    try:
        topic_summary = await asyncio.wait_for(
            get_topic_summary(
                context.query_request.query,
                context.client,
                model,
            ),
            timeout=TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS,
        )
        if topic_summary:
            update_conversation_topic_summary(
                context.conversation_id,
                topic_summary,
                user_id=context.user_id,
                skip_userid_check=context.skip_userid_check,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Topic summary timed out for interrupted turn, request %s",
            context.request_id,
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to generate topic summary for interrupted turn, request %s",
            context.request_id,
        )


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


async def _persist_interrupted_turn(
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
) -> None:
    """Persist the user query and an interrupted response into the conversation.

    Called when a streaming request is cancelled so the exchange is not lost.
    Persists immediately with topic_summary=None so the conversation exists
    when the client fetches. Topic summary is generated in a background task
    and updated when ready.

    Parameters:
    ----------
        context: The response generator context.
        responses_params: The Responses API parameters.
        turn_summary: TurnSummary with llm_response already set to the
            interrupted message.
    """
    try:
        await append_turn_to_conversation(
            context.client,
            responses_params.conversation,
            cast(str, responses_params.input),
            INTERRUPTED_RESPONSE_MESSAGE,
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to append interrupted turn to conversation for request %s",
            context.request_id,
        )

    try:
        completed_at = datetime.datetime.now(datetime.UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        store_query_results(
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            model=responses_params.model,
            completed_at=completed_at,
            started_at=context.started_at,
            summary=turn_summary,
            query=context.query_request.query,
            skip_userid_check=context.skip_userid_check,
            topic_summary=None,
        )

        if (
            not context.query_request.conversation_id
            and context.query_request.generate_topic_summary
        ):
            task = asyncio.create_task(
                _background_update_topic_summary(
                    context=context,
                    model=responses_params.model,
                )
            )
            _background_topic_summary_tasks.append(task)
            task.add_done_callback(_background_topic_summary_tasks.remove)
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to store interrupted query results for request %s",
            context.request_id,
        )


def _register_interrupt_callback(
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
) -> list[bool]:
    """Build an interrupt callback and register the stream for cancellation.

    The callback is invoked by ``cancel_stream`` when the client
    interrupts, so persistence runs regardless of where the
    ``CancelledError`` is raised in the ASGI stack.

    A mutable one-element list is used as a shared guard so the
    callback and the in-generator ``CancelledError`` handler never
    both persist the same turn.

    Parameters:
    ----------
        context: The response generator context.
        responses_params: The Responses API parameters.
        turn_summary: TurnSummary populated during streaming.

    Returns:
    -------
        A mutable list ``[False]`` used as a persist-done guard; the
        caller should check ``guard[0]`` before persisting and set
        it to ``True`` afterwards.
    """
    guard: list[bool] = [False]

    async def _on_interrupt() -> None:
        if guard[0]:
            return
        guard[0] = True
        turn_summary.llm_response = INTERRUPTED_RESPONSE_MESSAGE
        await _persist_interrupted_turn(context, responses_params, turn_summary)

    current_task = asyncio.current_task()
    if current_task is not None:
        get_stream_interrupt_registry().register_stream(
            request_id=context.request_id,
            user_id=context.user_id,
            task=current_task,
            on_interrupt=_on_interrupt,
        )
    else:
        logger.warning(
            "No current asyncio task for request %s; "
            "stream interruption will not be available",
            context.request_id,
        )

    return guard


async def generate_response(
    generator: AsyncIterator[str],
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
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

    Yields:
        SSE-formatted strings from the wrapped generator
    """
    persist_guard = _register_interrupt_callback(
        context, responses_params, turn_summary
    )

    stream_completed = False
    try:
        yield serialize_start_event(
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
        yield serialize_http_error_event(
            error_response, context.query_request.media_type
        )
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        yield serialize_http_error_event(
            error_response, context.query_request.media_type
        )
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        error_response = handle_known_apistatus_errors(e, responses_params.model)
        yield serialize_http_error_event(
            error_response, context.query_request.media_type
        )
    except asyncio.CancelledError:
        logger.info("Streaming request %s interrupted by user", context.request_id)
        current_task = asyncio.current_task()
        if current_task is not None:
            current_task.uncancel()
        if not persist_guard[0]:
            persist_guard[0] = True
            turn_summary.llm_response = INTERRUPTED_RESPONSE_MESSAGE
            await _persist_interrupted_turn(context, responses_params, turn_summary)
        yield serialize_interrupted_event(context.request_id)
    finally:
        get_stream_interrupt_registry().deregister_stream(context.request_id)

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

    yield serialize_end_event(
        turn_summary.token_usage,
        available_quotas,
        turn_summary.referenced_documents,
        context.query_request.media_type or MEDIA_TYPE_JSON,
    )
    completed_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

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


async def response_generator(
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
    media_type = context.query_request.media_type or MEDIA_TYPE_JSON
    dispatch_state = StreamDispatchState()

    logger.debug("Starting streaming response (Responses API) processing")
    async for chunk in turn_response:
        logger.debug(
            "Processing chunk %d, type: %s",
            dispatch_state.chunk_id,
            chunk.type,
        )
        dispatch_result = dispatch_stream_chunk(
            chunk,
            dispatch_state,
            media_type,
            context.model_id,
        )
        dispatch_state = dispatch_result.state
        for event in dispatch_result.events:
            yield event

    turn_summary.llm_response = dispatch_state.llm_response
    turn_summary.tool_calls.extend(dispatch_state.tool_calls)
    turn_summary.tool_results.extend(dispatch_state.tool_results)

    logger.debug(
        "Streaming complete - Tool calls: %d, Response chars: %d",
        len(turn_summary.tool_calls),
        len(turn_summary.llm_response),
    )

    # Extract token usage and referenced documents from the final response object
    if dispatch_state.latest_response_object is None:
        return
    final_response = dispatch_state.latest_response_object

    turn_summary.token_usage = extract_token_usage(
        final_response.usage, context.model_id, endpoint_path
    )
    # Parse tool-based referenced documents from the final response object
    tool_rag_docs = parse_referenced_documents(
        final_response,
        vector_store_ids=context.vector_store_ids,
        rag_id_mapping=context.rag_id_mapping,
    )
    # Combine inline RAG results (BYOK + Solr) with tool-based results
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        context.inline_rag_context.referenced_documents + tool_rag_docs
    )
    tool_rag_chunks = parse_rag_chunks(
        final_response,
        vector_store_ids=context.vector_store_ids,
        rag_id_mapping=context.rag_id_mapping,
    )
    turn_summary.rag_chunks = context.inline_rag_context.rag_chunks + tool_rag_chunks


async def shield_violation_generator(
    violation_message: str,
    media_type: str = MEDIA_TYPE_TEXT,
) -> AsyncIterator[str]:
    """
    Create an SSE stream for shield violation responses.

    Yields start, token, and end events immediately for shield violations.
    This function creates a minimal streaming response without going through
    the Llama Stack response format.

    Args:
        violation_message: The violation message to display.
        media_type: The media type for the response format.

    Yields:
        str: SSE-formatted strings for start, token, and end events.
    """
    yield serialize_event(
        LlmTokenStreamPayload(
            data=LlmTokenChunkData(id=0, token=violation_message),
        ),
        media_type,
    )
