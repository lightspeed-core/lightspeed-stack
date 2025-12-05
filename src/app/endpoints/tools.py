"""Handler for REST API call to list available tools from MCP servers."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_client import APIConnectionError, BadRequestError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    ToolsResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.tool_formatter import format_tools_list

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tools"])


tools_responses: dict[int | str, dict[str, Any]] = {
    200: ToolsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


@router.get("/tools", responses=tools_responses)
@authorize(Action.GET_TOOLS)
async def tools_endpoint_handler(  # pylint: disable=too-many-locals
    request: Request,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> ToolsResponse:
    """
    Handle requests to the /tools endpoint.

    Process GET requests to the /tools endpoint, returning a consolidated list of
    available tools from all configured MCP servers.

    Raises:
        HTTPException: If unable to connect to the Llama Stack server or if
        tool retrieval fails for any reason.

    Returns:
        ToolsResponse: An object containing the consolidated list of available tools
        with metadata including tool name, description, parameters, and server source.
    """
    # Used only by the middleware
    _ = auth

    # Nothing interesting in the request
    _ = request

    check_configuration_loaded(configuration)

    toolgroups_response = []
    try:
        client = AsyncLlamaStackClientHolder().get_client()
        logger.debug("Retrieving tools from all toolgroups")
        toolgroups_response = await client.toolgroups.list()
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e

    consolidated_tools = []
    mcp_server_names = (
        {mcp_server.name for mcp_server in configuration.mcp_servers}
        if configuration.mcp_servers
        else set()
    )

    for toolgroup in toolgroups_response:
        try:
            # Get tools for each toolgroup
            tools_response = await client.tools.list(toolgroup_id=toolgroup.identifier)
        except BadRequestError:
            logger.error("Toolgroup %s is not found", toolgroup.identifier)
            continue
        except APIConnectionError as e:
            logger.error("Unable to connect to Llama Stack: %s", e)
            response = ServiceUnavailableResponse(
                backend_name="Llama Stack", cause=str(e)
            )
            raise HTTPException(**response.model_dump()) from e

        # Convert tools to dict format
        tools_count = 0
        server_source = "unknown"

        for tool in tools_response:
            tool_dict = dict(tool)

            # Determine server source based on toolgroup type
            if toolgroup.identifier in mcp_server_names:
                # This is an MCP server toolgroup
                mcp_server = next(
                    (
                        s
                        for s in configuration.mcp_servers
                        if s.name == toolgroup.identifier
                    ),
                    None,
                )
                tool_dict["server_source"] = (
                    mcp_server.url if mcp_server else toolgroup.identifier
                )
            else:
                # This is a built-in toolgroup
                tool_dict["server_source"] = "builtin"

            consolidated_tools.append(tool_dict)
            tools_count += 1
            server_source = tool_dict["server_source"]

        logger.debug(
            "Retrieved %d tools from toolgroup %s (source: %s)",
            tools_count,
            toolgroup.identifier,
            server_source,
        )

    logger.info(
        "Retrieved total of %d tools (%d from built-in toolgroups, %d from MCP servers)",
        len(consolidated_tools),
        len([t for t in consolidated_tools if t.get("server_source") == "builtin"]),
        len([t for t in consolidated_tools if t.get("server_source") != "builtin"]),
    )

    # Format tools with structured description parsing
    formatted_tools = format_tools_list(consolidated_tools)

    return ToolsResponse(tools=formatted_tools)
