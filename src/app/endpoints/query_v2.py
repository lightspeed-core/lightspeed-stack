# pylint: disable=too-many-lines,too-many-locals,too-many-branches,too-many-nested-blocks

"""Handler for REST API call to provide answer to query using Response API."""

import json
import logging
from typing import Annotated, Any, Optional, cast

from fastapi import APIRouter, Depends, Request
from llama_stack_api.openai_responses import (
    OpenAIResponseMCPApprovalRequest,
    OpenAIResponseMCPApprovalResponse,
    OpenAIResponseObject,
    OpenAIResponseOutput,
    OpenAIResponseOutputMessageFileSearchToolCall,
    OpenAIResponseOutputMessageFunctionToolCall,
    OpenAIResponseOutputMessageMCPCall,
    OpenAIResponseOutputMessageMCPListTools,
    OpenAIResponseOutputMessageWebSearchToolCall,
)
from llama_stack_client import AsyncLlamaStackClient

import constants
import metrics
from app.endpoints.query import (
    query_endpoint_handler_base,
    validate_attachments_metadata,
)
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import AppConfig, configuration
from constants import DEFAULT_RAG_TOOL
from models.config import Action, ModelContextProtocolServer
from models.requests import QueryRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    QueryResponse,
    QuotaExceededResponse,
    ReferencedDocument,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from utils.endpoints import (
    check_configuration_loaded,
    get_system_prompt,
    get_topic_summary_system_prompt,
)
from utils.mcp_headers import mcp_headers_dependency
from utils.query import parse_arguments_string
from utils.responses import extract_text_from_response_output_item
from utils.shields import (
    append_turn_to_conversation,
    run_shield_moderation,
)
from utils.suid import normalize_conversation_id, to_llama_stack_conversation_id
from utils.token_counter import TokenCounter
from utils.types import RAGChunk, ToolCallSummary, ToolResultSummary, TurnSummary

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query_v1"])

