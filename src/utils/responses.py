# pylint: disable=too-many-lines,too-many-branches,too-many-nested-blocks,too-many-arguments,too-many-positional-arguments,too-many-locals
"""Utility functions for processing Responses API output."""

import json
from typing import Any, Optional, cast

from fastapi import HTTPException
from llama_stack_api.openai_responses import (
    OpenAIResponseObject,
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchCall,
    OpenAIResponseOutputMessageFunctionToolCall as FunctionCall,
    OpenAIResponseOutputMessageMCPCall as MCPCall,
    OpenAIResponseOutputMessageMCPListTools as MCPListTools,
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchCall,
    OpenAIResponseMCPApprovalRequest as MCPApprovalRequest,
    OpenAIResponseMCPApprovalResponse as MCPApprovalResponse,
)
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient
from llama_stack_client.types import ResponseObject
from llama_stack_client.types.response_object import Output, Usage

import constants
import metrics
from configuration import AppConfig, configuration
from constants import DEFAULT_RAG_TOOL
from models.config import Action, ModelContextProtocolServer
from models.database.conversations import UserConversation
from models.requests import QueryRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
)
from models.responses_api_types import ResponseInput
from utils.mcp_headers import McpHeaders
from utils.prompts import get_system_prompt, get_topic_summary_system_prompt
from utils.query import (
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    persist_user_conversation_details_from_responses,
    prepare_input,
    select_model_and_provider_id,
    store_conversation_into_cache_from_responses,
)
from utils.suid import to_llama_stack_conversation_id
from utils.token_counter import TokenCounter
from utils.types import (
    RAGChunk,
    ReferencedDocument,
    ResponsesApiParams,
    ToolCallSummary,
    ToolResultSummary,
)
from log import get_logger

logger = get_logger(__name__)


def extract_text_from_input(
    input_value: Optional[ResponseInput],
) -> str:  # pylint: disable=too-many-branches
    """Extract text content from Responses API input field.

    Args:
        input_value: The input value from ResponsesRequest

    Returns:
        Extracted text content as a string, or empty string if input is None or cannot be extracted
    """
    if input_value is None:
        return ""
    if isinstance(input_value, str):
        return input_value

    text_fragments: list[str] = []
    for message in input_value:
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                text_fragments.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, str):
                        text_fragments.append(part)
                    elif isinstance(part, dict):
                        text_value = part.get("text") or part.get("refusal")
                        if text_value:
                            text_fragments.append(str(text_value))
        elif hasattr(message, "content"):
            # Handle object with content attribute
            content = getattr(message, "content")
            if isinstance(content, str):
                text_fragments.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, str):
                        text_fragments.append(part)
                    elif hasattr(part, "text"):
                        text_fragments.append(getattr(part, "text", ""))
                    elif isinstance(part, dict):
                        text_value = part.get("text") or part.get("refusal")
                        if text_value:
                            text_fragments.append(str(text_value))
    return " ".join(text_fragments)


def extract_text_from_response_output_item(output_item: Any) -> str:
    """Extract assistant message text from a Responses API output item.

    Args:
        output_item: A Responses API output item from response.output array.

    Returns:
        Extracted text content, or empty string if not an assistant message.
    """
    if getattr(output_item, "type", None) != "message":
        return ""
    if getattr(output_item, "role", None) != "assistant":
        return ""

    content = getattr(output_item, "content", None)
    if isinstance(content, str):
        return content

    text_fragments: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                text_fragments.append(part)
                continue
            text_value = getattr(part, "text", None)
            if text_value:
                text_fragments.append(text_value)
                continue
            refusal = getattr(part, "refusal", None)
            if refusal:
                text_fragments.append(refusal)
                continue
            if isinstance(part, dict):
                dict_text = part.get("text") or part.get("refusal")
                if dict_text:
                    text_fragments.append(str(dict_text))

    return "".join(text_fragments)


