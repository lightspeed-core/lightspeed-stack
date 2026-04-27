"""Handler for REST API calls related to MCP server authentication."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

import constants
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from log import get_logger
from models.config import Action
from models.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    ForbiddenResponse,
    InternalServerErrorResponse,
    MCPClientAuthOptionsResponse,
    MCPServerAuthInfo,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)
router = APIRouter(prefix="/mcp-auth", tags=["mcp-auth"])


mcp_auth_responses: dict[int | str, dict[str, Any]] = {
    200: MCPClientAuthOptionsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}


@router.get("/client-options", responses=mcp_auth_responses)
@authorize(
    Action.GET_TOOLS
)  # Uses GET_TOOLS: discovering client auth is related to tool discovery
async def get_mcp_client_auth_options(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> MCPClientAuthOptionsResponse:
    """
    Get MCP servers that accept client-provided authorization.

    Returns a list of MCP servers configured to accept client-provided
    authorization tokens, along with the header names where clients
    should provide these tokens.

    This endpoint helps clients discover which MCP servers they can
    authenticate with using their own tokens.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - mcp_headers: Headers that should be passed to MCP servers.

    ### Returns:
    - MCPClientAuthOptionsResponse: List of MCP servers and their
      accepted client authentication headers.
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    servers_info = []

    for mcp_server in configuration.mcp_servers:
        if not mcp_server.authorization_headers:
            continue

        # Find headers with "client" value
        client_headers = [
            header_name
            for header_name, header_value in mcp_server.authorization_headers.items()
            if header_value.strip() == constants.MCP_AUTH_CLIENT
        ]

        if client_headers:
            servers_info.append(
                MCPServerAuthInfo(
                    name=mcp_server.name,
                    client_auth_headers=client_headers,
                )
            )

    return MCPClientAuthOptionsResponse(servers=servers_info)