query_v2_response: dict[int | str, dict[str, Any]] = {
    200: QueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["endpoint", "conversation read", "model override"]
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


def _build_tool_call_summary(  # pylint: disable=too-many-return-statements,too-many-branches
    output_item: OpenAIResponseOutput,
    rag_chunks: list[RAGChunk],
) -> tuple[Optional[ToolCallSummary], Optional[ToolResultSummary]]:
    """Translate Responses API tool outputs into ToolCallSummary and ToolResultSummary records.

    Processes OpenAI response output items and extracts tool call and result information.
    Also parses RAG chunks from file_search_call items and appends them to the provided list.

    Args:
        output_item: An OpenAIResponseOutput item from the response.output array
        rag_chunks: List to append extracted RAG chunks to (from file_search_call items)
    Returns:
        A tuple of (ToolCallSummary, ToolResultSummary) one of them possibly None
        if current llama stack Responses API does not provide the information.

    Supported tool types:
        - function_call: Function tool calls with parsed arguments (no result)
        - file_search_call: File search operations with results (also extracts RAG chunks)
        - web_search_call: Web search operations (incomplete)
        - mcp_call: MCP calls with server labels
        - mcp_list_tools: MCP server tool listings
        - mcp_approval_request: MCP approval requests (no result)
        - mcp_approval_response: MCP approval responses (no call)
    """
    item_type = getattr(output_item, "type", None)

    if item_type == "function_call":
        item = cast(OpenAIResponseOutputMessageFunctionToolCall, output_item)
        return (
            ToolCallSummary(
                id=item.call_id,
                name=item.name,
                args=parse_arguments_string(item.arguments),
                type="function_call",
            ),
            None,  # not supported by Responses API at all
        )

    if item_type == "file_search_call":
        file_search_item = cast(
            OpenAIResponseOutputMessageFileSearchToolCall, output_item
        )
        extract_rag_chunks_from_file_search_item(file_search_item, rag_chunks)
        response_payload: Optional[dict[str, Any]] = None
        if file_search_item.results is not None:
            response_payload = {
                "results": [result.model_dump() for result in file_search_item.results]
            }
        return ToolCallSummary(
            id=file_search_item.id,
            name=DEFAULT_RAG_TOOL,
            args={"queries": file_search_item.queries},
            type="file_search_call",
        ), ToolResultSummary(
            id=file_search_item.id,
            status=file_search_item.status,
            content=json.dumps(response_payload) if response_payload else "",
            type="file_search_call",
            round=1,
        )

    # Incomplete OpenAI Responses API definition in LLS: action attribute not supported yet
    if item_type == "web_search_call":
        web_search_item = cast(
            OpenAIResponseOutputMessageWebSearchToolCall, output_item
        )
        return (
            ToolCallSummary(
                id=web_search_item.id,
                name="web_search",
                args={},
                type="web_search_call",
            ),
            ToolResultSummary(
                id=web_search_item.id,
                status=web_search_item.status,
                content="",
                type="web_search_call",
                round=1,
            ),
        )

    if item_type == "mcp_call":
        mcp_call_item = cast(OpenAIResponseOutputMessageMCPCall, output_item)
        args = parse_arguments_string(mcp_call_item.arguments)
        if mcp_call_item.server_label:
            args["server_label"] = mcp_call_item.server_label
        content = (
            mcp_call_item.error
            if mcp_call_item.error
            else (mcp_call_item.output if mcp_call_item.output else "")
        )

        # Log MCP tool call
        logger.debug(
            "MCP tool call: %s on server '%s' (call_id: %s)",
            mcp_call_item.name,
            mcp_call_item.server_label,
            mcp_call_item.id,
        )
        logger.debug("  Arguments keys: %s", list(args.keys()) if args else [])

        # Log MCP tool result
        if mcp_call_item.error:
            logger.warning(
                "MCP tool result: %s FAILED - %s",
                mcp_call_item.name,
                mcp_call_item.error,
            )
        else:
            logger.debug(
                "MCP tool result: %s SUCCESS (output length: %d)",
                mcp_call_item.name,
                len(content),
            )
            logger.debug("  Output preview: <redacted> (%d chars)", len(content))

        return ToolCallSummary(
            id=mcp_call_item.id,
            name=mcp_call_item.name,
            args=args,
            type="mcp_call",
        ), ToolResultSummary(
            id=mcp_call_item.id,
            status="success" if mcp_call_item.error is None else "failure",
            content=content,
            type="mcp_call",
            round=1,
        )

    if item_type == "mcp_list_tools":
        mcp_list_tools_item = cast(OpenAIResponseOutputMessageMCPListTools, output_item)
        tools_info = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in mcp_list_tools_item.tools
        ]

        # Log MCP list_tools call
        logger.debug(
            "MCP server '%s' listed %d available tool(s)",
            mcp_list_tools_item.server_label,
            len(mcp_list_tools_item.tools),
        )
        logger.debug(
            "  Tools: %s",
            ", ".join(tool.name for tool in mcp_list_tools_item.tools),
        )

        content_dict = {
            "server_label": mcp_list_tools_item.server_label,
            "tools": tools_info,
        }
        return (
            ToolCallSummary(
                id=mcp_list_tools_item.id,
                name="mcp_list_tools",
                args={"server_label": mcp_list_tools_item.server_label},
                type="mcp_list_tools",
            ),
            ToolResultSummary(
                id=mcp_list_tools_item.id,
                status="success",
                content=json.dumps(content_dict),
                type="mcp_list_tools",
                round=1,
            ),
        )

    if item_type == "mcp_approval_request":
        approval_request_item = cast(OpenAIResponseMCPApprovalRequest, output_item)
        args = parse_arguments_string(approval_request_item.arguments)

        # Log MCP approval request
        logger.debug(
            "MCP approval requested: tool '%s' on server '%s'",
            approval_request_item.name,
            approval_request_item.server_label,
        )
        logger.debug("  Arguments: %s", args)

        return (
            ToolCallSummary(
                id=approval_request_item.id,
                name=approval_request_item.name,
                args=args,
                type="tool_call",
            ),
            None,
        )

    if item_type == "mcp_approval_response":
        approval_response_item = cast(OpenAIResponseMCPApprovalResponse, output_item)
        content_dict = {}
        if approval_response_item.reason:
            content_dict["reason"] = approval_response_item.reason
        return (
            None,
            ToolResultSummary(
                id=approval_response_item.approval_request_id,
                status="success" if approval_response_item.approve else "denied",
                content=json.dumps(content_dict),
                type="mcp_approval_response",
                round=1,
            ),
        )

    return None, None


