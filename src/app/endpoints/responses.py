# pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks, too-many-arguments,too-many-positional-arguments

"""Handler for REST API call to provide answer using Responses API (LCORE specification)."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any, AsyncIterator, Optional, Union, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api import OpenAIResponseObject, OpenAIResponseObjectStream
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage,
    OpenAIResponseObjectStreamResponseOutputItemAdded as OutputItemAddedChunk,
    OpenAIResponseObjectStreamResponseOutputItemDone as OutputItemDoneChunk,
    OpenAIResponseUsage as Usage,
)
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
from models.database.conversations import UserConversation
from models.requests import ResponsesRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ResponsesResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)

from utils.conversations import add_response_to_conversation
from utils.endpoints import (
    check_configuration_loaded,
    retrieve_turn_by_response_id,
    validate_and_retrieve_conversation,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.query import (
    consume_query_tokens,
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    store_query_results,
    update_azure_token,
    validate_model_provider_override,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    build_turn_summary,
    check_model_configured,
    create_new_conversation,
    deduplicate_referenced_documents,
    extract_text_from_response_item,
    extract_text_from_response_items,
    extract_token_usage,
    extract_vector_store_ids_from_tools,
    get_topic_summary,
    prepare_tools,
    select_model_for_responses,
)
from utils.conversations import append_turn_items_to_conversation
from utils.shields import run_shield_moderation
from utils.suid import (
    normalize_conversation_id,
    to_llama_stack_conversation_id,
)
from utils.types import (
    ReferencedDocument,
    ResponseInput,
    ResponsesApiParams,
    ShieldModerationResult,
    TurnSummary,
)
from utils.vector_search import (
    build_message_from_static_rag,
    format_rag_context_for_injection,
    perform_vector_search,
)

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
    responses_request = responses_request.model_copy(deep=True)
    check_configuration_loaded(configuration)
    started_at = datetime.now(UTC)
    user_id = auth[0]

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model in requests
    if responses_request.model:
        validate_model_provider_override(
            responses_request.model,
            None,  # provider specified as model prefix
            request.state.authorized_actions,
        )

    client = AsyncLlamaStackClientHolder().get_client()

    user_conversation: Optional[UserConversation] = None
    # Context for the LLM passed by conversation
    if responses_request.conversation:
        logger.info(
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
        responses_request.conversation = to_llama_stack_conversation_id(
            user_conversation.id
        )
        # Disable topic summary generation for existing conversations
        responses_request.generate_topic_summary = False

    # Context for the LLM passed by previous response id
    elif responses_request.previous_response_id:
        user_turn = retrieve_turn_by_response_id(responses_request.previous_response_id)
        user_conversation = validate_and_retrieve_conversation(
            normalized_conv_id=user_turn.conversation_id,
            user_id=user_id,
            others_allowed=Action.READ_OTHERS_CONVERSATIONS
            in request.state.authorized_actions,
        )
        # Conversation will be forked if the specified response is not the last response
        if user_conversation.last_response_id != responses_request.previous_response_id:
            logger.info("Forking conversation")
            responses_request.conversation = await create_new_conversation(client)
            # Copy the forked turn to the new conversation
            await add_response_to_conversation(
                client,
                responses_request.previous_response_id,
                responses_request.conversation,
            )
        else:  # Specified response is the last response in the conversation (no fork)
            logger.info("No fork, using existing conversation")
            responses_request.conversation = to_llama_stack_conversation_id(
                user_conversation.id
            )
            responses_request.generate_topic_summary = False
    else:  # No context passed, create new conversation
        responses_request.conversation = await create_new_conversation(client)

    # LCORE-specific: Automatically select model if not provided in request
    # This extends the base LLS API which requires model to be specified.
    if not responses_request.model:
        responses_request.model = await select_model_for_responses(
            client, user_conversation
        )
    if not await check_model_configured(client, responses_request.model):
        _, model_id = extract_provider_and_model_from_model_id(responses_request.model)
        error_response = NotFoundResponse(resource="model", resource_id=model_id)
        raise HTTPException(**error_response.model_dump())

    # Handle Azure token refresh if needed
    if (
        responses_request.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await update_azure_token(client)

    input_text = (
        responses_request.input
        if isinstance(responses_request.input, str)
        else extract_text_from_response_items(responses_request.input)
    )

    _, _, doc_ids_from_chunks, pre_rag_chunks = await perform_vector_search(
        client, input_text, responses_request.solr
    )

    rag_context = format_rag_context_for_injection(pre_rag_chunks)
    if isinstance(responses_request.input, str):
        responses_request.input = responses_request.input + rag_context
    else:
        responses_request.input.append(build_message_from_static_rag(rag_context))

    moderation_result = await run_shield_moderation(
        client, input_text, responses_request.shield_ids
    )

    # If tools attribute is None, configure all tools configured in LCORE
    if responses_request.tools is None:
        responses_request.tools = await prepare_tools(
            client,
            None,
            False,
            auth[1],
            _mcp_headers,
        )

    response_handler = (
        handle_streaming_response
        if responses_request.stream
        else handle_non_streaming_response
    )
    return await response_handler(
        client=client,
        request=responses_request,
        auth=auth,
        input_text=input_text,
        started_at=started_at,
        moderation_result=moderation_result,
        static_rag_docs=doc_ids_from_chunks,
    )


async def handle_streaming_response(
    client: AsyncLlamaStackClient,
    request: ResponsesRequest,
    auth: AuthTuple,
    input_text: str,
    started_at: datetime,
    moderation_result: ShieldModerationResult,
    static_rag_docs: list[ReferencedDocument],
) -> StreamingResponse:
    """Handle streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        request: ResponsesRequest (LCORE-specific fields e.g. generate_topic_summary)
        auth: Authentication tuple
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        moderation_result: Result of shield moderation check
        static_rag_docs: Static RAG documents to be used for the response
    Returns:
        StreamingResponse with SSE-formatted events
    """
    api_params = ResponsesApiParams.model_validate(request.model_dump())
    turn_summary = TurnSummary()
    # Handle blocked response
    if moderation_result.decision == "blocked":
        turn_summary.id = moderation_result.moderation_id
        turn_summary.llm_response = moderation_result.message
        available_quotas = get_available_quotas(
            quota_limiters=configuration.quota_limiters, user_id=auth[0]
        )
        generator = shield_violation_generator(
            moderation_result.refusal_response,
            api_params.conversation,
            moderation_result.moderation_id,
            request.echoed_params(),
            started_at,
            available_quotas,
        )
        if api_params.store:
            await append_turn_items_to_conversation(
                client,
                api_params.conversation,
                request.input,
                llm_output=[moderation_result.refusal_response],
            )
    else:
        try:
            # Do not pass the new conversation so that the full context is provided to the model
            response = await client.responses.create(**api_params.dump_for_create())
            generator = response_generator(
                cast(AsyncIterator[OpenAIResponseObjectStream], response),
                request.input,
                api_params,
                auth[0],
                turn_summary,
                vector_store_ids=extract_vector_store_ids_from_tools(api_params.tools),
                static_rag_docs=static_rag_docs,
            )
        except RuntimeError as e:  # library mode wraps 413 into runtime error
            if "context_length" in str(e).lower():
                error_response = PromptTooLongResponse(model=api_params.model)
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            error_response = handle_known_apistatus_errors(e, api_params.model)
            raise HTTPException(**error_response.model_dump()) from e

    return StreamingResponse(
        generate_response(
            generator,
            turn_summary,
            client=client,
            auth=auth,
            input_text=input_text,
            started_at=started_at,
            api_params=api_params,
            generate_topic_summary=request.generate_topic_summary or False,
        ),
        media_type="text/event-stream",
    )


async def shield_violation_generator(
    refusal_response: OpenAIResponseMessage,
    conversation_id: str,
    response_id: str,
    echoed_params: dict[str, Any],
    created_at: datetime,
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
        echoed_params: Echoed parameters from the request
        created_at: Unix timestamp when the response was created
        available_quotas: Available quotas dictionary for the user
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    normalized_conv_id = normalize_conversation_id(conversation_id)

    # 1. Send response.created event with status "in_progress" and empty output
    created_response_object = ResponsesResponse.model_construct(
        id=response_id,
        object="response",
        created_at=int(created_at.timestamp()),
        status="in_progress",
        output=[],
        conversation=normalized_conv_id,
        available_quotas={},
        output_text="",
        **echoed_params,
    )
    created_response_dict = created_response_object.model_dump(exclude_none=True)
    created_event = {
        "type": "response.created",
        "sequence_number": 0,
        "response": created_response_dict,
    }
    data_json = json.dumps(created_event)
    yield f"event: response.created\ndata: {data_json}\n\n"

    # 2. Send response.output_item.added event
    item_added_event = OutputItemAddedChunk(
        response_id=response_id,
        item=refusal_response,
        output_index=0,
        sequence_number=1,
    )
    data_json = json.dumps(item_added_event.model_dump(exclude_none=True))
    yield f"event: response.output_item.added\ndata: {data_json}\n\n"

    # 3. Send response.output_item.done event
    item_done_event = OutputItemDoneChunk(
        response_id=response_id,
        item=refusal_response,
        output_index=0,
        sequence_number=2,
    )
    data_json = json.dumps(item_done_event.model_dump(exclude_none=True))
    yield f"event: response.output_item.done\ndata: {data_json}\n\n"

    # 4. Send response.completed event with status "completed" and output populated
    completed_response_object = ResponsesResponse.model_construct(
        id=response_id,
        created_at=int(created_at.timestamp()),
        object="response",
        completed_at=int(datetime.now(UTC).timestamp()),
        status="completed",
        output=[refusal_response],
        usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0),
        conversation=normalized_conv_id,
        available_quotas=available_quotas,
        output_text=extract_text_from_response_item(refusal_response),
        **echoed_params,
    )
    completed_response_dict = completed_response_object.model_dump(exclude_none=True)
    completed_event = {
        "type": "response.completed",
        "sequence_number": 3,
        "response": completed_response_dict,
        "available_quotas": available_quotas,
    }
    data_json = json.dumps(completed_event)
    yield f"event: response.completed\ndata: {data_json}\n\n"

    yield "data: [DONE]\n\n"


async def response_generator(
    stream: AsyncIterator[OpenAIResponseObjectStream],
    user_input: ResponseInput,
    api_params: ResponsesApiParams,
    user_id: str,
    turn_summary: TurnSummary,
    static_rag_docs: list[ReferencedDocument],
    vector_store_ids: Optional[list[str]] = None,
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response with LCORE-enriched events.

    Args:
        stream: The streaming response from Llama Stack
        user_input: User input to the response
        api_params: ResponsesApiParams
        user_id: User ID for quota retrieval
        turn_summary: TurnSummary to populate during streaming
        static_rag_docs: Static RAG documents to be used for the response
        vector_store_ids: Vector store IDs used in the query for source resolution.
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    normalized_conv_id = normalize_conversation_id(api_params.conversation)

    logger.debug("Starting streaming response (Responses API) processing")

    latest_response_object: Optional[OpenAIResponseObject] = None
    sequence_number = 0

    async for chunk in stream:
        event_type = getattr(chunk, "type", None)
        logger.debug("Processing streaming chunk, type: %s", event_type)

        chunk_dict = chunk.model_dump(exclude_none=True)

        # Create own sequence number for chunks to maintain order
        chunk_dict["sequence_number"] = sequence_number
        sequence_number += 1

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
            latest_response_object = cast(
                OpenAIResponseObject, getattr(chunk, "response")
            )

            # Extract and consume tokens if any were used
            turn_summary.token_usage = extract_token_usage(
                latest_response_object.usage, api_params.model
            )
            consume_query_tokens(
                user_id=user_id,
                model_id=api_params.model,
                token_usage=turn_summary.token_usage,
            )

            # Get available quotas after token consumption
            available_quotas = get_available_quotas(
                quota_limiters=configuration.quota_limiters, user_id=user_id
            )
            chunk_dict["response"]["available_quotas"] = available_quotas

        data_json = json.dumps(chunk_dict)
        yield f"event: {event_type}\ndata: {data_json}\n\n"

    # Extract response metadata from final response object
    t = build_turn_summary(
        latest_response_object,
        api_params.model,
        vector_store_ids,
        configuration.rag_id_mapping,
    )
    t.referenced_documents = deduplicate_referenced_documents(
        static_rag_docs + t.referenced_documents
    )

    # Copy turn summary fields to the outer turn_summary
    for field, value in t.model_dump().items():
        setattr(turn_summary, field, value)

    client = AsyncLlamaStackClientHolder().get_client()
    # Explicitely append the turn to conversation if context passed by previous response
    if api_params.store and api_params.previous_response_id and latest_response_object:
        await append_turn_items_to_conversation(
            client, api_params.conversation, user_input, latest_response_object.output
        )

    yield "data: [DONE]\n\n"


async def generate_response(
    generator: AsyncIterator[str],
    turn_summary: TurnSummary,
    client: AsyncLlamaStackClient,
    auth: AuthTuple,
    input_text: str,
    started_at: datetime,
    api_params: ResponsesApiParams,
    generate_topic_summary: bool,
) -> AsyncIterator[str]:
    """Stream the response from the generator and persist conversation details.

    After streaming completes, conversation details are persisted.

    Args:
        generator: The SSE event generator
        turn_summary: TurnSummary populated during streaming
        moderation_result: Result of shield moderation check
        client: The AsyncLlamaStackClient instance
        user_id: The authenticated user ID
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        api_params: ResponsesApiParams
        generate_topic_summary: Whether to generate topic summary for new conversations

    Yields:
        SSE-formatted strings from the generator
    """
    user_id, _, skip_userid_check, _ = auth
    async for event in generator:
        yield event

    # Get topic summary for new conversation
    topic_summary = None
    if generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(input_text, client, api_params.model)

    completed_at = datetime.now(UTC)
    if api_params.store:
        store_query_results(
            user_id=user_id,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            started_at=started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at=completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            summary=turn_summary,
            query=input_text,
            attachments=[],
            skip_userid_check=skip_userid_check,
            topic_summary=topic_summary,
        )


async def handle_non_streaming_response(
    client: AsyncLlamaStackClient,
    request: ResponsesRequest,
    auth: AuthTuple,
    input_text: str,
    started_at: datetime,
    moderation_result: ShieldModerationResult,
    static_rag_docs: list[ReferencedDocument],
) -> ResponsesResponse:
    """Handle non-streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        api_params: Full API params with resolved model/conversation for responses.create
        user_id: The authenticated user ID
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        moderation_result: Result of shield moderation check
        static_rag_docs: Static RAG documents to be used for the response
    Returns:
        ResponsesResponse with the completed response
    """
    user_id, _, skip_userid_check, _ = auth
    api_params = ResponsesApiParams.model_validate(request.model_dump())

    # Fork: Get response object (blocked vs normal)
    if moderation_result.decision == "blocked":
        response_id = moderation_result.moderation_id
        completed_at = datetime.now(UTC)
        api_response = OpenAIResponseObject.model_construct(
            id=response_id,
            object="response",
            created_at=int(started_at.timestamp()),
            status="completed",
            output=[moderation_result.refusal_response],
            usage=Usage(input_tokens=0, output_tokens=0, total_tokens=0),
            **request.echoed_params(),
        )
        output_text = moderation_result.message
        if api_params.store:
            await append_turn_items_to_conversation(
                client,
                api_params.conversation,
                request.input,
                llm_output=[moderation_result.refusal_response],
            )
    else:
        try:
            api_response = cast(
                OpenAIResponseObject,
                await client.responses.create(**api_params.dump_for_create()),
            )
            token_usage = extract_token_usage(api_response.usage, api_params.model)
            logger.info("Consuming tokens")
            consume_query_tokens(
                user_id=user_id,
                model_id=api_params.model,
                token_usage=token_usage,
            )
            output_text = extract_text_from_response_items(api_response.output)
            # Explicitely append the turn to conversation if context passed by previous response
            if api_params.store and api_params.previous_response_id:
                await append_turn_items_to_conversation(
                    client, api_params.conversation, request.input, api_response.output
                )

        except RuntimeError as e:
            if "context_length" in str(e).lower():
                error_response = PromptTooLongResponse(model=api_params.model)
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            error_response = handle_known_apistatus_errors(e, api_params.model)
            raise HTTPException(**error_response.model_dump()) from e

    # Get available quotas
    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=user_id
    )
    # Get topic summary for new conversation
    topic_summary = None
    if request.generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(input_text, client, api_params.model)

    vector_store_ids = extract_vector_store_ids_from_tools(api_params.tools)
    turn_summary = build_turn_summary(
        api_response,
        api_params.model,
        vector_store_ids,
        configuration.rag_id_mapping,
    )
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        static_rag_docs + turn_summary.referenced_documents
    )
    completed_at = datetime.now(UTC)
    if api_params.store:
        store_query_results(
            user_id=user_id,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            started_at=started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at=completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            summary=turn_summary,
            query=input_text,
            attachments=[],
            skip_userid_check=skip_userid_check,
            topic_summary=topic_summary,
        )
    response = ResponsesResponse.model_validate(
        {
            **api_response.model_dump(exclude_none=True),
            "available_quotas": available_quotas,
            "conversation": normalize_conversation_id(api_params.conversation),
            "completed_at": int(completed_at.timestamp()),
            "output_text": output_text,
        }
    )
    return response
