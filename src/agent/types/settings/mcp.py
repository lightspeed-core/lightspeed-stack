"""MCP server settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from configuration import configuration
from models.api.requests import QueryRequest


@dataclass
class MCPSettings:
    """Settings for an MCP server."""

    id: str
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool | list[str] = True

    @classmethod
    def from_query_request(cls, request: QueryRequest) -> list[MCPSettings]:
        """Build MCP settings for every configured MCP server.

        Parameters:
            request: Incoming query. ``no_tools`` disables every server.

        Returns:
            One MCP setting per configured server, including that server's
            resolved authorization headers. ``enabled`` is false when the
            query disables tools.

        """
        return [
            cls(
                id=server.name,
                headers=dict(server.resolved_authorization_headers),
                enabled=not request.no_tools,
            )
            for server in configuration.mcp_servers
        ]
