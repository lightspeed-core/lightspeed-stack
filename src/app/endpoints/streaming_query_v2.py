"""Streaming query handler using Responses API (v2)."""

import logging
from typing import Annotated, Any, AsyncIterator, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from llama_stack.apis.agents.openai_responses import (
    OpenAIResponseObjectStream,
)
from llama_stack_client import AsyncLlamaStackClient  # type: ignore

from app.endpoints.query import (
    is_transcripts_enabled,
    persist_user_conversation_details,
    validate_attachments_metadata,
)
from app.endpoints.query_v2 import (
    extract_token_usage_from_responses_api,
    get_topic_summary,
    prepare_tools_for_responses_api,
)
from app.endpoints.streaming_query import (
    format_stream_data,
    stream_end_event,
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
from utils.mcp_headers import mcp_headers_dependency
from utils.shields import detect_shield_violations, get_available_shields
from utils.token_counter import TokenCounter
from utils.transcripts import store_transcript
from utils.types import ToolCallSummary, TurnSummary

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["streaming_query_v2"])
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
        summary = TurnSummary(llm_response="", tool_calls=[])

        # Determine media type for response formatting
        media_type = context.query_request.media_type or MEDIA_TYPE_JSON

        # Accumulators for Responses API
        text_parts: list[str] = []
        tool_item_registry: dict[str, dict[str, str]] = {}
        emitted_turn_complete = False

        # Handle conversation id and start event in-band on response.created
        conv_id = context.conversation_id

        # Track the latest response object from response.completed event
        latest_response_object: Any | None = None

        logger.debug("Starting streaming response (Responses API) processing")

        async for chunk in turn_response:
            event_type = getattr(chunk, "type", None)
            logger.debug("Processing chunk %d, type: %s", chunk_id, event_type)

            # Emit start on response.created
            if event_type == "response.created":
                try:
                    conv_id = getattr(chunk, "response").id
                except Exception:  # pylint: disable=broad-except
                    logger.warning("Missing response id!")
                    conv_id = ""
                yield stream_start_event(conv_id)
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

            # Completed response - capture final text and response object
            elif event_type == "response.completed":
                # Capture the response object for token usage extraction
                latest_response_object = getattr(chunk, "response", None)

                # Check for shield violations in the completed response
                if latest_response_object:
                    detect_shield_violations(
                        getattr(latest_response_object, "output", [])
                    )

                if not emitted_turn_complete:
                    final_message = summary.llm_response or "".join(text_parts)
                    if not final_message:
                        final_message = "No response from the model"
                    summary.llm_response = final_message
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

        # Extract token usage from the response object
        token_usage = (
            extract_token_usage_from_responses_api(
                latest_response_object, context.model_id, context.provider_id
            )
            if latest_response_object is not None
            else TokenCounter()
        )

        yield stream_end_event(context.metadata_map, summary, token_usage, media_type)

        # Perform cleanup tasks (database and cache operations)
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
            rag_chunks=[],  # Responses API uses empty list for rag_chunks
        )

    return response_generator


@router.post(
    "/streaming_query",
    response_class=StreamingResponse,
    responses=streaming_query_v2_responses,
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
    # List available shields for Responses API
    available_shields = await get_available_shields(client)

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

    create_params: dict[str, Any] = {
        "input": input_text,
        "model": model_id,
        "instructions": system_prompt,
        "stream": True,
        "store": True,
        "tools": toolgroups,
    }
    if query_request.conversation_id:
        create_params["previous_response_id"] = query_request.conversation_id

    # Add shields to extra_body if available
    if available_shields:
        create_params["extra_body"] = {"guardrails": available_shields}

    response = await client.responses.create(**create_params)
    response_stream = cast(AsyncIterator[OpenAIResponseObjectStream], response)

    # For streaming responses, the ID arrives in the first 'response.created' chunk
    # Return empty conversation_id here; it will be set once the first chunk is received
    return response_stream, ""