async def get_topic_summary(  # pylint: disable=too-many-nested-blocks
    question: str, client: AsyncLlamaStackClient, model_id: str
) -> str:
    """
    Get a topic summary for a question using Responses API.

    This is the Responses API version of get_topic_summary, which uses
    client.responses.create() instead of the Agent API.

    Args:
        question: The question to generate a topic summary for
        client: The AsyncLlamaStackClient to use for the request
        model_id: The llama stack model ID (full format: provider/model)

    Returns:
        str: The topic summary for the question
    """
    topic_summary_system_prompt = get_topic_summary_system_prompt(configuration)

    # Use Responses API to generate topic summary
    response = cast(
        OpenAIResponseObject,
        await client.responses.create(
            input=question,
            model=model_id,
            instructions=topic_summary_system_prompt,
            stream=False,
            store=False,  # Don't store topic summary requests
        ),
    )

    # Extract text from response output
    summary_text = "".join(
        extract_text_from_response_output_item(output_item)
        for output_item in response.output
    )

    return summary_text.strip() if summary_text else ""


@router.post("/query", responses=query_v2_response, summary="Query Endpoint Handler V1")
@authorize(Action.QUERY)
async def query_endpoint_handler_v2(
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: dict[str, dict[str, str]] = Depends(mcp_headers_dependency),
) -> QueryResponse:
    """
    Handle request to the /query endpoint using Responses API.

    This is a wrapper around query_endpoint_handler_base that provides
    the Responses API specific retrieve_response and get_topic_summary functions.

    Returns:
        QueryResponse: Contains the conversation ID and the LLM-generated response.
    """
    check_configuration_loaded(configuration)
    return await query_endpoint_handler_base(
        request=request,
        query_request=query_request,
        auth=auth,
        mcp_headers=mcp_headers,
        retrieve_response_func=retrieve_response,
        get_topic_summary_func=get_topic_summary,
    )


