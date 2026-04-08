# pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks, too-many-arguments,too-many-positional-arguments

"""Handler for REST API call to provide answer using Responses API (LCORE specification)."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api import (
    OpenAIResponseObject,
    OpenAIResponseObjectStream,
)
from llama_stack_api import (
    OpenAIResponseObjectStreamResponseOutputItemAdded as OutputItemAddedChunk,
)
from llama_stack_api import (
    OpenAIResponseObjectStreamResponseOutputItemDone as OutputItemDoneChunk,
)
from llama_stack_client import (
    APIConnectionError,
    AsyncLlamaStackClient,
)
from llama_stack_client import (
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
from log import get_logger
from models.config import Action
from models.requests import ResponsesRequest
from models.responses import (
    ConflictResponse,
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
from utils.conversations import append_turn_items_to_conversation
from utils.endpoints import (
    check_configuration_loaded,
    resolve_response_context,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.mcp_oauth_probe import check_mcp_auth
from utils.query import (
    consume_query_tokens,
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    is_context_length_error,
    store_query_results,
    update_azure_token,
    validate_model_provider_override,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    build_tool_call_summary,
    build_turn_summary,
    check_model_configured,
    deduplicate_referenced_documents,
    extract_attachments_text,
    extract_text_from_response_items,
    extract_token_usage,
    extract_vector_store_ids_from_tools,
    get_topic_summary,
    get_zero_usage,
    is_server_deployed_output,
    parse_rag_chunks,
    parse_referenced_documents,
    resolve_tool_choice,
    select_model_for_responses,
)
from utils.shields import run_shield_moderation
from utils.suid import (
    normalize_conversation_id,
)
from utils.tool_formatter import translate_vector_store_ids_to_user_facing
from utils.types import (
    RAGContext,
    ResponseInput,
    ResponsesApiParams,
    ShieldModerationBlocked,
    ShieldModerationResult,
    TurnSummary,
)
from utils.vector_search import (
    append_inline_rag_context_to_responses_input,
    build_rag_context,
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
    409: ConflictResponse.openapi_response(
        examples=["mcp tool conflict", "file search conflict"]
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
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> ResponsesResponse | StreamingResponse:
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
    # Known LLS bug: https://redhat.atlassian.net/browse/LCORE-1583
    if responses_request.reasoning is not None:
        logger.warning("reasoning is not yet supported in LCORE and will be ignored")
        responses_request.reasoning = None
    if responses_request.max_output_tokens is not None:
        logger.warning(
            "max_output_tokens is not yet supported in LCORE and will be ignored"
        )
        responses_request.max_output_tokens = None

    responses_request = responses_request.model_copy(deep=True)
    check_configuration_loaded(configuration)
    started_at = datetime.now(UTC)
    user_id = auth[0]

    await check_mcp_auth(configuration, mcp_headers)

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model in requests
    validate_model_provider_override(
        responses_request.model,
        None,  # provider specified as model prefix
        request.state.authorized_actions,
    )

    response_context = await resolve_response_context(
        user_id=user_id,
        others_allowed=(
            Action.READ_OTHERS_CONVERSATIONS in request.state.authorized_actions
        ),
        conversation_id=responses_request.conversation,
        previous_response_id=responses_request.previous_response_id,
        generate_topic_summary=responses_request.generate_topic_summary,
    )
    responses_request.conversation = response_context.conversation
    responses_request.generate_topic_summary = response_context.generate_topic_summary
    client = AsyncLlamaStackClientHolder().get_client()

    # LCORE-specific: Automatically select model if not provided in request
    # This extends the base LLS API which requires model to be specified.
    if not responses_request.model:
        responses_request.model = await select_model_for_responses(
            client, response_context.user_conversation
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
    attachments_text = extract_attachments_text(responses_request.input)

    moderation_result = await run_shield_moderation(
        client,
        input_text + "\n\n" + attachments_text,
        responses_request.shield_ids,
    )

    # Extract vector store IDs for Inline RAG context before resolving tool choice.
    vector_store_ids: Optional[list[str]] = (
        extract_vector_store_ids_from_tools(responses_request.tools)
        if responses_request.tools is not None
        else None
    )

    responses_request.tools, responses_request.tool_choice = await resolve_tool_choice(
        responses_request.tools,
        responses_request.tool_choice,
        auth[1],
        mcp_headers,
        request.headers,
    )

    filter_server_tools = (
        request.headers.get("X-LCS-Merge-Server-Tools", "").lower() == "true"
    )

    # Build RAG context from Inline RAG sources
    inline_rag_context = await build_rag_context(
        client,
        moderation_result.decision,
        input_text,
        vector_store_ids,
        responses_request.solr,
    )
    if moderation_result.decision == "passed":
        responses_request.input = append_inline_rag_context_to_responses_input(
            responses_request.input, inline_rag_context.context_text
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
        inline_rag_context=inline_rag_context,
        filter_server_tools=filter_server_tools,
    )


async def handle_streaming_response(
    client: AsyncLlamaStackClient,
    request: ResponsesRequest,
    auth: AuthTuple,
    input_text: str,
    started_at: datetime,
    moderation_result: ShieldModerationResult,
    inline_rag_context: RAGContext,
    filter_server_tools: bool = False,
) -> StreamingResponse:
    """Handle streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        request: ResponsesRequest (LCORE-specific fields e.g. generate_topic_summary)
        auth: Authentication tuple
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        moderation_result: Result of shield moderation check
        inline_rag_context: Inline RAG context to be used for the response
        filter_server_tools: Whether to filter server-deployed MCP tool events from the stream
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
            moderation_result,
            api_params.conversation,
            request.echoed_params(),
            started_at,
            available_quotas,
        )
        if api_params.store:
            await append_turn_items_to_conversation(
                client=client,
                conversation_id=api_params.conversation,
                user_input=request.input,
                llm_output=[moderation_result.refusal_response],
            )
    else:
        try:
            response = await client.responses.create(
                **api_params.model_dump(exclude_none=True)
            )
            generator = response_generator(
                stream=cast(AsyncIterator[OpenAIResponseObjectStream], response),
                user_input=request.input,
                api_params=api_params,
                user_id=auth[0],
                turn_summary=turn_summary,
                inline_rag_context=inline_rag_context,
                filter_server_tools=filter_server_tools,
            )
        except RuntimeError as e:  # library mode wraps 413 into runtime error
            if is_context_length_error(str(e)):
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
            generator=generator,
            turn_summary=turn_summary,
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
    moderation_result: ShieldModerationBlocked,
    conversation_id: str,
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
        moderation_result: The moderation result
        conversation_id: The conversation ID to include in the response
        echoed_params: Echoed parameters from the request
        created_at: Unix timestamp when the response was created
        available_quotas: Available quotas dictionary for the user
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    normalized_conv_id = normalize_conversation_id(conversation_id)

    # 1. Send response.created event with status "in_progress" and empty output
    created_response_object = ResponsesResponse.model_construct(
        id=moderation_result.moderation_id,
        created_at=int(created_at.timestamp()),
        status="in_progress",
        output=[],
        conversation=normalized_conv_id,
        available_quotas={},
        output_text="",
        **echoed_params,
    )
    created_response_dict = created_response_object.model_dump(
        exclude_none=True, by_alias=True
    )
    created_event = {
        "type": "response.created",
        "sequence_number": 0,
        "response": created_response_dict,
    }
    data_json = json.dumps(created_event)
    yield f"event: response.created\ndata: {data_json}\n\n"

    # 2. Send response.output_item.added event
    item_added_event = OutputItemAddedChunk(
        response_id=moderation_result.moderation_id,
        item=moderation_result.refusal_response,
        output_index=0,
        sequence_number=1,
    )
    data_json = json.dumps(
        item_added_event.model_dump(exclude_none=True, by_alias=True)
    )
    yield f"event: response.output_item.added\ndata: {data_json}\n\n"

    # 3. Send response.output_item.done event
    item_done_event = OutputItemDoneChunk(
        response_id=moderation_result.moderation_id,
        item=moderation_result.refusal_response,
        output_index=0,
        sequence_number=2,
    )
    data_json = json.dumps(item_done_event.model_dump(exclude_none=True, by_alias=True))
    yield f"event: response.output_item.done\ndata: {data_json}\n\n"

    # 4. Send response.completed event with status "completed" and output populated
    completed_response_object = ResponsesResponse.model_construct(
        id=moderation_result.moderation_id,
        created_at=int(created_at.timestamp()),
        completed_at=int(datetime.now(UTC).timestamp()),
        status="completed",
        output=[moderation_result.refusal_response],
        usage=get_zero_usage(),
        conversation=normalized_conv_id,
        available_quotas=available_quotas,
        output_text=moderation_result.message,
        **echoed_params,
    )
    completed_response_dict = completed_response_object.model_dump(
        exclude_none=True, by_alias=True
    )
    completed_event = {
        "type": "response.completed",
        "sequence_number": 3,
        "response": completed_response_dict,
    }
    data_json = json.dumps(completed_event)
    yield f"event: response.completed\ndata: {data_json}\n\n"

    yield "data: [DONE]\n\n"


