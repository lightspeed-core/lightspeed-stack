"""Utility functions for processing Responses API output."""

# pylint: disable=too-many-lines

import json
from collections.abc import Mapping, Sequence
from typing import Any, Optional, cast

from fastapi import HTTPException
from llama_stack_api.openai_responses import (
    OpenAIResponseContentPartRefusal as ContentPartRefusal,
    OpenAIResponseInputMessageContent as InputMessageContent,
    OpenAIResponseInputMessageContentText as InputTextPart,
    OpenAIResponseMessage as ResponseMessage,
    OpenAIResponseObject as ResponseObject,
    OpenAIResponseOutput as ResponseOutput,
    OpenAIResponseOutputMessageContent as OutputMessageContent,
    OpenAIResponseOutputMessageContentOutputText as OutputTextPart,
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchCall,
    OpenAIResponseOutputMessageFunctionToolCall as FunctionCall,
    OpenAIResponseOutputMessageMCPCall as MCPCall,
    OpenAIResponseOutputMessageMCPListTools as MCPListTools,
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchCall,
    OpenAIResponseMCPApprovalRequest as MCPApprovalRequest,
    OpenAIResponseMCPApprovalResponse as MCPApprovalResponse,
    OpenAIResponseUsage as ResponseUsage,
)
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient

import constants
import metrics
from configuration import configuration
from constants import DEFAULT_RAG_TOOL
from models.database.conversations import UserConversation
from models.requests import QueryRequest
from models.responses import (
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
)
from utils.mcp_oauth_probe import probe_mcp_oauth_and_raise_401
from utils.prompts import get_system_prompt, get_topic_summary_system_prompt
from utils.query import (
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    prepare_input,
)
from utils.mcp_headers import McpHeaders, extract_propagated_headers
from utils.suid import to_llama_stack_conversation_id
from utils.token_counter import TokenCounter
from utils.types import (
    RAGChunk,
    ReferencedDocument,
    ResponseItem,
    ResponsesApiParams,
    ToolCallSummary,
    ToolResultSummary,
    TurnSummary,
)
from log import get_logger

logger = get_logger(__name__)


async def get_topic_summary(
    question: str, client: AsyncLlamaStackClient, model_id: str
) -> str:
    """Get a topic summary for a question using Responses API.

    Args:
        question: The question to generate a topic summary for
        client: The AsyncLlamaStackClient to use for the request
        model_id: The llama stack model ID (full format: provider/model)

    Returns:
        The topic summary for the question
    """
    try:
        response = cast(
            ResponseObject,
            await client.responses.create(
                input=question,
                model=model_id,
                instructions=get_topic_summary_system_prompt(),
                stream=False,
                store=False,  # Don't store topic summary requests
            ),
        )
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except APIStatusError as e:
        error_response = handle_known_apistatus_errors(e, model_id)
        raise HTTPException(**error_response.model_dump()) from e

    return extract_text_from_response_items(response.output)


async def prepare_tools(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    client: AsyncLlamaStackClient,
    vector_store_ids: list[str] | None,
    no_tools: bool | None,
    token: str,
    mcp_headers: McpHeaders | None = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]] | None:
    """Prepare tools for Responses API including RAG and MCP tools.

    Args:
        client: The Llama Stack client instance
        vector_store_ids: The list of vector store IDs to use for RAG tools
            or None if all vector stores should be used
        no_tools: Whether to skip tool preparation
        token: Authentication token for MCP tools
        mcp_headers: Per-request headers for MCP servers
        request_headers: Incoming HTTP request headers for allowlist propagation

    Returns:
        List of tool configurations, or None if no tools available
    """
    if no_tools:
        return None

    toolgroups = []
    # Get all vector stores if vector stores are not restricted by request
    if vector_store_ids is None:
        try:
            vector_stores = await client.vector_stores.list()
            vector_store_ids = [vector_store.id for vector_store in vector_stores.data]
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except APIStatusError as e:
            error_response = InternalServerErrorResponse.generic()
            raise HTTPException(**error_response.model_dump()) from e

    # Add RAG tools if vector stores are available
    rag_tools = get_rag_tools(vector_store_ids)
    if rag_tools:
        toolgroups.extend(rag_tools)

    # Add MCP server tools
    mcp_tools = await get_mcp_tools(token, mcp_headers, request_headers)
    if mcp_tools:
        toolgroups.extend(mcp_tools)
        logger.debug(
            "Configured %d MCP tools: %s",
            len(mcp_tools),
            [tool.get("server_label", "unknown") for tool in mcp_tools],
        )
    # Convert empty list to None for consistency with existing behavior
    if not toolgroups:
        return None

    return toolgroups


