"""SSE formatting helpers for streaming query responses."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Optional

from fastapi import HTTPException

from lightspeed_stack.constants import (
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
    LLM_TURN_COMPLETE_EVENT,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
)
from lightspeed_stack.log import get_logger
from lightspeed_stack.models.api.responses.error import AbstractErrorResponse
from lightspeed_stack.models.common.turn_summary import ReferencedDocument
from lightspeed_stack.utils.token_counter import TokenCounter

logger = get_logger(__name__)


def stream_http_error_event(
    error: AbstractErrorResponse, media_type: Optional[str] = MEDIA_TYPE_JSON
) -> str:
    """Create an SSE-formatted error response for generic LLM or API errors.

    Args:
        error: An AbstractErrorResponse instance representing the error.
        media_type: The media type for the response format. Defaults to MEDIA_TYPE_JSON.

    Returns:
        A Server-Sent Events (SSE) formatted error message containing
        the serialized error details.
    """
    logger.error("Error while obtaining answer for user question")
    media_type = media_type or MEDIA_TYPE_JSON
    if media_type == MEDIA_TYPE_TEXT:
        return f"Status: {error.status_code} - {error.detail.response} - {error.detail.cause}"

    return format_stream_data(
        {
            "event": "error",
            "data": {
                "status_code": error.status_code,
                "response": error.detail.response,
                "cause": error.detail.cause,
            },
        }
    )


def format_stream_data(d: dict[str, Any]) -> str:
    """Format a dictionary as an SSE data event string.

    Args:
        d: The data to be formatted as an SSE event.

    Returns:
        The formatted SSE data string.
    """
    data = json.dumps(d)
    return f"data: {data}\n\n"


def stream_start_event(conversation_id: str, request_id: str) -> str:
    """Format an SSE start event for a streaming response.

    The payload contains both the conversation ID and the request ID
    so the client can correlate the stream with a conversation and
    use the request ID to issue an interrupt if needed.

    Args:
        conversation_id: Unique identifier for the conversation.
        request_id: Unique SUID for this streaming request,
            returned to the client for interrupt support.

    Returns:
        SSE-formatted string representing the start event.
    """
    return format_stream_data(
        {
            "event": "start",
            "data": {
                "conversation_id": conversation_id,
                "request_id": request_id,
            },
        }
    )


def stream_compaction_event(conversation_id: str) -> str:
    """Format an SSE event signalling that conversation compaction has started.

    Emitted before the summarization LLM call (R12) so the client can show a
    progress indicator while older turns are being summarized.

    Args:
        conversation_id: The conversation being compacted.

    Returns:
        SSE-formatted string representing the compaction event.
    """
    return format_stream_data(
        {
            "event": "compaction",
            "data": {
                "status": "started",
                "conversation_id": conversation_id,
            },
        }
    )


def stream_interrupted_event(request_id: str) -> str:
    """Format an SSE event indicating the stream was interrupted.

    Emitted to the client just before the generator closes so the
    frontend can distinguish an intentional user-initiated interruption
    from an unexpected connection drop.

    Args:
        request_id: Unique identifier for the interrupted request.

    Returns:
        SSE-formatted string representing the interrupted event.
    """
    return format_stream_data(
        {
            "event": "interrupted",
            "data": {
                "request_id": request_id,
            },
        }
    )


def stream_end_event(
    token_usage: TokenCounter,
    available_quotas: dict[str, int],
    referenced_documents: list[ReferencedDocument],
    media_type: str = MEDIA_TYPE_JSON,
) -> str:
    """Format the end event for a streaming response.

    Includes referenced document metadata and token usage information.

    Args:
        token_usage: Token usage information.
        available_quotas: Available quotas for the user.
        referenced_documents: List of referenced documents.
        media_type: The media type for the response format.

    Returns:
        A Server-Sent Events (SSE) formatted string representing the end event.
    """
    if media_type == MEDIA_TYPE_TEXT:
        ref_docs_string = "\n".join(
            f"{doc.doc_title}: {doc.doc_url}"
            for doc in referenced_documents
            if doc.doc_url and doc.doc_title
        )
        return f"\n\n---\n\n{ref_docs_string}" if ref_docs_string else ""

    referenced_docs_dict = [doc.model_dump(mode="json") for doc in referenced_documents]

    return format_stream_data(
        {
            "event": "end",
            "data": {
                "referenced_documents": referenced_docs_dict,
                "truncated": None,
                "input_tokens": token_usage.input_tokens,
                "output_tokens": token_usage.output_tokens,
            },
            "available_quotas": available_quotas,
        }
    )


def stream_event(data: dict[str, Any], event_type: str, media_type: str) -> str:
    """Build an SSE event string based on media type.

    Args:
        data: Dictionary containing the event data.
        event_type: Type of event (token, tool call, etc.).
        media_type: The media type for the response format.

    Returns:
        SSE-formatted string representing the event.
    """
    if media_type == MEDIA_TYPE_TEXT:
        if event_type == LLM_TOKEN_EVENT:
            return str(data.get("token", ""))
        if event_type == LLM_TOOL_CALL_EVENT:
            return f"[Tool Call: {data.get('function_name', 'unknown')}]\n"
        if event_type == LLM_TOOL_RESULT_EVENT:
            return "[Tool Result]\n"
        if event_type == LLM_TURN_COMPLETE_EVENT:
            return ""
        return ""

    return format_stream_data(
        {
            "event": event_type,
            "data": data,
        }
    )


def http_exception_stream_event(exc: HTTPException) -> str:
    """Render a FastAPI HTTPException as an SSE error event.

    Used by the compaction-aware streaming path, where the response is created
    inside the stream and so create-time errors must be surfaced as SSE events
    rather than as an HTTP status response.

    Args:
        exc: HTTP exception raised during in-stream response creation.

    Returns:
        SSE-formatted error event string.
    """
    detail = (
        exc.detail if isinstance(exc.detail, dict) else {"response": str(exc.detail)}
    )
    return format_stream_data(
        {"event": "error", "data": {"status_code": exc.status_code, **detail}}
    )


async def shield_violation_generator(
    violation_message: str,
    media_type: str = MEDIA_TYPE_TEXT,
) -> AsyncIterator[str]:
    """Create an SSE token stream for shield violation responses.

    Yields a single token event for shield violations. Callers should wrap
    this generator to emit start/end events and persist the blocked turn.

    Args:
        violation_message: The violation message to display.
        media_type: The media type for the response format.

    Yields:
        SSE-formatted token event string.
    """
    yield stream_event(
        {
            "id": 0,
            "token": violation_message,
        },
        LLM_TOKEN_EVENT,
        media_type,
    )
