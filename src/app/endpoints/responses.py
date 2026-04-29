# pylint: disable=too-many-locals,too-many-branches,too-many-nested-blocks,too-many-arguments,too-many-positional-arguments,too-many-lines,too-many-statements

"""Handler for REST API call to provide answer using Responses API (LCORE specification)."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
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
from constants import SUBSTITUTED_INSTRUCTIONS_PLACEHOLDER
from log import get_logger
from metrics import recording
from models.config import Action
from models.requests import ResponsesRequest
from models.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES_WITH_MCP_OAUTH,
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
    RAGContext,
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

_USER_AGENT_MAX_LENGTH: Final[int] = 128


@dataclass
class StreamChunkProcessingResult:
    """Result of preparing one Responses API stream chunk for SSE output."""

    event: Optional[str]
    sequence_number: int
    latest_response_object: Optional[OpenAIResponseObject] = None
    inference_metric_recorded: bool = False


def _record_response_inference_result(
    model_id: str,
    endpoint_path: str,
    result: str,
    duration: float,
    record_failure: bool = False,
) -> None:
    """Record backend inference metrics for a Responses API call.

    Args:
        model_id: Model identifier in provider/model format.
        endpoint_path: API endpoint path for metric labeling.
        result: Bounded result label for the inference duration metric.
        duration: Backend inference call duration in seconds.
        record_failure: Whether to increment the LLM failure counter as well.
    """
    provider, model = extract_provider_and_model_from_model_id(model_id)
    if record_failure:
        recording.record_llm_failure(provider, model, endpoint_path)
    recording.record_llm_inference_duration(
        provider, model, endpoint_path, result, duration
    )


def _check_response_quota(user_id: str, endpoint_path: str) -> None:
    """Check response quota availability and record bounded quota metrics."""
    quota_start_time = time.monotonic()
    try:
        check_tokens_available(configuration.quota_limiters, user_id)
    except HTTPException:
        recording.record_quota_check(
            endpoint_path,
            "user_id",
            "failure",
            time.monotonic() - quota_start_time,
        )
        raise
    recording.record_quota_check(
        endpoint_path,
        "user_id",
        "success",
        time.monotonic() - quota_start_time,
    )


def _record_stream_terminal_inference_result(
    event_type: Optional[str],
    api_params: ResponsesApiParams,
    endpoint_path: str,
    inference_start_time: Optional[float],
) -> None:
    """Record inference metrics after a terminal streaming response event."""
    if inference_start_time is None:
        return
    inference_result = "success" if event_type == "response.completed" else "failure"
    _record_response_inference_result(
        api_params.model,
        endpoint_path,
        inference_result,
        time.monotonic() - inference_start_time,
        record_failure=(inference_result == "failure"),
    )


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

    endpoint_path = "/v1/responses"

    _check_response_quota(user_id, endpoint_path)

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

    response_handler = (
        handle_streaming_response
        if original_request.stream
        else handle_non_streaming_response
    )
    return await response_handler(
        client=client,
        original_request=original_request,
        updated_request=updated_request,
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
    )


async def handle_streaming_response(
    client: AsyncLlamaStackClient,
    original_request: ResponsesRequest,
    updated_request: ResponsesRequest,
    auth: AuthTuple,
    input_text: str,
    started_at: datetime,
    moderation_result: ShieldModerationResult,
    inline_rag_context: RAGContext,
    filter_server_tools: bool = False,
    background_tasks: Optional[BackgroundTasks] = None,
    rh_identity_context: tuple[str, str] = ("", ""),
    user_agent: Optional[str] = None,
    endpoint_path: str = "",
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
        background_tasks: FastAPI background task manager for telemetry events
        rh_identity_context: Tuple of (org_id, system_id) from RH identity
        user_agent: Sanitized User-Agent string from request headers, or None.
    Returns:
        StreamingResponse with SSE-formatted events
    """
    api_params = ResponsesApiParams.model_validate(updated_request.model_dump())
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
            updated_request.echoed_params(),
            started_at,
            available_quotas,
        )
        if api_params.store:
            await append_turn_items_to_conversation(
                client=client,
                conversation_id=api_params.conversation,
                user_input=updated_request.input,
                llm_output=[moderation_result.refusal_response],
            )
        _queue_responses_splunk_event(
            background_tasks=background_tasks,
            input_text=input_text,
            response_text=moderation_result.message,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=rh_identity_context,
            inference_time=(datetime.now(UTC) - started_at).total_seconds(),
            sourcetype="responses_shield_blocked",
            user_agent=user_agent,
        )
    else:
        inference_start_time = time.monotonic()
        try:
            response = await client.responses.create(
                **api_params.model_dump(exclude_none=True)
            )
            generator = response_generator(
                stream=cast(AsyncIterator[OpenAIResponseObjectStream], response),
                original_request=original_request,
                updated_request=updated_request,
                api_params=api_params,
                user_id=auth[0],
                turn_summary=turn_summary,
                inline_rag_context=inline_rag_context,
                filter_server_tools=filter_server_tools,
                endpoint_path=endpoint_path,
                inference_start_time=inference_start_time,
            )
        except RuntimeError as e:  # library mode wraps 413 into runtime error
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "failure",
                time.monotonic() - inference_start_time,
                record_failure=True,
            )
            if is_context_length_error(str(e)):
                _queue_responses_splunk_event(
                    background_tasks=background_tasks,
                    input_text=input_text,
                    response_text=str(e),
                    conversation_id=normalize_conversation_id(api_params.conversation),
                    model=api_params.model,
                    rh_identity_context=rh_identity_context,
                    inference_time=(datetime.now(UTC) - started_at).total_seconds(),
                    sourcetype="responses_error",
                    fire_and_forget=True,
                    user_agent=user_agent,
                )
                error_response = PromptTooLongResponse(model=api_params.model)
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "failure",
                time.monotonic() - inference_start_time,
                record_failure=True,
            )
            _queue_responses_splunk_event(
                background_tasks=background_tasks,
                input_text=input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=rh_identity_context,
                inference_time=(datetime.now(UTC) - started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=user_agent,
            )
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "failure",
                time.monotonic() - inference_start_time,
                record_failure=True,
            )
            _queue_responses_splunk_event(
                background_tasks=background_tasks,
                input_text=input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=rh_identity_context,
                inference_time=(datetime.now(UTC) - started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=user_agent,
            )
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
            generate_topic_summary=updated_request.generate_topic_summary or False,
            background_tasks=background_tasks,
            rh_identity_context=rh_identity_context,
            shield_blocked=(moderation_result.decision == "blocked"),
            user_agent=user_agent,
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


def _process_stream_chunk(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    chunk: OpenAIResponseObjectStream,
    original_request: ResponsesRequest,
    api_params: ResponsesApiParams,
    user_id: str,
    turn_summary: TurnSummary,
    configured_mcp_labels: set[str],
    server_mcp_output_indices: set[int],
    sequence_number: int,
    endpoint_path: str,
    inference_start_time: Optional[float],
    normalized_conv_id: str,
) -> StreamChunkProcessingResult:
    """Prepare one streaming chunk for SSE output and terminal accounting."""
    event_type = getattr(chunk, "type", None)
    logger.debug("Processing streaming chunk, type: %s", event_type)

    if _should_filter_mcp_chunk(
        chunk, event_type, configured_mcp_labels, server_mcp_output_indices
    ):
        return StreamChunkProcessingResult(event=None, sequence_number=sequence_number)

    chunk_dict = chunk.model_dump(exclude_none=True, by_alias=True)
    chunk_dict["sequence_number"] = sequence_number
    sequence_number += 1

    if "response" in chunk_dict:
        chunk_dict["response"]["conversation"] = normalized_conv_id
        _sanitize_response_dict(
            chunk_dict["response"], configured_mcp_labels, original_request
        )
        tools = chunk_dict["response"].get("tools")
        if tools is not None:
            chunk_dict["response"]["tools"] = translate_vector_store_ids_to_user_facing(
                tools,
                configuration.rag_id_mapping,
            )

    if event_type == "response.in_progress":
        chunk_dict["response"]["available_quotas"] = {}
        chunk_dict["response"]["output_text"] = ""

    latest_response_object = None
    inference_metric_recorded = False
    if event_type in ("response.completed", "response.incomplete", "response.failed"):
        latest_response_object = _process_terminal_stream_chunk(
            chunk,
            chunk_dict,
            api_params,
            user_id,
            turn_summary,
            endpoint_path,
            inference_start_time,
        )
        inference_metric_recorded = True

    return StreamChunkProcessingResult(
        event=f"event: {event_type or 'error'}\ndata: {json.dumps(chunk_dict)}\n\n",
        sequence_number=sequence_number,
        latest_response_object=latest_response_object,
        inference_metric_recorded=inference_metric_recorded,
    )


def _process_terminal_stream_chunk(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    chunk: OpenAIResponseObjectStream,
    chunk_dict: dict[str, Any],
    api_params: ResponsesApiParams,
    user_id: str,
    turn_summary: TurnSummary,
    endpoint_path: str,
    inference_start_time: Optional[float],
) -> OpenAIResponseObject:
    """Handle token, quota, output, and inference metrics for terminal chunks."""
    latest_response_object = cast(OpenAIResponseObject, cast(Any, chunk).response)
    turn_summary.token_usage = extract_token_usage(
        latest_response_object.usage, api_params.model, endpoint_path
    )
    consume_query_tokens(
        user_id=user_id,
        model_id=api_params.model,
        token_usage=turn_summary.token_usage,
    )
    chunk_dict["response"]["available_quotas"] = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=user_id
    )
    turn_summary.llm_response = extract_text_from_response_items(
        latest_response_object.output
    )
    chunk_dict["response"]["output_text"] = turn_summary.llm_response
    _record_stream_terminal_inference_result(
        getattr(chunk, "type", None), api_params, endpoint_path, inference_start_time
    )
    return latest_response_object


