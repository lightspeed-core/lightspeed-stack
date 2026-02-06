"""Utility functions for working with queries."""

import json
from typing import Any, AsyncIterator, Optional

from llama_stack_api.openai_responses import (
    OpenAIResponseContentPartOutputText,
    OpenAIResponseMessage,
    OpenAIResponseObject,
    OpenAIResponseObjectStream,
    OpenAIResponseObjectStreamResponseCompleted,
    OpenAIResponseObjectStreamResponseContentPartAdded,
    OpenAIResponseObjectStreamResponseCreated,
    OpenAIResponseObjectStreamResponseOutputTextDelta,
    OpenAIResponseObjectStreamResponseOutputTextDone,
    OpenAIResponseOutputMessageContentOutputText,
)


def parse_arguments_string(arguments_str: str) -> dict[str, Any]:
    """
    Try to parse an arguments string into a dictionary.

    Attempts multiple parsing strategies:
    1. Try parsing the string as-is as JSON (if it's already valid JSON)
    2. Try wrapping the string in {} if it doesn't start with {
    3. Return {"args": arguments_str} if all attempts fail

    Args:
        arguments_str: The arguments string to parse

    Returns:
        Parsed dictionary if successful, otherwise {"args": arguments_str}
    """
    # Try parsing as-is first (most common case)
    try:
        parsed = json.loads(arguments_str)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Try wrapping in {} if string doesn't start with {
    # This handles cases where the string is just the content without braces
    stripped = arguments_str.strip()
    if stripped and not stripped.startswith("{"):
        try:
            wrapped = "{" + stripped + "}"
            parsed = json.loads(wrapped)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: return wrapped in arguments key
    return {"args": arguments_str}


async def create_violation_stream(
    message: str,
    shield_model: Optional[str] = None,
) -> AsyncIterator[OpenAIResponseObjectStream]:
    """Generate a minimal streaming response for cases where input is blocked by a shield.

    This yields only the essential streaming events to indicate that the input was rejected.
    Dummy item identifiers are used solely for protocol compliance and are not used later.
    """
    response_id = "resp_shield_violation"

    # Create the response object with empty output at the beginning
    response_obj = OpenAIResponseObject(
        id=response_id,
        created_at=0,  # not used
        model=shield_model or "shield",
        output=[],
        status="in_progress",
        store=False,
    )
    yield OpenAIResponseObjectStreamResponseCreated(response=response_obj)

    # Triggers empty initial token
    yield OpenAIResponseObjectStreamResponseContentPartAdded(
        content_index=0,
        response_id=response_id,
        item_id="msg_shield_violation_1",
        output_index=0,
        part=OpenAIResponseContentPartOutputText(text=""),
        sequence_number=0,
    )

    # Text delta
    yield OpenAIResponseObjectStreamResponseOutputTextDelta(
        content_index=1,
        delta=message,
        item_id="msg_shield_violation_2",
        output_index=1,
        sequence_number=1,
    )

    # Output text done
    yield OpenAIResponseObjectStreamResponseOutputTextDone(
        content_index=2,
        text=message,
        item_id="msg_shield_violation_3",
        output_index=2,
        sequence_number=2,
    )

    # Fill the output when message is completed
    response_obj.output = [
        OpenAIResponseMessage(
            id="msg_shield_violation_4",
            content=[OpenAIResponseOutputMessageContentOutputText(text=message)],
            role="assistant",
            status="completed",
        )
    ]
    # Update status to completed
    response_obj.status = "completed"

    # Completed response triggers turn complete event
    yield OpenAIResponseObjectStreamResponseCompleted(response=response_obj)