def _is_server_mcp_output_item(
    item: dict[str, Any], configured_mcp_labels: set[str]
) -> bool:
    """Check if a serialized output item is a server-deployed MCP tool call.

    Args:
        item: A dict from the serialized response output array.
        configured_mcp_labels: Set of server_label names configured in LCS.

    Returns:
        True if the item is an MCP call/list/approval from a server-deployed MCP server.
    """
    item_type = item.get("type")
    if item_type in ("mcp_call", "mcp_list_tools", "mcp_approval_request"):
        return item.get("server_label") in configured_mcp_labels
    return False


def _should_filter_mcp_chunk(
    chunk: OpenAIResponseObjectStream,
    event_type: Optional[str],
    configured_mcp_labels: set[str],
    server_mcp_output_indices: set[int],
) -> bool:
    """Check if a streaming chunk is a server-deployed MCP event that should be filtered.

    Args:
        chunk: The streaming chunk to check.
        event_type: The event type of the chunk.
        configured_mcp_labels: Set of server_label names configured in LCS.
        server_mcp_output_indices: Tracked output indices of server-deployed MCP calls.

    Returns:
        True if the chunk should be filtered out from the client stream.
    """
    if event_type == "response.output_item.added":
        item_added_chunk = cast(OutputItemAddedChunk, chunk)
        item = item_added_chunk.item
        item_type = getattr(item, "type", None)
        if item_type in ("mcp_call", "mcp_list_tools", "mcp_approval_request"):
            server_label = getattr(item, "server_label", None)
            if server_label in configured_mcp_labels:
                server_mcp_output_indices.add(item_added_chunk.output_index)
                return True

    if event_type and (
        event_type.startswith("response.mcp_call.")
        or event_type.startswith("response.mcp_list_tools.")
        or event_type.startswith("response.mcp_approval_request.")
    ):
        output_index = getattr(chunk, "output_index", None)
        if output_index in server_mcp_output_indices:
            return True

    if event_type == "response.output_item.done":
        item_done_chunk = cast(OutputItemDoneChunk, chunk)
        item = item_done_chunk.item
        item_type = getattr(item, "type", None)
        if item_type in ("mcp_call", "mcp_list_tools", "mcp_approval_request"):
            if item_done_chunk.output_index in server_mcp_output_indices:
                server_mcp_output_indices.discard(item_done_chunk.output_index)
                return True

    return False


