"""Streaming query handler using Responses API."""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Any, AsyncIterator, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api.openai_responses import (
    OpenAIResponseObject,
    OpenAIResponseObjectStream,
    OpenAIResponseObjectStreamResponseMcpCallArgumentsDone as MCPArgsDoneChunk,
    OpenAIResponseObjectStreamResponseOutputItemAdded as OutputItemAddedChunk,
    OpenAIResponseObjectStreamResponseOutputItemDone as OutputItemDoneChunk,
    OpenAIResponseObjectStreamResponseOutputTextDelta as TextDeltaChunk,
    OpenAIResponseObjectStreamResponseOutputTextDone as TextDoneChunk,
    OpenAIResponseOutputMessageMCPCall as MCPCall,
)
from llama_stack_client import (
    APIConnectionError,
    APIStatusError as LLSApiStatusError,
)
from openai._exceptions import APIStatusError as OpenAIAPIStatusError
import metrics
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import (
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
    LLM_TURN_COMPLETE_EVENT,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
)
from models.config import Action
from models.context import ResponseGeneratorContext
from models.requests import QueryRequest
from models.responses import (
    AbstractErrorResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    StreamingQueryResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from utils.types import RAGChunk, ReferencedDocument
from utils.endpoints import (
    check_configuration_loaded,
    validate_and_retrieve_conversation,
)
from utils.mcp_headers import mcp_headers_dependency, McpHeaders
from utils.query import (
    consume_query_tokens,
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    store_query_results,
    update_azure_token,
    validate_attachments_metadata,
    validate_model_provider_override,
)
from utils.quota import check_tokens_available, get_available_quotas
from utils.responses import (
    build_mcp_tool_call_from_arguments_done,
    build_tool_call_summary,
    build_tool_result_from_mcp_output_item_done,
    extract_token_usage,
    get_topic_summary,
    parse_referenced_documents,
    prepare_responses_params,
)
from utils.shields import (
    append_turn_to_conversation,
    run_shield_moderation,
)
from utils.suid import normalize_conversation_id
from utils.token_counter import TokenCounter
from utils.types import ResponsesApiParams, TurnSummary
from utils.vector_search import format_rag_context_for_injection, perform_vector_search

logger = logging.getLogger(__name__)
router = APIRouter(tags=["streaming_query"])

streaming_query_responses: dict[int | str, dict[str, Any]] = {
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


@router.post(
    "/streaming_query",
    response_class=StreamingResponse,
    responses=streaming_query_responses,
    summary="Streaming Query Endpoint Handler",
)
@authorize(Action.STREAMING_QUERY)
async def streaming_query_endpoint_handler(  # pylint: disable=too-many-locals
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: McpHeaders = Depends(mcp_headers_dependency),
) -> StreamingResponse:
    """
    Handle request to the /streaming_query endpoint using Responses API.

    Returns a streaming response using Server-Sent Events (SSE) format with
    content type text/event-stream.

    Returns:
        SSE-formatted events for the query lifecycle.

    Raises:
        HTTPException:
            - 401: Unauthorized - Missing or invalid credentials
            - 403: Forbidden - Insufficient permissions or model override not allowed
            - 404: Not Found - Conversation, model, or provider not found
            - 413: Prompt too long - Prompt exceeded model's context window size
            - 422: Unprocessable Entity - Request validation failed
            - 429: Quota limit exceeded - The token quota for model or user has been exceeded
            - 500: Internal Server Error - Configuration not loaded or other server errors
            - 503: Service Unavailable - Unable to connect to Llama Stack backend
    """
    check_configuration_loaded(configuration)

    user_id, _user_name, _skip_userid_check, token = auth
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Check token availability
    check_tokens_available(configuration.quota_limiters, user_id)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(query_request, request.state.authorized_actions)

    # Validate attachments if provided
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    # Retrieve conversation if conversation_id is provided
    user_conversation = None
    if query_request.conversation_id:
        logger.debug(
            "Conversation ID specified in query: %s", query_request.conversation_id
        )
        normalized_conv_id = normalize_conversation_id(query_request.conversation_id)
        user_conversation = validate_and_retrieve_conversation(
            normalized_conv_id=normalized_conv_id,
            user_id=user_id,
            others_allowed=Action.READ_OTHERS_CONVERSATIONS
            in request.state.authorized_actions,
        )

    client = AsyncLlamaStackClientHolder().get_client()

    pre_rag_chunks: list[RAGChunk] = []
    doc_ids_from_chunks: list[ReferencedDocument] = []

    _, _, doc_ids_from_chunks, pre_rag_chunks = await perform_vector_search(
        client, query_request, configuration
    )
    rag_context = format_rag_context_for_injection(pre_rag_chunks)
    if rag_context:
        query_request = query_request.model_copy(deep=True)
        query_request.query = query_request.query + rag_context

    # Prepare API request parameters
    responses_params = await prepare_responses_params(
        client=client,
        query_request=query_request,
        user_conversation=user_conversation,
        token=token,
        mcp_headers=mcp_headers,
        stream=True,
        store=True,
    )

    # Handle Azure token refresh if needed
    if (
        responses_params.model.startswith("azure")
        and AzureEntraIDManager().is_entra_id_configured
        and AzureEntraIDManager().is_token_expired
        and AzureEntraIDManager().refresh_token()
    ):
        client = await update_azure_token(client)

    # Create context
    context = ResponseGeneratorContext(
        conversation_id=normalize_conversation_id(responses_params.conversation),
        model_id=responses_params.model,
        user_id=user_id,
        skip_userid_check=_skip_userid_check,
        query_request=query_request,
        started_at=started_at,
        client=client,
    )

    # Update metrics for the LLM call
    provider_id, model_id = extract_provider_and_model_from_model_id(
        responses_params.model
    )
    metrics.llm_calls_total.labels(provider_id, model_id).inc()

    generator, turn_summary = await retrieve_response_generator(
        responses_params=responses_params,
        context=context,
        doc_ids_from_chunks=doc_ids_from_chunks,
    )

    response_media_type = (
        MEDIA_TYPE_TEXT
        if query_request.media_type == MEDIA_TYPE_TEXT
        else MEDIA_TYPE_EVENT_STREAM
    )

    return StreamingResponse(
        generate_response(
            generator=generator,
            context=context,
            responses_params=responses_params,
            turn_summary=turn_summary,
        ),
        media_type=query_request.media_type or MEDIA_TYPE_TEXT,
    )


async def retrieve_response_generator(
    responses_params: ResponsesApiParams,
    context: ResponseGeneratorContext,
    doc_ids_from_chunks: list[ReferencedDocument],
) -> tuple[AsyncIterator[str], TurnSummary]:
    """
    Retrieve the appropriate response generator.

    Handles shield moderation check and retrieves response.
    Returns the generator (shield violation or response generator) and turn_summary.
    Fills turn_summary attributes for token usage, referenced documents, and tool calls.

    Args:
        responses_params: The Responses API parameters
        context: The response generator context

    Returns:
        tuple[AsyncIterator[str], TurnSummary]: The response generator and turn summary

    """
    turn_summary = TurnSummary()
    try:
        moderation_result = await run_shield_moderation(
            context.client, responses_params.input
        )
        if moderation_result.blocked:
            violation_message = moderation_result.message or ""
            turn_summary.llm_response = violation_message
            await append_turn_to_conversation(
                context.client,
                responses_params.conversation,
                responses_params.input,
                violation_message,
            )
            media_type = context.query_request.media_type or MEDIA_TYPE_JSON
            return (
                shield_violation_generator(violation_message, media_type),
                turn_summary,
            )
        # Retrieve response stream (may raise exceptions)
        response = await context.client.responses.create(
            **responses_params.model_dump()
        )
        # Store pre-RAG documents for later merging
        turn_summary.pre_rag_documents = doc_ids_from_chunks
        return response_generator(response, context, turn_summary), turn_summary

    # Handle know LLS client errors only at stream creation time and shield execution
    except RuntimeError as e:  # library mode wraps 413 into runtime error
        if "context_length" in str(e).lower():
            error_response = PromptTooLongResponse(model=responses_params.model)
            raise HTTPException(**error_response.model_dump()) from e
        raise e
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e

    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        error_response = handle_known_apistatus_errors(e, responses_params.model)
        raise HTTPException(**error_response.model_dump()) from e


async def generate_response(
    generator: AsyncIterator[str],
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
) -> AsyncIterator[str]:
    """Wrap a generator with cleanup logic.

    Re-yields events from the generator, handles errors, and ensures
    persistence and token consumption after completion.

    Args:
        generator: The base generator to wrap
        context: The response generator context
        responses_params: The Responses API parameters
        turn_summary: TurnSummary populated during streaming

    Yields:
        SSE-formatted strings from the wrapped generator
    """
    yield stream_start_event(context.conversation_id)

    # Re-yield all events from the generator
    try:
        async for event in generator:
            yield event

    # Handle known LLS client errors during response generation time
    except RuntimeError as e:  # library mode wraps 413 into runtime error
        error_response = (
            PromptTooLongResponse(model=responses_params.model)
            if "context_length" in str(e).lower()
            else InternalServerErrorResponse.generic()
        )
        yield stream_http_error_event(error_response, context.query_request.media_type)
        return
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        yield stream_http_error_event(error_response, context.query_request.media_type)
        return
    except (LLSApiStatusError, OpenAIAPIStatusError) as e:
        error_response = handle_known_apistatus_errors(e, responses_params.model)
        yield stream_http_error_event(error_response, context.query_request.media_type)
        return

    # Get topic summary for new conversations if needed
    topic_summary = None
    if not context.query_request.conversation_id:
        should_generate = context.query_request.generate_topic_summary
        if should_generate:
            logger.debug("Generating topic summary for new conversation")
            topic_summary = await get_topic_summary(
                context.query_request.query,
                context.client,
                responses_params.model,
            )

    # Consume tokens
    logger.info("Consuming tokens")
    consume_query_tokens(
        user_id=context.user_id,
        model_id=responses_params.model,
        token_usage=turn_summary.token_usage,
        configuration=configuration,
    )
    # Get available quotas
    logger.info("Getting available quotas")
    available_quotas = get_available_quotas(
        quota_limiters=configuration.quota_limiters, user_id=context.user_id
    )

    yield stream_end_event(
        turn_summary.token_usage,
        available_quotas,
        turn_summary.referenced_documents,
        context.query_request.media_type or MEDIA_TYPE_JSON,
    )
    completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Store query results (transcript, conversation details, cache)
    logger.info("Storing query results")
    store_query_results(
        user_id=context.user_id,
        conversation_id=context.conversation_id,
        model=responses_params.model,
        completed_at=completed_at,
        started_at=context.started_at,
        summary=turn_summary,
        query_request=context.query_request,
        configuration=configuration,
        skip_userid_check=context.skip_userid_check,
        topic_summary=topic_summary,
    )


async def response_generator(  # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    turn_response: AsyncIterator[OpenAIResponseObjectStream],
    context: ResponseGeneratorContext,
    turn_summary: TurnSummary,
) -> AsyncIterator[str]:
    """Generate SSE formatted streaming response.

    Processes streaming chunks from Llama Stack and converts them to
    Server-Sent Events (SSE) format. Uses handler functions to process
    different event types and populate turn_summary during streaming.

    Args:
        turn_response: The streaming response from Llama Stack
        context: The response generator context
        turn_summary: TurnSummary to populate during streaming

    Yields:
        SSE-formatted strings for tokens, tool calls, tool results,
        turn completion, and error events.
    """
    chunk_id = 0
    media_type = context.query_request.media_type or MEDIA_TYPE_JSON
    text_parts: list[str] = []
    mcp_calls: dict[int, tuple[str, str]] = (
        {}
    )  # output_index -> (mcp_call_id, mcp_call_name)
    latest_response_object: Optional[OpenAIResponseObject] = None

    logger.debug("Starting streaming response (Responses API) processing")

    async for chunk in turn_response:
        event_type = getattr(chunk, "type", None)
        logger.debug("Processing chunk %d, type: %s", chunk_id, event_type)

        # Content part started - emit an empty token to kick off UI streaming
        if event_type == "response.content_part.added":
            yield stream_event(
                {
                    "id": chunk_id,
                    "token": "",
                },
                LLM_TOKEN_EVENT,
                media_type,
            )
            chunk_id += 1

        # Store MCP call item info for later lookup when arguments.done event occurs
        elif event_type == "response.output_item.added":
            item_added_chunk = cast(OutputItemAddedChunk, chunk)
            if item_added_chunk.item.type == "mcp_call":
                mcp_call_item = cast(MCPCall, item_added_chunk.item)
                mcp_calls[item_added_chunk.output_index] = (
                    mcp_call_item.id,
                    mcp_call_item.name,
                )

        # Text streaming - emit token delta
        elif event_type == "response.output_text.delta":
            delta_chunk = cast(TextDeltaChunk, chunk)
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
            text_done_chunk = cast(TextDoneChunk, chunk)
            turn_summary.llm_response = text_done_chunk.text

        # Emit tool call when MCP call arguments are done
        elif event_type == "response.mcp_call.arguments.done":
            mcp_arguments_done_chunk = cast(MCPArgsDoneChunk, chunk)
            tool_call = build_mcp_tool_call_from_arguments_done(
                mcp_arguments_done_chunk.output_index,
                mcp_arguments_done_chunk.arguments,
                mcp_calls,
            )
            if tool_call:
                turn_summary.tool_calls.append(tool_call)
                yield stream_event(
                    tool_call.model_dump(),
                    LLM_TOOL_CALL_EVENT,
                    media_type,
                )

        # Process tool calls and results when output items are done
        # For mcp_call, only emit result (call was already emitted when arguments.done)
        # For other types, emit both call and result
        elif event_type == "response.output_item.done":
            output_item_done_chunk = cast(OutputItemDoneChunk, chunk)
            item_type = output_item_done_chunk.item.type
            # Skip message items as they are parsed separately
            if item_type == "message":
                continue

            output_index = output_item_done_chunk.output_index

            # For mcp_call, only emit result if call was already emitted when arguments.done
            # (indicated by output_index not being in mcp_calls dict)
            # If output_index is in dict, process in else branch (emit both call and result)
            if item_type == "mcp_call" and output_index not in mcp_calls:
                # Call was already emitted during arguments.done, only emit result
                mcp_call_item = cast(MCPCall, output_item_done_chunk.item)
                tool_result = build_tool_result_from_mcp_output_item_done(mcp_call_item)
                turn_summary.tool_results.append(tool_result)
                yield stream_event(
                    tool_result.model_dump(),
                    LLM_TOOL_RESULT_EVENT,
                    media_type,
                )
            else:
                # For all other types (and mcp_call when arguments.done didn't happen),
                # emit both call and result together
                tool_call, tool_result = build_tool_call_summary(
                    output_item_done_chunk.item, turn_summary.rag_chunks
                )
                if tool_call:
                    turn_summary.tool_calls.append(tool_call)
                    yield stream_event(
                        tool_call.model_dump(),
                        LLM_TOOL_CALL_EVENT,
                        media_type,
                    )
                if tool_result:
                    turn_summary.tool_results.append(tool_result)
                    yield stream_event(
                        tool_result.model_dump(),
                        LLM_TOOL_RESULT_EVENT,
                        media_type,
                    )

        # Completed response - capture final text and response object
        elif event_type == "response.completed":
            latest_response_object = cast(
                OpenAIResponseObject, getattr(chunk, "response")
            )
            turn_summary.llm_response = turn_summary.llm_response or "".join(text_parts)
            yield stream_event(
                {
                    "id": chunk_id,
                    "token": turn_summary.llm_response,
                },
                LLM_TURN_COMPLETE_EVENT,
                media_type,
            )
            chunk_id += 1

        # Incomplete or failed response - emit error
        elif event_type in ("response.incomplete", "response.failed"):
            latest_response_object = cast(
                OpenAIResponseObject, getattr(chunk, "response")
            )
            error_message = (
                latest_response_object.error.message
                if latest_response_object.error
                else "An unexpected error occurred while processing the request."
            )
            error_response = (
                PromptTooLongResponse(model=context.model_id)
                if "context_length" in error_message.lower()
                else InternalServerErrorResponse.query_failed(error_message)
            )
            yield stream_http_error_event(error_response, media_type)

    logger.debug(
        "Streaming complete - Tool calls: %d, Response chars: %d",
        len(turn_summary.tool_calls),
        len(turn_summary.llm_response),
    )

    # Extract token usage and referenced documents from the final response object
    turn_summary.token_usage = extract_token_usage(
        latest_response_object, context.model_id
    )
    tool_based_documents = parse_referenced_documents(latest_response_object)
    
    # Merge pre-RAG documents with tool-based documents (similar to query.py)
    if turn_summary.pre_rag_documents:
        all_documents = turn_summary.pre_rag_documents + tool_based_documents
        seen = set()
        deduplicated_documents = []
        for doc in all_documents:
            key = (doc.doc_url, doc.doc_title)
            if key not in seen:
                seen.add(key)
                deduplicated_documents.append(doc)
        turn_summary.referenced_documents = deduplicated_documents
    else:
        turn_summary.referenced_documents = tool_based_documents


def stream_http_error_event(
    error: AbstractErrorResponse, media_type: str | None = MEDIA_TYPE_JSON
) -> str:
    """
    Create an SSE-formatted error response for generic LLM or API errors.

    Args:
        error: An AbstractErrorResponse instance representing the error.
        media_type: The media type for the response format. Defaults to MEDIA_TYPE_JSON if None.
    Returns:
        str: A Server-Sent Events (SSE) formatted error message containing
            the serialized error details.
    """
    logger.error("Error while obtaining answer for user question")
    media_type = media_type or MEDIA_TYPE_JSON
    if media_type == MEDIA_TYPE_TEXT:
        return f"Status: {error.status_code} - {error.detail.response} - {error.detail.cause}"

    return format_stream_data(
        {
            "event": "error",
            "data": {
                "status_code": error.status_code,
                "response": error.detail.response,
                "cause": error.detail.cause,
            },
        }
    )


def format_stream_data(d: dict) -> str:
    """
    Create a response generator function for Responses API streaming.

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


def stream_end_event(
    token_usage: TokenCounter,
    available_quotas: dict[str, int],
    referenced_documents: list[ReferencedDocument],
    media_type: str = MEDIA_TYPE_JSON,
) -> str:
    """
    Yield the end of the data stream.

    Format and return the end event for a streaming response,
    including referenced document metadata and token usage information.

    Parameters:
        token_usage (TokenCounter): Token usage information.
        available_quotas (dict[str, int]): Available quotas for the user.
        referenced_documents (list[ReferencedDocument]): List of referenced documents.
        media_type (str): The media type for the response format.

    Returns:
        str: A Server-Sent Events (SSE) formatted string
        representing the end of the data stream.
    """
    if media_type == MEDIA_TYPE_TEXT:
        ref_docs_string = "\n".join(
            f"{doc.doc_title}: {doc.doc_url}"
            for doc in referenced_documents
            if doc.doc_url and doc.doc_title
        )
        return f"\n\n---\n\n{ref_docs_string}" if ref_docs_string else ""

    referenced_docs_dict = [doc.model_dump(mode="json") for doc in referenced_documents]

    return format_stream_data(
        {
            "event": "end",
            "data": {
                "referenced_documents": referenced_docs_dict,
                "truncated": None,
                "input_tokens": token_usage.input_tokens,
                "output_tokens": token_usage.output_tokens,
            },
            "available_quotas": available_quotas,
        }
    )


def stream_event(data: dict, event_type: str, media_type: str) -> str:
    """Build an item to yield based on media type.

    Args:
        data: Dictionary containing the event data
        event_type: Type of event (token, tool call, etc.)
        media_type: The media type for the response format

    Returns:
        SSE-formatted string representing the event
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
    """
    Create an SSE stream for shield violation responses.

    Yields start, token, and end events immediately for shield violations.
    This function creates a minimal streaming response without going through
    the Llama Stack response format.

    Args:
        violation_message: The violation message to display.
        media_type: The media type for the response format.

    Yields:
        str: SSE-formatted strings for start, token, and end events.
    """
    yield stream_event(
        {
            "id": 0,
            "token": violation_message,
        },
        LLM_TOKEN_EVENT,
        media_type,
    )