def _build_provider_data_headers(
    tools: list[dict[str, Any]] | None,
) -> dict[str, str] | None:
    """Build extra HTTP headers containing MCP provider data for Llama Stack.

    Extracts per-server auth headers from MCP tool definitions and encodes
    them as a JSON ``x-llamastack-provider-data`` header that Llama Stack
    uses to authenticate with downstream MCP servers.

    Args:
        tools: Prepared tool definitions (may include MCP and non-MCP tools).

    Returns:
        Dict with a single ``x-llamastack-provider-data`` key, or None when
        no MCP tools carry headers.
    """
    if not tools:
        return None

    mcp_headers: McpHeaders = {
        tool["server_url"]: tool["headers"]
        for tool in tools
        if tool.get("type") == "mcp" and tool.get("headers") and tool.get("server_url")
    }

    if not mcp_headers:
        return None

    return {"x-llamastack-provider-data": json.dumps({"mcp_headers": mcp_headers})}


async def prepare_responses_params(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    client: AsyncLlamaStackClient,
    query_request: QueryRequest,
    user_conversation: UserConversation | None,
    token: str,
    mcp_headers: McpHeaders | None = None,
    stream: bool = False,
    store: bool = True,
    request_headers: Optional[Mapping[str, str]] = None,
) -> ResponsesApiParams:
    """Prepare API request parameters for Responses API.

    Args:
        client: The AsyncLlamaStackClient instance (must be initialized by caller)
        query_request: The query request containing the user's question
        user_conversation: The user conversation if conversation_id was provided, None otherwise
        token: The authentication token for authorization
        mcp_headers: Optional MCP headers for multi-component processing
        stream: Whether to stream the response
        store: Whether to store the response
        request_headers: Incoming HTTP request headers for allowlist propagation

    Returns:
        ResponsesApiParams containing all prepared parameters for the API request
    """
    if query_request.model and query_request.provider:
        model = f"{query_request.provider}/{query_request.model}"
    else:
        model = await select_model_for_responses(client, user_conversation)

    if not await check_model_configured(client, model):
        _, model_id = extract_provider_and_model_from_model_id(model)
        error_response = NotFoundResponse(resource="model", resource_id=model_id)
        raise HTTPException(**error_response.model_dump())

    # Use system prompt from request or default one
    system_prompt = get_system_prompt(query_request.system_prompt)
    logger.debug("Using system prompt: %s", system_prompt)

    # Prepare tools for responses API
    tools = await prepare_tools(
        client,
        query_request.vector_store_ids,
        query_request.no_tools,
        token,
        mcp_headers,
        request_headers,
    )

    # Prepare input for Responses API
    input_text = prepare_input(query_request)

    # Handle conversation ID for Responses API
    conversation_id = query_request.conversation_id
    if conversation_id:
        # Conversation ID was provided - convert to llama-stack format
        logger.debug("Using existing conversation ID: %s", conversation_id)
        llama_stack_conv_id = to_llama_stack_conversation_id(conversation_id)
    else:
        # No conversation_id provided - create a new conversation first
        logger.debug("No conversation_id provided, creating new conversation")
        try:
            conversation = await client.conversations.create(metadata={})
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except APIStatusError as e:
            error_response = InternalServerErrorResponse.generic()
            raise HTTPException(**error_response.model_dump()) from e

        llama_stack_conv_id = conversation.id
        logger.info(
            "Created new conversation with ID: %s",
            llama_stack_conv_id,
        )

    # Build x-llamastack-provider-data header from MCP tool headers
    extra_headers = _build_provider_data_headers(tools)

    return ResponsesApiParams(
        input=input_text,
        model=model,
        instructions=system_prompt,
        tools=tools,
        conversation=llama_stack_conv_id,
        stream=stream,
        store=store,
        extra_headers=extra_headers,
    )


