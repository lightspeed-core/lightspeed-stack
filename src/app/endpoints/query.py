"""Handler for REST API call to provide answer to query using Response API."""

import datetime
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client import (
    APIConnectionError,
    APIStatusError as LLSApiStatusError,
    AsyncLlamaStackClient,
)
from openai._exceptions import (
    APIStatusError as OpenAIAPIStatusError,
)

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.config import Action
from models.requests import QueryRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QueryResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
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
    handle_known_apistatus_errors,
    prepare_input,
    store_query_results,
    update_azure_token,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    build_turn_summary,
    deduplicate_referenced_documents,
    extract_vector_store_ids_from_tools,
    get_topic_summary,
    prepare_responses_params,
)
from utils.shields import run_shield_moderation, validate_shield_ids_override
from utils.suid import normalize_conversation_id
from utils.types import (
    ResponsesApiParams,
    ShieldModerationResult,
    TurnSummary,
)
from utils.vector_search import build_rag_context

logger = get_logger(__name__)
router = APIRouter(tags=["query"])

query_response: dict[int | str, dict[str, Any]] = {
    200: QueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["endpoint", "conversation read", "model override"]
    ),
    404: NotFoundResponse.openapi_response(
        examples=["conversation", "model", "provider"]
    ),
    # 413: PromptTooLongResponse.openapi_response(),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
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

    Returns:
        QueryResponse: Contains the conversation ID and the LLM-generated response.

    Raises:
        HTTPException:
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

    await check_mcp_auth(configuration, mcp_headers)

    started_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    user_id, _, _skip_userid_check, token = auth
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
    moderation_result = await run_shield_moderation(
        client, moderation_input, query_request.shield_ids
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

    # Handle Azure token refresh if needed
    if (
        responses_params.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await update_azure_token(client)

    # Retrieve response using Responses API
    turn_summary = await retrieve_response(client, responses_params, moderation_result)

    if moderation_result.decision == "passed":
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
    if not user_conversation and query_request.generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(
            query_request.query, client, responses_params.model
        )
    else:
        topic_summary = None

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


async def retrieve_response(
    client: AsyncLlamaStackClient,
    responses_params: ResponsesApiParams,
    moderation_result: ShieldModerationResult,
) -> TurnSummary:
    """
    Retrieve response from LLMs and agents.

    Retrieves a response from the Llama Stack LLM using the Responses API.
    This function processes the prepared request and returns the LLM response.

    Parameters:
        client: The AsyncLlamaStackClient to use for the request.
        responses_params: The Responses API parameters.
        moderation_result: The moderation result.

    Returns:
        TurnSummary: Summary of the LLM response content
    """
    response: Optional[OpenAIResponseObject] = None
    if moderation_result.decision == "blocked":
        await append_turn_items_to_conversation(
            client,
            responses_params.conversation,
            responses_params.input,
            [moderation_result.refusal_response],
        )
        return TurnSummary(
            id=moderation_result.moderation_id, llm_response=moderation_result.message
        )
    try:
        response = await client.responses.create(
            **responses_params.model_dump(exclude_none=True)
        )
        response = cast(OpenAIResponseObject, response)

    except RuntimeError as e:  # library mode wraps 413 into runtime error
        if "context_length" in str(e).lower():
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

    vector_store_ids = extract_vector_store_ids_from_tools(responses_params.tools)
    rag_id_mapping = configuration.rag_id_mapping
    return build_turn_summary(
        response, responses_params.model, vector_store_ids, rag_id_mapping
    )
