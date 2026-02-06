"""Handler for REST API call to provide answer to streaming query."""  # pylint: disable=too-many-lines,too-many-locals,W0511

import ast
import json
import logging
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import (
    Any,
    Iterator,
    Optional,
)

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from llama_stack_client import (
    APIConnectionError,
    RateLimitError,  # type: ignore
)
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem
from openai._exceptions import APIStatusError

import metrics
from app.endpoints.query import (
    evaluate_model_hints,
    select_model_and_provider_id,
    validate_conversation_ownership,
)
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import DEFAULT_RAG_TOOL, MEDIA_TYPE_JSON, MEDIA_TYPE_TEXT
from models.context import ResponseGeneratorContext
from models.database.conversations import UserConversation
from models.requests import QueryRequest
from models.responses import (
    AbstractErrorResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    StreamingQueryResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from utils.endpoints import (
    ReferencedDocument,
    check_configuration_loaded,
    validate_model_provider_override,
)
from utils.token_counter import TokenCounter
from utils.types import content_to_str

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query"])

streaming_query_responses: dict[int | str, dict[str, Any]] = {
    200: StreamingQueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["conversation read", "endpoint", "model override"]
    ),
    404: NotFoundResponse.openapi_response(
        examples=["conversation", "model", "provider"]
    ),
    413: PromptTooLongResponse.openapi_response(),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


METADATA_PATTERN = re.compile(r"\nMetadata: (\{.+})\n")

# OLS-compatible event types
LLM_TOKEN_EVENT = "token"
LLM_TOOL_CALL_EVENT = "tool_call"
LLM_TOOL_RESULT_EVENT = "tool_result"
LLM_VALIDATION_EVENT = "validation"


def format_stream_data(d: dict) -> str:
    """
    Format a dictionary as a Server-Sent Events (SSE) data string.

    Parameters:
        d (dict): The data to be formatted as an SSE event.

    Returns:
        str: The formatted SSE data string.
    """
    data = json.dumps(d)
    return f"data: {data}\n\n"


def stream_start_event(conversation_id: str) -> str:
    """
    Yield the start of the data stream.

    Format a Server-Sent Events (SSE) start event containing the
    conversation ID.

    Parameters:
        conversation_id (str): Unique identifier for the
        conversation.

    Returns:
        str: SSE-formatted string representing the start event.
    """
    return format_stream_data(
        {
            "event": "start",
            "data": {
                "conversation_id": conversation_id,
            },
        }
    )


def stream_end_event(
    metadata_map: dict,
    token_usage: TokenCounter,
    available_quotas: dict[str, int],
    referenced_documents: list[ReferencedDocument],
    media_type: str = MEDIA_TYPE_JSON,
) -> str:
    """
    Yield the end of the data stream.

    Format and return the end event for a streaming response,
    including referenced document metadata and token usage information.

    Parameters:
        metadata_map (dict): A mapping containing metadata about
        referenced documents.
        summary (TurnSummary): Summary of the conversation turn.
        token_usage (TokenCounter): Token usage information.
        media_type (str): The media type for the response format.

    Returns:
        str: A Server-Sent Events (SSE) formatted string
        representing the end of the data stream.
    """
    if media_type == MEDIA_TYPE_TEXT:
        ref_docs_string = "\n".join(
            f'{v["title"]}: {v["docs_url"]}'
            for v in filter(
                lambda v: ("docs_url" in v) and ("title" in v),
                metadata_map.values(),
            )
        )
        return f"\n\n---\n\n{ref_docs_string}" if ref_docs_string else ""

    # Convert ReferencedDocument objects to dicts for JSON serialization
    # Use mode="json" to ensure AnyUrl is serialized to string (not just model_dump())
    referenced_docs_dict = [doc.model_dump(mode="json") for doc in referenced_documents]

    return format_stream_data(
        {
            "event": "end",
            "data": {
                "referenced_documents": referenced_docs_dict,
                "truncated": None,  # TODO(jboos): implement truncated
                "input_tokens": token_usage.input_tokens,
                "output_tokens": token_usage.output_tokens,
            },
            "available_quotas": available_quotas,
        }
    )


def stream_event(data: dict, event_type: str, media_type: str) -> str:
    """Build an item to yield based on media type.

    Args:
        data: The data to yield.
        event_type: The type of event (e.g. token, tool request, tool execution).
        media_type: Media type of the response (e.g. text or JSON).

    Returns:
        str: The formatted string or JSON to yield.
    """
    if media_type == MEDIA_TYPE_TEXT:
        if event_type == LLM_TOKEN_EVENT:
            return data["token"]
        if event_type == LLM_TOOL_CALL_EVENT:
            return f"\nTool call: {json.dumps(data)}\n"
        if event_type == LLM_TOOL_RESULT_EVENT:
            return f"\nTool result: {json.dumps(data)}\n"
        logger.error("Unknown event type: %s", event_type)
        return ""
    return format_stream_data(
        {
            "event": event_type,
            "data": data,
        }
    )


# -----------------------------------
# Error handling
# -----------------------------------
def _handle_error_event(
    chunk: Any, chunk_id: int, media_type: str = MEDIA_TYPE_JSON
) -> Iterator[str]:
    """
    Yield error event.

    Yield a formatted Server-Sent Events (SSE) error event
    containing the error message from a streaming chunk.

    Parameters:
        chunk_id (int): The unique identifier for the current
        streaming chunk.
        media_type (str): The media type for the response format.
    """
    if media_type == MEDIA_TYPE_TEXT:
        yield f"Error: {chunk.error['message']}"
    else:
        yield format_stream_data(
            {
                "event": "error",
                "data": {
                    "id": chunk_id,
                    "token": chunk.error["message"],
                },
            }
        )


def prompt_too_long_error(error: Exception, media_type: str) -> str:
    """Return error representation for long prompts.

    Args:
        error: The exception raised for long prompts.
        media_type: Media type of the response (e.g. text or JSON).

    Returns:
        str: The error message formatted for the media type.
    """
    logger.error("Prompt is too long: %s", error)
    if media_type == MEDIA_TYPE_TEXT:
        return f"Prompt is too long: {error}"
    return format_stream_data(
        {
            "event": "error",
            "data": {
                "status_code": 413,
                "response": "Prompt is too long",
                "cause": str(error),
            },
        }
    )


def generic_llm_error(error: Exception, media_type: str) -> str:
    """Return error representation for generic LLM errors.

    Args:
        error: The exception raised during processing.
        media_type: Media type of the response (e.g. text or JSON).

    Returns:
        str: The error message formatted for the media type.
    """
    logger.error("Error while obtaining answer for user question")
    logger.exception(error)

    if media_type == MEDIA_TYPE_TEXT:
        return f"Error: {str(error)}"
    return format_stream_data(
        {
            "event": "error",
            "data": {
                "response": "Internal server error",
                "cause": str(error),
            },
        }
    )


def stream_http_error(error: AbstractErrorResponse) -> Iterator[str]:
    """
    Yield an SSE-formatted error response for generic LLM or API errors.

    Args:
        error: An AbstractErrorResponse instance representing the error.

    Yields:
        str: A Server-Sent Events (SSE) formatted error message containing
            the serialized error details.
    """
    logger.error("Error while obtaining answer for user question")
    logger.exception(error)

    yield format_stream_data({"event": "error", "data": {**error.detail.model_dump()}})


# -----------------------------------
# Turn handling
# -----------------------------------
def _handle_turn_start_event(
    _chunk_id: int,
    media_type: str = MEDIA_TYPE_JSON,
    conversation_id: Optional[str] = None,
) -> Iterator[str]:
    """
    Yield turn start event.

    Yield a Server-Sent Event (SSE) start event indicating the
    start of a new conversation turn.

    Parameters:
        chunk_id (int): The unique identifier for the current
        chunk.

    Yields:
        str: SSE-formatted start event with conversation_id.
    """
    # Use provided conversation_id or generate one if not available
    if conversation_id is None:
        conversation_id = str(uuid.uuid4())

    if media_type == MEDIA_TYPE_TEXT:
        yield (
            f"data: {json.dumps({'event': 'start', 'data': {'conversation_id': conversation_id}})}\n\n"  # pylint: disable=line-too-long
        )
    else:
        yield format_stream_data(
            {
                "event": "start",
                "data": {"conversation_id": conversation_id},
            }
        )


def _handle_turn_complete_event(
    chunk: Any, _chunk_id: int, media_type: str = MEDIA_TYPE_JSON
) -> Iterator[str]:
    """
    Yield turn complete event.

    Yields a Server-Sent Event (SSE) indicating the completion of a
    conversation turn, including the full output message content.

    Parameters:
        chunk_id (int): The unique identifier for the current
        chunk.

    Yields:
        str: SSE-formatted string containing the turn completion
        event and output message content.
    """
    full_response = content_to_str(chunk.event.payload.turn.output_message.content)

    if media_type == MEDIA_TYPE_TEXT:
        yield (
            f"data: {json.dumps({'event': 'turn_complete', 'data': {'token': full_response}})}\n\n"
        )
    else:
        yield format_stream_data(
            {
                "event": "turn_complete",
                "data": {"token": full_response},
            }
        )


# -----------------------------------
# Shield handling
# -----------------------------------
def _handle_shield_event(
    chunk: Any, chunk_id: int, media_type: str = MEDIA_TYPE_JSON
) -> Iterator[str]:
    """
    Yield shield event.

    Processes a shield event chunk and yields a formatted SSE token
    event indicating shield validation results.

    Yields a "No Violation" token if no violation is detected, or a
    violation message if a shield violation occurs. Increments
    validation error metrics when violations are present.
    """
    if chunk.event.payload.event_type == "step_complete":
        violation = chunk.event.payload.step_details.violation
        if not violation:
            yield stream_event(
                data={
                    "id": chunk_id,
                    "token": "No Violation",
                },
                event_type=LLM_VALIDATION_EVENT,
                media_type=media_type,
            )
        else:
            # Metric for LLM validation errors
            metrics.llm_calls_validation_errors_total.inc()
            violation = (
                f"Violation: {violation.user_message} (Metadata: {violation.metadata})"
            )
            yield stream_event(
                data={
                    "id": chunk_id,
                    "token": violation,
                },
                event_type=LLM_VALIDATION_EVENT,
                media_type=media_type,
            )


# -----------------------------------
# Tool Execution handling
# -----------------------------------
# pylint: disable=R1702,R0912
def _handle_tool_execution_event(
    chunk: Any, chunk_id: int, metadata_map: dict, media_type: str = MEDIA_TYPE_JSON
) -> Iterator[str]:
    """
    Yield tool call event.

    Processes tool execution events from a streaming chunk and
    yields formatted Server-Sent Events (SSE) strings.

    Handles both tool call initiation and completion, including
    tool call arguments, responses, and summaries. Extracts and
    updates document metadata from knowledge search tool responses
    when present.

    Parameters:
        chunk_id (int): Unique identifier for the current streaming
        chunk.  metadata_map (dict): Dictionary to be updated with
        document metadata extracted from tool responses.

    Yields:
        str: SSE-formatted event strings representing tool call
        events and responses.
    """
    if chunk.event.payload.event_type == "step_start":
        yield stream_event(
            data={
                "id": chunk_id,
                "token": "",
            },
            event_type=LLM_TOOL_CALL_EVENT,
            media_type=media_type,
        )

    elif chunk.event.payload.event_type == "step_complete":
        for t in chunk.event.payload.step_details.tool_calls:
            yield stream_event(
                data={
                    "id": chunk_id,
                    "token": {
                        "tool_name": t.tool_name,
                        "arguments": t.arguments,
                    },
                },
                event_type=LLM_TOOL_CALL_EVENT,
                media_type=media_type,
            )

        for r in chunk.event.payload.step_details.tool_responses:
            if r.tool_name == "query_from_memory":
                inserted_context = content_to_str(r.content)
                yield stream_event(
                    data={
                        "id": chunk_id,
                        "token": {
                            "tool_name": r.tool_name,
                            "response": f"Fetched {len(inserted_context)} bytes from memory",
                        },
                    },
                    event_type=LLM_TOOL_RESULT_EVENT,
                    media_type=media_type,
                )

            elif r.tool_name == DEFAULT_RAG_TOOL and r.content:
                summary = ""
                for i, text_content_item in enumerate(r.content):
                    if isinstance(text_content_item, TextContentItem):
                        if i == 0:
                            summary = text_content_item.text
                            newline_pos = summary.find("\n")
                            if newline_pos > 0:
                                summary = summary[:newline_pos]
                        for match in METADATA_PATTERN.findall(text_content_item.text):
                            try:
                                meta = ast.literal_eval(match)
                                if "document_id" in meta:
                                    metadata_map[meta["document_id"]] = meta
                            except Exception:  # pylint: disable=broad-except
                                logger.debug(
                                    "An exception was thrown in processing %s",
                                    match,
                                )

                yield stream_event(
                    data={
                        "id": chunk_id,
                        "token": {
                            "tool_name": r.tool_name,
                            "summary": summary,
                        },
                    },
                    event_type=LLM_TOOL_RESULT_EVENT,
                    media_type=media_type,
                )

            else:
                yield stream_event(
                    data={
                        "id": chunk_id,
                        "token": {
                            "tool_name": r.tool_name,
                            "response": content_to_str(r.content),
                        },
                    },
                    event_type=LLM_TOOL_RESULT_EVENT,
                    media_type=media_type,
                )


# -----------------------------------
# Catch-all for everything else
# -----------------------------------
def _handle_heartbeat_event(
    chunk_id: int, media_type: str = MEDIA_TYPE_JSON
) -> Iterator[str]:
    """
    Yield a heartbeat event.

    Yield a heartbeat event as a Server-Sent Event (SSE) for the
    given chunk ID.

    Parameters:
        chunk_id (int): The identifier for the current streaming
        chunk.

    Yields:
        str: SSE-formatted heartbeat event string.
    """
    yield stream_event(
        data={
            "id": chunk_id,
            "token": "heartbeat",
        },
        event_type=LLM_TOKEN_EVENT,
        media_type=media_type,
    )


async def streaming_query_endpoint_handler_base(  # pylint: disable=too-many-locals,too-many-statements,too-many-arguments,too-many-positional-arguments
    request: Request,
    query_request: QueryRequest,
    auth: AuthTuple,
    mcp_headers: dict[str, dict[str, str]],
    retrieve_response_func: Callable[..., Any],
    create_response_generator_func: Callable[..., Any],
) -> StreamingResponse:
    """
    Handle streaming query endpoints with common logic.

    This base handler contains all the common logic for streaming query endpoints
    and accepts functions for API-specific behavior (Agent API vs Responses API).

    Args:
        request: The FastAPI request object
        query_request: The query request from the user
        auth: Authentication tuple (user_id, username, skip_check, token)
        mcp_headers: MCP headers for tool integrations
        retrieve_response_func: Function to retrieve the streaming response
        create_response_generator_func: Function factory that creates the response generator

    Returns:
        StreamingResponse: An HTTP streaming response yielding SSE-formatted events

    Raises:
        HTTPException: Returns HTTP 500 if unable to connect to Llama Stack
    """
    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(query_request, request.state.authorized_actions)

    # log Llama Stack configuration
    logger.info("Llama stack config: %s", configuration.llama_stack_configuration)

    user_id, _user_name, _skip_userid_check, token = auth

    user_conversation: Optional[UserConversation] = None
    if query_request.conversation_id:
        user_conversation = validate_conversation_ownership(
            user_id=user_id, conversation_id=query_request.conversation_id
        )

        if user_conversation is None:
            logger.warning(
                "User %s attempted to query conversation %s they don't own",
                user_id,
                query_request.conversation_id,
            )
            forbidden_error = ForbiddenResponse.conversation(
                action="read",
                resource_id=query_request.conversation_id,
                user_id=user_id,
            )
            return StreamingResponse(
                stream_http_error(forbidden_error),
                media_type="text/event-stream",
                status_code=forbidden_error.status_code,
            )

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
            await client.models.list(),
            *evaluate_model_hints(
                user_conversation=user_conversation, query_request=query_request
            ),
        )

        if (
            provider_id == "azure"
            and AzureEntraIDManager().is_entra_id_configured
            and AzureEntraIDManager().is_token_expired
            and AzureEntraIDManager().refresh_token()
        ):
            if AsyncLlamaStackClientHolder().is_library_client:
                client = await AsyncLlamaStackClientHolder().reload_library_client()
            else:
                azure_config = next(
                    p.config
                    for p in await client.providers.list()
                    if p.provider_type == "remote::azure"
                )
                client = AsyncLlamaStackClientHolder().update_provider_data(
                    {
                        "azure_api_key": AzureEntraIDManager().access_token.get_secret_value(),
                        "azure_api_base": str(azure_config.get("api_base")),
                    }
                )

        response, conversation_id = await retrieve_response_func(
            client,
            llama_stack_model_id,
            query_request,
            token,
            mcp_headers=mcp_headers,
        )

        metadata_map: dict[str, dict[str, Any]] = {}

        # Create context object for response generator
        context = ResponseGeneratorContext(
            conversation_id=conversation_id,
            user_id=user_id,
            skip_userid_check=_skip_userid_check,
            model_id=model_id,
            provider_id=provider_id,
            llama_stack_model_id=llama_stack_model_id,
            query_request=query_request,
            started_at=started_at,
            client=client,
            metadata_map=metadata_map,
        )

        # Create the response generator using the provided factory function
        response_generator = create_response_generator_func(context)

        # Update metrics for the LLM call
        metrics.llm_calls_total.labels(provider_id, model_id).inc()

        # Determine media type for response
        # Note: The HTTP Content-Type header is always text/event-stream for SSE,
        # but the media_type parameter controls how the content is formatted
        return StreamingResponse(
            response_generator(response), media_type="text/event-stream"
        )
    except APIConnectionError as e:
        metrics.llm_calls_failures_total.inc()
        logger.error("Unable to connect to Llama Stack: %s", e)
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        return StreamingResponse(
            stream_http_error(error_response),
            status_code=error_response.status_code,
            media_type="text/event-stream",
        )
    except RateLimitError as e:
        used_model = getattr(e, "model", "")
        if used_model:
            error_response = QuotaExceededResponse.model(used_model)
        else:
            error_response = QuotaExceededResponse(
                response="The quota has been exceeded", cause=str(e)
            )
        return StreamingResponse(
            stream_http_error(error_response),
            status_code=error_response.status_code,
            media_type="text/event-stream",
        )
    except APIStatusError as e:
        metrics.llm_calls_failures_total.inc()
        logger.error("API status error: %s", e)
        error_response = InternalServerErrorResponse.generic()
        return StreamingResponse(
            stream_http_error(error_response),
            status_code=error_response.status_code,
            media_type=query_request.media_type or MEDIA_TYPE_JSON,
        )
