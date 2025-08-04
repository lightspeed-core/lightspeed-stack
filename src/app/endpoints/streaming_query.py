"""Handler for REST API call to provide answer to streaming query."""

import ast
from contextlib import suppress
import json
import re
import logging
from typing import Any, AsyncIterator, Iterator

from llama_stack_client import APIConnectionError
from llama_stack_client.lib.agents.agent import AsyncAgent  # type: ignore
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack_client.types import UserMessage  # type: ignore

from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.types.shared import ToolCall
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem

from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import StreamingResponse

from auth import get_auth_dependency
from client import AsyncLlamaStackClientHolder
from configuration import configuration
import metrics
from models.requests import QueryRequest
from utils.endpoints import check_configuration_loaded, get_system_prompt
from utils.common import retrieve_user_id
from utils.mcp_headers import mcp_headers_dependency, handle_mcp_headers_with_toolgroups
from utils.suid import get_suid
from utils.types import GraniteToolParser

from app.endpoints.query import (
    get_rag_toolgroups,
    is_input_shield,
    is_output_shield,
    is_transcripts_enabled,
    store_transcript,
    select_model_and_provider_id,
    validate_attachments_metadata,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query"])
auth_dependency = get_auth_dependency()


# # pylint: disable=R0913,R0917
async def get_agent(
    client: AsyncLlamaStackClient,
    model_id: str,
    system_prompt: str,
    available_input_shields: list[str],
    available_output_shields: list[str],
    conversation_id: str | None,
    no_tools: bool = False,
) -> tuple[AsyncAgent, str, str]:
    """Get existing agent or create a new one with session persistence."""
    existing_agent_id = None
    if conversation_id:
        with suppress(ValueError):
            agent_response = await client.agents.retrieve(agent_id=conversation_id)
            existing_agent_id = agent_response.agent_id

    logger.debug("Creating new agent")
    agent = AsyncAgent(
        client,  # type: ignore[arg-type]
        model=model_id,
        instructions=system_prompt,
        input_shields=available_input_shields if available_input_shields else [],
        output_shields=available_output_shields if available_output_shields else [],
        tool_parser=None if no_tools else GraniteToolParser.get_parser(model_id),
        enable_session_persistence=True,
    )

    if existing_agent_id and conversation_id:
        orphan_agent_id = agent.agent_id
        agent._agent_id = conversation_id  # type: ignore[assignment]  # pylint: disable=protected-access
        await client.agents.delete(agent_id=orphan_agent_id)
        sessions_response = await client.agents.session.list(agent_id=conversation_id)
        logger.info("session response: %s", sessions_response)
        session_id = str(sessions_response.data[0]["session_id"])
    else:
        conversation_id = agent.agent_id
        session_id = await agent.create_session(get_suid())

    return agent, conversation_id, session_id


METADATA_PATTERN = re.compile(r"\nMetadata: (\{.+})\n")


def format_stream_data(d: dict) -> str:
    """Format outbound data in the Event Stream Format."""
    data = json.dumps(d)
    return f"data: {data}\n\n"


def stream_start_event(conversation_id: str) -> str:
    """Yield the start of the data stream.

    Args:
        conversation_id: The conversation ID (UUID).
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
    """Yield the end of the data stream."""
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

    This function processes chunks from the LLama Stack streaming response and formats
    them into Server-Sent Events (SSE) format for the client. It handles two main
    event types:

    1. step_progress: Contains text deltas from the model inference process
    2. step_complete: Contains information about completed tool execution steps

    Args:
        chunk: The streaming chunk from LLama Stack containing event data
        chunk_id: The current chunk ID counter (gets incremented for each token)

    Returns:
        Iterator[str]: An iterable list of formatted SSE data strings with event information
    """
    if hasattr(chunk, "error"):
        yield from _handle_error_event(chunk, chunk_id)
        return

    event_type = chunk.event.payload.event_type
    step_type = getattr(chunk.event.payload, "step_type", None)

    if event_type in {"turn_start", "turn_awaiting_input"}:
        yield from _handle_turn_start_event(chunk_id)
    elif event_type == "turn_complete":
        yield from _handle_turn_complete_event(chunk, chunk_id)
    elif step_type == "shield_call":
        yield from _handle_shield_event(chunk, chunk_id)
    elif step_type == "inference":
        yield from _handle_inference_event(chunk, chunk_id)
    elif step_type == "tool_execution":
        yield from _handle_tool_execution_event(chunk, chunk_id, metadata_map)
    else:
        yield from _handle_heartbeat_event(chunk_id)


# -----------------------------------
# Error handling
# -----------------------------------
def _handle_error_event(chunk: Any, chunk_id: int) -> Iterator[str]:
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
    yield format_stream_data(
        {
            "event": "turn_complete",
            "data": {
                "id": chunk_id,
                "token": chunk.event.payload.turn.output_message.content,
            },
        }
    )


# -----------------------------------
# Shield handling
# -----------------------------------
def _handle_shield_event(chunk: Any, chunk_id: int) -> Iterator[str]:
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
                        "token": f"Tool:{t.tool_name} arguments:{t.arguments}",
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
                            "token": f"Fetched {len(inserted_context)} bytes from memory",
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
                            "token": f"Tool:{r.tool_name} summary:{summary}",
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
                            "token": f"Tool:{r.tool_name} response:{r.content}",
                        },
                    }
                )


