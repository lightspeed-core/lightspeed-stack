"""Handler for REST API call to provide answer to streaming query."""

import json
import logging
import re
from typing import Any, AsyncIterator

from cachetools import TTLCache  # type: ignore

from llama_stack_client import APIConnectionError
from llama_stack_client.lib.agents.agent import AsyncAgent  # type: ignore
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack_client.types.shared.interleaved_content_item import TextContentItem
from llama_stack_client.types import UserMessage  # type: ignore

from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import StreamingResponse

from auth import get_auth_dependency
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.requests import QueryRequest
from utils.endpoints import check_configuration_loaded, get_system_prompt
from utils.common import retrieve_user_id
from utils.mcp_headers import mcp_headers_dependency
from utils.suid import get_suid
from utils.token_counter import get_token_counter
from utils.types import GraniteToolParser

from app.endpoints.query import (
    get_rag_toolgroups,
    is_transcripts_enabled,
    store_transcript,
    select_model_id,
    validate_attachments_metadata,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query"])
auth_dependency = get_auth_dependency()

# Global agent registry to persist agents across requests
_agent_cache: TTLCache[str, AsyncAgent] = TTLCache(maxsize=1000, ttl=3600)


async def get_agent(
    client: AsyncLlamaStackClient,
    model_id: str,
    system_prompt: str,
    available_shields: list[str],
    conversation_id: str | None,
) -> tuple[AsyncAgent, str]:
    """Get existing agent or create a new one with session persistence."""
    if conversation_id is not None:
        agent = _agent_cache.get(conversation_id)
        if agent:
            logger.debug("Reusing existing agent with key: %s", conversation_id)
            return agent, conversation_id

    logger.debug("Creating new agent")
    agent = AsyncAgent(
        client,  # type: ignore[arg-type]
        model=model_id,
        instructions=system_prompt,
        input_shields=available_shields if available_shields else [],
        tool_parser=GraniteToolParser.get_parser(model_id),
        enable_session_persistence=True,
    )
    conversation_id = await agent.create_session(get_suid())
    _agent_cache[conversation_id] = agent
    return agent, conversation_id


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


def stream_end_event(metadata_map: dict, metrics_map: dict[str, int]) -> str:
    """Yield the end of the data stream.

    Args:
        metadata_map: Dictionary containing metadata about referenced documents
        metrics_map: Dictionary containing metrics like 'input_tokens' and 'output_tokens'
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
                "input_tokens": metrics_map.get("input_tokens", 0),
                "output_tokens": metrics_map.get("output_tokens", 0),
            },
            "available_quotas": {},  # TODO(jboos): implement available quotas
        }
    )


def stream_build_event(chunk: Any, chunk_id: int, metadata_map: dict) -> str | None:
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
    # pylint: disable=R1702
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
        if (
            chunk.event.payload.event_type == "step_complete"
            and chunk.event.payload.step_details.step_type == "tool_execution"
        ):
            for r in chunk.event.payload.step_details.tool_responses:
                if r.tool_name == "knowledge_search" and r.content:
                    for text_content_item in r.content:
                        if isinstance(text_content_item, TextContentItem):
                            for match in METADATA_PATTERN.findall(
                                text_content_item.text
                            ):
                                meta = json.loads(match.replace("'", '"'))
                                metadata_map[meta["document_id"]] = meta
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
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> StreamingResponse:
    """Handle request to the /streaming_query endpoint."""
    check_configuration_loaded(configuration)

    llama_stack_config = configuration.llama_stack_configuration
    logger.info("LLama stack config: %s", llama_stack_config)

    try:
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        model_id = select_model_id(await client.models.list(), query_request)
        response, conversation_id, token_usage = await retrieve_response(
            client,
            model_id,
            query_request,
            auth,
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
                if event := stream_build_event(chunk, chunk_id, metadata_map):
                    complete_response += json.loads(event.replace("data: ", ""))[
                        "data"
                    ]["token"]
                    chunk_id += 1
                    yield event

            # Currently (2025-07-08) the usage is not returned by the API, so we need to estimate
            # try:
            #     output_tokens = response.usage.get("completion_tokens", 0)
            # except AttributeError:
            # Estimate output tokens from complete response
            try:
                output_tokens = get_token_counter(model_id).count_tokens(
                    complete_response
                )
                logger.debug("Estimated output tokens: %s", output_tokens)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to estimate output tokens: %s", e)
                output_tokens = 0

            metrics_map = {
                "input_tokens": token_usage["input_tokens"],
                "output_tokens": output_tokens,
            }
            yield stream_end_event(metadata_map, metrics_map)

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

        return StreamingResponse(response_generator(response))
    # connection to Llama Stack server
    except APIConnectionError as e:
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
) -> tuple[Any, str, dict[str, int]]:
    """Retrieve response from LLMs and agents."""
    available_shields = [shield.identifier for shield in await client.shields.list()]
    if not available_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info("Available shields found: %s", available_shields)

    # use system prompt from request or default one
    system_prompt = get_system_prompt(query_request, configuration)
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    agent, conversation_id = await get_agent(
        client,
        model_id,
        system_prompt,
        available_shields,
        query_request.conversation_id,
    )

    # preserve compatibility when mcp_headers is not provided
    if mcp_headers is None:
        mcp_headers = {}
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
    response = await agent.create_turn(
        messages=[UserMessage(role="user", content=query_request.query)],
        session_id=conversation_id,
        documents=query_request.get_documents(),
        stream=True,
        toolgroups=toolgroups or None,
    )

    # Currently (2025-07-08) the usage is not returned by the API, so we need to estimate it
    # try:
    #     token_usage = {
    #         "input_tokens": response.usage.get("prompt_tokens", 0),
    #         "output_tokens": 0,  # Will be calculated during streaming
    #     }
    # except AttributeError:
    #     # Estimate input tokens (Output will be calculated during streaming)
    try:
        token_usage = get_token_counter(model_id).count_turn_tokens(
            system_prompt, query_request.query
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to estimate token usage: %s", e)
        token_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
        }

    return response, conversation_id, token_usage
