"""Streaming query handler using Responses API (v2)."""

import logging
from typing import Annotated, Any, AsyncIterator, Optional, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from llama_stack_api.openai_responses import (
    OpenAIResponseObject,
    OpenAIResponseObjectStream,
    OpenAIResponseObjectStreamResponseCompleted,
    OpenAIResponseObjectStreamResponseFailed,
    OpenAIResponseObjectStreamResponseOutputItemDone,
    OpenAIResponseObjectStreamResponseOutputTextDelta,
    OpenAIResponseObjectStreamResponseOutputTextDone,
)
from llama_stack_client import AsyncLlamaStackClient

from app.endpoints.query import (
    is_transcripts_enabled,
    persist_user_conversation_details,
    validate_attachments_metadata,
)
from app.endpoints.query_v2 import (
    _build_tool_call_summary,
    extract_token_usage_from_responses_api,
    get_topic_summary,
    parse_referenced_documents_from_responses_api,
    prepare_tools_for_responses_api,
)
from app.endpoints.streaming_query import (
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
    format_stream_data,
    stream_end_event,
    stream_event,
    stream_start_event,
    streaming_query_endpoint_handler_base,
)
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from constants import MEDIA_TYPE_JSON
from models.config import Action
from models.context import ResponseGeneratorContext
from models.requests import QueryRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    StreamingQueryResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from utils.endpoints import (
    cleanup_after_streaming,
    get_system_prompt,
)
from utils.query import create_violation_stream
from utils.quota import consume_tokens, get_available_quotas
from utils.suid import normalize_conversation_id, to_llama_stack_conversation_id
from utils.mcp_headers import mcp_headers_dependency
from utils.shields import (
    append_turn_to_conversation,
    run_shield_moderation,
)
from utils.token_counter import TokenCounter
from utils.transcripts import store_transcript
from utils.types import RAGChunk, TurnSummary

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query_v1"])
auth_dependency = get_auth_dependency()

streaming_query_v2_responses: dict[int | str, dict[str, Any]] = {
    200: StreamingQueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["conversation read", "endpoint", "model override"]
    ),
    404: NotFoundResponse.openapi_response(
        examples=["conversation", "model", "provider"]
    ),
    # 413: PromptTooLongResponse.openapi_response(),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


