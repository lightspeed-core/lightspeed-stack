"""Handler for REST API calls to dynamically manage MCP servers."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from llama_stack_api.common.errors import ToolGroupNotFoundError
from llama_stack_client import APIConnectionError, APIStatusError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.config import Action, ModelContextProtocolServer
from models.requests import MCPServerRegistrationRequest
from models.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    ConflictResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    MCPServerDeleteResponse,
    MCPServerInfo,
    MCPServerListResponse,
    MCPServerRegistrationResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
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
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
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

    Adds the MCP server to the runtime configuration and registers it
    as a toolgroup with Llama Stack so it becomes available for queries.

    ### Parameters:
    - request: Model containing attributes to dynamically registering an MCP server.
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - body: Headers that should be passed to MCP servers.

    ### Raises:
    - HTTPException: On duplicate name, Llama Stack connection error, or
      registration failure.

    ### Returns:
    - MCPServerRegistrationResponse: Details of the newly registered server.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    mcp_server = ModelContextProtocolServer(
        name=body.name,
        url=body.url,
        provider_id=body.provider_id,
        authorization_headers=body.authorization_headers or {},
        headers=body.headers or [],
        timeout=body.timeout,
    )

    try:
        configuration.add_mcp_server(mcp_server)
    except ValueError as e:
        response = ConflictResponse(resource="MCP server", resource_id=body.name)
        raise HTTPException(**response.model_dump()) from e

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        await client.toolgroups.register(  # pyright: ignore[reportDeprecated]
            toolgroup_id=mcp_server.name,
            provider_id=mcp_server.provider_id,
            mcp_endpoint={"uri": mcp_server.url},
        )
    except APIConnectionError as e:
        configuration.remove_mcp_server(body.name)
        logger.error("Failed to register MCP server with Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e
    except Exception as e:  # pylint: disable=broad-exception-caught
        configuration.remove_mcp_server(body.name)
        logger.error("Failed to register MCP toolgroup: %s", e)
        error_response = InternalServerErrorResponse.mcp_server_registration_failed()
        raise HTTPException(**error_response.model_dump()) from e

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
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
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

    servers = []
    for mcp in configuration.mcp_servers:
        source = "api" if configuration.is_dynamic_mcp_server(mcp.name) else "config"
        servers.append(
            MCPServerInfo(
                name=mcp.name,
                url=mcp.url,
                provider_id=mcp.provider_id,
                source=source,
            )
        )

    return MCPServerListResponse(servers=servers)


delete_responses: dict[int | str, dict[str, Any]] = {
    200: MCPServerDeleteResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint", "mcp server static"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}


@router.delete("/mcp-servers/{name}", responses=delete_responses)
@authorize(Action.DELETE_MCP_SERVER)
async def delete_mcp_server_handler(
    request: Request,
    name: str,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> MCPServerDeleteResponse:
    """Unregister a dynamically registered MCP server.

    Removes the MCP server from the runtime configuration and unregisters
    its toolgroup from Llama Stack. Only servers registered via the API
    can be deleted; statically configured servers cannot be removed.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Authentication tuple from the auth dependency (used by middleware).
    - name: MCP server name

    ### Raises:
    - HTTPException: If the server is not found, is statically configured, or
      Llama Stack unregistration fails.

    ### Returns:
    - MCPServerDeleteResponse: Confirmation of the deletion.
    """
    _ = auth
    _ = request

    check_configuration_loaded(configuration)

    if not configuration.is_dynamic_mcp_server(name):
        static_mcp_names = {s.name for s in configuration.mcp_servers}
        if name in static_mcp_names:
            response = ForbiddenResponse.mcp_server_static_config(name)
            raise HTTPException(**response.model_dump())

    try:
        configuration.remove_mcp_server(name)
        local_deleted = True
    except ValueError as e:
        logger.error("Failed to remove MCP server from configuration: %s", e)
        local_deleted = False

    try:
        client = AsyncLlamaStackClientHolder().get_client()
        await client.toolgroups.unregister(  # pyright: ignore[reportDeprecated]
            toolgroup_id=name
        )
    except APIConnectionError as e:
        logger.error("Failed to connect to Llama Stack: %s", e)
        svc_response = ServiceUnavailableResponse(
            backend_name="Llama Stack", cause=str(e)
        )
        raise HTTPException(**svc_response.model_dump()) from e
    except (APIStatusError, ToolGroupNotFoundError):
        logger.warning("MCP server not found, treating as already deleted.")

    return MCPServerDeleteResponse(deleted=local_deleted, name=name)
