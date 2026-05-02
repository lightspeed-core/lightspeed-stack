# pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks,too-many-arguments,too-many-positional-arguments,too-many-lines,too-many-statements

"""Handler for REST API call to provide answer using Responses API (LCORE specification)."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, Final, Optional, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
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
from constants import ENDPOINT_PATH_RESPONSES, SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER
from log import get_logger
from models.api.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH,
    ConflictResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.responses_context import ResponsesContext
from models.config import Action
from models.requests import ResponsesRequest
from models.responses import (
    ResponsesResponse,
)
from observability import ResponsesEventData, build_responses_event, send_splunk_event
from utils.conversations import append_turn_items_to_conversation
from utils.endpoints import (
    check_configuration_loaded,
    resolve_response_context,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.mcp_oauth_probe import check_mcp_auth
from utils.prompts import get_system_prompt
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
    resolve_client_tool_choice,
    resolve_tool_choice,
    select_model_for_responses,
)
from utils.rh_identity import get_rh_identity_context
from utils.shields import run_shield_moderation
from utils.suid import (
    normalize_conversation_id,
)
from utils.tool_formatter import translate_vector_store_ids_to_user_facing
from utils.types import (
    ShieldModerationBlocked,
    TurnSummary,
)
from utils.vector_search import (
    append_inline_rag_context_to_responses_input,
    build_rag_context,
)

logger = get_logger(__name__)
router = APIRouter(tags=["responses"])

_USER_AGENT_MAX_LENGTH: Final[int] = 128


def _get_user_agent(request: Request) -> Optional[str]:
    """Extract and sanitize the User-Agent header from the request.

    Parses the raw User-Agent header, strips control characters and newlines,
    and truncates to a safe maximum length. Returns None when the header is
    absent or empty.

    Args:
        request: The FastAPI request object.

    Returns:
        Sanitized User-Agent string, or None if the header is absent or empty.
    """
    raw = request.headers.get("User-Agent", "")
    if not raw:
        return None
    sanitized = "".join(c for c in raw if ord(c) >= 32 and c not in ("\r", "\n"))
    sanitized = sanitized[:_USER_AGENT_MAX_LENGTH]
    return sanitized or None


responses_response: dict[int | str, dict[str, Any]] = {
    200: ResponsesResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH
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
    413: PromptTooLongResponse.openapi_response(examples=["context window exceeded"]),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}


# Strong references for fire-and-forget telemetry tasks so they aren't
# garbage-collected before completion (the event loop only holds weak refs).
_background_splunk_tasks: set[asyncio.Task[None]] = set()


def _queue_responses_splunk_event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    background_tasks: Optional[BackgroundTasks],
    input_text: str,
    response_text: str,
    conversation_id: str,
    model: str,
    rh_identity_context: tuple[str, str],
    inference_time: float,
    sourcetype: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    fire_and_forget: bool = False,
    user_agent: Optional[str] = None,
) -> None:
    """Build and queue a Splunk telemetry event for the responses endpoint.

    No-op when background_tasks is None and fire_and_forget is False
    (Splunk telemetry disabled).

    Args:
        background_tasks: FastAPI background task manager, or None if disabled.
        input_text: User input text.
        response_text: Response text from LLM or shield.
        conversation_id: Conversation identifier.
        model: Model name used for inference.
        rh_identity_context: Tuple of (org_id, system_id) from RH identity.
        inference_time: Request processing duration in seconds.
        sourcetype: Splunk sourcetype for the event.
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens produced.
        fire_and_forget: When True, dispatch via asyncio.create_task() instead
            of background_tasks.  Use for error paths where an HTTPException
            follows, since FastAPI discards BackgroundTasks on non-2xx responses.
        user_agent: Sanitized User-Agent string from the request header, or None.
    """
    if not fire_and_forget and background_tasks is None:
        return
    org_id, system_id = rh_identity_context
    event_data = ResponsesEventData(
        input_text=input_text,
        response_text=response_text,
        conversation_id=conversation_id,
        model=model,
        org_id=org_id,
        system_id=system_id,
        inference_time=inference_time,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        user_agent=user_agent,
    )
    event = build_responses_event(event_data)
    if fire_and_forget:
        task = asyncio.create_task(send_splunk_event(event, sourcetype))
        _background_splunk_tasks.add(task)
        task.add_done_callback(_background_splunk_tasks.discard)
    elif background_tasks is not None:
        background_tasks.add_task(send_splunk_event, event, sourcetype)


@router.post(
    "/responses",
    responses=responses_response,
    response_model=None,
    summary="Responses Endpoint Handler",
)
@authorize(Action.RESPONSES)
async def responses_endpoint_handler(
    request: Request,
    responses_request: ResponsesRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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
    original_request = responses_request  # read-only request
    updated_request = responses_request.model_copy(deep=True)
    _ = responses_request

    # Known LLS bug: https://redhat.atlassian.net/browse/LCORE-1583
    if original_request.reasoning is not None:
        logger.warning("reasoning is not yet supported in LCORE and will be ignored")
        updated_request.reasoning = None

    check_configuration_loaded(configuration)
    started_at = datetime.now(UTC)
    rh_identity_context = get_rh_identity_context(request)
    user_id, _, _, token = auth

    await check_mcp_auth(configuration, mcp_headers, token, request.headers)

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model in requests
    validate_model_provider_override(
        original_request.model,
        None,  # provider specified as model prefix
        request.state.authorized_actions,
    )

    updated_request.instructions = get_system_prompt(
        original_request.instructions, field_name="instructions"
    )

    response_context = await resolve_response_context(
        user_id=user_id,
        others_allowed=(
            Action.READ_OTHERS_CONVERSATIONS in request.state.authorized_actions
        ),
        conversation_id=original_request.conversation,
        previous_response_id=original_request.previous_response_id,
        generate_topic_summary=original_request.generate_topic_summary,
    )
    updated_request.conversation = response_context.conversation
    updated_request.generate_topic_summary = response_context.generate_topic_summary
    client = AsyncLlamaStackClientHolder().get_client()

    # LCORE-specific: Automatically select model if not provided in request
    # This extends the base LLS API which requires model to be specified.
    updated_request.model = await select_model_for_responses(
        original_request.model, client, response_context.user_conversation
    )
    if not await check_model_configured(client, updated_request.model):
        _, model_id = extract_provider_and_model_from_model_id(updated_request.model)
        error_response = NotFoundResponse(resource="model", resource_id=model_id)
        raise HTTPException(**error_response.model_dump())

    # Handle Azure token refresh if needed
    if (
        updated_request.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await update_azure_token(client)

    input_text = (
        original_request.input
        if isinstance(original_request.input, str)
        else extract_text_from_response_items(original_request.input)
    )
    attachments_text = extract_attachments_text(original_request.input)

    endpoint_path = ENDPOINT_PATH_RESPONSES
    moderation_result = await run_shield_moderation(
        client,
        input_text + "\n\n" + attachments_text,
        endpoint_path,
        original_request.shield_ids,
    )

    filter_server_tools = (
        request.headers.get("X-LCS-Merge-Server-Tools", "").lower() == "true"
    )
    resolver = (
        resolve_client_tool_choice if filter_server_tools else resolve_tool_choice
    )
    updated_request.tools, updated_request.tool_choice = await resolver(
        original_request.tools,
        original_request.tool_choice,
        token,
        mcp_headers,
        request.headers,
    )

    # Extract vector store IDs for Inline RAG context from the original request
    vector_store_ids: Optional[list[str]] = (
        extract_vector_store_ids_from_tools(original_request.tools)
        if original_request.tools is not None
        else None
    )
    # Build RAG context from Inline RAG sources
    inline_rag_context = await build_rag_context(
        client,
        moderation_result.decision,
        input_text,
        vector_store_ids,
        original_request.solr,
    )
    if moderation_result.decision == "passed":
        updated_request.input = append_inline_rag_context_to_responses_input(
            original_request.input, inline_rag_context.context_text
        )

    api_params = ResponsesApiParams.model_validate(updated_request.model_dump())
    context = ResponsesContext(
        client=client,
        auth=auth,
        input_text=input_text,
        started_at=started_at,
        moderation_result=moderation_result,
        inline_rag_context=inline_rag_context,
        filter_server_tools=filter_server_tools,
        background_tasks=background_tasks,
        rh_identity_context=rh_identity_context,
        user_agent=_get_user_agent(request),
        endpoint_path=endpoint_path,
        generate_topic_summary=updated_request.generate_topic_summary,
    )
    response_handler = (
        handle_streaming_response
        if original_request.stream
        else handle_non_streaming_response
    )
    return await response_handler(
        original_request=original_request,
        api_params=api_params,
        context=context,
    )


async def handle_streaming_response(
    original_request: ResponsesRequest,
    api_params: ResponsesApiParams,
    context: ResponsesContext,
) -> StreamingResponse:
    """Handle streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        original_request: Original request (read-only)
        api_params: API parameters
        responses_context: Responses context
    Returns:
        StreamingResponse with SSE-formatted events
    """
    turn_summary = TurnSummary()
    # Handle blocked response
    if context.moderation_result.decision == "blocked":
        turn_summary.id = context.moderation_result.moderation_id
        turn_summary.llm_response = context.moderation_result.message
        generator = shield_violation_generator(api_params, context)
        if api_params.store:
            await append_turn_items_to_conversation(
                client=context.client,
                conversation_id=api_params.conversation,
                user_input=api_params.input,
                llm_output=[context.moderation_result.refusal_response],
            )
        _queue_responses_splunk_event(
            background_tasks=context.background_tasks,
            input_text=context.input_text,
            response_text=context.moderation_result.message,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=context.rh_identity_context,
            inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
            sourcetype="responses_shield_blocked",
            user_agent=context.user_agent,
        )
    else:
        try:
            response = await context.client.responses.create(
                **api_params.model_dump(exclude_none=True)
            )
            generator = response_generator(
                stream=cast(AsyncIterator[OpenAIResponseObjectStream], response),
                original_request=original_request,
                api_params=api_params,
                context=context,
                turn_summary=turn_summary,
            )
        except RuntimeError as e:  # library mode wraps 413 into runtime error
            if is_context_length_error(str(e)):
                _queue_responses_splunk_event(
                    background_tasks=context.background_tasks,
                    input_text=context.input_text,
                    response_text=str(e),
                    conversation_id=normalize_conversation_id(api_params.conversation),
                    model=api_params.model,
                    rh_identity_context=context.rh_identity_context,
                    inference_time=(
                        datetime.now(UTC) - context.started_at
                    ).total_seconds(),
                    sourcetype="responses_error",
                    fire_and_forget=True,
                    user_agent=context.user_agent,
                )
                error_response = PromptTooLongResponse(model=api_params.model)
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            _queue_responses_splunk_event(
                background_tasks=context.background_tasks,
                input_text=context.input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=context.rh_identity_context,
                inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=context.user_agent,
            )
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            _queue_responses_splunk_event(
                background_tasks=context.background_tasks,
                input_text=context.input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=context.rh_identity_context,
                inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=context.user_agent,
            )
            error_response = handle_known_apistatus_errors(e, api_params.model)
            raise HTTPException(**error_response.model_dump()) from e

    return StreamingResponse(
        generate_response(
            generator=generator,
            api_params=api_params,
            context=context,
            turn_summary=turn_summary,
        ),
        media_type="text/event-stream",
    )


async def shield_violation_generator(
    api_params: ResponsesApiParams,
    context: ResponsesContext,
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response for shield-blocked requests.

    Args:
        api_params: ResponsesApiParams
        context: ResponsesContext
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    normalized_conv_id = normalize_conversation_id(api_params.conversation)
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=context.auth[0]
    )
    moderation_result = cast(ShieldModerationBlocked, context.moderation_result)

    # 1. Send response.created event with status "in_progress" and empty output
    created_response_object = ResponsesResponse.model_construct(
        id=moderation_result.moderation_id,
        created_at=int(context.started_at.timestamp()),
        status="in_progress",
        output=[],
        conversation=normalized_conv_id,
        available_quotas={},
        output_text="",
        **api_params.echoed_params(configuration.rag_id_mapping),
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
        created_at=int(context.started_at.timestamp()),
        completed_at=int(datetime.now(UTC).timestamp()),
        status="completed",
        output=[moderation_result.refusal_response],
        usage=get_zero_usage(),
        conversation=normalized_conv_id,
        available_quotas=available_quotas,
        output_text=moderation_result.message,
        **api_params.echoed_params(configuration.rag_id_mapping),
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


def _sanitize_response_dict(
    response_dict: dict[str, Any],
    configured_mcp_labels: set[str],
    original_request: ResponsesRequest,
) -> None:
    """Sanitize a serialized response object in-place to remove internal details.

    Strips fields that expose server-side implementation details from the
    response object before it is forwarded to the client.

    Args:
        response_dict: Mutable dict produced by ``model_dump`` on a response
            object.  Modified in-place.
        configured_mcp_labels: Set of ``server_label`` values that identify
            server-deployed MCP servers.
        original_request: Original request object
    """
    if original_request.instructions is None:
        response_dict["instructions"] = SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER
    # else: leave instructions as-is (echo back client's value)

    if tools := response_dict.get("tools"):
        response_dict["tools"] = [
            tool
            for tool in tools
            if tool.get("server_label") not in configured_mcp_labels
        ]

    if output := response_dict.get("output"):
        response_dict["output"] = [
            item
            for item in output
            if not _is_server_mcp_output_item(item, configured_mcp_labels)
        ]

    if original_request.model is None:
        model = response_dict.get("model")
        if model and "/" in model:
            response_dict["model"] = model.rsplit("/", 1)[-1]


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
    if chunk.type == "response.output_item.added":
        item_added_chunk = cast(OutputItemAddedChunk, chunk)
        item = item_added_chunk.item
        item_type = getattr(item, "type", None)
        if item_type in ("mcp_call", "mcp_list_tools", "mcp_approval_request"):
            server_label = getattr(item, "server_label", None)
            if server_label in configured_mcp_labels:
                server_mcp_output_indices.add(item_added_chunk.output_index)
                return True

    if chunk.type and (
        chunk.type.startswith("response.mcp_call.")
        or chunk.type.startswith("response.mcp_list_tools.")
        or chunk.type.startswith("response.mcp_approval_request.")
    ):
        output_index = getattr(chunk, "output_index", None)
        if output_index in server_mcp_output_indices:
            return True

    if chunk.type == "response.output_item.done":
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
    api_params: ResponsesApiParams,
    context: ResponsesContext,
    turn_summary: TurnSummary,
) -> None:
    """Populate turn summary with metadata extracted from the final response object.

    Args:
        response_object: The completed response object from Llama Stack
        api_params: ResponsesApiParams
        context: Responses context
        turn_summary: TurnSummary to populate
    """
    turn_summary.id = response_object.id
    vector_store_ids = extract_vector_store_ids_from_tools(api_params.tools)
    tool_rag_docs = parse_referenced_documents(
        response_object, vector_store_ids, configuration.rag_id_mapping
    )
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        context.inline_rag_context.referenced_documents + tool_rag_docs
    )
    for item in response_object.output:
        if context.filter_server_tools and not is_server_deployed_output(item):
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
    turn_summary.rag_chunks = context.inline_rag_context.rag_chunks + tool_rag_chunks


async def response_generator(
    stream: AsyncIterator[OpenAIResponseObjectStream],
    original_request: ResponsesRequest,
    api_params: ResponsesApiParams,
    context: ResponsesContext,
    turn_summary: TurnSummary,
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response with LCORE-enriched events.

    Args:
        stream: The streaming response from Llama Stack
        original_request: Original request (read-only)
        api_params: ResponsesApiParams
        context: Responses context
        turn_summary: TurnSummary to populate during streaming
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    logger.debug("Starting streaming response (Responses API) processing")

    latest_response_object: Optional[OpenAIResponseObject] = None
    sequence_number = 0
    configured_mcp_labels = {s.name for s in configuration.mcp_servers}
    # Track output indices of server-deployed MCP calls to filter their events
    server_mcp_output_indices: set[int] = set()

    async for chunk in stream:
        logger.debug("Processing streaming chunk, type: %s", chunk.type)

        # Filter out streaming events for server-deployed MCP tools.
        # These are handled internally by LCS and should not be forwarded
        # to clients that don't understand the mcp_call item type.
        if _should_filter_mcp_chunk(
            chunk, configured_mcp_labels, server_mcp_output_indices
        ):
            continue

        chunk_dict = chunk.model_dump(exclude_none=True, by_alias=True)

        # Create own sequence number for chunks to maintain order
        chunk_dict["sequence_number"] = sequence_number
        sequence_number += 1

        if "response" in chunk_dict:
            chunk_dict["response"]["conversation"] = normalize_conversation_id(
                api_params.conversation
            )
            _sanitize_response_dict(
                chunk_dict["response"],
                configured_mcp_labels,
                original_request,
            )
            tools = chunk_dict["response"].get("tools")
            if tools is not None:
                chunk_dict["response"]["tools"] = (
                    translate_vector_store_ids_to_user_facing(
                        tools,
                        configuration.rag_id_mapping,
                    )
                )
        # Intermediate response - no quota consumption and text yet
        if chunk.type == "response.in_progress":
            chunk_dict["response"]["available_quotas"] = {}
            chunk_dict["response"]["output_text"] = ""

        # Handle completion, incomplete, and failed events - only quota handling here
        if chunk.type in (
            "response.completed",
            "response.incomplete",
            "response.failed",
        ):
            latest_response_object = cast(
                OpenAIResponseObject, cast(Any, chunk).response
            )

            # Extract and consume tokens if any were used
            turn_summary.token_usage = extract_token_usage(
                latest_response_object.usage, api_params.model, context.endpoint_path
            )
            consume_query_tokens(
                user_id=context.auth[0],
                model_id=api_params.model,
                token_usage=turn_summary.token_usage,
            )

            # Get available quotas after token consumption
            chunk_dict["response"]["available_quotas"] = get_available_quotas(
                quota_limiters=configuration.quota_limiters, user_id=context.auth[0]
            )
            turn_summary.llm_response = extract_text_from_response_items(
                latest_response_object.output
            )
            chunk_dict["response"]["output_text"] = turn_summary.llm_response

        yield f"event: {chunk.type or 'error'}\ndata: {json.dumps(chunk_dict)}\n\n"

    # Extract response metadata from final response object
    if latest_response_object:
        _populate_turn_summary(
            latest_response_object,
            api_params,
            context,
            turn_summary,
        )

    # Explicitly append the turn to conversation if context passed by previous response
    if api_params.store and api_params.previous_response_id and latest_response_object:
        await append_turn_items_to_conversation(
            context.client,
            api_params.conversation,
            api_params.input,
            latest_response_object.output,
        )

    yield "data: [DONE]\n\n"


async def generate_response(
    generator: AsyncIterator[str],
    api_params: ResponsesApiParams,
    context: ResponsesContext,
    turn_summary: TurnSummary,
) -> AsyncIterator[str]:
    """Stream the response from the generator and persist conversation details.

    After streaming completes, conversation details are persisted.

    Args:
        generator: The SSE event generator
        turn_summary: TurnSummary populated during streaming
        api_params: ResponsesApiParams
        context: Responses context
        turn_summary: TurnSummary to populate during streaming
    Yields:
        SSE-formatted strings from the generator
    """
    user_id, _, skip_userid_check, _ = context.auth
    async for event in generator:
        yield event

    # Get topic summary for new conversation
    topic_summary = None
    if context.generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(
            context.input_text, context.client, api_params.model
        )

    completed_at = datetime.now(UTC)
    if api_params.store:
        store_query_results(
            user_id=user_id,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            started_at=context.started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at=completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            summary=turn_summary,
            query=context.input_text,
            attachments=[],
            skip_userid_check=skip_userid_check,
            topic_summary=topic_summary,
        )
    if context.moderation_result.decision == "passed":
        _queue_responses_splunk_event(
            background_tasks=context.background_tasks,
            input_text=context.input_text,
            response_text=turn_summary.llm_response,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=context.rh_identity_context,
            inference_time=(completed_at - context.started_at).total_seconds(),
            sourcetype="responses_completed",
            input_tokens=turn_summary.token_usage.input_tokens,
            output_tokens=turn_summary.token_usage.output_tokens,
        )


async def handle_non_streaming_response(
    original_request: ResponsesRequest,
    api_params: ResponsesApiParams,
    context: ResponsesContext,
) -> ResponsesResponse:
    """Handle non-streaming response from Responses API.

    Args:
        original_request: Original request (read-only)
        api_params: API parameters
        context: Responses context
    Returns:
        ResponsesResponse with the completed response
    """
    user_id, _, skip_userid_check, _ = context.auth

    # Fork: Get response object (blocked vs normal)
    if context.moderation_result.decision == "blocked":
        output_text = context.moderation_result.message
        api_response = OpenAIResponseObject.model_construct(
            id=context.moderation_result.moderation_id,
            created_at=int(context.started_at.timestamp()),
            status="completed",
            output=[context.moderation_result.refusal_response],
            usage=get_zero_usage(),
            **api_params.echoed_params(configuration.rag_id_mapping),
        )
        if api_params.store:
            await append_turn_items_to_conversation(
                client=context.client,
                conversation_id=api_params.conversation,
                user_input=api_params.input,
                llm_output=[context.moderation_result.refusal_response],
            )
        _queue_responses_splunk_event(
            background_tasks=context.background_tasks,
            input_text=context.input_text,
            response_text=output_text,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=context.rh_identity_context,
            inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
            sourcetype="responses_shield_blocked",
            user_agent=context.user_agent,
        )
    else:
        try:
            api_response = cast(
                OpenAIResponseObject,
                await context.client.responses.create(
                    **api_params.model_dump(exclude_none=True)
                ),
            )
            token_usage = extract_token_usage(
                api_response.usage, api_params.model, context.endpoint_path
            )
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
                    context.client,
                    api_params.conversation,
                    api_params.input,
                    api_response.output,
                )

        except RuntimeError as e:
            if is_context_length_error(str(e)):
                _queue_responses_splunk_event(
                    background_tasks=context.background_tasks,
                    input_text=context.input_text,
                    response_text=str(e),
                    conversation_id=normalize_conversation_id(api_params.conversation),
                    model=api_params.model,
                    rh_identity_context=context.rh_identity_context,
                    inference_time=(
                        datetime.now(UTC) - context.started_at
                    ).total_seconds(),
                    sourcetype="responses_error",
                    fire_and_forget=True,
                    user_agent=context.user_agent,
                )
                error_response = PromptTooLongResponse(model=api_params.model)
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            _queue_responses_splunk_event(
                background_tasks=context.background_tasks,
                input_text=context.input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=context.rh_identity_context,
                inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=context.user_agent,
            )
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            _queue_responses_splunk_event(
                background_tasks=context.background_tasks,
                input_text=context.input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=context.rh_identity_context,
                inference_time=(datetime.now(UTC) - context.started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=context.user_agent,
            )
            error_response = handle_known_apistatus_errors(e, api_params.model)
            raise HTTPException(**error_response.model_dump()) from e

    # Get available quotas
    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=user_id
    )
    # Get topic summary for new conversation
    topic_summary = None
    if context.generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(
            context.input_text, context.client, api_params.model
        )

    vector_store_ids = extract_vector_store_ids_from_tools(api_params.tools)
    turn_summary = build_turn_summary(
        api_response,
        api_params.model,
        context.endpoint_path,
        vector_store_ids,
        configuration.rag_id_mapping,
        filter_server_tools=context.filter_server_tools,
    )
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        context.inline_rag_context.referenced_documents
        + turn_summary.referenced_documents
    )
    turn_summary.rag_chunks.extend(context.inline_rag_context.rag_chunks)
    completed_at = datetime.now(UTC)
    if context.moderation_result.decision == "passed":
        _queue_responses_splunk_event(
            background_tasks=context.background_tasks,
            input_text=context.input_text,
            response_text=output_text,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=context.rh_identity_context,
            inference_time=(completed_at - context.started_at).total_seconds(),
            sourcetype="responses_completed",
            input_tokens=turn_summary.token_usage.input_tokens,
            output_tokens=turn_summary.token_usage.output_tokens,
        )
    if api_params.store:
        store_query_results(
            user_id=user_id,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            started_at=context.started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at=completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            summary=turn_summary,
            query=context.input_text,
            attachments=[],
            skip_userid_check=skip_userid_check,
            topic_summary=topic_summary,
        )
    configured_mcp_labels = {s.name for s in configuration.mcp_servers}
    response_dict = api_response.model_dump(exclude_none=True)
    _sanitize_response_dict(
        response_dict,
        configured_mcp_labels,
        original_request,
    )
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
