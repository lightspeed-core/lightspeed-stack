"""Handler for REST API call to provide streaming answer to query using Agent API."""

import json
import logging
import re
from typing import Annotated, Any, AsyncIterator, cast

from llama_stack_client import APIConnectionError
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack_client.lib.agents.event_logger import interleaved_content_as_str
from llama_stack_client.types import UserMessage  # type: ignore
from llama_stack_client.types.agents.agent_turn_response_stream_chunk import (
    AgentTurnResponseStreamChunk,
)

from fastapi import APIRouter, HTTPException, Request, status, Depends
from fastapi.responses import StreamingResponse

from app.endpoints.query import (
    get_rag_toolgroups,
)
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
import metrics
from metrics.utils import update_llm_token_count_from_turn
from models.config import Action
from models.requests import QueryRequest
from models.responses import UnauthorizedResponse, ForbiddenResponse
from models.database.conversations import UserConversation
from utils.endpoints import (
    check_configuration_loaded,
    get_agent,
    get_system_prompt,
    validate_model_provider_override,
    validate_conversation_ownership,
)
from utils.mcp_headers import mcp_headers_dependency, handle_mcp_headers_with_toolgroups
from utils.transcripts import store_transcript
from utils.types import TurnSummary
from utils.query import (
    is_input_shield,
    is_output_shield,
    is_transcripts_enabled,
    select_model_and_provider_id,
    validate_attachments_metadata,
    persist_user_conversation_details,
    evaluate_model_hints,
)
from utils.streaming_query import (
    stream_start_event,
    stream_end_event,
    stream_build_event,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query"])
auth_dependency = get_auth_dependency()

streaming_query_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Streaming response with Server-Sent Events",
        "content": {
            "text/event-stream": {
                "schema": {
                    "type": "string",
                    "example": (
                        'data: {"event": "start", '
                        '"data": {"conversation_id": "123e4567-e89b-12d3-a456-426614174000"}}\n\n'
                        'data: {"event": "token", "data": {"id": 0, "role": "inference", '
                        '"token": "Hello"}}\n\n'
                        'data: {"event": "end", "data": {"referenced_documents": [], '
                        '"truncated": null, "input_tokens": 0, "output_tokens": 0}, '
                        '"available_quotas": {}}\n\n'
                    ),
                }
            }
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


@router.post("/streaming_query", responses=streaming_query_responses)
@authorize(Action.STREAMING_QUERY)
async def streaming_query_endpoint_handler(  # pylint: disable=too-many-locals
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
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
                    rag_chunks=[],  # TODO(lucasagomes): implement rag_chunks
                    truncated=False,  # TODO(lucasagomes): implement truncation as part
                    # of quota work
                    attachments=query_request.attachments or [],
                )

        persist_user_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id,
            model=model_id,
            provider_id=provider_id,
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