def _populate_turn_summary(
    response_object: OpenAIResponseObject,
    turn_summary: TurnSummary,
    api_params: ResponsesApiParams,
    inline_rag_context: RAGContext,
    filter_server_tools: bool,
) -> None:
    """Populate turn summary with metadata extracted from the final response object.

    Args:
        response_object: The completed response object from Llama Stack
        turn_summary: TurnSummary to populate
        api_params: ResponsesApiParams
        inline_rag_context: Inline RAG context used for the response
        filter_server_tools: Whether to filter server-deployed MCP tool events
    """
    turn_summary.id = response_object.id
    vector_store_ids = extract_vector_store_ids_from_tools(api_params.tools)
    tool_rag_docs = parse_referenced_documents(
        response_object, vector_store_ids, configuration.rag_id_mapping
    )
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        inline_rag_context.referenced_documents + tool_rag_docs
    )
    for item in response_object.output:
        if filter_server_tools and not is_server_deployed_output(item):
            continue
        tool_call, tool_result = build_tool_call_summary(item)
        if tool_call:
            turn_summary.tool_calls.append(tool_call)
        if tool_result:
            turn_summary.tool_results.append(tool_result)

    tool_rag_chunks = parse_rag_chunks(
        response_object,
        vector_store_ids,
        configuration.rag_id_mapping,
    )
    turn_summary.rag_chunks = inline_rag_context.rag_chunks + tool_rag_chunks


