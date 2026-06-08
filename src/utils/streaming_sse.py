"""Shared SSE formatting helpers for streaming endpoints."""

import json
from collections.abc import AsyncIterator

from constants import (
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
    LLM_TURN_COMPLETE_EVENT,
    MEDIA_TYPE_TEXT,
)


def format_stream_data(d: dict) -> str:
    """Format a dictionary as an SSE ``data:`` line.

    Args:
        d: Event payload to serialize.

    Returns:
        SSE-formatted data string.
    """
    data = json.dumps(d)
    return f"data: {data}\n\n"


def stream_event(data: dict, event_type: str, media_type: str) -> str:
    """Build a streaming event string for JSON or plain-text clients.

    Args:
        data: Dictionary containing the event data.
        event_type: Type of event (token, tool call, etc.).
        media_type: The media type for the response format.

    Returns:
        SSE-formatted string representing the event.
    """
    if media_type == MEDIA_TYPE_TEXT:
        if event_type == LLM_TOKEN_EVENT:
            return data.get("token", "")
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


async def shield_violation_generator(
    violation_message: str,
    media_type: str = MEDIA_TYPE_TEXT,
) -> AsyncIterator[str]:
    """Create an SSE stream for shield violation responses.

    Yields a token event immediately for shield violations without going
    through the Llama Stack response format.

    Args:
        violation_message: The violation message to display.
        media_type: The media type for the response format.

    Yields:
        SSE-formatted strings for the violation token event.
    """
    yield stream_event(
        {
            "id": 0,
            "token": violation_message,
        },
        LLM_TOKEN_EVENT,
        media_type,
    )