def create_responses_response_generator(  # pylint: disable=too-many-locals,too-many-statements
    context: ResponseGeneratorContext,
) -> Any:
    """
    Create a response generator function for Responses API streaming.

    This factory function returns an async generator that processes streaming
    responses from the Responses API and yields Server-Sent Events (SSE).

    Args:
        context: Context object containing all necessary parameters for response generation

    Returns:
        An async generator function that yields SSE-formatted strings
    """

    async def response_generator(  # pylint: disable=too-many-branches,too-many-statements
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
        summary = TurnSummary(
            llm_response="", tool_calls=[], tool_results=[], rag_chunks=[]
        )

        # Determine media type for response formatting
        media_type = context.query_request.media_type or MEDIA_TYPE_JSON

        # Accumulators for Responses API
        text_parts: list[str] = []
        emitted_turn_complete = False

        # Use the conversation_id from context (either provided or newly created)
        conv_id = context.conversation_id

        # Track the latest response object from response.completed event
        latest_response_object: Optional[Any] = None

        # RAG chunks
        rag_chunks: list[RAGChunk] = []

        logger.debug("Starting streaming response (Responses API) processing")

        async for chunk in turn_response:
            event_type = getattr(chunk, "type", None)
            logger.debug("Processing chunk %d, type: %s", chunk_id, event_type)

            # Emit start event when response is created
            if event_type == "response.created":
                yield stream_start_event(conv_id)

            # Text streaming
            if event_type == "response.output_text.delta":
                delta_chunk = cast(
                    OpenAIResponseObjectStreamResponseOutputTextDelta, chunk
                )
                if delta_chunk.delta:
                    text_parts.append(delta_chunk.delta)
                    yield stream_event(
                        {
                            "id": chunk_id,
                            "token": delta_chunk.delta,
                        },
                        LLM_TOKEN_EVENT,
                        media_type,
                    )
                    chunk_id += 1

            # Final text of the output (capture, but emit at response.completed)
            elif event_type == "response.output_text.done":
                text_done_chunk = cast(
                    OpenAIResponseObjectStreamResponseOutputTextDone, chunk
                )
                if text_done_chunk.text:
                    summary.llm_response = text_done_chunk.text

            # Content part started - emit an empty token to kick off UI streaming
            elif event_type == "response.content_part.added":
                yield stream_event(
                    {
                        "id": chunk_id,
                        "token": "",
                    },
                    LLM_TOKEN_EVENT,
                    media_type,
                )
                chunk_id += 1

            # Process tool calls and results are emitted together when output items are done
            # TODO(asimurka): support emitting tool calls and results separately when ready
            elif event_type == "response.output_item.done":
                output_item_done_chunk = cast(
                    OpenAIResponseObjectStreamResponseOutputItemDone, chunk
                )
                if output_item_done_chunk.item.type == "message":
                    continue
                tool_call, tool_result = _build_tool_call_summary(
                    output_item_done_chunk.item, rag_chunks
                )
                if tool_call:
                    summary.tool_calls.append(tool_call)
                    yield stream_event(
                        tool_call.model_dump(),
                        LLM_TOOL_CALL_EVENT,
                        media_type,
                    )
                if tool_result:
                    summary.tool_results.append(tool_result)
                    yield stream_event(
                        tool_result.model_dump(),
                        LLM_TOOL_RESULT_EVENT,
                        media_type,
                    )

            # Completed response - capture final text and response object
            elif event_type == "response.completed":
                # Capture the response object for token usage extraction
                completed_chunk = cast(
                    OpenAIResponseObjectStreamResponseCompleted, chunk
                )
                latest_response_object = completed_chunk.response

                if not emitted_turn_complete:
                    final_message = summary.llm_response or "".join(text_parts)
                    if not final_message:
                        final_message = "No response from the model"
                    summary.llm_response = final_message
                    yield stream_event(
                        {
                            "id": chunk_id,
                            "token": final_message,
                        },
                        "turn_complete",
                        media_type,
                    )
                    chunk_id += 1
                    emitted_turn_complete = True

            # Incomplete response - emit error because LLS does not
            # support incomplete responses "incomplete_detail" attribute yet
            elif event_type == "response.incomplete":
                error_response = InternalServerErrorResponse.query_failed(
                    "An unexpected error occurred while processing the request."
                )
                logger.error("Incomplete response received during streaming")
                yield format_stream_data(
                    {"event": "error", "data": {**error_response.detail.model_dump()}}
                )
                return

            # Failed response - emit error with custom cause from error message
            elif event_type == "response.failed":
                failed_chunk = cast(OpenAIResponseObjectStreamResponseFailed, chunk)
                latest_response_object = failed_chunk.response
                error_message = (
                    failed_chunk.response.error.message
                    if failed_chunk.response.error
                    else "An unexpected error occurred while processing the request."
                )
                error_response = InternalServerErrorResponse.query_failed(error_message)
                logger.error("Failed response during streaming: %s", error_message)
                yield format_stream_data(
                    {"event": "error", "data": {**error_response.detail.model_dump()}}
                )
                return

        logger.debug(
            "Streaming complete - Tool calls: %d, Response chars: %d",
            len(summary.tool_calls),
            len(summary.llm_response),
        )

        # Extract token usage from the response object
        token_usage = (
            extract_token_usage_from_responses_api(
                latest_response_object, context.model_id, context.provider_id
            )
            if latest_response_object is not None
            else TokenCounter()
        )
        consume_tokens(
            configuration.quota_limiters,
            configuration.token_usage_history,
            context.user_id,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            model_id=context.model_id,
            provider_id=context.provider_id,
        )
        referenced_documents = parse_referenced_documents_from_responses_api(
            cast(OpenAIResponseObject, latest_response_object)
        )
        available_quotas = get_available_quotas(
            configuration.quota_limiters, context.user_id
        )
        yield stream_end_event(
            context.metadata_map,
            token_usage,
            available_quotas,
            referenced_documents,
            media_type,
        )

        # Perform cleanup tasks (database and cache operations))
        await cleanup_after_streaming(
            user_id=context.user_id,
            conversation_id=conv_id,
            model_id=context.model_id,
            provider_id=context.provider_id,
            llama_stack_model_id=context.llama_stack_model_id,
            query_request=context.query_request,
            summary=summary,
            metadata_map=context.metadata_map,
            started_at=context.started_at,
            client=context.client,
            config=configuration,
            skip_userid_check=context.skip_userid_check,
            get_topic_summary_func=get_topic_summary,
            is_transcripts_enabled_func=is_transcripts_enabled,
            store_transcript_func=store_transcript,
            persist_user_conversation_details_func=persist_user_conversation_details,
            rag_chunks=[rag_chunk.model_dump() for rag_chunk in rag_chunks],
        )

    return response_generator


@router.post(
    "/streaming_query",
    response_class=StreamingResponse,
    responses=streaming_query_v2_responses,
    summary="Streaming Query Endpoint Handler V1",
)
@authorize(Action.STREAMING_QUERY)
async def streaming_query_endpoint_handler_v2(  # pylint: disable=too-many-locals
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(auth_dependency)],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> StreamingResponse:
    """
    Handle request to the /streaming_query endpoint using Responses API.

    Returns a streaming response using Server-Sent Events (SSE) format with
    content type text/event-stream.

    Returns:
        StreamingResponse: An HTTP streaming response yielding
        SSE-formatted events for the query lifecycle with content type
        text/event-stream.

    Raises:
        HTTPException:
            - 401: Unauthorized - Missing or invalid credentials
            - 403: Forbidden - Insufficient permissions or model override not allowed
            - 404: Not Found - Conversation, model, or provider not found
            - 422: Unprocessable Entity - Request validation failed
            - 429: Too Many Requests - Quota limit exceeded
            - 500: Internal Server Error - Configuration not loaded or other server errors
            - 503: Service Unavailable - Unable to connect to Llama Stack backend
    """
    return await streaming_query_endpoint_handler_base(
        request=request,
        query_request=query_request,
        auth=auth,
        mcp_headers=mcp_headers,
        retrieve_response_func=retrieve_response,
        create_response_generator_func=create_responses_response_generator,
    )


async def retrieve_response(  # pylint: disable=too-many-locals
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: Optional[dict[str, dict[str, str]]] = None,
) -> tuple[AsyncIterator[OpenAIResponseObjectStream], str]:
    """
    Retrieve response from LLMs and agents.

    Asynchronously retrieves a streaming response and conversation
    ID from the Llama Stack agent for a given user query.

    This function configures shields, system prompt, and tool usage
    based on the request and environment. It prepares the agent with
    appropriate headers and toolgroups, validates attachments if
    present, and initiates a streaming turn with the user's query
    and any provided documents.

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
    # use system prompt from request or default one
    system_prompt = get_system_prompt(query_request, configuration)
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    # Prepare tools for responses API
    toolgroups = await prepare_tools_for_responses_api(
        client, query_request, token, configuration, mcp_headers
    )

    # Prepare input for Responses API
    # Convert attachments to text and concatenate with query
    input_text = query_request.query
    if query_request.attachments:
        for attachment in query_request.attachments:
            input_text += (
                f"\n\n[Attachment: {attachment.attachment_type}]\n"
                f"{attachment.content}"
            )

    # Handle conversation ID for Responses API
    # Create conversation upfront if not provided
    conversation_id = query_request.conversation_id
    if conversation_id:
        # Conversation ID was provided - convert to llama-stack format
        logger.debug("Using existing conversation ID: %s", conversation_id)
        llama_stack_conv_id = to_llama_stack_conversation_id(conversation_id)
    else:
        # No conversation_id provided - create a new conversation first
        logger.debug("No conversation_id provided, creating new conversation")
        conversation = await client.conversations.create(metadata={})
        llama_stack_conv_id = conversation.id
        # Store the normalized version for later use
        conversation_id = normalize_conversation_id(llama_stack_conv_id)
        logger.info(
            "Created new conversation with ID: %s (normalized: %s)",
            llama_stack_conv_id,
            conversation_id,
        )

    # Run shield moderation before calling LLM
    moderation_result = await run_shield_moderation(client, input_text)
    if moderation_result.blocked:
        violation_message = moderation_result.message or ""
        await append_turn_to_conversation(
            client, llama_stack_conv_id, input_text, violation_message
        )
        return (
            create_violation_stream(violation_message, moderation_result.shield_model),
            normalize_conversation_id(conversation_id),
        )

    create_params: dict[str, Any] = {
        "input": input_text,
        "model": model_id,
        "instructions": system_prompt,
        "stream": True,
        "store": True,
        "tools": toolgroups,
        "conversation": llama_stack_conv_id,
    }

    # Log request details before calling Llama Stack (same as non-streaming)
    if toolgroups:
        rag_tool_count = sum(1 for t in toolgroups if t.get("type") == "file_search")
        mcp_tool_count = sum(1 for t in toolgroups if t.get("type") == "mcp")
        logger.debug(
            "Calling Llama Stack Responses API (streaming) with %d tool(s): %d RAG + %d MCP",
            len(toolgroups),
            rag_tool_count,
            mcp_tool_count,
        )
        # Log MCP server endpoints that may be called
        mcp_servers = [
            (t.get("server_label"), t.get("server_url"))
            for t in toolgroups
            if t.get("type") == "mcp"
        ]
        if mcp_servers:
            logger.debug("MCP server endpoints that may be called:")
            for server_name, server_url in mcp_servers:
                logger.debug("  - %s: %s", server_name, server_url)
    else:
        logger.debug("Calling Llama Stack Responses API (streaming) without tools")

    response = await client.responses.create(**create_params)
    response_stream = cast(AsyncIterator[OpenAIResponseObjectStream], response)

    return response_stream, normalize_conversation_id(conversation_id)
