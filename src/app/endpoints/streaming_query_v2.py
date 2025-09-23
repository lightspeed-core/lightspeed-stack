"""Streaming query handler using Responses API (v2)."""

import logging
from typing import Annotated, Any, AsyncIterator, cast

from llama_stack_client import APIConnectionError
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from llama_stack.apis.agents.openai_responses import (
    OpenAIResponseObjectStream,
)

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from starlette import status

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
import metrics
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import QueryRequest
from utils.endpoints import (
    check_configuration_loaded,
    get_system_prompt,
    validate_model_provider_override,
    validate_conversation_ownership,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.query import (
    evaluate_model_hints,
    is_transcripts_enabled,
    persist_user_conversation_details,
    select_model_and_provider_id,
    validate_attachments_metadata,
)
from utils.streaming_query import (
    format_stream_data,
    stream_start_event,
    stream_end_event,
)
from utils.transcripts import store_transcript
from utils.types import TurnSummary, ToolCallSummary

from app.endpoints.query_v2 import (
    get_rag_tools,
    get_mcp_tools,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query_v2"])
auth_dependency = get_auth_dependency()


@router.post("/streaming_query")
@authorize(Action.STREAMING_QUERY)
async def streaming_query_endpoint_handler_v2(  # pylint: disable=too-many-locals
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
            *evaluate_model_hints(user_conversation=None, query_request=query_request),
        )

        response, _ = await retrieve_response(
            client,
            llama_stack_model_id,
            query_request,
            token,
            mcp_headers=mcp_headers,
        )
        metadata_map: dict[str, dict[str, Any]] = {}

        async def response_generator(
            turn_response: AsyncIterator[OpenAIResponseObjectStream],
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
            summary = TurnSummary(llm_response="", tool_calls=[])

            # Accumulators for Responses API
            text_parts: list[str] = []
            tool_item_registry: dict[str, dict[str, str]] = {}
            emitted_turn_complete = False

            # Handle conversation id and start event in-band on response.created
            conv_id = ""

            logger.debug("Starting streaming response (Responses API) processing")

            async for chunk in turn_response:
                event_type = getattr(chunk, "type", None)
                logger.debug("Processing chunk %d, type: %s", chunk_id, event_type)

                # Emit start and persist on response.created
                if event_type == "response.created":
                    try:
                        conv_id = getattr(chunk, "response").id
                    except Exception:
                        conv_id = ""
                    yield stream_start_event(conv_id)
                    if conv_id:
                        persist_user_conversation_details(
                            user_id=user_id,
                            conversation_id=conv_id,
                            model=model_id,
                            provider_id=provider_id,
                        )
                    continue

                # Text streaming
                if event_type == "response.output_text.delta":
                    delta = getattr(chunk, "delta", "")
                    if delta:
                        text_parts.append(delta)
                        yield format_stream_data(
                            {
                                "event": "token",
                                "data": {
                                    "id": chunk_id,
                                    "token": delta,
                                },
                            }
                        )
                        chunk_id += 1

                # Final text of the output (capture, but emit at response.completed)
                elif event_type == "response.output_text.done":
                    final_text = getattr(chunk, "text", "")
                    if final_text:
                        summary.llm_response = final_text

                # Content part started - emit an empty token to kick off UI streaming if desired
                elif event_type == "response.content_part.added":
                    yield format_stream_data(
                        {
                            "event": "token",
                            "data": {
                                "id": chunk_id,
                                "token": "",
                            },
                        }
                    )
                    chunk_id += 1

                # Track tool call items as they are added so we can build a summary later
                elif event_type == "response.output_item.added":
                    item = getattr(chunk, "item", None)
                    item_type = getattr(item, "type", None)
                    if item and item_type == "function_call":
                        item_id = getattr(item, "id", "")
                        name = getattr(item, "name", "function_call")
                        call_id = getattr(item, "call_id", item_id)
                        if item_id:
                            tool_item_registry[item_id] = {
                                "name": name,
                                "call_id": call_id,
                            }

                # Stream tool call arguments as tool_call events
                elif event_type == "response.function_call_arguments.delta":
                    delta = getattr(chunk, "delta", "")
                    yield format_stream_data(
                        {
                            "event": "tool_call",
                            "data": {
                                "id": chunk_id,
                                "role": "tool_execution",
                                "token": delta,
                            },
                        }
                    )
                    chunk_id += 1

                # Finalize tool call arguments and append to summary
                elif event_type in (
                    "response.function_call_arguments.done",
                    "response.mcp_call.arguments.done",
                ):
                    item_id = getattr(chunk, "item_id", "")
                    arguments = getattr(chunk, "arguments", "")
                    meta = tool_item_registry.get(item_id, {})
                    summary.tool_calls.append(
                        ToolCallSummary(
                            id=meta.get("call_id", item_id or "unknown"),
                            name=meta.get("name", "tool_call"),
                            args=arguments,
                            response=None,
                        )
                    )

                # Completed response - capture final text if any
                elif event_type == "response.completed":
                    if not emitted_turn_complete:
                        final_message = summary.llm_response or "".join(text_parts)
                        yield format_stream_data(
                            {
                                "event": "turn_complete",
                                "data": {
                                    "id": chunk_id,
                                    "token": final_message,
                                },
                            }
                        )
                        chunk_id += 1
                        emitted_turn_complete = True

                # Ignore other event types for now; could add heartbeats if desired

            logger.debug(
                "Streaming complete - Tool calls: %d, Response chars: %d",
                len(summary.tool_calls),
                len(summary.llm_response),
            )

            yield stream_end_event(metadata_map)

            if not is_transcripts_enabled():
                logger.debug("Transcript collection is disabled in the configuration")
            else:
                store_transcript(
                    user_id=user_id,
                    conversation_id=conv_id,
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

        # Conversation persistence is handled inside the stream
        # once the response.created event provides the ID

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
) -> tuple[AsyncIterator[OpenAIResponseObjectStream], str]:
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
    logger.info("Shields are not yet supported in Responses API. Disabling safety")

    # use system prompt from request or default one
    system_prompt = get_system_prompt(query_request, configuration)
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    # Prepare tools for responses API
    tools: list[dict[str, Any]] = []
    if not query_request.no_tools:
        # Get vector databases for RAG tools
        vector_db_ids = [
            vector_db.identifier for vector_db in await client.vector_dbs.list()
        ]

        # Add RAG tools if vector databases are available
        rag_tools = get_rag_tools(vector_db_ids)
        if rag_tools:
            tools.extend(rag_tools)

        # Add MCP server tools
        mcp_tools = get_mcp_tools(configuration.mcp_servers, token)
        if mcp_tools:
            tools.extend(mcp_tools)
            logger.debug(
                "Configured %d MCP tools: %s",
                len(mcp_tools),
                [tool.get("server_label", "unknown") for tool in mcp_tools],
            )

    response = await client.responses.create(
        input=query_request.query,
        model=model_id,
        instructions=system_prompt,
        previous_response_id=query_request.conversation_id,
        tools=(cast(Any, tools) if tools else cast(Any, None)),
        stream=True,
        store=True,
    )

    response_stream = cast(AsyncIterator[OpenAIResponseObjectStream], response)

    # For streaming responses, the ID arrives in the first 'response.created' chunk
    # Return empty conversation_id here; it will be set once the first chunk is received
    return response_stream, ""
