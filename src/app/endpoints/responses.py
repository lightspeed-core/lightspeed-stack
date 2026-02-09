# pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks

"""Handler for REST API call to provide answer using Responses API (LCORE specification)."""

import json
import logging
from datetime import UTC, datetime
import sqlite3
from typing import Annotated, Any, AsyncIterator, Optional, Union, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api.openai_responses import (
    OpenAIResponseObject,
    OpenAIResponseObjectStream,
)
from llama_stack_client import (
    APIConnectionError,
    APIStatusError as LLSApiStatusError,
)
from openai._exceptions import (
    APIStatusError as OpenAIAPIStatusError,
)
import psycopg2
from sqlalchemy.exc import SQLAlchemyError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from cache.cache_error import CacheError
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.cache_entry import CacheEntry
from models.config import Action
from models.requests import ResponsesRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    ResponsesResponse,
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
    persist_user_conversation_details,
    store_conversation_into_cache,
    store_query_results,
    update_azure_token,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    extract_text_from_input,
    extract_token_usage,
    get_topic_summary,
    select_model_for_responses,
    validate_model_override_permissions,
)
from utils.shields import (
    append_turn_to_conversation,
    run_shield_moderation,
)
from utils.suid import normalize_conversation_id, to_llama_stack_conversation_id

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["responses"])

