"""Handler for REST API call to list available tools from MCP servers."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncOgxClientHolder
from configuration import configuration
from log import get_logger
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import ToolsResponse
from models.common.tools import CatalogTool
from models.config import Action, ModelContextProtocolServer
from utils.builtin_tools import get_file_search_tools
from utils.endpoints import check_configuration_loaded
from utils.mcp_headers import (
    McpHeaders,
    build_mcp_headers,
    find_unresolved_auth_headers,
    mcp_headers_dependency,
)
from utils.mcp_oauth_probe import check_mcp_auth
from utils.mcp_tools import list_mcp_tools
from utils.pydantic_ai_helpers import get_agent_capability_tools
from utils.tool_formatter import build_catalog_tool

logger = get_logger(__name__)
router = APIRouter(tags=["tools"])


tools_responses: dict[int | str, dict[str, Any]] = {
    200: ToolsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["ogx", "kubernetes api"]
    ),
}


@router.get("/tools", responses=tools_responses)
@authorize(Action.GET_TOOLS)
async def tools_endpoint_handler(  # pylint: disable=too-many-locals
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: McpHeaders = Depends(mcp_headers_dependency),
) -> ToolsResponse:
    """
    Handle requests to the /tools endpoint.

    Process GET requests to the /tools endpoint, returning a consolidated list of
    available tools from all configured MCP servers.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - mcp_headers: Headers that should be passed to MCP servers.

    ### Raises:
    - HTTPException: with status 401 for unauthorized access.
    - HTTPException: with status 403 if permission is denied.
    - HTTPException: with status 422 if mcp_headers parameter is
      improper.
    - HTTPException: with status 500 and a detail object containing `response`
      and `cause` when service configuration is wrong or incomplete.
    - HTTPException: with status 503 and a detail object containing `response`
      and `cause` when unable to connect to Llama Stack.

    ### Returns:
    - ToolsResponse: An object containing the consolidated list of available
      tools with metadata including tool name, description, parameters, and
      server source.
    """
    _, _, _, token = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    complete_mcp_headers = build_mcp_headers(
        configuration, mcp_headers, request.headers, token
    )

    # Check MCP auth
    await check_mcp_auth(configuration, mcp_headers, token, request.headers)

    client = AsyncOgxClientHolder().get_client()
    consolidated_tools: list[CatalogTool] = list(await get_file_search_tools(client))

    for mcp_server in configuration.mcp_servers:
        consolidated_tools.extend(
            await _list_tools_for_mcp_server(
                mcp_server,
                complete_mcp_headers.get(mcp_server.name, {}),
            )
        )

    existing_tool_ids = {
        tool.identifier for tool in consolidated_tools if tool.identifier
    }
    for tool in get_agent_capability_tools(configuration.skills):
        if tool.identifier not in existing_tool_ids:
            consolidated_tools.append(tool)
            existing_tool_ids.add(tool.identifier)

    builtin_tool_count = len(
        [tool for tool in consolidated_tools if tool.server_source == "builtin"]
    )
    mcp_tool_count = len(consolidated_tools) - builtin_tool_count
    logger.info(
        "Retrieved total of %d tools (%d builtin, %d from MCP servers)",
        len(consolidated_tools),
        builtin_tool_count,
        mcp_tool_count,
    )

    return ToolsResponse(tools=consolidated_tools)


async def _list_tools_for_mcp_server(
    mcp_server: ModelContextProtocolServer,
    headers: dict[str, str],
) -> list[CatalogTool]:
    """Discover tools from a single configured MCP server.

    ### Parameters:
    - mcp_server: MCP server configuration entry.
    - headers: Resolved request headers for the server.

    ### Returns:
    - Catalog tools for the server, or an empty list when skipped or failing.
    """
    unresolved = find_unresolved_auth_headers(
        mcp_server.authorization_headers,
        headers,
    )
    if unresolved:
        logger.warning(
            "Skipping MCP server %s: required %d auth headers but only resolved %d",
            mcp_server.name,
            len(mcp_server.authorization_headers),
            len(mcp_server.authorization_headers) - len(unresolved),
        )
        return []

    discovered_tools = await list_mcp_tools(
        endpoint=mcp_server.url,
        headers=headers,
    )
    if not discovered_tools:
        return []

    tools = [
        build_catalog_tool(
            tool, mcp_server.provider_id, mcp_server.name, mcp_server.url
        )
        for tool in discovered_tools
    ]
    logger.debug(
        "Retrieved %d tools from MCP server %s (source: %s)",
        len(tools),
        mcp_server.name,
        mcp_server.url,
    )
    return tools
