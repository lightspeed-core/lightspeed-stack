"""Handler for REST API call to provide answer to streaming query."""  # pylint: disable=too-many-lines

import ast
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, AsyncGenerator, AsyncIterator, Iterator, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from llama_stack_client import (
    APIConnectionError,
    AsyncLlamaStackClient,  # type: ignore
)
from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.types import UserMessage  # type: ignore
from llama_stack_client.types.agents.agent_turn_response_stream_chunk import (
    AgentTurnResponseStreamChunk,
)
from llama_stack_client.types.shared import ToolCall
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem
from pydantic import AnyUrl

from app.database import get_session
from app.endpoints.query import (
    get_rag_toolgroups,
    is_input_shield,
    is_output_shield,
    is_transcripts_enabled,
    select_model_and_provider_id,
    validate_attachments_metadata,
    validate_conversation_ownership,
    persist_user_conversation_details,
    evaluate_model_hints,
    get_topic_summary,
)
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import DEFAULT_RAG_TOOL, MEDIA_TYPE_JSON, MEDIA_TYPE_TEXT
import metrics
from metrics.utils import update_llm_token_count_from_turn
from models.cache_entry import CacheEntry
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import QueryRequest
from models.responses import ForbiddenResponse, UnauthorizedResponse, ReferencedDocument
from utils.endpoints import (
    check_configuration_loaded,
    create_referenced_documents_with_metadata,
    create_rag_chunks_dict,
    get_agent,
    get_system_prompt,
    store_conversation_into_cache,
    validate_model_provider_override,
)
from utils.mcp_headers import handle_mcp_headers_with_toolgroups, mcp_headers_dependency
from utils.token_counter import TokenCounter, extract_token_usage_from_turn
from utils.transcripts import store_transcript
from utils.types import TurnSummary

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query"])

streaming_query_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Streaming response with Server-Sent Events",
        "content": {
            "application/json": {
                "schema": {
                    "type": "string",
                    "example": (
                        'data: {"event": "start", '
                        '"data": {"conversation_id": "123e4567-e89b-12d3-a456-426614174000"}}\n\n'
                        'data: {"event": "token", "data": {"id": 0, "token": "Hello"}}\n\n'
                        'data: {"event": "end", "data": {"referenced_documents": [], '
                        '"truncated": null, "input_tokens": 0, "output_tokens": 0}, '
                        '"available_quotas": {}}\n\n'
                    ),
                }
            },
            "text/plain": {
                "schema": {
                    "type": "string",
                    "example": "Hello world!\n\n---\n\nReference: https://example.com/doc",
                }
            },
        },
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    401: {
        "description": "Unauthorized: Invalid or missing Bearer token for k8s auth",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
    500: {
        "detail": {
            "response": "Unable to connect to Llama Stack",
            "cause": "Connection error.",
        }
    },
}


METADATA_PATTERN = re.compile(r"\nMetadata: (\{.+})\n")

