"""Utility functions for processing Responses API output."""

# pylint: disable=too-many-lines

import json
from collections.abc import Mapping, Sequence
from typing import Any, Optional, cast

from fastapi import HTTPException
from llama_stack_api import OpenAIResponseObject
from llama_stack_api.openai_responses import (
    OpenAIResponseContentPartRefusal as ContentPartRefusal,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputMessageContent as InputMessageContent,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputMessageContentFile as InputFilePart,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputMessageContentText as InputTextPart,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputTool as InputTool,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoice as ToolChoice,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoiceAllowedTools as AllowedTools,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoiceMode as ToolChoiceMode,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolFileSearch as InputToolFileSearch,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolMCP as InputToolMCP,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMCPApprovalRequest as MCPApprovalRequest,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMCPApprovalResponse as MCPApprovalResponse,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage as ResponseMessage,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseObject as ResponseObject,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutput as ResponseOutput,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageContent as OutputMessageContent,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageContentOutputText as OutputTextPart,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchCall,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageFunctionToolCall as FunctionCall,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageMCPCall as MCPCall,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageMCPListTools as MCPListTools,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchCall,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseUsage as ResponseUsage,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseUsageInputTokensDetails as UsageInputTokensDetails,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseUsageOutputTokensDetails as UsageOutputTokensDetails,
)
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient

import constants
import metrics
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from constants import DEFAULT_RAG_TOOL
from log import get_logger
from models.config import ByokRag
from models.database.conversations import UserConversation
from models.requests import QueryRequest
from models.responses import (
    ConflictResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
)
from utils.mcp_headers import (
    McpHeaders,
    build_mcp_headers,
    find_unresolved_auth_headers,
)
from utils.prompts import get_system_prompt, get_topic_summary_system_prompt
from utils.query import (
    extract_provider_and_model_from_model_id,
    handle_known_apistatus_errors,
    prepare_input,
)
from utils.suid import to_llama_stack_conversation_id
from utils.token_counter import TokenCounter
from utils.types import (
    RAGChunk,
    ReferencedDocument,
    ResponseInput,
    ResponseItem,
    ResponsesApiParams,
    ToolCallSummary,
    ToolResultSummary,
    TurnSummary,
)

logger = get_logger(__name__)


async def get_vector_store_ids(
    client: AsyncLlamaStackClient,
    vector_store_ids: Optional[list[str]] = None,
) -> list[str]:
    """Get vector store IDs for querying.

    If vector_store_ids are provided, returns them. Otherwise fetches all
    available vector stores from Llama Stack.

    Args:
        client: The AsyncLlamaStackClient to use for fetching stores
        vector_store_ids: Optional list of vector store IDs. If provided,
            returns this list. If None, fetches all available vector stores.

    Returns:
        List of vector store IDs to query

    Raises:
        HTTPException: With ServiceUnavailableResponse if connection fails,
            or InternalServerErrorResponse if API returns an error status
    """
    if vector_store_ids is not None:
        return vector_store_ids

    try:
        vector_stores = await client.vector_stores.list()
        return [vector_store.id for vector_store in vector_stores.data]
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except APIStatusError as e:
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e


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
    vector_store_ids: Optional[list[str]],
    no_tools: Optional[bool],
    token: str,
    mcp_headers: Optional[McpHeaders] = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> Optional[list[InputTool]]:
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

    toolgroups: list[InputTool] = []
    effective_ids: list[str] = []

    # Vector store ID resolution priority:
    #   1. Per-request IDs: highest prio; customer-facing rag_ids are translated to vector_db_ids.
    #   2. rag.tool config IDs: used when no per-request IDs provided, and rag.tool is configured.
    #      If rag.inline is configured, but not rag.tool, tool RAG is disabled.
    #   3. All registered vector DBs: fallback when neither rag.tool nor rag.inline are configured.
    #      IDs fetched from llama-stack are already internal and need no translation.
    byok_rags = configuration.configuration.byok_rag

    is_tool_rag_enabled = len(configuration.configuration.rag.tool) > 0
    is_inline_rag_enabled = len(configuration.configuration.rag.inline) > 0

    if vector_store_ids is not None:
        effective_ids = resolve_vector_store_ids(vector_store_ids, byok_rags)
    elif is_tool_rag_enabled:
        effective_ids = resolve_vector_store_ids(
            configuration.configuration.rag.tool, byok_rags
        )
    elif not is_inline_rag_enabled:
        effective_ids = await get_vector_store_ids(client, None)

    # Add RAG tools if vector stores are available
    rag_tools = get_rag_tools(effective_ids)
    if rag_tools:
        toolgroups.extend(rag_tools)

    # Add MCP server tools
    mcp_tools = await get_mcp_tools(token, mcp_headers, request_headers)
    if mcp_tools:
        toolgroups.extend(mcp_tools)
        logger.debug(
            "Configured %d MCP tools: %s",
            len(mcp_tools),
            [tool.server_label for tool in mcp_tools],
        )
    # Convert empty list to None for consistency with existing behavior
    if not toolgroups:
        return None

    return toolgroups