responses_response: dict[int | str, dict[str, Any]] = {
    200: ResponsesResponse.openapi_response(),
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


@router.post(
    "/responses",
    responses=responses_response,
    summary="Responses Endpoint Handler",
)
@authorize(Action.QUERY)
async def responses_endpoint_handler(
    request: Request,
    responses_request: ResponsesRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> Union[ResponsesResponse, StreamingResponse]:
    """
    Handle request to the /responses endpoint using Responses API (LCORE specification).

    Processes a POST request to the responses endpoint, forwarding the
    user's request to a selected Llama Stack LLM and returning the generated response
    following the LCORE OpenAPI specification.

    Returns:
        ResponsesResponse: Contains the response following LCORE specification (non-streaming).
        StreamingResponse: SSE-formatted streaming response with enriched events (streaming).
            - response.created event includes conversation attribute
            - response.completed event includes available_quotas attribute

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
    if responses_request.model:
        validate_model_override_permissions(
            responses_request.model,
            request.state.authorized_actions,
        )

    user_conversation = None
    if responses_request.conversation:
        logger.debug(
            "Conversation ID specified in request: %s", responses_request.conversation
        )
        user_conversation = validate_and_retrieve_conversation(
            normalized_conv_id=normalize_conversation_id(responses_request.conversation),
            user_id=user_id,
            others_allowed=Action.READ_OTHERS_CONVERSATIONS
            in request.state.authorized_actions,
        )
        # Convert to llama-stack format if needed
        responses_request.conversation = to_llama_stack_conversation_id(user_conversation.id)

    client = AsyncLlamaStackClientHolder().get_client()

    # LCORE-specific: Automatically select model if not provided in request
    # This extends the base LLS API which requires model to be specified.
    if not responses_request.model:
        responses_request.model = await select_model_for_responses(
            client, user_conversation
        )

    # Prepare API request parameters
    api_params = responses_request.model_dump(
        exclude_none=True, exclude={"generate_topic_summary"}
    )

    # Handle Azure token refresh if needed
    if (
        api_params["model"].startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await update_azure_token(client)

    # Retrieve response using Responses API
    try:
        # Extract text from input for shield moderation (input can be string or complex object)
        input_text_for_moderation = extract_text_from_input(responses_request.input)
        moderation_result = await run_shield_moderation(
            client, input_text_for_moderation
        )
        if moderation_result.blocked:
            violation_message = moderation_result.message or ""
            if responses_request.conversation:
                await append_turn_to_conversation(
                    client,
                    responses_request.conversation,
                    input_text_for_moderation,
                    violation_message,
                )
            return ResponsesResponse.model_construct(
                status="blocked",
                text=violation_message,
                error={"message": violation_message},
                conversation=responses_request.conversation,
            )

        response = await client.responses.create(**api_params)
        
        # Handle streaming response
        if responses_request.stream:
            stream_iterator = cast(AsyncIterator[OpenAIResponseObjectStream], response)
            return StreamingResponse(
                _stream_responses(
                    stream_iterator,
                    responses_request.conversation,
                    user_id,
                    api_params.get("model", ""),
                ),
                media_type="text/event-stream",
            )
        
        response = cast(OpenAIResponseObject, response)

    except RuntimeError as e:  # library mode wraps 413 into runtime error
        if "context_length" in str(e).lower():
            error_response = PromptTooLongResponse(model=api_params.get("model", ""))
            raise HTTPException(**error_response.model_dump()) from e
        raise e
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        error_response = handle_known_apistatus_errors(e, api_params.get("model", ""))
        raise HTTPException(**error_response.model_dump()) from e

    # Extract token usage
    token_usage = extract_token_usage(response, api_params["model"])

    # Consume tokens
    logger.info("Consuming tokens")
    consume_query_tokens(
        user_id=user_id,
        model_id=api_params["model"],
        token_usage=token_usage,
        configuration=configuration,
    )

    # Get available quotas
    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=user_id
    )

    # Get topic summary for new conversation
    if not user_conversation and responses_request.generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(
            extract_text_from_input(responses_request.input), client, api_params["model"]
        )
    else:
        topic_summary = None

    try:
        logger.info("Persisting conversation details")
        # Extract provider_id from model_id (format: "provider/model")
        persist_user_conversation_details(
            user_id=user_id,
            conversation_id=responses_request.conversation or "",
            model_id=api_params["model"],
            provider_id=api_params["model"].split("/")[0], # type: ignore
            topic_summary=topic_summary,
        )
    except SQLAlchemyError as e:
        logger.exception("Error persisting conversation details.")
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e

    # Store conversation in cache
    try:
        completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        cache_entry = CacheEntry(
            query=extract_text_from_input(responses_request.input),
            response="",
            provider=api_params["model"].split("/")[0], # type: ignore
            model=api_params["model"],
            started_at=started_at,
            completed_at=completed_at,
            referenced_documents=None,
            tool_calls=None,
            tool_results=None,
        )

        logger.info("Storing conversation in cache")
        store_conversation_into_cache(
            config=configuration,
            user_id=user_id,
            conversation_id=responses_request.conversation or "",
            cache_entry=cache_entry,
            _skip_userid_check=_skip_userid_check,
            topic_summary=topic_summary,
        )
    except (CacheError, ValueError, psycopg2.Error, sqlite3.Error) as e:
        logger.exception("Error storing conversation in cache: %s", e)
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e

    # Extract response fields using model_dump, excluding output/text which are handled separately
    response_dict = cast(OpenAIResponseObject, response).model_dump()

    logger.info("Building final response")
    return ResponsesResponse(
        **response_dict,
        conversation=responses_request.conversation,
        available_quotas=available_quotas,
    )


async def _stream_responses(
    stream: AsyncIterator[OpenAIResponseObjectStream],
    conversation_id: Optional[str],
    user_id: str,
    model_id: str,
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response with LCORE-enriched events.
    
    Processes streaming chunks from Llama Stack and converts them to
    Server-Sent Events (SSE) format, enriching response.created with conversation
    and response.completed with available_quotas. All other events are forwarded
    exactly as received from the stream.
    
    Args:
        stream: The streaming response from Llama Stack
        conversation_id: The conversation ID to include in response.created
        user_id: User ID for quota retrieval
        model_id: Model ID for token usage extraction
        
    Yields:
        SSE-formatted strings for streaming events.
    """    
    normalized_conv_id = normalize_conversation_id(conversation_id) if conversation_id else None
    latest_response_object: Optional[OpenAIResponseObject] = None
    
    async for chunk in stream:
        event_type = getattr(chunk, "type", None)
        logger.debug("Processing streaming chunk, type: %s", event_type)
        
        # Get the original chunk data as dict (exact same structure as original)
        chunk_dict = chunk.model_dump() if hasattr(chunk, "model_dump") else {}
        
        # Enrich response.created event with conversation attribute
        if event_type == "response.created":
            response_obj = getattr(chunk, "response", None)
            if response_obj:
                latest_response_object = cast(OpenAIResponseObject, response_obj)
            
            # Add conversation attribute to the original chunk data
            if normalized_conv_id:
                chunk_dict["conversation"] = normalized_conv_id
        
        # Enrich response.completed event with available_quotas attribute
        elif event_type == "response.completed":
            response_obj = getattr(chunk, "response", None)
            if response_obj:
                latest_response_object = cast(OpenAIResponseObject, response_obj)
            
            # Extract token usage
            token_usage_obj = None
            if latest_response_object:
                token_usage_obj = extract_token_usage(latest_response_object, model_id)
            
            # Get available quotas
            available_quotas = get_available_quotas(
                quota_limiters=configuration.quota_limiters, user_id=user_id
            )
            
            # Consume tokens
            if token_usage_obj and latest_response_object:
                consume_query_tokens(
                    user_id=user_id,
                    model_id=model_id,
                    token_usage=token_usage_obj,
                    configuration=configuration,
                )
            
            # Add available_quotas attribute to the original chunk data
            if available_quotas:
                chunk_dict["available_quotas"] = available_quotas
        
        yield json.dumps(chunk_dict)