def extract_vector_store_ids_from_tools(
    tools: list[dict[str, Any]] | None,
) -> list[str]:
    """Extract vector store IDs from prepared tool configurations.

    Parameters:
        tools: The prepared tools list from ResponsesApiParams.

    Returns:
        List of vector store IDs used in file_search tools, or empty list.
    """
    if not tools:
        return []
    for tool in tools:
        if tool.get("type") == "file_search":
            return tool.get("vector_store_ids", [])
    return []


def get_rag_tools(vector_store_ids: list[str]) -> list[dict[str, Any]] | None:
    """Convert vector store IDs to tools format for Responses API.

    Args:
        vector_store_ids: List of vector store identifiers

    Returns:
        List containing file_search tool configuration, or None if no vector stores provided
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


async def get_mcp_tools(  # pylint: disable=too-many-return-statements,too-many-locals
    token: str | None = None,
    mcp_headers: McpHeaders | None = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]]:
    """Convert MCP servers to tools format for Responses API.

    Args:
        token: Optional authentication token for MCP server authorization
        mcp_headers: Optional per-request headers for MCP servers, keyed by server URL
        request_headers: Optional incoming HTTP request headers for allowlist propagation

    Returns:
        List of MCP tool definitions with server details and optional auth headers

    Raises:
        HTTPException: 401 with WWW-Authenticate header when an MCP server uses OAuth,
            no headers are passed, and the server responds with 401 and WWW-Authenticate.
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
            case constants.MCP_AUTH_OAUTH:
                # use oauth token
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
    for mcp_server in configuration.mcp_servers:
        # Base tool definition
        tool_def = {
            "type": "mcp",
            "server_label": mcp_server.name,
            "server_url": mcp_server.url,
            "require_approval": "never",
        }

        # Build headers
        headers = {}
        for name, value in mcp_server.resolved_authorization_headers.items():
            # for each defined header
            h_value = _get_token_value(value, name)
            # only add the header if we got value
            if h_value is not None:
                headers[name] = h_value

        # Skip server if auth headers were configured but not all could be resolved
        if mcp_server.authorization_headers and len(headers) != len(
            mcp_server.authorization_headers
        ):
            # If OAuth was required and no headers passed, probe endpoint and forward
            # 401 with WWW-Authenticate so the client can perform OAuth
            uses_oauth = (
                constants.MCP_AUTH_OAUTH
                in mcp_server.resolved_authorization_headers.values()
            )
            if uses_oauth and (
                mcp_headers is None or not mcp_headers.get(mcp_server.name)
            ):
                await probe_mcp_oauth_and_raise_401(mcp_server.url)
            logger.warning(
                "Skipping MCP server %s: required %d auth headers but only resolved %d",
                mcp_server.name,
                len(mcp_server.authorization_headers),
                len(headers),
            )
            continue

        # Propagate allowlisted headers from the incoming request
        if mcp_server.headers and request_headers is not None:
            propagated = extract_propagated_headers(mcp_server, request_headers)
            existing_lower = {name.lower() for name in headers}
            for h_name, h_value in propagated.items():
                if h_name.lower() not in existing_lower:
                    headers[h_name] = h_value
                    existing_lower.add(h_name.lower())

        if len(headers) > 0:
            # add headers to tool definition
            tool_def["headers"] = headers  # type: ignore[index]
        # collect tools info
        tools.append(tool_def)
    return tools


