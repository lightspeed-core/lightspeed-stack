"""Handler for REST API call to provide answer to query using Response API."""

import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from client import AsyncOgxClientHolder
from configuration import configuration
from constants import ENDPOINT_PATH_QUERY
from log import get_logger
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
from models.api.responses.successful import QueryResponse
from models.config import Action
from utils.agents.query import retrieve_agent_response
from utils.conversation_compaction import (
    apply_compaction_blocking,
    configured_conversation_cache,
)
from utils.endpoints import (
    check_configuration_loaded,
    validate_and_retrieve_conversation,
)
from utils.mcp_headers import McpHeaders, mcp_headers_dependency
from utils.mcp_oauth_probe import check_mcp_auth
from utils.query import (
    consume_query_tokens,
    store_query_results,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.quota_utils import check_tokens_available, get_available_quotas
from utils.responses import (
    deduplicate_referenced_documents,
    maybe_get_topic_summary,
    prepare_responses_params,
)
from utils.shields import validate_shield_ids_override
from utils.suid import normalize_conversation_id
from utils.vector_search import build_rag_context

logger = get_logger(__name__)
router = APIRouter(tags=["query"])

query_response: dict[int | str, dict[str, Any]] = {
    200: QueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["endpoint", "conversation read", "model override"]
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


@router.post("/query", responses=query_response, summary="Query Endpoint Handler")
@authorize(Action.QUERY)
async def query_endpoint_handler(
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: McpHeaders = Depends(mcp_headers_dependency),
) -> QueryResponse:
    """
    Handle request to the /query endpoint using Responses API.

    Processes a POST request to a query endpoint, forwarding the
    user's query to a selected Llama Stack LLM and returning the generated response.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - query_request: Request to the LLM.
    - auth: Auth context tuple resolved from the authentication dependency.
    - mcp_headers: Headers that should be passed to MCP servers.

    ### Returns:
    - QueryResponse: Contains the conversation ID and the LLM-generated response.

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

    started_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    user_id, _, _skip_userid_check, token = auth

    # Check MCP Auth
    await check_mcp_auth(configuration, mcp_headers, token, request.headers)

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(
        query_request.model, query_request.provider, request.state.authorized_actions
    )

    # Validate shield_ids override if provided
    validate_shield_ids_override(query_request.shield_ids, configuration)

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
    endpoint_path = ENDPOINT_PATH_QUERY

    # Build RAG context from Inline RAG sources
    inline_rag_context = await build_rag_context(
        client,
        query_request.query,
        query_request.vector_store_ids,
        query_request.solr,
    )

    # Prepare API request parameters
    responses_params = await prepare_responses_params(
        client,
        query_request,
        user_conversation,
        token,
        mcp_headers,
        stream=False,
        store=True,
        request_headers=request.headers,
        inline_rag_context=inline_rag_context.context_text,
    )

    # Compact the conversation if it is approaching the context window limit.
    # When compaction is active, params carry explicit input and the
    # conversation parameter is dropped (lightspeed-stack owns the context).
    compaction = await apply_compaction_blocking(
        client,
        responses_params,
        configuration.inference,
        configuration.compaction,
        cache=configured_conversation_cache(),
        user_id=user_id,
        skip_user_id_check=_skip_userid_check,
    )
    responses_params = compaction.params

    # Handle Azure token refresh if needed
    if (
        responses_params.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await AsyncOgxClientHolder().update_azure_token()

    # Retrieve response using Responses API
    turn_summary = await retrieve_agent_response(
        client,
        responses_params,
        endpoint_path,
        compaction.original_input if compaction.compacted else None,
        no_tools=bool(query_request.no_tools),
        shield_ids=query_request.shield_ids,
    )

    # Combine inline RAG results (BYOK + Solr) with tool-based RAG results for the transcript
    rag_chunks = inline_rag_context.rag_chunks
    tool_rag_chunks = turn_summary.rag_chunks
    logger.info("RAG as a tool retrieved %d chunks", len(tool_rag_chunks))
    turn_summary.rag_chunks = rag_chunks + tool_rag_chunks

    # Add tool-based RAG documents and chunks
    rag_documents = inline_rag_context.referenced_documents
    tool_rag_documents = turn_summary.referenced_documents
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        rag_documents + tool_rag_documents
    )

    # Get topic summary for new conversation
    should_generate = not user_conversation and bool(
        query_request.generate_topic_summary
    )
    topic_summary = await maybe_get_topic_summary(
        generate_topic_summary=should_generate,
        input_text=query_request.query,
        client=client,
        model_id=responses_params.model,
    )

    logger.info("Consuming tokens")
    consume_query_tokens(
        user_id=user_id,
        model_id=responses_params.model,
        token_usage=turn_summary.token_usage,
    )

    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=user_id
    )

    completed_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    conversation_id = normalize_conversation_id(responses_params.conversation)

    logger.info("Storing query results")
    store_query_results(
        user_id=user_id,
        conversation_id=conversation_id,
        model=responses_params.model,
        started_at=started_at,
        completed_at=completed_at,
        summary=turn_summary,
        query=query_request.query,
        attachments=query_request.attachments,
        skip_userid_check=_skip_userid_check,
        topic_summary=topic_summary,
    )

    logger.info("Building final response")
    return QueryResponse(
        conversation_id=conversation_id,
        response=turn_summary.llm_response,
        tool_calls=turn_summary.tool_calls,
        tool_results=turn_summary.tool_results,
        rag_chunks=turn_summary.rag_chunks,
        referenced_documents=turn_summary.referenced_documents,
        truncated=False,
        input_tokens=turn_summary.token_usage.input_tokens,
        output_tokens=turn_summary.token_usage.output_tokens,
        available_quotas=available_quotas,
    )