def _build_provider_data_headers(
    tools: Optional[list[InputTool]],
) -> Optional[dict[str, str]]:
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
        tool.server_url: tool.headers
        for tool in tools
        if tool.type == "mcp" and tool.headers and tool.server_url
    }

    if not mcp_headers:
        return None

    return {"x-llamastack-provider-data": json.dumps({"mcp_headers": mcp_headers})}


async def prepare_responses_params(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    client: AsyncLlamaStackClient,
    query_request: QueryRequest,
    user_conversation: Optional[UserConversation],
    token: str,
    mcp_headers: Optional[McpHeaders] = None,
    stream: bool = False,
    store: bool = True,
    request_headers: Optional[Mapping[str, str]] = None,
    inline_rag_context: Optional[str] = None,
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
        inline_rag_context: Optional RAG context to inject into the query before
            sending to the LLM. Passed separately to keep QueryRequest a pure public
            API model.

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
    # Adds inline RAG context and attachments
    input_text = prepare_input(query_request, inline_rag_context)

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
    tools: Optional[list[InputTool]],
) -> list[str]:
    """Extract vector store IDs from prepared tool configurations.

    Parameters:
    ----------
        tools: The prepared tools list of InputTool objects.

    Returns:
    -------
        List of vector store IDs used in file_search tools, or empty list.
    """
    if not tools:
        return []
    vector_store_ids: list[str] = []
    for tool in tools:
        if tool.type == "file_search":
            vector_store_ids.extend(tool.vector_store_ids)
    return vector_store_ids


def tool_matches_allowed_entry(tool: InputTool, entry: dict[str, str]) -> bool:
    """Check whether a tool matches every field on one allowlist row.

    Parameters:
    ----------
        tool: Configured input tool.
        entry: Single row from allowed_tools.tools (field names match tool attributes).

    Returns:
    -------
        True if each entry key exists on the tool, the attribute is not None, and
        the value matches (including string coercion).
    """
    for key, value in entry.items():
        if not hasattr(tool, key):
            return False
        attr = getattr(tool, key)
        if attr is None:
            return False
        if attr != value and str(attr) != value:
            return False
    return True


def group_mcp_tools_by_server(
    entries: list[dict[str, str]],
) -> dict[str, Optional[list[str]]]:
    """Group MCP tool filters by server_label.

    Ignores non-mcp rows and rows without server_label. If any mcp row for a
    server has no name field, that server is unrestricted. Otherwise unique
    names are kept in first-seen order.

    Parameters:
    ----------
        entries: Raw allowlist rows (typically allowed_tools.tools).

    Returns:
    -------
        Mapping from server_label to None (no name restriction) or to the list
        of allowed tool names on that server.
    """
    unrestricted_servers: set[str] = set()
    server_to_names: dict[str, list[str]] = {}
    for entry in entries:
        if entry.get("type") != "mcp":
            continue
        server = entry.get("server_label")
        if not server:
            continue
        # Unrestricted entry (no "name")
        if "name" not in entry:
            unrestricted_servers.add(server)
            continue
        # Skip collecting names if already unrestricted
        if server in unrestricted_servers:
            continue
        name = entry["name"]
        if server not in server_to_names:
            server_to_names[server] = []

        if name not in server_to_names[server]:
            server_to_names[server].append(name)

    # Build final result
    result: dict[str, Optional[list[str]]] = {}
    for server in unrestricted_servers:
        result[server] = None

    for server, names in server_to_names.items():
        if server not in unrestricted_servers:
            result[server] = names

    return result


