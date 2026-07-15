"""Handler for REST API calls to dynamically manage MCP servers."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from configuration import configuration
from log import get_logger
from models.api.requests import MCPServerRegistrationRequest
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ConflictResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import (
    MCPServerDeleteResponse,
    MCPServerListResponse,
    MCPServerRegistrationResponse,
)
from models.common import MCPServerInfo
from models.config import Action, ModelContextProtocolServer
from utils.endpoints import check_configuration_loaded

logger = get_logger(__name__)
router = APIRouter(tags=["mcp-servers"])


register_responses: dict[int | str, dict[str, Any]] = {
    201: MCPServerRegistrationResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    409: ConflictResponse.openapi_response(examples=["mcp server"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["configuration", "mcp server registration"]
    ),
}


@router.post(
    "/mcp-servers",
    responses=register_responses,
    status_code=status.HTTP_201_CREATED,
)
@authorize(Action.REGISTER_MCP_SERVER)
async def register_mcp_server_handler(
    request: Request,
    body: MCPServerRegistrationRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> MCPServerRegistrationResponse:
    """Register an MCP server dynamically at runtime.

    Adds the MCP server to the runtime configuration so it becomes available
    for queries.

    ### Parameters:
    - request: Model containing attributes to dynamically registering an MCP server.
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - body: Headers that should be passed to MCP servers.

    ### Raises:
    - HTTPException: On duplicate name or registration failure.

    ### Returns:
    - MCPServerRegistrationResponse: Details of the newly registered server.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    mcp_server = ModelContextProtocolServer.model_validate(
        body.model_dump(exclude_none=True)
    )

    try:
        configuration.add_mcp_server(mcp_server)
    except ValueError as exc:
        response = ConflictResponse(resource="MCP server", resource_id=body.name)
        raise HTTPException(**response.model_dump()) from exc

    logger.info("Dynamically registered MCP server: %s at %s", body.name, body.url)

    return MCPServerRegistrationResponse(
        name=mcp_server.name,
        url=mcp_server.url,
        provider_id=mcp_server.provider_id,
        message=f"MCP server '{mcp_server.name}' registered successfully",
    )


list_responses: dict[int | str, dict[str, Any]] = {
    200: MCPServerListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
}


@router.get("/mcp-servers", responses=list_responses)
@authorize(Action.LIST_MCP_SERVERS)
async def list_mcp_servers_handler(
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> MCPServerListResponse:
    """List all registered MCP servers.

    Returns both statically configured (from YAML) and dynamically
    registered (via API) MCP servers.

    ### Parameters:
    - request: Model containing attributes to dynamically registering an MCP server.
    - auth: Authentication tuple from the auth dependency (used by middleware).

    ### Raises:
    - HTTPException: If configuration is not loaded.

    ### Returns:
    - MCPServerListResponse: List of all registered MCP servers with source info.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    servers = [
        MCPServerInfo(
            name=mcp.name,
            url=mcp.url,
            provider_id=mcp.provider_id,
            source="api" if configuration.is_dynamic_mcp_server(mcp.name) else "config",
        )
        for mcp in configuration.mcp_servers
    ]

    return MCPServerListResponse(servers=servers)


delete_responses: dict[int | str, dict[str, Any]] = {
    200: MCPServerDeleteResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "mcp server static"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
}


@router.delete("/mcp-servers/{name}", responses=delete_responses)
@authorize(Action.DELETE_MCP_SERVER)
async def delete_mcp_server_handler(
    request: Request,
    name: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> MCPServerDeleteResponse:
    """Unregister a dynamically registered MCP server.

    Removes the MCP server from the runtime configuration. Only servers
    registered via the API can be deleted; statically configured servers
    cannot be removed.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - name: MCP server name

    ### Raises:
    - HTTPException: If the server is not found or is statically configured.

    ### Returns:
    - MCPServerDeleteResponse: Confirmation of the deletion.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    if not configuration.is_dynamic_mcp_server(name):
        static_mcp_names = {server.name for server in configuration.mcp_servers}
        if name in static_mcp_names:
            response = ForbiddenResponse.mcp_server_static_config(name)
            raise HTTPException(**response.model_dump())

    try:
        configuration.remove_mcp_server(name)
        local_deleted = True
    except ValueError as exc:
        logger.error("Failed to remove MCP server from configuration: %s", exc)
        local_deleted = False

    return MCPServerDeleteResponse(deleted=local_deleted, name=name)