def parse_referenced_documents(  # pylint: disable=too-many-locals
    response: ResponseObject | None,
    vector_store_ids: list[str] | None = None,
    rag_id_mapping: dict[str, str] | None = None,
) -> list[ReferencedDocument]:
    """Parse referenced documents from Responses API response.

    Args:
        response: The OpenAI Response API response object
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.

    Returns:
        List of referenced documents with doc_url, doc_title, and source
    """
    documents: list[ReferencedDocument] = []
    # Use a set to track unique documents by (doc_url, doc_title) tuple
    seen_docs: set[tuple[str | None, str | None]] = set()

    # Handle None response (e.g., when agent fails)
    if response is None or not response.output:
        return documents

    vs_ids = vector_store_ids or []
    id_mapping = rag_id_mapping or {}

    for output_item in response.output:
        item_type = getattr(output_item, "type", None)

        if item_type == "file_search_call":
            results = getattr(output_item, "results", []) or []
            for result in results:
                resolved_source = _resolve_source_for_result(result, vs_ids, id_mapping)

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
                    # Treat empty string as None for URL to satisfy AnyUrl | None
                    final_url = doc_url if doc_url else None
                    if (final_url, doc_title) not in seen_docs:
                        documents.append(
                            ReferencedDocument(
                                doc_url=final_url,
                                doc_title=doc_title,
                                source=resolved_source,
                            )
                        )
                        seen_docs.add((final_url, doc_title))

    return documents


def extract_token_usage(usage: ResponseUsage | None, model: str) -> TokenCounter:
    """Extract token usage from Responses API usage object and update metrics.

    Args:
        usage: ResponseUsage from the Responses API response, or None if not available.
        model: The model identifier in "provider/model" format

    Returns:
        TokenCounter with input_tokens and output_tokens
    """
    provider_id, model_id = extract_provider_and_model_from_model_id(model)
    if usage is None:
        logger.debug(
            "No usage information in Responses API response, token counts will be 0"
        )
        _increment_llm_call_metric(provider_id, model_id)
        return TokenCounter(llm_calls=1)

    token_counter = TokenCounter(
        input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, llm_calls=1
    )
    logger.debug(
        "Extracted token usage from Responses API: input=%d, output=%d",
        token_counter.input_tokens,
        token_counter.output_tokens,
    )

    # Update Prometheus metrics only when we have actual usage data
    try:
        metrics.llm_token_sent_total.labels(provider_id, model_id).inc(
            token_counter.input_tokens
        )
        metrics.llm_token_received_total.labels(provider_id, model_id).inc(
            token_counter.output_tokens
        )
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning("Failed to update token metrics: %s", e)

    _increment_llm_call_metric(provider_id, model_id)
    return token_counter