def mcp_strip_name_from_allowlist_entries(
    allowed_entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Copy allowlist rows and remove the name field from mcp rows only.

    Parameters:
    ----------
        allowed_entries: Original allowed_tools.tools rows.

    Returns:
    -------
        Shallow-copied rows; name is dropped only when type is mcp.
    """
    result: list[dict[str, str]] = []
    for entry in allowed_entries:
        new_entry = entry.copy()
        if new_entry.get("type") == "mcp":
            new_entry.pop("name", None)

        result.append(new_entry)

    return result


def mcp_project_allowed_tools_to_names(
    tool: InputToolMCP, names: list[str]
) -> list[str] | None:
    """Intersect allowlist tool names with the MCP tool allowed_tools constraint.

    Parameters:
    ----------
        tool: MCP tool; allowed_tools may be unset, a list of names, or a filter.
        names: Names from grouped allowlist rows for this server_label.

    Returns:
    -------
        List of names in the intersection, or None if names is empty or the
        intersection is empty.
    """
    if not names:
        return None
    name_set = set(names)
    allowed = tool.allowed_tools
    if allowed is None:
        permitted = name_set
    elif isinstance(allowed, list):
        permitted = name_set & set(allowed)
    else:
        if allowed.tool_names is None:
            permitted = name_set
        else:
            permitted = name_set & set(allowed.tool_names)

    if not permitted:
        return None

    return list(permitted)


def filter_tools_by_allowed_entries(
    tools: Optional[list[InputTool]],
    allowed_entries: list[dict[str, str]],
) -> Optional[list[InputTool]]:
    """Drop tools that match no allowlist row; narrow MCP allowed_tools when needed.

    Parameters:
    ----------
        tools: Candidate tools (e.g. after BYOK translation or prepare_tools).
        allowed_entries: Rows from allowed_tools.tools.

    Returns:
    -------
        Sublist of tools matching at least one sanitized row. MCP tools may be
        copied with a tighter allowed_tools list when the allowlist names tools
        per server. Empty allowlist yields an empty list.
    """
    if tools is None:
        return None

    if not allowed_entries:
        return []

    mcp_names_by_server = group_mcp_tools_by_server(allowed_entries)
    sanitized_entries = mcp_strip_name_from_allowlist_entries(allowed_entries)
    filtered: list[InputTool] = []
    for tool in tools:
        # Skip tools not matching any allowlist entry
        if not any(tool_matches_allowed_entry(tool, e) for e in sanitized_entries):
            continue
        # Non-MCP tools pass through and are handled separately
        if tool.type != "mcp":
            filtered.append(tool)
            continue

        mcp_tool = cast(InputToolMCP, tool)
        server = mcp_tool.server_label

        narrowed_names = mcp_names_by_server.get(server)
        # No filters specified for this MCP server
        if narrowed_names is None:
            filtered.append(tool)
            continue

        # Apply intersection
        permitted = mcp_project_allowed_tools_to_names(mcp_tool, narrowed_names)
        if permitted is None:
            continue

        filtered.append(mcp_tool.model_copy(update={"allowed_tools": permitted}))

    return filtered


def resolve_vector_store_ids(
    vector_store_ids: list[str], byok_rags: list[ByokRag]
) -> list[str]:
    """Translate customer-facing rag_ids to llama-stack vector_db_ids.

    Each ID is looked up against the BYOK RAG configuration. If a matching
    ``rag_id`` is found, the corresponding ``vector_db_id`` is returned.
    The special ``okp`` ID is mapped to the Solr vector store ID.
    Otherwise the ID is passed through unchanged (assumed to already be a
    llama-stack vector store ID).

    Parameters:
    ----------
        vector_store_ids: List of IDs from the client request (may be
            customer-facing rag_ids or raw llama-stack vector_db_ids).
        byok_rags: BYOK RAG configuration entries.

    Returns:
    -------
        List of llama-stack vector_db_ids ready for the Llama Stack API.
    """
    rag_id_to_vector_db_id = {brag.rag_id: brag.vector_db_id for brag in byok_rags}
    rag_id_to_vector_db_id[constants.OKP_RAG_ID] = (
        constants.SOLR_DEFAULT_VECTOR_STORE_ID
    )
    return [rag_id_to_vector_db_id.get(vs_id, vs_id) for vs_id in vector_store_ids]


def translate_tools_vector_store_ids(
    tools: list[InputTool], byok_rags: list[ByokRag]
) -> list[InputTool]:
    """Translate user-facing vector_store_ids to llama-stack IDs in each file_search tool.

    Parameters:
    ----------
        tools: List of request tools (may contain file_search with user-facing IDs).
        byok_rags: BYOK RAG configuration for ID resolution.

    Returns:
    -------
        New list of tools with file_search vector_store_ids translated; other tools
        unchanged.
    """
    result: list[InputTool] = []
    for tool in tools:
        if tool.type == "file_search":
            resolved_ids = resolve_vector_store_ids(tool.vector_store_ids, byok_rags)
            result.append(tool.model_copy(update={"vector_store_ids": resolved_ids}))
        else:
            result.append(tool)
    return result


def get_rag_tools(vector_store_ids: list[str]) -> Optional[list[InputToolFileSearch]]:
    """Convert vector store IDs to tools format for Responses API.

    Args:
        vector_store_ids: List of vector store identifiers

    Returns:
        List containing file_search tool configuration, or empty list if no stores available
    """
    if vector_store_ids == []:
        return []

    return [
        InputToolFileSearch(
            type="file_search",
            vector_store_ids=vector_store_ids,
            max_num_results=constants.TOOL_RAG_MAX_CHUNKS,
        )
    ]


async def get_mcp_tools(
    token: Optional[str] = None,
    mcp_headers: Optional[McpHeaders] = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> list[InputToolMCP]:
    """Convert MCP servers to tools format for Responses API.

    Fully delegates header assembly to ``build_mcp_headers``, which handles static
    config tokens, the kubernetes Bearer token, client/oauth client-provided headers,
    and propagated request headers.

    Args:
        token: Optional Kubernetes service-account token for ``kubernetes`` auth headers.
        mcp_headers: Optional per-request headers for MCP servers, keyed by server name.
        request_headers: Optional incoming HTTP request headers for allowlist propagation.

    Returns:
        List of MCP tool definitions with server details and optional auth. When
        present, the Authorization header is set as the tool's "authorization"
        field; any other resolved headers are set in "headers".

    Raises:
        HTTPException: 401 with WWW-Authenticate header when an MCP server uses OAuth,
            no headers are passed, and the server responds with 401 and WWW-Authenticate.
    """
    complete_headers = build_mcp_headers(
        configuration, mcp_headers or {}, request_headers, token
    )

    tools: list[InputToolMCP] = []
    for mcp_server in configuration.mcp_servers:
        headers: dict[str, str] = dict(complete_headers.get(mcp_server.name, {}))

        # Skip server if any configured auth header could not be resolved.
        unresolved = find_unresolved_auth_headers(
            mcp_server.authorization_headers, headers
        )
        if unresolved:
            logger.warning(
                "Skipping MCP server %s: required %d auth headers but only resolved %d",
                mcp_server.name,
                len(mcp_server.authorization_headers),
                len(mcp_server.authorization_headers) - len(unresolved),
            )
            continue

        authorization = headers.pop("Authorization", None)
        tools.append(
            InputToolMCP(
                type="mcp",
                server_label=mcp_server.name,
                server_url=mcp_server.url,
                require_approval="never",
                headers=headers if headers else None,
                authorization=authorization,
            )
        )
    return tools


def apply_mcp_headers_to_explicit_tools(
    tools: list[InputTool],
    token: Optional[str] = None,
    mcp_headers: Optional[McpHeaders] = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> list[InputTool]:
    """Merge resolved MCP headers into explicit request MCP tools.

    Args:
        tools: Tools from the request after BYOK translation.
        token: Optional bearer token for kubernetes MCP auth.
        mcp_headers: Per-request MCP-HEADERS map keyed by server name.
        request_headers: Incoming HTTP headers for allowlist propagation.

    Returns:
        New tool list with MCP entries updated or omitted.
    """
    if not tools:
        return tools

    complete_headers = build_mcp_headers(
        configuration, mcp_headers or {}, request_headers, token
    )
    servers_by_name = {s.name: s for s in configuration.mcp_servers}

    out: list[InputTool] = []
    for tool in tools:
        if tool.type != "mcp":
            out.append(tool)
            continue

        mcp_tool = cast(InputToolMCP, tool)
        mcp_server = servers_by_name.get(mcp_tool.server_label)
        if mcp_server is None:
            out.append(tool)
            continue

        headers: dict[str, str] = dict(complete_headers.get(mcp_server.name, {}))
        unresolved = find_unresolved_auth_headers(
            mcp_server.authorization_headers, headers
        )
        if unresolved:
            logger.warning(
                "Skipping explicit MCP tool %s: required %d auth headers but only resolved %d",
                mcp_server.name,
                len(mcp_server.authorization_headers),
                len(mcp_server.authorization_headers) - len(unresolved),
            )
            continue

        authorization = headers.pop("Authorization", None)
        out.append(
            mcp_tool.model_copy(
                update={
                    "headers": headers if headers else None,
                    "authorization": authorization,
                }
            )
        )
    return out


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


def parse_rag_chunks(
    response: Optional[ResponseObject],
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
) -> list[RAGChunk]:
    """Extract RAG chunks from file_search_call items in a Responses API response.

    Args:
        response: The OpenAI Response API response object
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.

    Returns:
        List of RAG chunks derived from tool file search results (not mutated in place).
    """
    if response is None or not response.output:
        return []

    rag_chunks: list[RAGChunk] = []
    for output_item in response.output:
        if output_item.type == "file_search_call":
            rag_chunks.extend(
                extract_rag_chunks_from_file_search_item(
                    cast(FileSearchCall, output_item),
                    vector_store_ids,
                    rag_id_mapping,
                )
            )

    return rag_chunks


def extract_token_usage(usage: Optional[ResponseUsage], model: str) -> TokenCounter:
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
) -> tuple[Optional[ToolCallSummary], Optional[ToolResultSummary]]:
    """Translate Responses API tool outputs into ToolCallSummary and ToolResultSummary.

    Args:
        output_item: A ResponseOutput item from the response.output array

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
    ----------
        result: A file search result object with optional attributes.
        vector_store_ids: The vector store IDs used in this query.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.

    Returns:
    -------
        The resolved index name, or None if resolution is not possible.
    """
    if len(vector_store_ids) == 1:
        store_id = vector_store_ids[0]
        return rag_id_mapping.get(store_id, store_id)

    if len(vector_store_ids) > 1:
        attributes = getattr(result, "attributes", {}) or {}

        # Primary: read index name embedded directly by rag-content.
        # This value is already the user-facing rag_id, not a vector_db_id,
        # so no mapping is needed.
        attr_source: Optional[str] = attributes.get("source")
        if attr_source:
            return attr_source

        # Fallback: if llama-stack ever populates vector_store_id in results,
        # use it with the rag_id_mapping.
        attr_store_id: Optional[str] = attributes.get("vector_store_id")
        if attr_store_id:
            return rag_id_mapping.get(attr_store_id, attr_store_id)

    return None


def _build_chunk_attributes(result: Any) -> Optional[dict[str, Any]]:
    """Extract document metadata attributes from a file search result.

    Parameters:
    ----------
        result: A file search result object with optional attributes.

    Returns:
    -------
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
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
) -> list[RAGChunk]:
    """Extract RAG chunks from a file search tool call item.

    Args:
        item: The file search tool call item
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.

    Returns:
        List of RAG chunks extracted from the file search tool call item.
    """
    if item.results is None:
        return []

    rag_chunks: list[RAGChunk] = []
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
    return rag_chunks


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

            # Workaround to llama-stack watsonx bug
            if model_id.startswith("watsonx/") and model.id == model_id.removeprefix(
                "watsonx/"
            ):
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
    user_conversation: Optional[UserConversation],
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
        return f"{user_conversation.last_used_provider}/{user_conversation.last_used_model}"

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

    # Workaround to llama-stack bug for watsonx
    # model needs to be "watsonx/<model_id>" in the response request
    metadata = model.custom_metadata or {}
    if metadata.get("provider_id") == "watsonx":
        provider_resource_id = metadata.get("provider_resource_id")
        if isinstance(provider_resource_id, str):
            return provider_resource_id
    return model.id


