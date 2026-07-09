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
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import ToolsResponse
from models.config import Action, ModelContextProtocolServer
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


def _normalize_and_enrich_tool_dict(
    tool_dict: dict[str, Any],
    mcp_server: ModelContextProtocolServer,
) -> dict[str, Any]:
    """Normalize and enrich a single tool definition from llama-stack /v1/tools endpoint.

    Normalizes field names from llama-stack format and enriches the tool
    dictionary with metadata from the MCP server configuration.

    Field transformations:
    - ``name`` -> ``identifier``
    - ``input_schema`` -> ``parameters`` (converted to OpenAPI format)

    Metadata additions:
    - ``provider_id``: From mcp_server.provider_id if not present in tool
    - ``type``: Set to "tool" if not present in tool
    - ``server_source``: MCP server URL or name as fallback

    Args:
        tool_dict: Raw tool dictionary from /v1/tools response.
        mcp_server: MCP server configuration containing provider_id and URL.

    Returns:
        Normalized and enriched tool dictionary.

    Example:
        >>> tool = {
        ...     "name": "search_web",
        ...     "description": "Search the web",
        ...     "input_schema": {"type": "object", "properties": {"query": {...}}}
        ... }
        >>> server = ModelContextProtocolServer(
        ...     name="brave-search",
        ...     provider_id="model-context-protocol",
        ...     url="http://localhost:8401/sse"
        ... )
        >>> result = _normalize_and_enrich_tool_dict(tool, server)
        >>> result["identifier"]
        'search_web'
        >>> result["server_source"]
        'http://localhost:8401/sse'
        >>> result["provider_id"]
        'model-context-protocol'
    """
    # Normalize field names
    if "name" in tool_dict and not tool_dict.get("identifier"):
        tool_dict["identifier"] = tool_dict["name"]
    tool_dict.pop("name", None)

    if "input_schema" in tool_dict and not tool_dict.get("parameters"):
        tool_dict["parameters"] = _input_schema_to_parameters(tool_dict["input_schema"])
    tool_dict.pop("input_schema", None)

    # Add metadata from MCP server configuration
    if not tool_dict.get("provider_id"):
        tool_dict["provider_id"] = mcp_server.provider_id

    if not tool_dict.get("type"):
        tool_dict["type"] = "tool"

    tool_dict["server_source"] = mcp_server.url or mcp_server.name

    return tool_dict


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

    # Check MCP Auth
    await check_mcp_auth(configuration, mcp_headers, token, request.headers)

    client = AsyncLlamaStackClientHolder().get_client()
    consolidated_tools = []

    # Query tools for each configured MCP server
    for mcp_server in configuration.mcp_servers or []:
        headers = complete_mcp_headers.get(mcp_server.name, {})
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

            # Use /v1/tools endpoint with toolgroup_id filter
            # Note: client.toolgroups and client.tools were removed in v0.7.0
            params = {"toolgroup_id": mcp_server.name}
            if authorization:
                params["authorization"] = authorization

            tools_data = await client.get(
                "/v1/tools",
                cast_to=dict,  # type: ignore[arg-type]
                options={"params": params, "headers": headers},
            )
            tools_response = tools_data.get("tools", [])  # type: ignore[union-attr]
        except BadRequestError:
            logger.error("Toolgroup %s is not found", mcp_server.name)
            continue
        except APIConnectionError as e:
            logger.error("Unable to connect to Llama Stack: %s", e)
            response = ServiceUnavailableResponse(
                backend_name="Llama Stack", cause=str(e)
            )
            raise HTTPException(**response.model_dump()) from e

        # Process and normalize tools from this MCP server
        for tool in tools_response:
            tool_dict = dict(tool) if not isinstance(tool, dict) else tool
            normalized_tool = _normalize_and_enrich_tool_dict(tool_dict, mcp_server)
            consolidated_tools.append(normalized_tool)

        logger.debug(
            "Retrieved %d tools from MCP server %s (source: %s)",
            len(tools_response),
            mcp_server.name,
            mcp_server.url or mcp_server.name,
        )

    logger.info(
        "Retrieved total of %d tools from %d configured MCP servers",
        len(consolidated_tools),
        len(configuration.mcp_servers or []),
    )

    # Format tools with structured description parsing
    formatted_tools = format_tools_list(consolidated_tools)

    return ToolsResponse(tools=formatted_tools)