def build_tool_call_summary(  # pylint: disable=too-many-return-statements,too-many-branches,too-many-locals
    output_item: ResponseOutput,
    rag_chunks: list[RAGChunk],
    vector_store_ids: list[str] | None = None,
    rag_id_mapping: dict[str, str] | None = None,
) -> tuple[ToolCallSummary | None, ToolResultSummary | None]:
    """Translate Responses API tool outputs into ToolCallSummary and ToolResultSummary.

    Args:
        output_item: A ResponseOutput item from the response.output array
        rag_chunks: List to append extracted RAG chunks to (from file_search_call items)
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.

    Returns:
        Tuple of (ToolCallSummary, ToolResultSummary), one may be None
    """
    item_type = getattr(output_item, "type", None)

    if item_type == "function_call":
        item = cast(FunctionCall, output_item)
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
        file_search_item = cast(FileSearchCall, output_item)
        extract_rag_chunks_from_file_search_item(
            file_search_item, rag_chunks, vector_store_ids, rag_id_mapping
        )
        response_payload: dict[str, Any] | None = None
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
        web_search_item = cast(WebSearchCall, output_item)
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
        mcp_call_item = cast(MCPCall, output_item)
        args = parse_arguments_string(mcp_call_item.arguments)
        if mcp_call_item.server_label:
            args["server_label"] = mcp_call_item.server_label
        content = (
            mcp_call_item.error
            if mcp_call_item.error
            else (mcp_call_item.output if mcp_call_item.output else "")
        )

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
        mcp_list_tools_item = cast(MCPListTools, output_item)
        tools_info = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in mcp_list_tools_item.tools
        ]
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
        approval_request_item = cast(MCPApprovalRequest, output_item)
        args = parse_arguments_string(approval_request_item.arguments)
        return (
            ToolCallSummary(
                id=approval_request_item.id,
                name=approval_request_item.name,
                args=args,
                type="mcp_approval_request",
            ),
            None,
        )

    if item_type == "mcp_approval_response":
        approval_response_item = cast(MCPApprovalResponse, output_item)
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


def build_mcp_tool_call_from_arguments_done(
    output_index: int,
    arguments: str,
    mcp_call_items: dict[int, tuple[str, str]],
) -> ToolCallSummary | None:
    """Build ToolCallSummary from MCP call arguments completion event.

    Args:
        output_index: The output index of the MCP call item
        arguments: The JSON string of arguments from the arguments.done event
        mcp_call_items: Dictionary storing item ID and name, keyed by output_index

    Returns:
        ToolCallSummary for the MCP call, or None if item info not found
    """
    item_info = mcp_call_items.get(output_index)
    if not item_info:
        return None

    # remove from dict to indicate it was processed during arguments.done
    del mcp_call_items[output_index]
    item_id, item_name = item_info
    args = parse_arguments_string(arguments)
    return ToolCallSummary(
        id=item_id,
        name=item_name,
        args=args,
        type="mcp_call",
    )


def build_tool_result_from_mcp_output_item_done(
    output_item: MCPCall,
) -> ToolResultSummary:
    """Build ToolResultSummary from MCP call output item done event.

    Args:
        output_item: An MCP call output item

    Returns:
        ToolResultSummary for the MCP call
    """
    content = (
        output_item.error
        if output_item.error
        else (output_item.output if output_item.output else "")
    )
    return ToolResultSummary(
        id=output_item.id,
        status="success" if output_item.error is None else "failure",
        content=content,
        type="mcp_call",
        round=1,
    )


def _resolve_source_for_result(
    result: Any,
    vector_store_ids: list[str],
    rag_id_mapping: dict[str, str],
) -> str | None:
    """Resolve the human-friendly index name for a file search result.

    Uses the vector store mapping to convert internal llama-stack IDs
    to user-facing rag_ids from configuration.

    Parameters:
        result: A file search result object with optional attributes.
        vector_store_ids: The vector store IDs used in this query.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.

    Returns:
        The resolved index name, or None if resolution is not possible.
    """
    if len(vector_store_ids) == 1:
        store_id = vector_store_ids[0]
        return rag_id_mapping.get(store_id, store_id)

    if len(vector_store_ids) > 1:
        attributes = getattr(result, "attributes", {}) or {}
        attr_store_id: str | None = attributes.get("vector_store_id")
        if attr_store_id:
            return rag_id_mapping.get(attr_store_id, attr_store_id)

    return None


def _build_chunk_attributes(result: Any) -> dict[str, Any] | None:
    """Extract document metadata attributes from a file search result.

    Parameters:
        result: A file search result object with optional attributes.

    Returns:
        Dictionary of metadata attributes, or None if no attributes available.
    """
    attributes = getattr(result, "attributes", None)
    if not attributes:
        return None
    if isinstance(attributes, dict):
        return attributes if attributes else None
    return None


