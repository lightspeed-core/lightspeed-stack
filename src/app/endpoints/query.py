# pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks

"""Handler for REST API call to provide answer to query using Response API."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client import (
    APIConnectionError,
    AsyncLlamaStackClient,
    APIStatusError as LLSApiStatusError,
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
from utils.endpoints import (
    check_configuration_loaded,
    validate_and_retrieve_conversation,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.query import (
    consume_query_tokens,
    handle_known_apistatus_errors,
    store_query_results,
    update_azure_token,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    build_tool_call_summary,
    extract_text_from_response_output_item,
    extract_token_usage,
    get_topic_summary,
    parse_referenced_documents,
    prepare_responses_params,
)
from utils.shields import (
    append_turn_to_conversation,
    run_shield_moderation,
)
from utils.suid import normalize_conversation_id
from utils.types import ResponsesApiParams, TurnSummary

logger = logging.getLogger("app.endpoints.handlers")
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
        examples=["model", "conversation", "provider"]
    ),
    413: PromptTooLongResponse.openapi_response(),
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
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
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

    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    user_id, _, _skip_userid_check, token = auth
    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(query_request, request.state.authorized_actions)

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

    # Prepare API request parameters
    responses_params = await prepare_responses_params(
        client,
        query_request,
        user_conversation,
        token,
        mcp_headers,
        stream=False,
        store=True,
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
    turn_summary = await retrieve_response(client, responses_params)

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
        configuration=configuration,
    )

    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=user_id
    )

    completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    conversation_id = normalize_conversation_id(responses_params.conversation)

    logger.info("Storing query results")
    store_query_results(
        user_id=user_id,
        conversation_id=conversation_id,
        model=responses_params.model,
        started_at=started_at,
        completed_at=completed_at,
        summary=turn_summary,
        query_request=query_request,
        configuration=configuration,
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


async def retrieve_response(  # pylint: disable=too-many-locals
    client: AsyncLlamaStackClient,
    responses_params: ResponsesApiParams,
) -> TurnSummary:
    """
    Retrieve response from LLMs and agents.

    Retrieves a response from the Llama Stack LLM using the Responses API.
    This function processes the prepared request and returns the LLM response.

    Parameters:
        client: The AsyncLlamaStackClient to use for the request.
        responses_params: The Responses API parameters.

    Returns:
        TurnSummary: Summary of the LLM response content
    """
    summary = TurnSummary()

    try:
        moderation_result = await run_shield_moderation(client, responses_params.input)
        if moderation_result.blocked:
            # Handle shield moderation blocking
            violation_message = moderation_result.message or ""
            await append_turn_to_conversation(
                client,
                responses_params.conversation,
                responses_params.input,
                violation_message,
            )
            summary.llm_response = violation_message
            return summary
        response = await client.responses.create(**responses_params.model_dump())
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

    # Process OpenAI response format
    for output_item in response.output:
        message_text = extract_text_from_response_output_item(output_item)
        if message_text:
            summary.llm_response += message_text

        tool_call, tool_result = build_tool_call_summary(
            output_item, summary.rag_chunks
        )
        if tool_call:
            summary.tool_calls.append(tool_call)
        if tool_result:
            summary.tool_results.append(tool_result)

    logger.info(
        "Response processing complete - Tool calls: %d, Response length: %d chars",
        len(summary.tool_calls),
        len(summary.llm_response),
    )

    # Extract referenced documents and token usage from Responses API response
    summary.referenced_documents = parse_referenced_documents(response)
    summary.token_usage = extract_token_usage(response, responses_params.model)

    return summary