async def response_generator(
    stream: AsyncIterator[OpenAIResponseObjectStream],
    user_input: ResponseInput,
    api_params: ResponsesApiParams,
    user_id: str,
    turn_summary: TurnSummary,
    inline_rag_context: RAGContext,
    filter_server_tools: bool = False,
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response with LCORE-enriched events.

    Args:
        stream: The streaming response from Llama Stack
        user_input: User input to the response
        api_params: ResponsesApiParams
        user_id: User ID for quota retrieval
        turn_summary: TurnSummary to populate during streaming
        inline_rag_context: Inline RAG context to be used for the response
        filter_server_tools: Whether to filter server-deployed MCP tool events from the stream
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    normalized_conv_id = normalize_conversation_id(api_params.conversation)

    logger.debug("Starting streaming response (Responses API) processing")

    latest_response_object: Optional[OpenAIResponseObject] = None
    sequence_number = 0
    configured_mcp_labels = (
        {s.name for s in configuration.mcp_servers} if filter_server_tools else set()
    )
    # Track output indices of server-deployed MCP calls to filter their events
    server_mcp_output_indices: set[int] = set()

    async for chunk in stream:
        event_type = getattr(chunk, "type", None)
        logger.debug("Processing streaming chunk, type: %s", event_type)

        # Filter out streaming events for server-deployed MCP tools.
        # These are handled internally by LCS and should not be forwarded
        # to clients that don't understand the mcp_call item type.
        if _should_filter_mcp_chunk(
            chunk, event_type, configured_mcp_labels, server_mcp_output_indices
        ):
            continue

        chunk_dict = chunk.model_dump(exclude_none=True, by_alias=True)

        # Create own sequence number for chunks to maintain order
        chunk_dict["sequence_number"] = sequence_number
        sequence_number += 1

        if "response" in chunk_dict:
            chunk_dict["response"]["conversation"] = normalized_conv_id
            tools = chunk_dict["response"].get("tools")
            if tools is not None:
                chunk_dict["response"]["tools"] = (
                    translate_vector_store_ids_to_user_facing(
                        tools,
                        configuration.rag_id_mapping,
                    )
                )
            # Remove server-deployed MCP items from the output array so
            # clients only see item types they understand (message, function_call, etc.)
            output = chunk_dict["response"].get("output")
            if output is not None:
                chunk_dict["response"]["output"] = [
                    item
                    for item in output
                    if not _is_server_mcp_output_item(item, configured_mcp_labels)
                ]

        # Intermediate response - no quota consumption and text yet
        if event_type == "response.in_progress":
            chunk_dict["response"]["available_quotas"] = {}
            chunk_dict["response"]["output_text"] = ""

        # Handle completion, incomplete, and failed events - only quota handling here
        if event_type in (
            "response.completed",
            "response.incomplete",
            "response.failed",
        ):
            latest_response_object = cast(
                OpenAIResponseObject, cast(Any, chunk).response
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
            turn_summary.llm_response = extract_text_from_response_items(
                latest_response_object.output
            )
            chunk_dict["response"]["output_text"] = turn_summary.llm_response

        data_json = json.dumps(chunk_dict)
        yield f"event: {event_type or 'error'}\ndata: {data_json}\n\n"

    # Extract response metadata from final response object
    if latest_response_object:
        _populate_turn_summary(
            latest_response_object,
            turn_summary,
            api_params,
            inline_rag_context,
            filter_server_tools,
        )

    client = AsyncLlamaStackClientHolder().get_client()
    # Explicitly append the turn to conversation if context passed by previous response
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
        client: The AsyncLlamaStackClient instance
        auth: Authentication tuple
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
    inline_rag_context: RAGContext,
    filter_server_tools: bool = False,
) -> ResponsesResponse:
    """Handle non-streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        request: Request object
        auth: Authentication tuple
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        moderation_result: Result of shield moderation check
        inline_rag_context: Inline RAG context to be used for the response
        filter_server_tools: Whether to filter server-deployed MCP tool output
    Returns:
        ResponsesResponse with the completed response
    """
    user_id, _, skip_userid_check, _ = auth
    api_params = ResponsesApiParams.model_validate(request.model_dump())

    # Fork: Get response object (blocked vs normal)
    if moderation_result.decision == "blocked":
        output_text = moderation_result.message
        api_response = OpenAIResponseObject.model_construct(
            id=moderation_result.moderation_id,
            created_at=int(started_at.timestamp()),
            status="completed",
            output=[moderation_result.refusal_response],
            usage=get_zero_usage(),
            **request.echoed_params(),
        )
        if api_params.store:
            await append_turn_items_to_conversation(
                client=client,
                conversation_id=api_params.conversation,
                user_input=request.input,
                llm_output=[moderation_result.refusal_response],
            )
    else:
        try:
            api_response = cast(
                OpenAIResponseObject,
                await client.responses.create(
                    **api_params.model_dump(exclude_none=True)
                ),
            )
            token_usage = extract_token_usage(api_response.usage, api_params.model)
            logger.info("Consuming tokens")
            consume_query_tokens(
                user_id=user_id,
                model_id=api_params.model,
                token_usage=token_usage,
            )
            output_text = extract_text_from_response_items(api_response.output)
            # Explicitly append the turn to conversation if context passed by previous response
            if api_params.store and api_params.previous_response_id:
                await append_turn_items_to_conversation(
                    client, api_params.conversation, request.input, api_response.output
                )

        except RuntimeError as e:
            if is_context_length_error(str(e)):
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
        filter_server_tools=filter_server_tools,
    )
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        inline_rag_context.referenced_documents + turn_summary.referenced_documents
    )
    turn_summary.rag_chunks.extend(inline_rag_context.rag_chunks)
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
    response_dict = api_response.model_dump(exclude_none=True)
    tools = response_dict.get("tools")
    if tools is not None:
        response_dict["tools"] = translate_vector_store_ids_to_user_facing(
            tools,
            configuration.rag_id_mapping,
        )
    response = ResponsesResponse.model_validate(
        {
            **response_dict,
            "available_quotas": available_quotas,
            "conversation": normalize_conversation_id(api_params.conversation),
            "completed_at": int(completed_at.timestamp()),
            "output_text": output_text,
        }
    )
    return response
