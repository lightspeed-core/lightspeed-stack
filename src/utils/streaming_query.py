"""Utility functions for streaming query endpoints."""

import ast
import json
import re
import logging
from typing import Any, AsyncIterator, Iterator

from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.types.agents.agent_turn_response_stream_chunk import (
    AgentTurnResponseStreamChunk,
)
from llama_stack_client.types.shared import ToolCall
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem

import metrics
from utils.types import TurnSummary
from utils.endpoints import get_system_prompt
from metrics.utils import update_llm_token_count_from_turn

logger = logging.getLogger("utils.streaming_query")

METADATA_PATTERN = re.compile(r"\nMetadata: (\{.+})\n")


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


def stream_end_event(metadata_map: dict) -> str:
    """
    Yield the end of the data stream.

    Format and return the end event for a streaming response,
    including referenced document metadata and placeholder token
    counts.

    Parameters:
        metadata_map (dict): A mapping containing metadata about
        referenced documents.

    Returns:
        str: A Server-Sent Events (SSE) formatted string
        representing the end of the data stream.
    """
    return format_stream_data(
        {
            "event": "end",
            "data": {
                "referenced_documents": [
                    {
                        "doc_url": v["docs_url"],
                        "doc_title": v["title"],
                    }
                    for v in filter(
                        lambda v: ("docs_url" in v) and ("title" in v),
                        metadata_map.values(),
                    )
                ],
                "truncated": None,  # TODO(jboos): implement truncated
                "input_tokens": 0,  # TODO(jboos): implement input tokens
                "output_tokens": 0,  # TODO(jboos): implement output tokens
            },
            "available_quotas": {},  # TODO(jboos): implement available quotas
        }
    )



def stream_build_event(chunk: Any, chunk_id: int, metadata_map: dict) -> Iterator[str]:
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
        yield from _handle_error_event(chunk, chunk_id)

    event_type = chunk.event.payload.event_type
    step_type = getattr(chunk.event.payload, "step_type", None)

    match (event_type, step_type):
        case (("turn_start" | "turn_awaiting_input"), _):
            yield from _handle_turn_start_event(chunk_id)
        case ("turn_complete", _):
            yield from _handle_turn_complete_event(chunk, chunk_id)
        case (_, "shield_call"):
            yield from _handle_shield_event(chunk, chunk_id)
        case (_, "inference"):
            yield from _handle_inference_event(chunk, chunk_id)
        case (_, "tool_execution"):
            yield from _handle_tool_execution_event(chunk, chunk_id, metadata_map)
        case _:
            logger.debug(
                "Unhandled event combo: event_type=%s, step_type=%s",
                event_type,
                step_type,
            )
            yield from _handle_heartbeat_event(chunk_id)


# -----------------------------------
# Error handling
# -----------------------------------
def _handle_error_event(chunk: Any, chunk_id: int) -> Iterator[str]:
    """
    Yield error event.

    Yield a formatted Server-Sent Events (SSE) error event
    containing the error message from a streaming chunk.

    Parameters:
        chunk_id (int): The unique identifier for the current
        streaming chunk.
    """
    yield format_stream_data(
        {
            "event": "error",
            "data": {
                "id": chunk_id,
                "token": chunk.error["message"],
            },
        }
    )


# -----------------------------------
# Turn handling
# -----------------------------------
def _handle_turn_start_event(chunk_id: int) -> Iterator[str]:
    """
    Yield turn start event.

    Yield a Server-Sent Event (SSE) token event indicating the
    start of a new conversation turn.

    Parameters:
        chunk_id (int): The unique identifier for the current
        chunk.

    Yields:
        str: SSE-formatted token event with an empty token to
        signal turn start.
    """
    yield format_stream_data(
        {
            "event": "token",
            "data": {
                "id": chunk_id,
                "token": "",
            },
        }
    )


def _handle_turn_complete_event(chunk: Any, chunk_id: int) -> Iterator[str]:
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
    yield format_stream_data(
        {
            "event": "turn_complete",
            "data": {
                "id": chunk_id,
                "token": interleaved_content_as_str(
                    chunk.event.payload.turn.output_message.content
                ),
            },
        }
    )

# -----------------------------------
# Shield handling
# -----------------------------------
def _handle_shield_event(chunk: Any, chunk_id: int) -> Iterator[str]:
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
            yield format_stream_data(
                {
                    "event": "token",
                    "data": {
                        "id": chunk_id,
                        "role": chunk.event.payload.step_type,
                        "token": "No Violation",
                    },
                }
            )
        else:
            # Metric for LLM validation errors
            metrics.llm_calls_validation_errors_total.inc()
            violation = (
                f"Violation: {violation.user_message} (Metadata: {violation.metadata})"
            )
            yield format_stream_data(
                {
                    "event": "token",
                    "data": {
                        "id": chunk_id,
                        "role": chunk.event.payload.step_type,
                        "token": violation,
                    },
                }
            )