async def response_generator(
    stream: AsyncIterator[OpenAIResponseObjectStream],
    original_request: ResponsesRequest,
    updated_request: ResponsesRequest,
    api_params: ResponsesApiParams,
    user_id: str,
    turn_summary: TurnSummary,
    inline_rag_context: RAGContext,
    filter_server_tools: bool = False,
    endpoint_path: str = "",
    inference_start_time: Optional[float] = None,
) -> AsyncIterator[str]:
    """Generate SSE-formatted streaming response with LCORE-enriched events.

    Args:
        stream: The streaming response from Llama Stack
        original_request: Original request object
        updated_request: Updated request object
        api_params: ResponsesApiParams
        user_id: User ID for quota retrieval
        turn_summary: TurnSummary to populate during streaming
        inline_rag_context: Inline RAG context to be used for the response
        filter_server_tools: Whether to filter server-deployed MCP tool events from the stream
        endpoint_path: API endpoint path used for metric labeling.
        inference_start_time: Monotonic clock time when the backend stream was requested.
    Yields:
        SSE-formatted strings for streaming events, ending with [DONE]
    """
    normalized_conv_id = normalize_conversation_id(api_params.conversation)

    logger.debug("Starting streaming response (Responses API) processing")

    latest_response_object: Optional[OpenAIResponseObject] = None
    sequence_number = 0
    configured_mcp_labels = {s.name for s in configuration.mcp_servers}
    # Track output indices of server-deployed MCP calls to filter their events
    server_mcp_output_indices: set[int] = set()
    inference_metric_recorded = False

    try:
        async for chunk in stream:
            result = _process_stream_chunk(
                chunk,
                original_request,
                api_params,
                user_id,
                turn_summary,
                configured_mcp_labels,
                server_mcp_output_indices,
                sequence_number,
                endpoint_path,
                inference_start_time,
                normalized_conv_id,
            )
            sequence_number = result.sequence_number
            if result.event is None:
                continue
            if result.latest_response_object is not None:
                latest_response_object = result.latest_response_object
            inference_metric_recorded = (
                inference_metric_recorded or result.inference_metric_recorded
            )
            yield result.event
    except (RuntimeError, APIConnectionError, LLSApiStatusError, OpenAIAPIStatusError):
        if not inference_metric_recorded and inference_start_time is not None:
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "failure",
                time.monotonic() - inference_start_time,
                record_failure=True,
            )
        raise

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
            client,
            api_params.conversation,
            updated_request.input,
            latest_response_object.output,
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
    background_tasks: Optional[BackgroundTasks] = None,
    rh_identity_context: tuple[str, str] = ("", ""),
    shield_blocked: bool = False,
    user_agent: Optional[str] = None,
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
        background_tasks: FastAPI background task manager for telemetry events
        rh_identity_context: Tuple of (org_id, system_id) from RH identity
        shield_blocked: Whether the request was blocked by a shield
        user_agent: Sanitized User-Agent string from request headers, or None.
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
    if not shield_blocked:
        _queue_responses_splunk_event(
            background_tasks=background_tasks,
            input_text=input_text,
            response_text=turn_summary.llm_response,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=rh_identity_context,
            inference_time=(completed_at - started_at).total_seconds(),
            sourcetype="responses_completed",
            input_tokens=(
                turn_summary.token_usage.input_tokens if turn_summary.token_usage else 0
            ),
            output_tokens=(
                turn_summary.token_usage.output_tokens
                if turn_summary.token_usage
                else 0
            ),
            user_agent=user_agent,
        )


