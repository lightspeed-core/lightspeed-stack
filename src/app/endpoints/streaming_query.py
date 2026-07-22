"""Streaming query handler using Responses API."""

import asyncio
import datetime
from collections.abc import AsyncIterator
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from ogx_client import (
    APIConnectionError,
)
from ogx_client import (
    APIStatusError as LLSApiStatusError,
)
from openai._exceptions import APIStatusError as OpenAIAPIStatusError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from client import AsyncOgxClientHolder
from configuration import configuration
from constants import (
    ENDPOINT_PATH_STREAMING_QUERY,
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
)
from utils.endpoints import (
    check_configuration_loaded,
    validate_and_retrieve_conversation,
)
from utils.mcp_headers import McpHeaders, mcp_headers_dependency
from utils.mcp_oauth_probe import check_mcp_auth
from utils.query import (
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    is_context_length_error,
    prepare_input,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.quota_utils import check_tokens_available
from utils.responses import (
    deduplicate_referenced_documents,
    extract_vector_store_ids_from_tools,
    prepare_responses_params,
)
from utils.shields import (
    run_shield_moderation,
    validate_shield_ids_override,
)
from utils.streaming_sse import (
    http_exception_stream_event,
    stream_compaction_event,
    stream_http_error_event,
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
        examples=["ogx", "kubernetes api"]
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
    - 503: Service Unavailable - Unable to connect to OGX backend
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

    client = AsyncOgxClientHolder().get_client()

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
        client = await AsyncOgxClientHolder().update_azure_token()

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
        no_tools=bool(query_request.no_tools),
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
        ),
        media_type=response_media_type,
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
            ServiceUnavailableResponse(backend_name="OGX", cause=str(e)),
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