def is_server_deployed_output(output_item: ResponseOutput) -> bool:
    """Check if a response output item belongs to a tool deployed by LCS.

    In the hybrid architecture clients may provide their own tools (function
    tools or MCP servers running locally) alongside server-configured tools.
    This function identifies items that belong to LCS-deployed tools so that
    only those are included in server-side processing (turn summary, metrics,
    storage).  Client tool output items are still returned in the response
    to the caller but are not processed internally.

    Args:
        output_item: A ResponseOutput item from the response.

    Returns:
        True if the item should be processed by LCS, False for client tools.
    """
    item_type = getattr(output_item, "type", None)

    # function_call items are always from client-provided tools;
    # LCS only configures file_search and mcp tools.
    if item_type == "function_call":
        return False

    # MCP items: check server_label against configured servers
    if item_type in ("mcp_call", "mcp_list_tools", "mcp_approval_request"):
        server_label = getattr(output_item, "server_label", None)
        if server_label is not None:
            configured_labels = {s.name for s in configuration.mcp_servers}
            return server_label in configured_labels

    # file_search_call, web_search_call, message, and unknown types
    # are treated as server-side.
    return True


def build_turn_summary(
    response: Optional[OpenAIResponseObject],
    model: str,
    vector_store_ids: Optional[list[str]] = None,
    rag_id_mapping: Optional[dict[str, str]] = None,
    filter_server_tools: bool = False,
) -> TurnSummary:
    """Build a TurnSummary from a ResponseObject.

    Args:
        response: The ResponseObject to build the turn summary from, or None
        model: The model identifier in "provider/model" format
        vector_store_ids: Vector store IDs used in the query for source resolution.
        rag_id_mapping: Mapping from vector_db_id to user-facing rag_id.
        filter_server_tools: When True, skip client-provided tool output items
            so only server-deployed tool calls are included in the summary.

    Returns:
        TurnSummary with extracted response text, referenced_documents, rag_chunks,
        tool_calls, and tool_results. All fields are empty/default if response is None
        or has no output.
    """
    summary = TurnSummary()

    if response is None or response.output is None:
        return summary

    summary.id = response.id
    # Extract text from output items
    summary.llm_response = extract_text_from_response_items(response.output)

    # Extract referenced documents and tool calls/results
    summary.referenced_documents = parse_referenced_documents(
        response, vector_store_ids, rag_id_mapping
    )

    for item in response.output:
        if filter_server_tools and not is_server_deployed_output(item):
            continue
        tool_call, tool_result = build_tool_call_summary(item)
        if tool_call:
            summary.tool_calls.append(tool_call)
        if tool_result:
            summary.tool_results.append(tool_result)

    summary.rag_chunks = parse_rag_chunks(response, vector_store_ids, rag_id_mapping)
    summary.token_usage = extract_token_usage(response.usage, model)
    return summary