# -----------------------------------
# Catch-all for everything else
# -----------------------------------
def _handle_heartbeat_event(chunk_id: int) -> Iterator[str]:
    yield format_stream_data(
        {
            "event": "heartbeat",
            "data": {
                "id": chunk_id,
                "token": "heartbeat",
            },
        }
    )


@router.post("/streaming_query")
async def streaming_query_endpoint_handler(
    _request: Request,
    query_request: QueryRequest,
    auth: Any = Depends(auth_dependency),
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> StreamingResponse:
    """Handle request to the /streaming_query endpoint."""
    check_configuration_loaded(configuration)

    llama_stack_config = configuration.llama_stack_configuration
    logger.info("LLama stack config: %s", llama_stack_config)

    _user_id, _user_name, token = auth

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        model_id, provider_id = select_model_and_provider_id(
            await client.models.list(), query_request
        )
        response, conversation_id = await retrieve_response(
            client,
            model_id,
            query_request,
            token,
            mcp_headers=mcp_headers,
        )
        metadata_map: dict[str, dict[str, Any]] = {}

        async def response_generator(turn_response: Any) -> AsyncIterator[str]:
            """Generate SSE formatted streaming response."""
            chunk_id = 0
            complete_response = ""

            # Send start event
            yield stream_start_event(conversation_id)

            async for chunk in turn_response:
                for event in stream_build_event(chunk, chunk_id, metadata_map):
                    complete_response += json.loads(event.replace("data: ", ""))[
                        "data"
                    ]["token"]
                    chunk_id += 1
                    yield event

            yield stream_end_event(metadata_map)

            if not is_transcripts_enabled():
                logger.debug("Transcript collection is disabled in the configuration")
            else:
                store_transcript(
                    user_id=retrieve_user_id(auth),
                    conversation_id=conversation_id,
                    query_is_valid=True,  # TODO(lucasagomes): implement as part of query validation
                    query=query_request.query,
                    query_request=query_request,
                    response=complete_response,
                    rag_chunks=[],  # TODO(lucasagomes): implement rag_chunks
                    truncated=False,  # TODO(lucasagomes): implement truncation as part
                    # of quota work
                    attachments=query_request.attachments or [],
                )

        # Update metrics for the LLM call
        metrics.llm_calls_total.labels(provider_id, model_id).inc()

        return StreamingResponse(response_generator(response))
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


async def retrieve_response(
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: dict[str, dict[str, str]] | None = None,
) -> tuple[Any, str]:
    """Retrieve response from LLMs and agents."""
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

        logger.debug("Session ID: %s", conversation_id)
        vector_db_ids = [
            vector_db.identifier for vector_db in await client.vector_dbs.list()
        ]
        toolgroups = (get_rag_toolgroups(vector_db_ids) or []) + [
            mcp_server.name for mcp_server in configuration.mcp_servers
        ]
        # Convert empty list to None for consistency with existing behavior
        if not toolgroups:
            toolgroups = None

    logger.debug("Session ID: %s", conversation_id)
    response = await agent.create_turn(
        messages=[UserMessage(role="user", content=query_request.query)],
        session_id=session_id,
        documents=query_request.get_documents(),
        stream=True,
        toolgroups=toolgroups,
    )

    return response, conversation_id
