# pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks, too-many-arguments,too-many-positional-arguments

"""Handler for REST API call to provide answer using Responses API (LCORE specification)."""

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, AsyncIterator, Optional, Union, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage,
    OpenAIResponseObjectStreamResponseOutputItemAdded as OutputItemAddedChunk,
    OpenAIResponseObjectStreamResponseOutputItemDone as OutputItemDoneChunk,
)
from llama_stack_client import (
    APIConnectionError,
    APIStatusError as LLSApiStatusError,
    AsyncLlamaStackClient,
)
from llama_stack_client.types import ResponseObject, ResponseObjectStream
from llama_stack_client.types.response_object import Usage
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
from models.database.conversations import UserConversation
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.responses_api_types import ResponsesRequest, ResponsesResponse
from utils.endpoints import (
    check_configuration_loaded,
    validate_and_retrieve_conversation,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.query import (
    consume_query_tokens,
    handle_known_apistatus_errors,
    update_azure_token,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    extract_response_metadata,
    extract_text_from_input,
    extract_text_from_response_output_item,
    extract_token_usage,
    extract_vector_store_ids_from_tools,
    get_topic_summary,
    persist_response_metadata,
    select_model_for_responses,
    validate_model_override_permissions,
)
from utils.shields import (
    append_refused_turn_to_conversation,
    run_shield_moderation,
)
from utils.suid import normalize_conversation_id, to_llama_stack_conversation_id
from utils.types import ShieldModerationResult, TurnSummary

logger = get_logger(__name__)
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
    response_model=None,
    summary="Responses Endpoint Handler",
)
@authorize(Action.QUERY)
async def responses_endpoint_handler(
    request: Request,
    responses_request: ResponsesRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    _mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
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
    user_id, _, _skip_userid_check, _token = auth

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    if responses_request.model:
        validate_model_override_permissions(
            responses_request.model,
            request.state.authorized_actions,
        )

    user_conversation: Optional[UserConversation] = None
    if responses_request.conversation:
        logger.debug(
            "Conversation ID specified in request: %s", responses_request.conversation
        )
        user_conversation = validate_and_retrieve_conversation(
            normalized_conv_id=normalize_conversation_id(
                responses_request.conversation
            ),
            user_id=user_id,
            others_allowed=Action.READ_OTHERS_CONVERSATIONS
            in request.state.authorized_actions,
        )
        # Convert to llama-stack format if needed
        responses_request.conversation = to_llama_stack_conversation_id(
            user_conversation.id
        )

    client = AsyncLlamaStackClientHolder().get_client()

    # LCORE-specific: Automatically select model if not provided in request
    # This extends the base LLS API which requires model to be specified.
    if not responses_request.model:
        responses_request.model = await select_model_for_responses(
            client, user_conversation
        )

    # TODO(asimurka): LCORE-1263 Add implicit conversation management

    # Handle Azure token refresh if needed
    if (
        responses_request.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await update_azure_token(client)

    input_text = extract_text_from_input(responses_request.input)
    moderation_result = await run_shield_moderation(client, input_text)

    # If blocked, persist refusal to conversation before handling
    # The condition will be simplified when implementing LCORE-1263
    if (
        moderation_result.blocked
        and moderation_result.refusal_response
        and responses_request.conversation
    ):
        await append_refused_turn_to_conversation(
            client,
            responses_request.conversation,
            responses_request.input,
            moderation_result.refusal_response,
        )

    response_handler = (
        handle_streaming_response
        if responses_request.stream
        else handle_non_streaming_response
    )
    return await response_handler(
        client=client,
        request=responses_request,
        user_id=user_id,
        input_text=input_text,
        started_at=started_at,
        user_conversation=user_conversation,
        moderation_result=moderation_result,
        _skip_userid_check=_skip_userid_check,
    )


async def handle_streaming_response(
    client: AsyncLlamaStackClient,
    request: ResponsesRequest,
    user_id: str,
    input_text: str,
    started_at: str,
    user_conversation: Optional[UserConversation],
    moderation_result: ShieldModerationResult,
    _skip_userid_check: bool,
) -> StreamingResponse:
    """Handle streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        request: ResponsesRequest containing API request parameters
        user_id: The authenticated user ID
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        user_conversation: The user conversation if available, None for new conversations
        moderation_result: Result of shield moderation check
        _skip_userid_check: Whether to skip user ID check for cache operations

    Returns:
        StreamingResponse with SSE-formatted events
    """
    turn_summary = TurnSummary()
    # Handle blocked response
    if moderation_result.blocked and moderation_result.refusal_response:
        turn_summary.llm_response = moderation_result.message or ""
        available_quotas = get_available_quotas(
            quota_limiters=configuration.quota_limiters, user_id=user_id
        )
        generator = shield_violation_generator(
            moderation_result.refusal_response,
            request.conversation or "",
            moderation_result.moderation_id or "",
            int(time.time()),
            request.get_mirrored_params(),
            available_quotas,
        )

    else:
        api_params = request.model_dump(
            exclude_none=True, exclude={"generate_topic_summary"}
        )  # LCORE-specific feature
        try:
            response = await client.responses.create(**api_params)
            generator = response_generator(
                cast(AsyncIterator[ResponseObjectStream], response),
                request.conversation or "",  # Will be fixed later in LCORE-1263
                user_id,
                api_params["model"],
                turn_summary,
                vector_store_ids=extract_vector_store_ids_from_tools(
                    api_params.get("tools", [])
                ),
            )
        except RuntimeError as e:  # library mode wraps 413 into runtime error
            if "context_length" in str(e).lower():
                error_response = PromptTooLongResponse(
                    model=api_params.get("model", "")
                )
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            error_response = handle_known_apistatus_errors(
                e, api_params.get("model", "")
            )
            raise HTTPException(**error_response.model_dump()) from e

    normalized_conv_id = normalize_conversation_id(request.conversation or "")
    return StreamingResponse(
        generate_response(
            generator,
            turn_summary,
            client=client,
            user_id=user_id,
            input_text=input_text,
            started_at=started_at,
            user_conversation=user_conversation,
            generate_topic_summary=request.generate_topic_summary or False,
            model_id=request.model or "",
            conversation_id=normalized_conv_id,
            _skip_userid_check=_skip_userid_check,
        ),
        media_type="text/event-stream",
    )


async def shield_violation_generator(
    refusal_response: OpenAIResponseMessage,
    conversation_id: str,
    response_id: str,
    created_at: int,
    mirrored_params: dict[str, Any],
    available_quotas: dict[str, int],
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response for shield-blocked requests.

    Follows the Open Responses spec:
    - Content-Type: text/event-stream
    - Each event has 'event:' field matching the type in the event body
    - Data objects are JSON-encoded strings
    - Terminal event is the literal string [DONE]
    - Emits full event sequence: response.created (in_progress), output_item.added,
      output_item.done, response.completed (completed)
    - Performs topic summary and persistence after [DONE] is emitted

    Args:
        refusal_response: The refusal response message object
        conversation_id: The conversation ID to include in the response
        response_id: Unique identifier for this response
        created_at: Unix timestamp when the response was created
        mirrored_params: Request parameters to mirror in the response (model, instructions, etc.)
        available_quotas: Available quotas dictionary for the user
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    normalized_conv_id = normalize_conversation_id(conversation_id)

    # 1. Send response.created event with status "in_progress" and empty output
    created_response_object = ResponsesResponse.model_construct(
        id=response_id,
        created_at=created_at,
        object="response",
        status="in_progress",
        output=[],
        usage=None,
        conversation=normalized_conv_id,
        available_quotas={},
        output_text="",
        **mirrored_params,
    )
    created_response_dict = created_response_object.model_dump(exclude_none=True)
    created_event = {
        "type": "response.created",
        "response": created_response_dict,
    }
    data_json = json.dumps(created_event)
    yield f"event: response.created\ndata: {data_json}\n\n"

    # 2. Send response.output_item.added event
    output_index = 0
    sequence_number = 1
    item_added_event = OutputItemAddedChunk(
        response_id=response_id,
        item=refusal_response,
        output_index=output_index,
        sequence_number=sequence_number,
    )
    data_json = json.dumps(item_added_event.model_dump(exclude_none=True))
    yield f"event: response.output_item.added\ndata: {data_json}\n\n"

    # 3. Send response.output_item.done event
    sequence_number = 2
    item_done_event = OutputItemDoneChunk(
        response_id=response_id,
        item=refusal_response,
        output_index=output_index,
        sequence_number=sequence_number,
    )
    data_json = json.dumps(item_done_event.model_dump(exclude_none=True))
    yield f"event: response.output_item.done\ndata: {data_json}\n\n"

    # 4. Send response.completed event with status "completed" and output populated
    completed_response_object = ResponsesResponse.model_construct(
        id=response_id,
        created_at=created_at,
        object="response",
        status="completed",
        output=[refusal_response],
        usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0),
        conversation=normalized_conv_id,
        available_quotas=available_quotas,
        output_text=extract_text_from_response_output_item(refusal_response),
        **mirrored_params,
    )
    completed_response_dict = completed_response_object.model_dump(exclude_none=True)
    completed_event = {
        "type": "response.completed",
        "response": completed_response_dict,
        "available_quotas": available_quotas,
    }
    data_json = json.dumps(completed_event)
    yield f"event: response.completed\ndata: {data_json}\n\n"

    yield "data: [DONE]\n\n"


async def response_generator(
    stream: AsyncIterator[ResponseObjectStream],
    conversation_id: str,
    user_id: str,
    model_id: str,
    turn_summary: TurnSummary,
    vector_store_ids: Optional[list[str]] = None,
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response with LCORE-enriched events.

    Args:
        stream: The streaming response from Llama Stack
        conversation_id: The llama-stack conversation ID (will be normalized)
        user_id: User ID for quota retrieval
        model_id: Model ID for token usage extraction
        turn_summary: TurnSummary to populate during streaming
        vector_store_ids: Vector store IDs used in the query for source resolution.
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    # Normalize conversation_id once before streaming
    # (conversation is always present when streaming)
    normalized_conv_id = normalize_conversation_id(conversation_id)

    logger.debug("Starting streaming response (Responses API) processing")

    latest_response_object: Optional[ResponseObject] = None

    async for chunk in stream:
        event_type = getattr(chunk, "type", None)
        logger.debug("Processing streaming chunk, type: %s", event_type)

        chunk_dict = chunk.model_dump()

        # Add conversation attribute to the response if chunk has it
        if "response" in chunk_dict:
            chunk_dict["response"]["conversation"] = normalized_conv_id

        # Intermediate response - no quota consumption yet
        if event_type == "response.in_progress":
            chunk_dict["response"]["available_quotas"] = {}

        # Handle completion, incomplete, and failed events - only quota handling here
        if event_type in (
            "response.completed",
            "response.incomplete",
            "response.failed",
        ):
            latest_response_object = cast(ResponseObject, getattr(chunk, "response"))

            # Extract and consume tokens if any were used
            turn_summary.token_usage = extract_token_usage(
                latest_response_object.usage, model_id
            )
            consume_query_tokens(
                user_id=user_id,
                model_id=model_id,
                token_usage=turn_summary.token_usage,
                configuration=configuration,
            )

            # Get available quotas after token consumption
            available_quotas = get_available_quotas(
                quota_limiters=configuration.quota_limiters, user_id=user_id
            )
            chunk_dict["response"]["available_quotas"] = available_quotas

        data_json = json.dumps(chunk_dict)
        yield f"event: {event_type}\ndata: {data_json}\n\n"

    # Extract response metadata from final response object
    (
        turn_summary.llm_response,
        turn_summary.referenced_documents,
        turn_summary.tool_calls,
        turn_summary.tool_results,
    ) = extract_response_metadata(
        latest_response_object, vector_store_ids, configuration.rag_id_mapping
    )

    yield "data: [DONE]\n\n"


async def generate_response(
    generator: AsyncIterator[str],
    turn_summary: TurnSummary,
    client: AsyncLlamaStackClient,
    user_id: str,
    input_text: str,
    started_at: str,
    user_conversation: Optional[UserConversation],
    generate_topic_summary: bool,
    model_id: str,
    conversation_id: str,
    _skip_userid_check: bool,
) -> AsyncIterator[str]:
    """Stream the response from the generator and persist conversation details.

    After streaming completes, conversation details are persisted.

    Args:
        generator: The SSE event generator
        turn_summary: TurnSummary populated during streaming
        client: The AsyncLlamaStackClient instance
        user_id: The authenticated user ID
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        user_conversation: The user conversation if available, None for new conversations
        generate_topic_summary: Whether to generate topic summary for new conversations
        model_id: Model identifier
        conversation_id: Normalized conversation ID
        _skip_userid_check: Whether to skip user ID check for cache operations

    Yields:
        SSE-formatted strings from the generator
    """
    async for event in generator:
        yield event

    # Get topic summary for new conversation
    topic_summary = None
    if not user_conversation and generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(input_text, client, model_id)

    # Persist conversation details and cache
    completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if conversation_id:  # Will be removed in LCORE-1263
        await persist_response_metadata(
            user_id=user_id,
            conversation_id=conversation_id,
            model_id=model_id,
            input_text=input_text,
            response_text=turn_summary.llm_response,
            started_at=started_at,
            completed_at=completed_at,
            topic_summary=topic_summary,
            referenced_documents=turn_summary.referenced_documents,
            tool_calls=turn_summary.tool_calls,
            tool_results=turn_summary.tool_results,
            _skip_userid_check=_skip_userid_check,
        )


async def handle_non_streaming_response(
    client: AsyncLlamaStackClient,
    request: ResponsesRequest,
    user_id: str,
    input_text: str,
    started_at: str,
    user_conversation: Optional[UserConversation],
    moderation_result: ShieldModerationResult,
    _skip_userid_check: bool,
) -> ResponsesResponse:
    """Handle non-streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        request: ResponsesRequest containing API request parameters
        user_id: The authenticated user ID
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        user_conversation: The user conversation if available, None for new conversations
        moderation_result: Result of shield moderation check
        _skip_userid_check: Whether to skip user ID check for cache operations

    Returns:
        ResponsesResponse with the completed response
    """
    # Extract conversation_id and mirrored params (common for both paths)
    conversation_id = normalize_conversation_id(request.conversation or "")

    api_params = request.model_dump(
        exclude_none=True, exclude={"generate_topic_summary"}
    )
    # Fork: Get response object (blocked vs normal)
    if moderation_result.blocked and moderation_result.refusal_response:
        # Create blocked response object
        created_at = int(time.time())
        response_id = f"resp_{uuid.uuid4().hex[:24]}"
        response = ResponsesResponse.model_construct(
            id=response_id,
            created_at=created_at,
            status="completed",
            completed_at=created_at,
            output=[moderation_result.refusal_response],
            usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0),
            output_text=extract_text_from_response_output_item(
                moderation_result.refusal_response
            ),
            **request.get_mirrored_params(),
        )
    else:
        # Get normal response from API
        try:
            api_response = cast(
                ResponseObject, await client.responses.create(**api_params)
            )
            token_usage = extract_token_usage(api_response.usage, request.model or "")
            # Consume tokens
            logger.info("Consuming tokens")
            consume_query_tokens(
                user_id=user_id,
                model_id=request.model or "",
                token_usage=token_usage,
                configuration=configuration,
            )
            response = ResponsesResponse.model_construct(
                **api_response.model_dump(),
                output_text=api_response.output_text,
            )

        except RuntimeError as e:  # library mode wraps 413 into runtime error
            if "context_length" in str(e).lower():
                error_response = PromptTooLongResponse(model=request.model)
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            error_response = handle_known_apistatus_errors(e, request.model or "")
            raise HTTPException(**error_response.model_dump()) from e

    # Get available quotas
    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=user_id
    )
    # Get topic summary for new conversation
    topic_summary = None
    if not user_conversation and request.generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(input_text, client, request.model or "")

    # Extract response metadata
    vector_store_ids = extract_vector_store_ids_from_tools(api_params.get("tools", []))
    response_text, referenced_documents, tool_calls, tool_results = (
        extract_response_metadata(
            cast(ResponseObject, response),
            vector_store_ids,
            configuration.rag_id_mapping,
        )
    )  # safe to cast (uses only common fields)

    if conversation_id:  # Will be removed in LCORE-1263
        await persist_response_metadata(
            user_id=user_id,
            conversation_id=conversation_id,
            model_id=request.model or "",
            input_text=input_text,
            response_text=response_text,
            started_at=started_at,
            completed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            topic_summary=topic_summary,
            referenced_documents=referenced_documents,
            tool_calls=tool_calls,
            tool_results=tool_results,
            _skip_userid_check=_skip_userid_check,
        )

    response.available_quotas = available_quotas
    response.conversation = conversation_id
    response.completed_at = int(time.time())
    return response