async def retrieve_response(  # pylint: disable=too-many-locals,too-many-branches,too-many-arguments,too-many-statements
    client: AsyncLlamaStackClient,
    model_id: str,
    query_request: QueryRequest,
    token: str,
    mcp_headers: Optional[dict[str, dict[str, str]]] = None,
    *,
    provider_id: str = "",
) -> tuple[TurnSummary, str, list[ReferencedDocument], TokenCounter]:
    """
    Retrieve response from LLMs and agents.

    Retrieves a response from the Llama Stack LLM or agent for a
    given query, handling shield configuration, tool usage, and
    attachment validation.

    This function configures system prompts, shields, and toolgroups
    (including RAG and MCP integration) as needed based on
    the query request and system configuration. It
    validates attachments, manages conversation and session
    context, and processes MCP headers for multi-component
    processing. Corresponding metrics are updated.

    Parameters:
        client (AsyncLlamaStackClient): The AsyncLlamaStackClient to use for the request.
        model_id (str): The identifier of the LLM model to use.
        query_request (QueryRequest): The user's query and associated metadata.
        token (str): The authentication token for authorization.
        mcp_headers (dict[str, dict[str, str]], optional): Headers for multi-component processing.
        provider_id (str): The identifier of the LLM provider to use.

    Returns:
        tuple[TurnSummary, str]: A tuple containing a summary of the LLM or agent's response content
        and the conversation ID, the list of parsed referenced documents,
        and token usage information.
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
            # Append attachment content with type label
            input_text += (
                f"\n\n[Attachment: {attachment.attachment_type}]\n{attachment.content}"
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
        summary = TurnSummary(
            llm_response=violation_message,
            tool_calls=[],
            tool_results=[],
            rag_chunks=[],
        )
        return (
            summary,
            normalize_conversation_id(conversation_id),
            [],
            TokenCounter(),
        )

    # Create OpenAI response using responses API
    create_kwargs: dict[str, Any] = {
        "input": input_text,
        "model": model_id,
        "instructions": system_prompt,
        "tools": cast(Any, toolgroups),
        "stream": False,
        "store": True,
        "conversation": llama_stack_conv_id,
    }

    # Log request details before calling Llama Stack
    if toolgroups:
        rag_tool_count = sum(1 for t in toolgroups if t.get("type") == "file_search")
        mcp_tool_count = sum(1 for t in toolgroups if t.get("type") == "mcp")
        logger.debug(
            "Calling Llama Stack Responses API with %d tool(s): %d RAG + %d MCP",
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
        logger.debug("Calling Llama Stack Responses API without tools")

    response = await client.responses.create(**create_kwargs)
    response = cast(OpenAIResponseObject, response)
    logger.debug(
        "Received response with ID: %s, conversation ID: %s, output items: %d",
        response.id,
        conversation_id,
        len(response.output),
    )

    # Process OpenAI response format
    llm_response = ""
    tool_calls: list[ToolCallSummary] = []
    tool_results: list[ToolResultSummary] = []
    rag_chunks: list[RAGChunk] = []
    for output_item in response.output:
        message_text = extract_text_from_response_output_item(output_item)
        if message_text:
            llm_response += message_text

        tool_call, tool_result = _build_tool_call_summary(output_item, rag_chunks)
        if tool_call:
            tool_calls.append(tool_call)
        if tool_result:
            tool_results.append(tool_result)

    logger.info(
        "Response processing complete - Tool calls: %d, Response length: %d chars",
        len(tool_calls),
        len(llm_response),
    )

    summary = TurnSummary(
        llm_response=llm_response,
        tool_calls=tool_calls,
        tool_results=tool_results,
        rag_chunks=rag_chunks,
    )

    # Extract referenced documents and token usage from Responses API response
    referenced_documents = parse_referenced_documents_from_responses_api(response)
    model_label = model_id.split("/", 1)[1] if "/" in model_id else model_id
    token_usage = extract_token_usage_from_responses_api(
        response, model_label, provider_id, system_prompt
    )

    if not summary.llm_response:
        logger.warning(
            "Response lacks content (conversation_id=%s)",
            conversation_id,
        )

    return (
        summary,
        normalize_conversation_id(conversation_id),
        referenced_documents,
        token_usage,
    )


def extract_rag_chunks_from_file_search_item(
    item: OpenAIResponseOutputMessageFileSearchToolCall,
    rag_chunks: list[RAGChunk],
) -> None:
    """Extract RAG chunks from a file search tool call item and append to rag_chunks.

    Args:
        item: The file search tool call item.
        rag_chunks: List to append extracted RAG chunks to.
    """
    if item.results is not None:
        for result in item.results:
            rag_chunk = RAGChunk(
                content=result.text, source=result.filename, score=result.score
            )
            rag_chunks.append(rag_chunk)


def parse_rag_chunks_from_responses_api(
    response_obj: OpenAIResponseObject,
) -> list[RAGChunk]:
    """
    Extract rag_chunks from the llama-stack OpenAI response.

    Args:
        response_obj: The ResponseObject from OpenAI compatible response API in llama-stack.

    Returns:
        List of RAGChunk with content, source, score
    """
    rag_chunks: list[RAGChunk] = []

    for output_item in response_obj.output:
        item_type = getattr(output_item, "type", None)
        if item_type == "file_search_call":
            item = cast(OpenAIResponseOutputMessageFileSearchToolCall, output_item)
            extract_rag_chunks_from_file_search_item(item, rag_chunks)

    return rag_chunks


def parse_referenced_documents_from_responses_api(
    response: OpenAIResponseObject,  # pylint: disable=unused-argument
) -> list[ReferencedDocument]:
    """
    Parse referenced documents from OpenAI Responses API response.

    Args:
        response: The OpenAI Response API response object

    Returns:
        list[ReferencedDocument]: List of referenced documents with doc_url and doc_title
    """
    documents: list[ReferencedDocument] = []
    # Use a set to track unique documents by (doc_url, doc_title) tuple
    seen_docs: set[tuple[Optional[str], Optional[str]]] = set()

    # Handle None response (e.g., when agent fails)
    if response is None or not response.output:
        return documents

    for output_item in response.output:
        item_type = getattr(output_item, "type", None)

        # 1. Parse from file_search_call results
        if item_type == "file_search_call":
            results = getattr(output_item, "results", []) or []
            for result in results:
                # Handle both object and dict access
                if isinstance(result, dict):
                    attributes = result.get("attributes", {})
                else:
                    attributes = getattr(result, "attributes", {})

                # Try to get URL from attributes
                # Look for common URL fields in attributes
                doc_url = (
                    attributes.get("doc_url")
                    or attributes.get("docs_url")
                    or attributes.get("url")
                    or attributes.get("link")
                )
                doc_title = attributes.get("title")

                if doc_title or doc_url:
                    # Treat empty string as None for URL to satisfy Optional[AnyUrl]
                    final_url = doc_url if doc_url else None
                    if (final_url, doc_title) not in seen_docs:
                        documents.append(
                            ReferencedDocument(doc_url=final_url, doc_title=doc_title)
                        )
                        seen_docs.add((final_url, doc_title))

    return documents


def extract_token_usage_from_responses_api(
    response: OpenAIResponseObject,
    model: str,
    provider: str,
    system_prompt: str = "",  # pylint: disable=unused-argument
) -> TokenCounter:
    """
    Extract token usage from OpenAI Responses API response and update metrics.

    This function extracts token usage information from the Responses API response
    object and updates Prometheus metrics. If usage information is not available,
    it returns zero values without estimation.

    Note: When llama stack internally uses chat_completions, the usage field may be
    empty or a dict. This is expected and will be populated in future llama stack versions.

    Args:
        response: The OpenAI Response API response object
        model: The model identifier for metrics labeling
        provider: The provider identifier for metrics labeling
        system_prompt: The system prompt used (unused, kept for compatibility)

    Returns:
        TokenCounter: Token usage information with input_tokens and output_tokens
    """
    token_counter = TokenCounter()
    token_counter.llm_calls = 1

    # Extract usage from the response if available
    # Note: usage attribute exists at runtime but may not be in type definitions
    usage = getattr(response, "usage", None)
    if usage:
        try:
            # Handle both dict and object cases due to llama_stack inconsistency:
            # - When llama_stack converts to chat_completions internally, usage is a dict
            # - When using proper Responses API, usage should be an object
            # TODO: Remove dict handling once llama_stack standardizes on object type  # pylint: disable=fixme
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
            else:
                # Object with attributes (expected final behavior)
                input_tokens = getattr(usage, "input_tokens", 0)
                output_tokens = getattr(usage, "output_tokens", 0)
            # Only set if we got valid values
            if input_tokens or output_tokens:
                token_counter.input_tokens = input_tokens or 0
                token_counter.output_tokens = output_tokens or 0

                logger.debug(
                    "Extracted token usage from Responses API: input=%d, output=%d",
                    token_counter.input_tokens,
                    token_counter.output_tokens,
                )

                # Update Prometheus metrics only when we have actual usage data
                try:
                    metrics.llm_token_sent_total.labels(provider, model).inc(
                        token_counter.input_tokens
                    )
                    metrics.llm_token_received_total.labels(provider, model).inc(
                        token_counter.output_tokens
                    )
                except (AttributeError, TypeError, ValueError) as e:
                    logger.warning("Failed to update token metrics: %s", e)
                _increment_llm_call_metric(provider, model)
            else:
                logger.debug(
                    "Usage object exists but tokens are 0 or None, treating as no usage info"
                )
                # Still increment the call counter
                _increment_llm_call_metric(provider, model)
        except (AttributeError, KeyError, TypeError) as e:
            logger.warning(
                "Failed to extract token usage from response.usage: %s. Usage value: %s",
                e,
                usage,
            )
            # Still increment the call counter
            _increment_llm_call_metric(provider, model)
    else:
        # No usage information available - this is expected when llama stack
        # internally converts to chat_completions
        logger.debug(
            "No usage information in Responses API response, token counts will be 0"
        )
        # token_counter already initialized with 0 values
        # Still increment the call counter
        _increment_llm_call_metric(provider, model)

    return token_counter


def _increment_llm_call_metric(provider: str, model: str) -> None:
    """Safely increment LLM call metric."""
    try:
        metrics.llm_calls_total.labels(provider, model).inc()
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning("Failed to update LLM call metric: %s", e)


def get_rag_tools(vector_store_ids: list[str]) -> Optional[list[dict[str, Any]]]:
    """
    Convert vector store IDs to tools format for Responses API.

    Args:
        vector_store_ids: List of vector store identifiers

    Returns:
        Optional[list[dict[str, Any]]]: List containing file_search tool configuration,
        or None if no vector stores provided
    """
    if not vector_store_ids:
        return None

    return [
        {
            "type": "file_search",
            "vector_store_ids": vector_store_ids,
            "max_num_results": 10,
        }
    ]


def get_mcp_tools(
    mcp_servers: list[ModelContextProtocolServer],
    token: str | None = None,
    mcp_headers: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Convert MCP servers to tools format for Responses API.

    Args:
        mcp_servers: List of MCP server configurations
        token: Optional authentication token for MCP server authorization
        mcp_headers: Optional per-request headers for MCP servers, keyed by server URL

    Returns:
        list[dict[str, Any]]: List of MCP tool definitions with server
            details and optional auth headers

    The way it works is we go through all the defined mcp servers and
    create a tool definitions for each of them. If MCP server definition
    has a non-empty resolved_authorization_headers we create invocation
    headers, following the algorithm:
    1. If the header value is 'kubernetes' the header value is a k8s token
    2. If the header value is 'client':
        find the value for a given MCP server/header in mcp_headers.
        if the value is not found omit this header, otherwise use found value
    3.  otherwise use the value from resolved_authorization_headers directly

    This algorithm allows to:
    1. Use static global header values, provided by configuration
    2. Use user specific k8s token, which will work for the majority of kubernetes
       based MCP servers
    3. Use user specific tokens (passed by the client) for user specific MCP headers

    Note: Starting with llama_stack 0.4.x, the Authorization header must be passed
    via the 'authorization' parameter instead of in the 'headers' dict.
    """

    def _get_token_value(original: str, header: str) -> str | None:
        """Convert to header value."""
        match original:
            case constants.MCP_AUTH_KUBERNETES:
                # use k8s token
                if token is None or token == "":
                    return None
                return f"Bearer {token}"
            case constants.MCP_AUTH_CLIENT:
                # use client provided token
                if mcp_headers is None:
                    return None
                c_headers = mcp_headers.get(mcp_server.name, None)
                if c_headers is None:
                    return None
                return c_headers.get(header, None)
            case _:
                # use provided
                return original

    tools = []
    for mcp_server in mcp_servers:
        # Base tool definition
        tool_def = {
            "type": "mcp",
            "server_label": mcp_server.name,
            "server_url": mcp_server.url,
            "require_approval": "never",
        }

        # Log header resolution process
        if mcp_server.authorization_headers:
            logger.debug(
                "MCP server '%s': Resolving %d authorization header(s)",
                mcp_server.name,
                len(mcp_server.authorization_headers),
            )

        # Build headers and separate Authorization header
        headers = {}
        authorization = None
        for name, value in mcp_server.resolved_authorization_headers.items():
            # for each defined header
            h_value = _get_token_value(value, name)
            # only add the header if we got value
            if h_value is not None:
                # Log successful resolution - determine auth type for logging
                match value:
                    case _ if value == constants.MCP_AUTH_KUBERNETES:
                        auth_type = "kubernetes"
                    case _ if value == constants.MCP_AUTH_CLIENT:
                        auth_type = "client"
                    case _:
                        auth_type = "static"

                logger.debug(
                    "MCP server '%s': Header '%s' -> type: %s (resolved)",
                    mcp_server.name,
                    name,
                    auth_type,
                )
                # Special handling for Authorization header (llama_stack 0.4.x+)
                if name.lower() == "authorization":
                    authorization = h_value
                else:
                    headers[name] = h_value
            else:
                # Log failed resolution
                logger.debug(
                    "MCP server '%s': Header '%s' -> FAILED to resolve (value was: %s)",
                    mcp_server.name,
                    name,
                    value,
                )

        # Skip server if auth headers were configured but not all could be resolved
        resolved_count = len(headers) + (1 if authorization is not None else 0)
        if mcp_server.resolved_authorization_headers and resolved_count != len(
            mcp_server.resolved_authorization_headers
        ):
            required_headers = list(mcp_server.authorization_headers.keys())
            resolved_headers = list(headers.keys())
            if authorization is not None:
                resolved_headers.append("Authorization")
            missing_headers = [h for h in required_headers if h not in resolved_headers]

            logger.debug(
                "MCP server '%s' SKIPPED - incomplete auth: "
                "Required: %s | Resolved: %s | Missing: %s (resolved_count=%d, expected=%d)",
                mcp_server.name,
                ", ".join(required_headers),
                ", ".join(resolved_headers) if resolved_headers else "none",
                ", ".join(missing_headers) if missing_headers else "none",
                resolved_count,
                len(mcp_server.resolved_authorization_headers),
            )
            continue

        # Add authorization parameter if we have an Authorization header
        if authorization is not None:
            tool_def["authorization"] = authorization  # type: ignore[index]

        # Add other headers if present
        if len(headers) > 0:
            tool_def["headers"] = headers  # type: ignore[index]

        # Log successful tool creation
        logger.debug(
            "MCP server '%s': Tool ADDED (authorization: %s, headers: %d)",
            mcp_server.name,
            "SET" if authorization is not None else "NOT SET",
            len(headers),
        )

        # collect tools info
        tools.append(tool_def)

    logger.debug("get_mcp_tools: Returning %d tool(s)", len(tools))
    return tools


