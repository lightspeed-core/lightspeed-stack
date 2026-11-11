"""Factory for building MCP capabilities from MCP server settings."""

from typing import Final, Optional

from pydantic_ai.capabilities import MCP

from agent.types.settings import MCPSettings
from configuration import configuration

_AUTHORIZATION_HEADER: Final[str] = "authorization"


def _process_headers(
    headers: Optional[dict[str, str]],
) -> tuple[Optional[str], Optional[dict[str, str]]]:
    """Separate the Authorization header from the other MCP headers.

    Parameters:
        headers: HTTP headers configured for the MCP server.

    Returns:
        The Authorization header value and the remaining headers. The value is
        ``None`` when no Authorization header is present. Remaining headers are
        ``None`` when none are left.

    """
    if not headers:
        return None, None

    authorization_token: Optional[str] = None
    remaining_headers: dict[str, str] = {}

    for name, value in headers.items():
        if name.lower() == _AUTHORIZATION_HEADER.lower():
            authorization_token = value
        else:
            remaining_headers[name] = value

    return authorization_token, remaining_headers or None


class MCPFactory:
    """Factory for building MCP capabilities."""

    @staticmethod
    def build_capability(setting: MCPSettings) -> Optional[MCP]:
        """Build an MCP capability from MCP server settings.

        The Authorization header in ``settings.headers`` is passed as the
        capability authorization token so native and local MCP requests send it.

        Parameters:
            settings: MCP server settings, including the server URL and headers.

        Returns:
            An MCP capability configured for the server.

        """
        if not setting.enabled:
            return None

        mcp = next(
            (mcp for mcp in configuration.mcp_servers if mcp.name == setting.id),
            None,
        )

        if mcp is None:
            return None

        if isinstance(setting.enabled, list):
            allowed_tools = setting.enabled
        else:
            allowed_tools = None

        authorization_token, headers = _process_headers(setting.headers)

        return MCP(
            url=mcp.url,
            authorization_token=authorization_token,
            headers=headers,
            allowed_tools=allowed_tools,
        )

    @staticmethod
    def build_capabilities(settings: Optional[list[MCPSettings]]) -> list[MCP]:
        """Build MCP capabilities from MCP server settings.

        Parameters:
            settings: MCP server settings to turn into capabilities.

        Returns:
            One MCP capability per server, in the same order.

        """
        if not settings:
            return []

        return [
            capability
            for setting in settings
            if (capability := MCPFactory.build_capability(setting)) is not None
        ]