def extract_text_from_output_items(output_items: list[Output]) -> str:
    """Extract and aggregate text from a list of Responses API output items.

    Args:
        output_items: List of output items from response.output array.

    Returns:
        Aggregated text content from all output items, joined with spaces.
    """
    text_parts = [extract_text_from_response_output_item(item) for item in output_items]
    return " ".join(text_parts)


async def get_topic_summary(  # pylint: disable=too-many-nested-blocks
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
    topic_summary_system_prompt = get_topic_summary_system_prompt(configuration)

    # Use Responses API to generate topic summary
    try:
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
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except APIStatusError as e:
        error_response = handle_known_apistatus_errors(e, model_id)
        raise HTTPException(**error_response.model_dump()) from e

    # Extract text from response output
    summary_text = "".join(
        extract_text_from_response_output_item(output_item)
        for output_item in response.output
    )

    return summary_text.strip() if summary_text else ""


def validate_model_override_permissions(
    model_id: Optional[str], authorized_actions: set[Action] | frozenset[Action]
) -> None:
    """Validate whether model/provider overrides are allowed by RBAC.

    Args:
        model_id: The model identifier in format "provider/model" (e.g., "openai/gpt-4-turbo").
                  If None, no validation is performed.
        authorized_actions: Set of actions the user is authorized to perform.

    Raises:
        HTTPException: HTTP 403 if model_id is provided and the caller lacks
                       Action.MODEL_OVERRIDE permission.
    """
    if model_id is None:
        return

    # Check if user has permission to override model/provider
    if Action.MODEL_OVERRIDE not in authorized_actions:
        response = ForbiddenResponse.model_override()
        raise HTTPException(**response.model_dump())


async def prepare_tools(
    client: AsyncLlamaStackClient,
    query_request: QueryRequest,
    token: str,
    config: AppConfig,
    mcp_headers: Optional[McpHeaders] = None,
) -> Optional[list[dict[str, Any]]]:
    """Prepare tools for Responses API including RAG and MCP tools.

    Args:
        client: The Llama Stack client instance
        query_request: The user's query request
        token: Authentication token for MCP tools
        config: Configuration object containing MCP server settings
        mcp_headers: Per-request headers for MCP servers

    Returns:
        List of tool configurations, or None if no_tools is True or no tools available
    """
    if query_request.no_tools:
        return None

    toolgroups = []
    # Get vector stores for RAG tools - use specified ones or fetch all
    if query_request.vector_store_ids:
        vector_store_ids = query_request.vector_store_ids
    else:
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
    mcp_tools = get_mcp_tools(config.mcp_servers, token, mcp_headers)
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


async def select_model_for_responses(
    client: AsyncLlamaStackClient,
    user_conversation: Optional[UserConversation],
) -> str:
    """Select model and provider for Responses API (takes model in provider/model format).

    Extracts provider and model from the joined format, applies conversation hints if needed,
    and invokes the internal model selection function. This function is intended for use
    with ResponsesRequest which has a combined model field in "provider/model" format.

    Args:
        client: The AsyncLlamaStackClient instance
        user_conversation: The user conversation if conversation_id was provided, None otherwise

    Returns:
        The llama_stack_model_id in "provider/model" format

    Raises:
        HTTPException: If models cannot be fetched or an error occurs, or if no LLM model is found
    """
    # Early return if conversation has existing last_used_model
    if (
        user_conversation is not None
        and user_conversation.last_used_model
        and user_conversation.last_used_provider
    ):
        model_id = f"{user_conversation.last_used_provider}/{user_conversation.last_used_model}"
        try:
            await client.models.retrieve(model_id)
            logger.debug(
                "Using last used model from conversation: %s",
                model_id,
            )
            return model_id
        except APIStatusError as e:
            if e.status_code == 404:
                logger.warning(
                    "Last used model %s from conversation not found, "
                    "will select from available models",
                    model_id,
                )
                # Fall through to select from available models
            else:
                error_response = InternalServerErrorResponse.generic()
                raise HTTPException(**error_response.model_dump()) from e
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e

    # Fetch models list
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

    try:
        model = next(
            m
            for m in models
            if m.custom_metadata and m.custom_metadata.get("model_type") == "llm"
        )
        logger.info("Selected first LLM model: %s", model.id)
        return model.id
    except StopIteration as e:
        message = "No LLM model found in available models"
        logger.error(message)
        response = NotFoundResponse(resource="model", resource_id="")
        raise HTTPException(**response.model_dump()) from e


async def prepare_responses_params(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    client: AsyncLlamaStackClient,
    query_request: QueryRequest,
    user_conversation: Optional[UserConversation],
    token: str,
    mcp_headers: Optional[McpHeaders] = None,
    stream: bool = False,
    store: bool = True,
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

    Returns:
        ResponsesApiParams containing all prepared parameters for the API request
    """
    # Select model and provider
    # Use select_model_and_provider_id directly with model hints from query_request
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

    # Apply conversation hints if available
    model_id = query_request.model
    provider_id = query_request.provider
    if user_conversation is not None:
        if model_id is None:
            model_id = user_conversation.last_used_model
        if provider_id is None:
            provider_id = user_conversation.last_used_provider

    llama_stack_model_id, _model_id, _provider_id = select_model_and_provider_id(
        models, model_id, provider_id
    )

    # Use system prompt from request or default one
    system_prompt = get_system_prompt(query_request, configuration)
    logger.debug("Using system prompt: %s", system_prompt)

    # Prepare tools for responses API
    tools = await prepare_tools(
        client, query_request, token, configuration, mcp_headers
    )

    # Prepare input for Responses API
    input_text = prepare_input(query_request)

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

    return ResponsesApiParams(
        input=input_text,
        model=llama_stack_model_id,
        instructions=system_prompt,
        tools=tools,
        conversation=llama_stack_conv_id,
        stream=stream,
        store=store,
    )


def extract_vector_store_ids_from_tools(
    tools: Optional[list[dict[str, Any]]],
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


def get_rag_tools(vector_store_ids: list[str]) -> Optional[list[dict[str, Any]]]:
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


def get_mcp_tools(
    mcp_servers: list[ModelContextProtocolServer],
    token: str | None = None,
    mcp_headers: Optional[McpHeaders] = None,
) -> list[dict[str, Any]]:
    """Convert MCP servers to tools format for Responses API.

    Args:
        mcp_servers: List of MCP server configurations
        token: Optional authentication token for MCP server authorization
        mcp_headers: Optional per-request headers for MCP servers, keyed by server URL

    Returns:
        List of MCP tool definitions with server details and optional auth headers
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
            logger.warning(
                "Skipping MCP server %s: required %d auth headers but only resolved %d",
                mcp_server.name,
                len(mcp_server.authorization_headers),
                len(headers),
            )
            continue

        if len(headers) > 0:
            # add headers to tool definition
            tool_def["headers"] = headers  # type: ignore[index]
        # collect tools info
        tools.append(tool_def)
    return tools


def parse_referenced_documents(  # pylint: disable=too-many-locals
    response: Optional[ResponseObject],
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
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
    seen_docs: set[tuple[Optional[str], Optional[str]]] = set()

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
                    # Treat empty string as None for URL to satisfy Optional[AnyUrl]
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


def extract_token_usage(usage: Optional[Usage], model_id: str) -> TokenCounter:
    """Extract token usage from Responses API usage object and update metrics.

    Args:
        usage: Optional[Usage] from llama_stack_client.types.response_object. The Usage
            object from the Responses API response, or None if not available.
        model_id: The model identifier for metrics labeling

    Returns:
        TokenCounter with input_tokens and output_tokens
    """
    token_counter = TokenCounter()
    token_counter.llm_calls = 1
    provider, model = extract_provider_and_model_from_model_id(model_id)

    if usage is None:
        logger.debug(
            "No usage information in Responses API response, token counts will be 0"
        )
        _increment_llm_call_metric(provider, model)
        return token_counter

    try:
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
    except (AttributeError, TypeError) as e:
        logger.warning("Failed to extract token usage from usage object: %s", e)
        _increment_llm_call_metric(provider, model)
        return token_counter

    # Only set if we got valid values
    if not (input_tokens or output_tokens):
        logger.debug(
            "Usage object exists but tokens are 0 or None, treating as no usage info"
        )
        _increment_llm_call_metric(provider, model)
        return token_counter

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
    return token_counter


def build_tool_call_summary(  # pylint: disable=too-many-return-statements,too-many-branches
    output_item: Output,
    rag_chunks: list[RAGChunk],
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
) -> tuple[Optional[ToolCallSummary], Optional[ToolResultSummary]]:
    """Translate Responses API tool outputs into ToolCallSummary and ToolResultSummary.

    Args:
        output_item: An OpenAIResponseOutput item from the response.output array
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
) -> Optional[ToolCallSummary]:
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
) -> Optional[str]:
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
        attr_store_id: Optional[str] = attributes.get("vector_store_id")
        if attr_store_id:
            return rag_id_mapping.get(attr_store_id, attr_store_id)

    return None


def _build_chunk_attributes(result: Any) -> Optional[dict[str, Any]]:
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
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
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


def extract_response_metadata(
    response: Optional[ResponseObject],
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
) -> tuple[
    str, list[ReferencedDocument], list[ToolCallSummary], list[ToolResultSummary]
]:
    """Extract response text and metadata from a ResponseObject.

    Args:
        response: The ResponseObject to extract metadata from, or None
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.

    Returns:
        Tuple of (response_text, referenced_documents, tool_calls, tool_results)
        All list fields are empty lists if response is None or has no output
    """
    if response is None or not response.output:
        return "", [], [], []

    # Extract text from output items
    response_text = extract_text_from_output_items(response.output)

    # Extract referenced documents and tool calls/results
    referenced_documents = parse_referenced_documents(
        response, vector_store_ids, rag_id_mapping
    )
    rag_chunks: list[RAGChunk] = []
    tool_calls: list[ToolCallSummary] = []
    tool_results: list[ToolResultSummary] = []

    for item in response.output:
        tool_call, tool_result = build_tool_call_summary(
            item, rag_chunks, vector_store_ids, rag_id_mapping
        )
        if tool_call:
            tool_calls.append(tool_call)
        if tool_result:
            tool_results.append(tool_result)

    return response_text, referenced_documents, tool_calls, tool_results


async def persist_response_metadata(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    user_id: str,
    conversation_id: str,
    model_id: str,
    input_text: str,
    response_text: str,
    started_at: str,
    completed_at: str,
    topic_summary: Optional[str],
    referenced_documents: list[ReferencedDocument],
    tool_calls: list[ToolCallSummary],
    tool_results: list[ToolResultSummary],
    _skip_userid_check: bool,
) -> None:
    """Persist response metadata to database and cache.

    Args:
        user_id: The authenticated user ID
        conversation_id: The conversation ID
        model_id: Model identifier in "provider/model" format
        input_text: The input text
        response_text: The extracted response text
        started_at: Timestamp when the conversation started
        completed_at: Timestamp when the conversation completed
        topic_summary: Optional topic summary
        referenced_documents: List of referenced documents
        tool_calls: List of tool calls
        tool_results: List of tool results
        _skip_userid_check: Whether to skip user ID check for cache operations
    """
    logger.info("Persisting conversation details")
    persist_user_conversation_details_from_responses(
        user_id=user_id,
        conversation_id=conversation_id,
        model=model_id,
        started_at=started_at,
        completed_at=completed_at,
        topic_summary=topic_summary,
    )

    logger.info("Storing conversation in cache")
    store_conversation_into_cache_from_responses(
        config=configuration,
        user_id=user_id,
        conversation_id=conversation_id,
        model=model_id,
        query=input_text,
        response=response_text,
        started_at=started_at,
        completed_at=completed_at,
        _skip_userid_check=_skip_userid_check,
        topic_summary=topic_summary,
        referenced_documents=referenced_documents,
        tool_calls=tool_calls,
        tool_results=tool_results,
    )


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
