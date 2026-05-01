"""Handler for REST API call to list available tools from MCP servers."""

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_client import APIConnectionError, BadRequestError

from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from log import get_logger
from models.api.responses import (
    UNAUTHORIZED_OPENAPI_EXAMPLES,
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.config import Action
from models.responses import (
    ToolsResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.mcp_headers import (
    McpHeaders,
    build_mcp_headers,
    find_unresolved_auth_headers,
    mcp_headers_dependency,
)
from utils.mcp_oauth_probe import check_mcp_auth
from utils.tool_formatter import format_tools_list

logger = get_logger(__name__)
router = APIRouter(tags=["tools"])


def _input_schema_to_parameters(
    schema: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert a JSON Schema input_schema to a flat list of parameter dicts.

    The Llama Stack SDK returns tool parameters as a JSON Schema object
    (``input_schema``).  This function converts that representation into
    the flat parameter list format used by the tools endpoint response.

    Parameters:
    ----------
        schema: JSON Schema dict with ``properties`` and ``required`` keys,
                or ``None`` if the tool has no parameters.

    Returns:
    -------
        A list of parameter dicts, each containing ``name``, ``description``,
        ``parameter_type``, ``required``, and ``default`` keys.
    """
    if not schema or "properties" not in schema:
        return []

    required_params = set(schema.get("required", []))
    return [
        {
            "name": name,
            "description": prop.get("description", ""),
            "parameter_type": prop.get("type", "string"),
            "required": name in required_params,
            "default": prop.get("default"),
        }
        for name, prop in schema["properties"].items()
    ]


def _normalize_tool_dict(tool_dict: dict[str, Any], toolgroup: Any) -> None:
    """Normalize a ToolDef dict to the endpoint's response format.

    Remaps field names (``name`` -> ``identifier``, ``input_schema`` ->
    ``parameters``) and propagates ``provider_id``/``type`` from the
    parent toolgroup.  Handles both missing keys and empty legacy
    placeholders.
    """
    if "name" in tool_dict and not tool_dict.get("identifier"):
        tool_dict["identifier"] = tool_dict["name"]
    tool_dict.pop("name", None)

    if "input_schema" in tool_dict and not tool_dict.get("parameters"):
        tool_dict["parameters"] = _input_schema_to_parameters(tool_dict["input_schema"])
    tool_dict.pop("input_schema", None)

    if not tool_dict.get("provider_id"):
        tool_dict["provider_id"] = toolgroup.provider_id
    if not tool_dict.get("type"):
        tool_dict["type"] = getattr(toolgroup, "type", None) or "tool"


tools_responses: dict[int | str, dict[str, Any]] = {
    200: ToolsResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(
        examples=["llama stack", "kubernetes api"]
    ),
}


@router.get("/tools", responses=tools_responses)
@authorize(Action.GET_TOOLS)
async def tools_endpoint_handler(  # pylint: disable=too-many-locals,too-many-statements
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
    - HTTPException: If unable to connect to the Llama Stack server or if tool
      retrieval fails for any reason.

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

    # Check MCP Auth
    await check_mcp_auth(configuration, mcp_headers, token, request.headers)

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
        mcp_server = None
        if toolgroup.identifier in mcp_server_names:
            mcp_server = next(
                (
                    s
                    for s in configuration.mcp_servers
                    if s.name == toolgroup.identifier
                ),
                None,
            )

        headers = complete_mcp_headers.get(toolgroup.identifier, {})
        if mcp_server is not None:
            unresolved = find_unresolved_auth_headers(
                mcp_server.authorization_headers, headers
            )
            if unresolved:
                logger.warning(
                    "Skipping MCP server %s: required %d auth headers "
                    "but only resolved %d",
                    mcp_server.name,
                    len(mcp_server.authorization_headers),
                    len(mcp_server.authorization_headers) - len(unresolved),
                )
                continue

        try:
            authorization = headers.pop("Authorization", None)

            tools_response = await client.tools.list(
                toolgroup_id=toolgroup.identifier,
                extra_headers=headers,
                extra_query={"authorization": authorization},
            )
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

            _normalize_tool_dict(tool_dict, toolgroup)

            # Determine server source based on toolgroup type
            if mcp_server:
                tool_dict["server_source"] = mcp_server.url or toolgroup.identifier
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