# -----------------------------------
# Inference handling
# -----------------------------------
def _handle_inference_event(chunk: Any, chunk_id: int) -> Iterator[str]:
    """
    Yield inference step event.

    Yield formatted Server-Sent Events (SSE) strings for inference
    step events during streaming.

    Processes inference-related streaming chunks, yielding SSE
    events for step start, text token deltas, and tool call deltas.
    Supports both string and ToolCall object tool calls.
    """
    if chunk.event.payload.event_type == "step_start":
        yield format_stream_data(
            {
                "event": "token",
                "data": {
                    "id": chunk_id,
                    "role": chunk.event.payload.step_type,
                    "token": "",
                },
            }
        )

    elif chunk.event.payload.event_type == "step_progress":
        if chunk.event.payload.delta.type == "tool_call":
            if isinstance(chunk.event.payload.delta.tool_call, str):
                yield format_stream_data(
                    {
                        "event": "tool_call",
                        "data": {
                            "id": chunk_id,
                            "role": chunk.event.payload.step_type,
                            "token": chunk.event.payload.delta.tool_call,
                        },
                    }
                )
            elif isinstance(chunk.event.payload.delta.tool_call, ToolCall):
                yield format_stream_data(
                    {
                        "event": "tool_call",
                        "data": {
                            "id": chunk_id,
                            "role": chunk.event.payload.step_type,
                            "token": chunk.event.payload.delta.tool_call.tool_name,
                        },
                    }
                )

        elif chunk.event.payload.delta.type == "text":
            yield format_stream_data(
                {
                    "event": "token",
                    "data": {
                        "id": chunk_id,
                        "role": chunk.event.payload.step_type,
                        "token": chunk.event.payload.delta.text,
                    },
                }
            )


# -----------------------------------
# Tool Execution handling
# -----------------------------------
# pylint: disable=R1702,R0912
def _handle_tool_execution_event(
    chunk: Any, chunk_id: int, metadata_map: dict
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
        yield format_stream_data(
            {
                "event": "tool_call",
                "data": {
                    "id": chunk_id,
                    "role": chunk.event.payload.step_type,
                    "token": "",
                },
            }
        )

    elif chunk.event.payload.event_type == "step_complete":
        for t in chunk.event.payload.step_details.tool_calls:
            yield format_stream_data(
                {
                    "event": "tool_call",
                    "data": {
                        "id": chunk_id,
                        "role": chunk.event.payload.step_type,
                        "token": {
                            "tool_name": t.tool_name,
                            "arguments": t.arguments,
                        },
                    },
                }
            )

        for r in chunk.event.payload.step_details.tool_responses:
            if r.tool_name == "query_from_memory":
                inserted_context = interleaved_content_as_str(r.content)
                yield format_stream_data(
                    {
                        "event": "tool_call",
                        "data": {
                            "id": chunk_id,
                            "role": chunk.event.payload.step_type,
                            "token": {
                                "tool_name": r.tool_name,
                                "response": f"Fetched {len(inserted_context)} bytes from memory",
                            },
                        },
                    }
                )

            elif r.tool_name == "knowledge_search" and r.content:
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

                yield format_stream_data(
                    {
                        "event": "tool_call",
                        "data": {
                            "id": chunk_id,
                            "role": chunk.event.payload.step_type,
                            "token": {
                                "tool_name": r.tool_name,
                                "summary": summary,
                            },
                        },
                    }
                )

            else:
                yield format_stream_data(
                    {
                        "event": "tool_call",
                        "data": {
                            "id": chunk_id,
                            "role": chunk.event.payload.step_type,
                            "token": {
                                "tool_name": r.tool_name,
                                "response": interleaved_content_as_str(r.content),
                            },
                        },
                    }
                )


# -----------------------------------
# Catch-all for everything else
# -----------------------------------
def _handle_heartbeat_event(chunk_id: int) -> Iterator[str]:
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
    yield format_stream_data(
        {
            "event": "heartbeat",
            "data": {
                "id": chunk_id,
                "token": "heartbeat",
            },
        }
    )


def process_streaming_response(
    turn_response: AsyncIterator[AgentTurnResponseStreamChunk],
    conversation_id: str,
    query_request: Any,
    configuration: Any,
    model_id: str,
    provider_id: str,
) -> AsyncIterator[str]:
    """
    Generate SSE formatted streaming response.

    Asynchronously generates a stream of Server-Sent Events
    (SSE) representing incremental responses from a
    language model turn.

    Yields start, token, tool call, turn completion, and
    end events as SSE-formatted strings. Collects the
    complete response for transcript storage if enabled.

    Parameters:
        turn_response: The async iterator of streaming chunks
        conversation_id: The conversation ID
        query_request: The original query request
        configuration: The system configuration
        model_id: The model identifier
        provider_id: The provider identifier

    Returns:
        AsyncIterator[str]: Stream of SSE-formatted strings
    """

    async def response_generator() -> AsyncIterator[str]:
        chunk_id = 0
        summary = TurnSummary(llm_response="No response from the model", tool_calls=[])
        metadata_map: dict[str, dict[str, Any]] = {}

        # Send start event
        yield stream_start_event(conversation_id)

        async for chunk in turn_response:
            p = chunk.event.payload
            if p.event_type == "turn_complete":
                summary.llm_response = interleaved_content_as_str(
                    p.turn.output_message.content
                )
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

            for event in stream_build_event(chunk, chunk_id, metadata_map):
                chunk_id += 1
                yield event

        yield stream_end_event(metadata_map)

    return response_generator()