async def prepare_tools_for_responses_api(
    client: AsyncLlamaStackClient,
    query_request: QueryRequest,
    token: str,
    config: AppConfig,
    mcp_headers: Optional[dict[str, dict[str, str]]] = None,
) -> Optional[list[dict[str, Any]]]:
    """
    Prepare tools for Responses API including RAG and MCP tools.

    This function retrieves vector stores and combines them with MCP
    server tools to create a unified toolgroups list for the Responses API.

    Args:
        client: The Llama Stack client instance
        query_request: The user's query request
        token: Authentication token for MCP tools
        config: Configuration object containing MCP server settings
        mcp_headers: Per-request headers for MCP servers

    Returns:
        Optional[list[dict[str, Any]]]: List of tool configurations for the
        Responses API, or None if no_tools is True or no tools are available
    """
    if query_request.no_tools:
        logger.debug("Tools disabled for this request (no_tools=True)")
        return None

    toolgroups = []
    # Get vector stores for RAG tools - use specified ones or fetch all
    if query_request.vector_store_ids:
        vector_store_ids = query_request.vector_store_ids
        logger.debug(
            "Using %d specified vector store(s): %s",
            len(vector_store_ids),
            vector_store_ids,
        )
    else:
        vector_store_ids = [
            vector_store.id for vector_store in (await client.vector_stores.list()).data
        ]
        logger.debug("Retrieved %d available vector store(s)", len(vector_store_ids))

    # Add RAG tools if vector stores are available
    rag_tools = get_rag_tools(vector_store_ids)
    if rag_tools:
        toolgroups.extend(rag_tools)
        logger.debug(
            "Added %d RAG tool(s) for vector stores: %s",
            len(rag_tools),
            vector_store_ids,
        )

    # Add MCP server tools
    mcp_tools = get_mcp_tools(config.mcp_servers, token, mcp_headers)
    if mcp_tools:
        toolgroups.extend(mcp_tools)
        mcp_server_names = [tool.get("server_label", "unknown") for tool in mcp_tools]
        logger.info(
            "Prepared %d MCP tool(s) for request: %s",
            len(mcp_tools),
            ", ".join(mcp_server_names),
        )
        # Debug: Show full tool definitions
        for tool in mcp_tools:
            logger.debug(
                "  MCP tool: %s at %s (auth: %s, headers: %d)",
                tool.get("server_label"),
                tool.get("server_url"),
                "yes" if "authorization" in tool else "no",
                len(tool.get("headers", {})),
            )
    else:
        if config.mcp_servers:
            logger.warning(
                "No MCP tools prepared (all %d configured servers were skipped)",
                len(config.mcp_servers),
            )
        else:
            logger.debug("No MCP servers configured")

    # Summary log
    if toolgroups:
        logger.info(
            "Prepared %d total tool(s) for Responses API: %d RAG + %d MCP",
            len(toolgroups),
            len(rag_tools) if rag_tools else 0,
            len(mcp_tools) if mcp_tools else 0,
        )
    else:
        logger.debug("No tools available for this request")

    # Convert empty list to None for consistency with existing behavior
    if not toolgroups:
        return None

    return toolgroups