async def handle_non_streaming_response(
    client: AsyncLlamaStackClient,
    original_request: ResponsesRequest,
    updated_request: ResponsesRequest,
    auth: AuthTuple,
    input_text: str,
    started_at: datetime,
    moderation_result: ShieldModerationResult,
    inline_rag_context: RAGContext,
    filter_server_tools: bool = False,
    background_tasks: Optional[BackgroundTasks] = None,
    rh_identity_context: tuple[str, str] = ("", ""),
    user_agent: Optional[str] = None,
    endpoint_path: str = "",
) -> ResponsesResponse:
    """Handle non-streaming response from Responses API.

    Args:
        client: The AsyncLlamaStackClient instance
        original_request: Original request object
        updated_request: Updated request object
        auth: Authentication tuple
        input_text: The extracted input text
        started_at: Timestamp when the conversation started
        moderation_result: Result of shield moderation check
        inline_rag_context: Inline RAG context to be used for the response
        filter_server_tools: Whether to filter server-deployed MCP tool output
        background_tasks: FastAPI background task manager for telemetry events
        rh_identity_context: Tuple of (org_id, system_id) from RH identity
        user_agent: Sanitized User-Agent string from request headers, or None.
    Returns:
        ResponsesResponse with the completed response
    """
    user_id, _, skip_userid_check, _ = auth
    api_params = ResponsesApiParams.model_validate(updated_request.model_dump())

    # Fork: Get response object (blocked vs normal)
    if moderation_result.decision == "blocked":
        output_text = moderation_result.message
        api_response = OpenAIResponseObject.model_construct(
            id=moderation_result.moderation_id,
            created_at=int(started_at.timestamp()),
            status="completed",
            output=[moderation_result.refusal_response],
            usage=get_zero_usage(),
            **updated_request.echoed_params(),
        )
        if api_params.store:
            await append_turn_items_to_conversation(
                client=client,
                conversation_id=api_params.conversation,
                user_input=updated_request.input,
                llm_output=[moderation_result.refusal_response],
            )
        _queue_responses_splunk_event(
            background_tasks=background_tasks,
            input_text=input_text,
            response_text=output_text,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=rh_identity_context,
            inference_time=(datetime.now(UTC) - started_at).total_seconds(),
            sourcetype="responses_shield_blocked",
            user_agent=user_agent,
        )
    else:
        inference_start_time = time.monotonic()
        try:
            api_response = cast(
                OpenAIResponseObject,
                await client.responses.create(
                    **api_params.model_dump(exclude_none=True)
                ),
            )
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "success",
                time.monotonic() - inference_start_time,
            )
            token_usage = extract_token_usage(
                api_response.usage, api_params.model, endpoint_path
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
                    client,
                    api_params.conversation,
                    updated_request.input,
                    api_response.output,
                )

        except RuntimeError as e:
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "failure",
                time.monotonic() - inference_start_time,
                record_failure=True,
            )
            if is_context_length_error(str(e)):
                _queue_responses_splunk_event(
                    background_tasks=background_tasks,
                    input_text=input_text,
                    response_text=str(e),
                    conversation_id=normalize_conversation_id(api_params.conversation),
                    model=api_params.model,
                    rh_identity_context=rh_identity_context,
                    inference_time=(datetime.now(UTC) - started_at).total_seconds(),
                    sourcetype="responses_error",
                    fire_and_forget=True,
                    user_agent=user_agent,
                )
                error_response = PromptTooLongResponse(model=api_params.model)
                raise HTTPException(**error_response.model_dump()) from e
            raise e
        except APIConnectionError as e:
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "failure",
                time.monotonic() - inference_start_time,
                record_failure=True,
            )
            _queue_responses_splunk_event(
                background_tasks=background_tasks,
                input_text=input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=rh_identity_context,
                inference_time=(datetime.now(UTC) - started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=user_agent,
            )
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            _record_response_inference_result(
                api_params.model,
                endpoint_path,
                "failure",
                time.monotonic() - inference_start_time,
                record_failure=True,
            )
            _queue_responses_splunk_event(
                background_tasks=background_tasks,
                input_text=input_text,
                response_text=str(e),
                conversation_id=normalize_conversation_id(api_params.conversation),
                model=api_params.model,
                rh_identity_context=rh_identity_context,
                inference_time=(datetime.now(UTC) - started_at).total_seconds(),
                sourcetype="responses_error",
                fire_and_forget=True,
                user_agent=user_agent,
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
    if updated_request.generate_topic_summary:
        logger.debug("Generating topic summary for new conversation")
        topic_summary = await get_topic_summary(input_text, client, api_params.model)

    vector_store_ids = extract_vector_store_ids_from_tools(api_params.tools)
    turn_summary = build_turn_summary(
        api_response,
        api_params.model,
        endpoint_path,
        vector_store_ids,
        configuration.rag_id_mapping,
        filter_server_tools=filter_server_tools,
    )
    turn_summary.referenced_documents = deduplicate_referenced_documents(
        inline_rag_context.referenced_documents + turn_summary.referenced_documents
    )
    turn_summary.rag_chunks.extend(inline_rag_context.rag_chunks)
    completed_at = datetime.now(UTC)
    if moderation_result.decision != "blocked":
        _queue_responses_splunk_event(
            background_tasks=background_tasks,
            input_text=input_text,
            response_text=output_text,
            conversation_id=normalize_conversation_id(api_params.conversation),
            model=api_params.model,
            rh_identity_context=rh_identity_context,
            inference_time=(completed_at - started_at).total_seconds(),
            sourcetype="responses_completed",
            input_tokens=(
                turn_summary.token_usage.input_tokens if turn_summary.token_usage else 0
            ),
            output_tokens=(
                turn_summary.token_usage.output_tokens
                if turn_summary.token_usage
                else 0
            ),
            user_agent=user_agent,
        )
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
