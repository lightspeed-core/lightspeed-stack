"""MCP server settings for an agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Request

import constants
from configuration import configuration
from log import get_logger
from models.api.requests import QueryRequest

logger = get_logger(__name__)


def _get_mcp_headers_from_request(request: Request) -> dict[str, dict[str, str]]:
    request_mcp_headers: dict[str, dict[str, str]] = {}
    try:
        parsed_headers = json.loads(request.headers.get("MCP-HEADERS", ""))
    except json.JSONDecodeError as error:
        logger.error("MCP headers decode error: %s", error)
    else:
        if isinstance(parsed_headers, dict):
            for server_name, server_headers in parsed_headers.items():
                if isinstance(server_name, str) and isinstance(server_headers, dict):
                    request_mcp_headers[server_name] = {
                        header_name: header_value
                        for header_name, header_value in server_headers.items()
                        if isinstance(header_name, str)
                        and isinstance(header_value, str)
                    }
        else:
            logger.error(
                "MCP headers wrong type supplied (mcp headers must be a "
                "dictionary), but type %s was supplied",
                type(parsed_headers),
            )
    return request_mcp_headers


@dataclass
class MCPSettings:
    """Settings for an MCP server."""

    id: str
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool | list[str] = True

    @classmethod
    def from_query_request(
        cls, request: Request, query_request: QueryRequest, token: str
    ) -> list[MCPSettings]:
        """Build MCP settings for every configured MCP server.

        Parameters:
            request: Incoming HTTP request. Supplies client MCP headers and
                allowlisted headers to propagate.
            query_request: Incoming query. ``no_tools`` disables every server.
            token: Authenticated user token. Used for ``kubernetes``
                authorization headers.

        Returns:
            One MCP setting per configured server, including that server's
            resolved headers. ``enabled`` is false when the query disables
            tools.

        """
        request_mcp_headers = _get_mcp_headers_from_request(request)

        settings: list[MCPSettings] = []
        for server in configuration.mcp_servers:
            headers: dict[str, str] = {}
            enabled = not query_request.no_tools

            for name, value in server.authorization_headers:
                match value:
                    case constants.MCP_AUTH_KUBERNETES if token:
                        headers[name] = f"Bearer {token}"
                    case constants.MCP_AUTH_CLIENT | constants.MCP_AUTH_OAUTH:
                        try:
                            headers[name] = request_mcp_headers[server.name][name]
                        except KeyError:
                            enabled = enabled and value is not constants.MCP_AUTH_CLIENT
                    case _:
                        try:
                            headers[name] = (
                                Path(value)
                                .expanduser()
                                .read_text(encoding="utf-8")
                                .strip()
                            )
                        except (OSError, UnicodeDecodeError) as error:
                            logger.warning(
                                "Secret file for server %s header %s could not be read: %s",
                                server.name,
                                name,
                                error,
                            )
                            enabled = False

            for propagated_header in server.headers:
                if not headers.get(propagated_header) and (
                    value := request.headers.get(propagated_header)
                ):
                    headers[propagated_header] = value

            settings.append(
                MCPSettings(id=server.name, headers=headers, enabled=enabled)
            )

        return settings