def extract_text_from_response_items(
    response_items: Optional[Sequence[ResponseItem]],
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
        Extracted text content, or empty string if not a message.
    """
    if response_item.type != "message":
        return ""

    message_item = cast(ResponseMessage, response_item)
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
        part_type = getattr(part, "type", None)
        if part_type == "input_text":
            input_text_part = cast(InputTextPart, part)
            if input_text_part.text:
                text_fragments.append(input_text_part.text.strip())
        elif part_type == "output_text":
            output_text_part = cast(OutputTextPart, part)
            if output_text_part.text:
                text_fragments.append(output_text_part.text.strip())
        elif part_type == "refusal":
            refusal_part = cast(ContentPartRefusal, part)
            if refusal_part.refusal:
                text_fragments.append(refusal_part.refusal.strip())

    return " ".join(text_fragments)


def deduplicate_referenced_documents(
    docs: list[ReferencedDocument],
) -> list[ReferencedDocument]:
    """Remove duplicate referenced documents based on URL and title."""
    seen: set[tuple[Optional[str], Optional[str]]] = set()
    out: list[ReferencedDocument] = []
    for d in docs:
        key = (str(d.doc_url) if d.doc_url else None, d.doc_title)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


async def create_new_conversation(
    client: AsyncLlamaStackClient,
) -> str:
    """Create a new conversation via the Llama Stack Conversations API.

    Args:
        client: The Llama Stack client used to create the conversation.

    Returns:
        The new conversation's ID (string), as returned by the API.
    """
    try:
        conversation = await client.conversations.create(metadata={})
        return conversation.id
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except APIStatusError as e:
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e


def get_zero_usage() -> ResponseUsage:
    """Create a Usage object with zero values for input and output tokens.

    Returns:
        Usage object with zero values for input and output tokens.
    """
    return ResponseUsage(
        input_tokens=0,
        input_tokens_details=UsageInputTokensDetails(cached_tokens=0),
        output_tokens=0,
        output_tokens_details=UsageOutputTokensDetails(reasoning_tokens=0),
        total_tokens=0,
    )


def extract_attachments_text(response_input: ResponseInput) -> str:
    """Extract file_data from input_file parts inside message content.

    Args:
        response_input: Response input (string or list of response items).

    Returns:
        All present file_data values joined by double newline.
    """
    if isinstance(response_input, str):
        return ""
    file_data_parts: list[str] = []
    for item in response_input:
        if item.type != "message":
            continue
        message = cast(ResponseMessage, item)
        content = message.content
        if isinstance(content, str):
            continue
        for part in content:
            if part.type == "input_file":
                file_part = cast(InputFilePart, part)
                if file_part.file_data:
                    file_data_parts.append(file_part.file_data)
    return "\n\n".join(file_data_parts)


def _merge_tools(
    client_tools: list[InputTool],
    server_tools: list[InputTool],
) -> list[InputTool]:
    """Merge server-configured tools into client-provided tools, rejecting conflicts.

    Raises an HTTP 409 error when a client tool conflicts with a
    server-configured tool.  Conflicts are detected by:
    - MCP tools: matching ``server_label``
    - file_search tools: client provides file_search when server also configures one

    Args:
        client_tools: Tools explicitly provided by the client.
        server_tools: Tools loaded from server configuration.

    Returns:
        Merged list with client tools first, followed by non-conflicting server tools.

    Raises:
        HTTPException: 409 if a client tool conflicts with a server-configured tool.
    """
    server_mcp_labels: set[str] = {
        t.server_label for t in server_tools if t.type == "mcp"
    }
    has_server_file_search = any(t.type == "file_search" for t in server_tools)

    for tool in client_tools:
        if tool.type == "mcp" and tool.server_label in server_mcp_labels:
            error_response = ConflictResponse.mcp_tool(tool.server_label)
            raise HTTPException(**error_response.model_dump())
        if tool.type == "file_search" and has_server_file_search:
            error_response = ConflictResponse.file_search()
            raise HTTPException(**error_response.model_dump())

    return list(client_tools) + list(server_tools)


async def _resolve_client_tools(
    tools: list[InputTool],
    token: str,
    mcp_headers: Optional[McpHeaders],
    request_headers: Optional[Mapping[str, str]],
    merge_server_tools: bool,
) -> list[InputTool]:
    """Resolve client-provided tools, optionally merging with server tools.

    Translates vector store IDs using BYOK configuration, applies MCP headers,
    and optionally merges server-configured tools when merge is requested.
    Conflicts (e.g. a client MCP tool with the same server_label as a
    server-configured one, or duplicate file_search tools) are rejected with
    a 409 error.

    Args:
        tools: Tools explicitly provided by the client.
        token: User token for MCP and auth.
        mcp_headers: Optional MCP headers.
        request_headers: Optional headers for tool resolution.
        merge_server_tools: Whether to merge server-configured tools.

    Returns:
        Resolved list of tools.
    """
    # Per-request override of vector stores (user-facing rag_ids)
    vector_store_ids = extract_vector_store_ids_from_tools(tools) or None
    # Translate user-facing rag_ids to llama-stack vector_store_ids in each file_search tool
    byok_rags = configuration.configuration.byok_rag
    prepared_tools = translate_tools_vector_store_ids(tools, byok_rags)
    prepared_tools = apply_mcp_headers_to_explicit_tools(
        prepared_tools, token, mcp_headers, request_headers
    )

    # Optionally merge server-configured tools (RAG, MCP) with client tools
    if merge_server_tools:
        client = AsyncLlamaStackClientHolder().get_client()
        server_tools = await prepare_tools(
            client=client,
            vector_store_ids=vector_store_ids,
            no_tools=False,
            token=token,
            mcp_headers=mcp_headers,
            request_headers=request_headers,
        )
        if server_tools:
            prepared_tools = _merge_tools(prepared_tools, server_tools)

    return prepared_tools


async def _resolve_server_tools(
    token: str,
    mcp_headers: Optional[McpHeaders],
    request_headers: Optional[Mapping[str, str]],
) -> Optional[list[InputTool]]:
    """Load all server-configured tools from LCORE configuration.

    Args:
        token: User token for MCP and auth.
        mcp_headers: Optional MCP headers.
        request_headers: Optional headers for tool resolution.

    Returns:
        List of server-configured tools, or None if none are configured.
    """
    client = AsyncLlamaStackClientHolder().get_client()
    return await prepare_tools(
        client=client,
        vector_store_ids=None,  # allow all vector stores configured
        no_tools=False,
        token=token,
        mcp_headers=mcp_headers,
        request_headers=request_headers,
    )


async def resolve_tool_choice(
    tools: Optional[list[InputTool]],
    tool_choice: Optional[ToolChoice],
    token: str,
    mcp_headers: Optional[McpHeaders] = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> tuple[Optional[list[InputTool]], Optional[ToolChoice]]:
    """Resolve tools and tool choice for the Responses API.

    When tool choice is mode none, returns (None, None) so Llama Stack sees no
    tools, even if the request listed tools.

    When tools is omitted, load tools from LCORE configuration via prepare_tools.
    When tools are present, translate vector store IDs using BYOK configuration.

    When filters are present, apply them to prepared tools and overwrite tool choice mode.

    If no tools remain after filtering, both prepared tools and tool choice are cleared.

    Args:
        tools: Request tools, or None for LCORE-configured tools.
        tool_choice: Requested strategy, or None.
        token: User token for MCP and auth.
        mcp_headers: Optional MCP headers.
        request_headers: Optional headers for tool resolution.

    Returns:
        Prepared tools and resolved tool choice, each possibly None.
    """
    # If tool_choice mode is "none", tools are explicitly disallowed
    if isinstance(tool_choice, ToolChoiceMode) and tool_choice == ToolChoiceMode.none:
        return None, None

    if tools is None:
        # Register all tools configured in LCORE configuration
        client = AsyncLlamaStackClientHolder().get_client()
        prepared_tools = await prepare_tools(
            client=client,
            vector_store_ids=None,  # allow all vector stores configured
            no_tools=False,
            token=token,
            mcp_headers=mcp_headers,
            request_headers=request_headers,
        )
    else:
        # Pass tools explicitly configured for this request
        byok_rags = configuration.configuration.byok_rag
        prepared_tools = translate_tools_vector_store_ids(tools, byok_rags)
        prepared_tools = apply_mcp_headers_to_explicit_tools(
            prepared_tools, token, mcp_headers, request_headers
        )

    if isinstance(tool_choice, AllowedTools):
        # Apply filters to tools if specified and overwrite tool choice mode
        prepared_tool_choice = ToolChoiceMode(tool_choice.mode)
        prepared_tools = filter_tools_by_allowed_entries(
            prepared_tools, tool_choice.tools
        )
    else:
        # Use request tool choice mode or default to auto
        prepared_tool_choice = tool_choice or ToolChoiceMode.auto

    # Clear tools and tool choice if no tools remain for consistency with Responses API
    if not prepared_tools:
        prepared_tools = None
        prepared_tool_choice = None

    return prepared_tools, prepared_tool_choice


async def resolve_client_tool_choice(
    tools: Optional[list[InputTool]],
    tool_choice: Optional[ToolChoice],
    token: str,
    mcp_headers: Optional[McpHeaders] = None,
    request_headers: Optional[Mapping[str, str]] = None,
) -> tuple[Optional[list[InputTool]], Optional[ToolChoice]]:
    """Resolve tools and tool choice when client tools are merged with server tools.

    This function isolates the tool resolution logic used when the
    ``X-LCS-Merge-Server-Tools`` header is present.  Client-provided tools are
    resolved via BYOK translation and MCP header application, then merged with
    server-configured tools.  Conflicts (duplicate MCP server_label or
    file_search) are rejected with a 409 error.

    When tool choice is mode none, returns (None, None) so Llama Stack sees no
    tools, even if the request listed tools.

    When filters are present, apply them to prepared tools and overwrite tool
    choice mode.

    If no tools remain after filtering, both prepared tools and tool choice are
    cleared.

    Args:
        tools: Request tools, or None for LCORE-configured tools.
        tool_choice: Requested strategy, or None.
        token: User token for MCP and auth.
        mcp_headers: Optional MCP headers.
        request_headers: Optional headers for tool resolution.

    Returns:
        Prepared tools and resolved tool choice, each possibly None.
    """
    # If tool_choice mode is "none", tools are explicitly disallowed
    if isinstance(tool_choice, ToolChoiceMode) and tool_choice == ToolChoiceMode.none:
        return None, None

    if tools:
        prepared_tools: Optional[list[InputTool]] = await _resolve_client_tools(
            tools, token, mcp_headers, request_headers, merge_server_tools=True
        )
    else:
        prepared_tools = await _resolve_server_tools(
            token, mcp_headers, request_headers
        )

    if isinstance(tool_choice, AllowedTools):
        # Apply filters to tools if specified and overwrite tool choice mode
        prepared_tool_choice = ToolChoiceMode(tool_choice.mode)
        prepared_tools = filter_tools_by_allowed_entries(
            prepared_tools, tool_choice.tools
        )
    else:
        # Use request tool choice mode or default to auto
        prepared_tool_choice = tool_choice or ToolChoiceMode.auto

    # Clear tools and tool choice if no tools remain for consistency with Responses API
    if not prepared_tools:
        prepared_tools = None
        prepared_tool_choice = None

    return prepared_tools, prepared_tool_choice