# OLS-compatible event types
LLM_TOKEN_EVENT = "token"
LLM_TOOL_CALL_EVENT = "tool_call"
LLM_TOOL_RESULT_EVENT = "tool_result"


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
    summary: TurnSummary,  # pylint: disable=unused-argument
    token_usage: TokenCounter,
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

    # For JSON media type, we need to create a proper structure
    # Since we don't have access to summary here, we'll create a basic structure
    referenced_docs_dict = [
        {
            "doc_url": v.get("docs_url"),
            "doc_title": v.get("title"),
        }
        for v in metadata_map.values()
        if "docs_url" in v and "title" in v
    ]

    return format_stream_data(
        {
            "event": "end",
            "data": {
                "rag_chunks": [],  # TODO(jboos): implement RAG chunks when summary is available
                "referenced_documents": referenced_docs_dict,
                "truncated": None,  # TODO(jboos): implement truncated
                "input_tokens": token_usage.input_tokens,
                "output_tokens": token_usage.output_tokens,
            },
            "available_quotas": {},  # TODO(jboos): implement available quotas
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


def stream_build_event(
    chunk: Any,
    chunk_id: int,
    metadata_map: dict,
    media_type: str = MEDIA_TYPE_JSON,
    conversation_id: str | None = None,
) -> Iterator[str]:
    """Build a streaming event from a chunk response.

    This function processes chunks from the Llama Stack streaming response and
    formats them into Server-Sent Events (SSE) format for the client. It
    dispatches on (event_type, step_type):

    1. turn_start, turn_awaiting_input -> start token
    2. turn_complete -> final output message
    3. step_* with step_type in {"shield_call", "inference", "tool_execution"} -> delegated handlers
    4. anything else -> heartbeat

    Args:
        chunk: The streaming chunk from Llama Stack containing event data
        chunk_id: The current chunk ID counter (gets incremented for each token)

    Returns:
        Iterator[str]: An iterable list of formatted SSE data strings with event information
    """
    if hasattr(chunk, "error"):
        yield from _handle_error_event(chunk, chunk_id, media_type)

    event_type = chunk.event.payload.event_type
    step_type = getattr(chunk.event.payload, "step_type", None)

    match (event_type, step_type):
        case (("turn_start" | "turn_awaiting_input"), _):
            yield from _handle_turn_start_event(chunk_id, media_type, conversation_id)
        case ("turn_complete", _):
            yield from _handle_turn_complete_event(chunk, chunk_id, media_type)
        case (_, "shield_call"):
            yield from _handle_shield_event(chunk, chunk_id, media_type)
        case (_, "inference"):
            yield from _handle_inference_event(chunk, chunk_id, media_type)
        case (_, "tool_execution"):
            yield from _handle_tool_execution_event(
                chunk, chunk_id, metadata_map, media_type
            )
        case _:
            logger.debug(
                "Unhandled event combo: event_type=%s, step_type=%s",
                event_type,
                step_type,
            )
            yield from _handle_heartbeat_event(chunk_id, media_type)


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


# -----------------------------------
# Turn handling
# -----------------------------------
def _handle_turn_start_event(
    _chunk_id: int,
    media_type: str = MEDIA_TYPE_JSON,
    conversation_id: str | None = None,
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
    full_response = interleaved_content_as_str(
        chunk.event.payload.turn.output_message.content
    )

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
                event_type=LLM_TOKEN_EVENT,
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
                event_type=LLM_TOKEN_EVENT,
                media_type=media_type,
            )


# -----------------------------------
# Inference handling
# -----------------------------------
def _handle_inference_event(
    chunk: Any, chunk_id: int, media_type: str = MEDIA_TYPE_JSON
) -> Iterator[str]:
    """
    Yield inference step event.

    Yield formatted Server-Sent Events (SSE) strings for inference
    step events during streaming.

    Processes inference-related streaming chunks, yielding SSE
    events for step start, text token deltas, and tool call deltas.
    Supports both string and ToolCall object tool calls.
    """
    if chunk.event.payload.event_type == "step_start":
        yield stream_event(
            data={
                "id": chunk_id,
                "token": "",
            },
            event_type=LLM_TOKEN_EVENT,
            media_type=media_type,
        )

    elif chunk.event.payload.event_type == "step_progress":
        if chunk.event.payload.delta.type == "tool_call":
            if isinstance(chunk.event.payload.delta.tool_call, str):
                yield stream_event(
                    data={
                        "id": chunk_id,
                        "token": chunk.event.payload.delta.tool_call,
                    },
                    event_type=LLM_TOOL_CALL_EVENT,
                    media_type=media_type,
                )
            elif isinstance(chunk.event.payload.delta.tool_call, ToolCall):
                yield stream_event(
                    data={
                        "id": chunk_id,
                        "token": chunk.event.payload.delta.tool_call.tool_name,
                    },
                    event_type=LLM_TOOL_CALL_EVENT,
                    media_type=media_type,
                )

        elif chunk.event.payload.delta.type == "text":
            yield stream_event(
                data={
                    "id": chunk_id,
                    "token": chunk.event.payload.delta.text,
                },
                event_type=LLM_TOKEN_EVENT,
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
                inserted_context = interleaved_content_as_str(r.content)
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
                            "response": interleaved_content_as_str(r.content),
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


@router.post("/streaming_query", responses=streaming_query_responses)
@authorize(Action.STREAMING_QUERY)
async def streaming_query_endpoint_handler(  # pylint: disable=too-many-locals,too-many-statements
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> StreamingResponse:
    """
    Handle request to the /streaming_query endpoint.

    This endpoint receives a query request, authenticates the user,
    selects the appropriate model and provider, and streams
    incremental response events from the Llama Stack backend to the
    client. Events include start, token updates, tool calls, turn
    completions, errors, and end-of-stream metadata. Optionally
    stores the conversation transcript if enabled in configuration.

    Returns:
        StreamingResponse: An HTTP streaming response yielding
        SSE-formatted events for the query lifecycle.

    Raises:
        HTTPException: Returns HTTP 500 if unable to connect to the
        Llama Stack server.
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

    user_conversation: UserConversation | None = None
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "response": "Access denied",
                    "cause": "You do not have permission to access this conversation",
                },
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
        response, conversation_id = await retrieve_response(
            client,
            llama_stack_model_id,
            query_request,
            token,
            mcp_headers=mcp_headers,
        )
        metadata_map: dict[str, dict[str, Any]] = {}

        async def response_generator(
            turn_response: AsyncIterator[AgentTurnResponseStreamChunk],
        ) -> AsyncIterator[str]:
            """
            Generate SSE formatted streaming response.

            Asynchronously generates a stream of Server-Sent Events
            (SSE) representing incremental responses from a
            language model turn.

            Yields start, token, tool call, turn completion, and
            end events as SSE-formatted strings. Collects the
            complete response for transcript storage if enabled.
            """
            chunk_id = 0
            summary = TurnSummary(
                llm_response="No response from the model", tool_calls=[]
            )

            # Determine media type for response formatting
            media_type = query_request.media_type or MEDIA_TYPE_JSON

            # Send start event at the beginning of the stream
            yield stream_start_event(conversation_id)

            latest_turn: Any | None = None

            async for chunk in turn_response:
                if chunk.event is None:
                    continue
                p = chunk.event.payload
                if p.event_type == "turn_complete":
                    summary.llm_response = interleaved_content_as_str(
                        p.turn.output_message.content
                    )
                    latest_turn = p.turn
                    system_prompt = get_system_prompt(query_request, configuration)
                    try:
                        update_llm_token_count_from_turn(
                            p.turn, model_id, provider_id, system_prompt
                        )
                    except Exception:  # pylint: disable=broad-except
                        logger.exception("Failed to update token usage metrics")
                elif p.event_type == "step_complete":
                    if p.step_details.step_type == "tool_execution":
                        summary.append_tool_calls_from_llama(p.step_details)

                for event in stream_build_event(
                    chunk, chunk_id, metadata_map, media_type, conversation_id
                ):
                    chunk_id += 1
                    yield event

            # Extract token usage from the turn
            token_usage = (
                extract_token_usage_from_turn(latest_turn)
                if latest_turn is not None
                else TokenCounter()
            )

            yield stream_end_event(metadata_map, summary, token_usage, media_type)

            if not is_transcripts_enabled():
                logger.debug("Transcript collection is disabled in the configuration")
            else:
                store_transcript(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    model_id=model_id,
                    provider_id=provider_id,
                    query_is_valid=True,  # TODO(lucasagomes): implement as part of query validation
                    query=query_request.query,
                    query_request=query_request,
                    summary=summary,
                    rag_chunks=create_rag_chunks_dict(summary),
                    truncated=False,  # TODO(lucasagomes): implement truncation as part
                    # of quota work
                    attachments=query_request.attachments or [],
                )

            # Get the initial topic summary for the conversation
            topic_summary = None
            with get_session() as session:
                existing_conversation = (
                    session.query(UserConversation)
                    .filter_by(id=conversation_id)
                    .first()
                )
                if not existing_conversation:
                    topic_summary = await get_topic_summary(
                        query_request.query, client, model_id
                    )

            completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            referenced_documents = create_referenced_documents_with_metadata(summary, metadata_map)

            cache_entry = CacheEntry(
                query=query_request.query,
                response=summary.llm_response,
                provider=provider_id,
                model=model_id,
                started_at=started_at,
                completed_at=completed_at,
                referenced_documents=referenced_documents if referenced_documents else None
            )
            
            store_conversation_into_cache(
                configuration,
                user_id,
                conversation_id,
                cache_entry,
                _skip_userid_check,
                topic_summary,
            )

            persist_user_conversation_details(
                user_id=user_id,
                conversation_id=conversation_id,
                model=model_id,
                provider_id=provider_id,
                topic_summary=topic_summary,
            )

        # Update metrics for the LLM call
        metrics.llm_calls_total.labels(provider_id, model_id).inc()

        # Determine media type for response
        # Note: The HTTP Content-Type header is always text/event-stream for SSE,
        # but the media_type parameter controls how the content is formatted
        return StreamingResponse(
            response_generator(response), media_type="text/event-stream"
        )
    # connection to Llama Stack server
    except APIConnectionError as e:
        # Update metrics for the LLM call failure
        metrics.llm_calls_failures_total.inc()
        logger.error("Unable to connect to Llama Stack: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unable to connect to Llama Stack",
                "cause": str(e),
            },
        ) from e
    except Exception as e:  # pylint: disable=broad-except
        # Handle other errors with OLS-compatible error response
        # This broad exception catch is intentional to ensure all errors
        # are converted to OLS-compatible streaming responses
        media_type = query_request.media_type or MEDIA_TYPE_JSON
        error_response = generic_llm_error(e, media_type)

        async def error_generator() -> AsyncGenerator[str, None]:
            yield error_response

        # Use text/event-stream for SSE-formatted JSON responses, text/plain for plain text
        content_type = (
            "text/event-stream" if media_type == MEDIA_TYPE_JSON else "text/plain"
        )
        return StreamingResponse(error_generator(), media_type=content_type)


async def retrieve_response(
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: dict[str, dict[str, str]] | None = None,
) -> tuple[AsyncIterator[AgentTurnResponseStreamChunk], str]:
    """
    Retrieve response from LLMs and agents.

    Asynchronously retrieves a streaming response and conversation
    ID from the Llama Stack agent for a given user query.

    This function configures input/output shields, system prompt,
    and tool usage based on the request and environment. It
    prepares the agent with appropriate headers and toolgroups,
    validates attachments if present, and initiates a streaming
    turn with the user's query and any provided documents.

    Parameters:
        model_id (str): Identifier of the model to use for the query.
        query_request (QueryRequest): The user's query and associated metadata.
        token (str): Authentication token for downstream services.
        mcp_headers (dict[str, dict[str, str]], optional):
        Multi-cluster proxy headers for tool integrations.

    Returns:
        tuple: A tuple containing the streaming response object
        and the conversation ID.
    """
    available_input_shields = [
        shield.identifier
        for shield in filter(is_input_shield, await client.shields.list())
    ]
    available_output_shields = [
        shield.identifier
        for shield in filter(is_output_shield, await client.shields.list())
    ]
    if not available_input_shields and not available_output_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info(
            "Available input shields: %s, output shields: %s",
            available_input_shields,
            available_output_shields,
        )
    # use system prompt from request or default one
    system_prompt = get_system_prompt(query_request, configuration)
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    agent, conversation_id, session_id = await get_agent(
        client,
        model_id,
        system_prompt,
        available_input_shields,
        available_output_shields,
        query_request.conversation_id,
        query_request.no_tools or False,
    )

    logger.debug("Conversation ID: %s, session ID: %s", conversation_id, session_id)
    # bypass tools and MCP servers if no_tools is True
    if query_request.no_tools:
        mcp_headers = {}
        agent.extra_headers = {}
        toolgroups = None
    else:
        # preserve compatibility when mcp_headers is not provided
        if mcp_headers is None:
            mcp_headers = {}

        mcp_headers = handle_mcp_headers_with_toolgroups(mcp_headers, configuration)

        if not mcp_headers and token:
            for mcp_server in configuration.mcp_servers:
                mcp_headers[mcp_server.url] = {
                    "Authorization": f"Bearer {token}",
                }

        agent.extra_headers = {
            "X-LlamaStack-Provider-Data": json.dumps(
                {
                    "mcp_headers": mcp_headers,
                }
            ),
        }

        vector_db_ids = [
            vector_db.identifier for vector_db in await client.vector_dbs.list()
        ]
        toolgroups = (get_rag_toolgroups(vector_db_ids) or []) + [
            mcp_server.name for mcp_server in configuration.mcp_servers
        ]
        # Convert empty list to None for consistency with existing behavior
        if not toolgroups:
            toolgroups = None

    response = await agent.create_turn(
        messages=[UserMessage(role="user", content=query_request.query)],
        session_id=session_id,
        documents=query_request.get_documents(),
        stream=True,
        toolgroups=toolgroups,
    )
    response = cast(AsyncIterator[AgentTurnResponseStreamChunk], response)

    return response, conversation_id
