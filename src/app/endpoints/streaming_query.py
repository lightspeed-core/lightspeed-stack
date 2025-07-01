"""Handler for REST API call to provide answer to streaming query."""

import json
import logging
from typing import Any, AsyncIterator

from llama_stack_client.lib.agents.agent import AsyncAgent  # type: ignore
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack_client.types import UserMessage  # type: ignore

from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse

from client import get_async_llama_stack_client
from configuration import configuration
from models.requests import QueryRequest
import constants
from utils.auth import auth_dependency
from utils.common import retrieve_user_id


from app.endpoints.query import (
    is_transcripts_enabled,
    retrieve_conversation_id,
    store_transcript,
    select_model_id,
    validate_attachments_metadata,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query"])


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


def stream_end_event() -> str:
    """Yield the end of the data stream."""
    return format_stream_data(
        {
            "event": "end",
            "data": {
                "referenced_documents": [],  # TODO(jboos): implement referenced documents
                "truncated": None,  # TODO(jboos): implement truncated
                "input_tokens": 0,  # TODO(jboos): implement input tokens
                "output_tokens": 0,  # TODO(jboos): implement output tokens
            },
            "available_quotas": {},  # TODO(jboos): implement available quotas
        }
    )


def stream_build_event(chunk: Any, chunk_id: int) -> str | None:
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
        str | None: A formatted SSE data string with event information, or None if
                   the chunk doesn't contain processable event data
    """
    if hasattr(chunk.event, "payload"):
        if chunk.event.payload.event_type == "step_progress":
            if hasattr(chunk.event.payload.delta, "text"):
                text = chunk.event.payload.delta.text
                return format_stream_data(
                    {
                        "event": "token",
                        "data": {
                            "id": chunk_id,
                            "role": chunk.event.payload.step_type,
                            "token": text,
                        },
                    }
                )
        if chunk.event.payload.event_type == "step_complete":
            if chunk.event.payload.step_details.step_type == "tool_execution":
                if chunk.event.payload.step_details.tool_calls:
                    tool_name = str(
                        chunk.event.payload.step_details.tool_calls[0].tool_name
                    )
                    return format_stream_data(
                        {
                            "event": "token",
                            "data": {
                                "id": chunk_id,
                                "role": chunk.event.payload.step_type,
                                "token": tool_name,
                            },
                        }
                    )
    return None


@router.post("/streaming_query")
async def streaming_query_endpoint_handler(
    _request: Request,
    query_request: QueryRequest,
    auth: Any = Depends(auth_dependency),
) -> StreamingResponse:
    """Handle request to the /streaming_query endpoint."""
    llama_stack_config = configuration.llama_stack_configuration
    logger.info("LLama stack config: %s", llama_stack_config)
    client = await get_async_llama_stack_client(llama_stack_config)
    model_id = select_model_id(await client.models.list(), query_request)
    conversation_id = retrieve_conversation_id(query_request)
    response = await retrieve_response(client, model_id, query_request)

    async def response_generator(turn_response: Any) -> AsyncIterator[str]:
        """Generate SSE formatted streaming response."""
        chunk_id = 0
        complete_response = ""

        # Send start event
        yield stream_start_event(conversation_id)

        async for chunk in turn_response:
            if event := stream_build_event(chunk, chunk_id):
                complete_response += json.loads(event.replace("data: ", ""))["data"][
                    "token"
                ]
                chunk_id += 1
                yield event

        yield stream_end_event()

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
                truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
                attachments=query_request.attachments or [],
            )

    return StreamingResponse(response_generator(response))


async def retrieve_response(
    client: AsyncLlamaStackClient, model_id: str, query_request: QueryRequest
) -> Any:
    """Retrieve response from LLMs and agents."""
    available_shields = [shield.identifier for shield in await client.shields.list()]
    if not available_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info("Available shields found: %s", available_shields)

    # use system prompt from request or default one
    system_prompt = (
        query_request.system_prompt
        if query_request.system_prompt
        else constants.DEFAULT_SYSTEM_PROMPT
    )
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    agent = AsyncAgent(
        client,  # type: ignore[arg-type]
        model=model_id,
        instructions=system_prompt,
        input_shields=available_shields if available_shields else [],
        tools=[],
    )
    session_id = await agent.create_session("chat_session")
    logger.debug("Session ID: %s", session_id)
    response = await agent.create_turn(
        messages=[UserMessage(role="user", content=query_request.query)],
        session_id=session_id,
        documents=query_request.get_documents(),
        stream=True,
    )

    return response