def extract_rag_chunks_from_file_search_item(
    item: FileSearchCall,
    rag_chunks: list[RAGChunk],
    vector_store_ids: list[str] | None = None,
    rag_id_mapping: dict[str, str] | None = None,
) -> None:
    """Extract RAG chunks from a file search tool call item.

    Args:
        item: The file search tool call item
        rag_chunks: List to append extracted RAG chunks to
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.
    """
    if item.results is not None:
        for result in item.results:
            source = _resolve_source_for_result(
                result, vector_store_ids or [], rag_id_mapping or {}
            )
            attributes = _build_chunk_attributes(result)
            rag_chunk = RAGChunk(
                content=result.text,
                source=source,
                score=result.score,
                attributes=attributes,
            )
            rag_chunks.append(rag_chunk)


def _increment_llm_call_metric(provider: str, model: str) -> None:
    """Safely increment LLM call metric."""
    try:
        metrics.llm_calls_total.labels(provider, model).inc()
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning("Failed to update LLM call metric: %s", e)


def parse_arguments_string(arguments_str: str) -> dict[str, Any]:
    """Parse an arguments string into a dictionary.

    Args:
        arguments_str: The arguments string to parse

    Returns:
        Parsed dictionary if successful, otherwise {"args": arguments_str}
    """
    # Try parsing as-is first (most common case)
    try:
        parsed = json.loads(arguments_str)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # Try wrapping in {} if string doesn't start with {
    # This handles cases where the string is just the content without braces
    stripped = arguments_str.strip()
    if stripped and not stripped.startswith("{"):
        try:
            wrapped = "{" + stripped + "}"
            parsed = json.loads(wrapped)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: return wrapped in arguments key
    return {"args": arguments_str}


async def check_model_configured(
    client: AsyncLlamaStackClient,
    model_id: str,
) -> bool:
    """Validate that a model is configured and available.

    Args:
        client: The AsyncLlamaStackClient instance
        model_id: The model identifier in "provider/model" format

    Returns:
        True if the model is available, False if not found (404)

    Raises:
        HTTPException: If there's a connection error or other API error
    """
    try:
        models = await client.models.list()
        for model in models:
            if model.id == model_id:
                return True
        return False
    except APIStatusError as e:
        response = InternalServerErrorResponse.generic()
        raise HTTPException(**response.model_dump()) from e
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e


async def select_model_for_responses(
    client: AsyncLlamaStackClient,
    user_conversation: UserConversation | None,
) -> str:
    """Select model for Responses API if not explicitly specified in the request.

    Model selection precedence:
    1. If conversation is provided and has last_used_model, use it
    2. If default model is configured, use it
    3. Otherwise, fetch available models and select the first LLM model (model_type="llm")
    4. Raise HTTPException if no LLM model is found

    Args:
        client: The AsyncLlamaStackClient instance
        user_conversation: The user conversation if conversation_id was provided, None otherwise

    Returns:
        The llama_stack_model_id in "provider/model" format

    Raises:
        HTTPException: If models cannot be fetched or an error occurs, or if no LLM model is found
    """
    # 1. Conversation has existing last_used_model
    if (
        user_conversation is not None
        and user_conversation.last_used_model
        and user_conversation.last_used_provider
    ):
        model_id = f"{user_conversation.last_used_provider}/{user_conversation.last_used_model}"
        return model_id

    # 2. Select default model from configuration
    if configuration.inference is not None:
        default_model = configuration.inference.default_model
        default_provider = configuration.inference.default_provider
        if default_model and default_provider:
            return f"{default_provider}/{default_model}"

    # 3. Fetch models list and select the first LLM model (model_type="llm")
    try:
        models = await client.models.list()
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except APIStatusError as e:
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e

    llm_models = [
        m
        for m in models
        if m.custom_metadata and m.custom_metadata.get("model_type") == "llm"
    ]
    if not llm_models:
        logger.error("No LLM model found in available models")
        response = NotFoundResponse(resource="model", resource_id=None)
        raise HTTPException(**response.model_dump())

    model = llm_models[0]
    logger.info("Selected first LLM model: %s", model.id)
    return model.id


def build_turn_summary(
    response: ResponseObject | None,
    model: str,
    vector_store_ids: list[str] | None = None,
    rag_id_mapping: dict[str, str] | None = None,
) -> TurnSummary:
    """Build a TurnSummary from a ResponseObject.

    Args:
        response: The ResponseObject to build the turn summary from, or None
        model: The model identifier in "provider/model" format
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.
    Returns:
        TurnSummary with extracted response text, referenced_documents, rag_chunks,
        tool_calls, and tool_results. All fields are empty/default if response is None
        or has no output.
    """
    summary = TurnSummary()

    if response is None or response.output is None:
        return summary

    # Extract text from output items
    summary.llm_response = extract_text_from_response_items(response.output)

    # Extract referenced documents and tool calls/results
    summary.referenced_documents = parse_referenced_documents(
        response, vector_store_ids, rag_id_mapping
    )

    for item in response.output:
        tool_call, tool_result = build_tool_call_summary(
            item, summary.rag_chunks, vector_store_ids, rag_id_mapping
        )
        if tool_call:
            summary.tool_calls.append(tool_call)
        if tool_result:
            summary.tool_results.append(tool_result)

    summary.token_usage = extract_token_usage(response.usage, model)
    return summary


def extract_text_from_response_items(
    response_items: Sequence[ResponseItem] | None,
) -> str:
    """Extract text from response items iteratively.

    Args:
        response_items: Sequence of response items (input or output), or None.

    Returns:
        Extracted text content concatenated from all items, or empty string if None.
    """
    if response_items is None:
        return ""

    text_fragments: list[str] = []
    for item in response_items:
        text = extract_text_from_response_item(item)
        if text:
            text_fragments.append(text)

    return " ".join(text_fragments)


def extract_text_from_response_item(response_item: ResponseItem) -> str:
    """Extract text from a single response item (input or output).

    Args:
        response_item: A single item from request input or response output.

    Returns:
        Extracted text content, or empty string if not a message or role is user.
    """
    if response_item.type != "message":
        return ""

    message_item = cast(ResponseMessage, response_item)
    if message_item.role == "user":
        return ""

    return _extract_text_from_content(message_item.content)


def _extract_text_from_content(
    content: str | Sequence[InputMessageContent] | Sequence[OutputMessageContent],
) -> str:
    """Extract text from message content.

    Args:
        content: Content from ResponseMessage.content which can be
                str or sequence of content parts (input or output).

    Returns:
        Extracted text content. Only extracts text from input_text, output_text,
        or refusal types. Other content types (images, files, etc.) are ignored.
    """
    if isinstance(content, str):
        return content

    text_fragments: list[str] = []
    for part in content:
        if part.type == "input_text":
            input_text_part = cast(InputTextPart, part)
            if input_text_part.text:
                text_fragments.append(input_text_part.text.strip())
        elif part.type == "output_text":
            output_text_part = cast(OutputTextPart, part)
            if output_text_part.text:
                text_fragments.append(output_text_part.text.strip())
        elif part.type == "refusal":
            refusal_part = cast(ContentPartRefusal, part)
            if refusal_part.refusal:
                text_fragments.append(refusal_part.refusal.strip())

    return " ".join(text_fragments)


def deduplicate_referenced_documents(
    docs: list[ReferencedDocument],
) -> list[ReferencedDocument]:
    """Remove duplicate referenced documents based on URL and title."""
    seen: set[tuple[str | None, str | None]] = set()
    out: list[ReferencedDocument] = []
    for d in docs:
        key = (str(d.doc_url) if d.doc_url else None, d.doc_title)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out
