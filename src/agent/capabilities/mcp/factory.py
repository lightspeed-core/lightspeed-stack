"""Factory for building MCP capabilities from MCP server settings."""

from typing import Final, Optional, cast

import httpx
from fastmcp.exceptions import AuthorizationError
from mcp.client.auth.exceptions import OAuthFlowError
from pydantic_ai.capabilities import MCP
from pydantic_ai.mcp import MCPToolset

from agent.capabilities.mcp.errors import (
    MCPAuthError,
    MCPConnectionError,
    MCPError,
    MCPHealthError,
)
from agent.types.settings import MCPSettings
from configuration import configuration
from log import get_logger

logger = get_logger(__name__)

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


async def _validate_mcp_capability(capability: MCP) -> None:
    """Open an MCP session and require the server to identify itself.

    Parameters:
        capability: MCP capability whose local toolset is probed.

    Raises:
        ValueError: If the capability has no local ``MCPToolset``.
        MCPAuthError: If the server rejected the credentials.
        MCPConnectionError: If the server could not be reached.
        MCPHealthError: If the session opened without server info, or failed
            for another reason.

    """
    toolset = capability.local
    if not isinstance(toolset, MCPToolset):
        raise ValueError("MCP capability has no local toolset to probe")

    try:
        async with toolset:
            try:
                server_info = toolset.server_info
            except AttributeError:
                logger.warning(
                    "MCP probe failed for %s at %s: Server info not available",
                    capability.id,
                    capability.url,
                )
                raise MCPHealthError(
                    capability.id,
                    capability.url,
                    "Server info not available",
                ) from None
            logger.debug(
                "MCP server %s at %s reported %s",
                capability.id,
                capability.url,
                server_info,
            )
    except MCPError:
        raise
    except (Exception, ExceptionGroup) as exc:
        # Any failure to open the session is a failed health check. An
        # authentication failure wins when a group contains both.
        pending: list[BaseException] = [exc]
        causes: list[BaseException] = []
        while pending:
            current = pending.pop(0)
            if isinstance(current, BaseExceptionGroup):
                # isinstance does not bind BaseExceptionGroup's type parameter,
                # so exceptions is not known to be a sequence of BaseException.
                nested = cast(tuple[BaseException, ...], current.exceptions)
                pending = list(nested) + pending
            else:
                causes.append(current)

        auth_cause: BaseException | None = None
        connection_cause: BaseException | None = None
        for cause in causes:
            if isinstance(cause, (AuthorizationError, OAuthFlowError)) or (
                isinstance(cause, httpx.HTTPStatusError)
                and cause.response.status_code in (401, 403)
            ):
                auth_cause = cause
                break
            if connection_cause is None and isinstance(
                cause, (httpx.RequestError, OSError)
            ):
                connection_cause = cause

        if auth_cause is not None:
            cause = auth_cause
            error_type: type[MCPError] = MCPAuthError
        elif connection_cause is not None:
            cause = connection_cause
            error_type = MCPConnectionError
        else:
            cause = causes[0] if causes else exc
            error_type = MCPHealthError

        www_authenticate = (
            cause.response.headers.get("WWW-Authenticate")
            if isinstance(cause, httpx.HTTPStatusError)
            else None
        )
        if isinstance(cause, httpx.HTTPStatusError):
            message = f"HTTP {cause.response.status_code}"
            if www_authenticate:
                message = f"{message}: {www_authenticate}"
        else:
            message = str(cause)

        logger.warning(
            "MCP probe failed for %s at %s: %s",
            capability.id,
            capability.url,
            message,
        )
        if error_type is MCPAuthError:
            raise MCPAuthError(
                capability.id,
                capability.url,
                message,
                www_authenticate=www_authenticate,
            ) from exc
        raise error_type(capability.id, capability.url, message) from exc


class MCPFactory:
    """Factory for building MCP capabilities."""

    @staticmethod
    async def build_capability(setting: MCPSettings) -> Optional[MCP]:
        """Build an MCP capability from MCP server settings.

        The Authorization header in ``setting.headers`` is passed as the
        capability authorization token so native and local MCP requests send it.
        The server is probed before the capability is returned.

        Parameters:
            setting: MCP server settings, including the server id and headers.

        Returns:
            An MCP capability configured for the server, or ``None`` when the
            server is disabled or not configured.

        Raises:
            MCPAuthError: If the server rejected the credentials.
            MCPConnectionError: If the server could not be reached.
            MCPHealthError: If the server did not pass the health check.

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

        capability = MCP(
            url=mcp.url,
            authorization_token=authorization_token,
            headers=headers,
            allowed_tools=allowed_tools,
        )
        await _validate_mcp_capability(capability)
        return capability

    @staticmethod
    async def build_capabilities(settings: Optional[list[MCPSettings]]) -> list[MCP]:
        """Build MCP capabilities from MCP server settings.

        Each enabled, configured server is health-checked. Servers that are
        disabled or missing from configuration are skipped.

        Parameters:
            settings: MCP server settings to turn into capabilities.

        Returns:
            One MCP capability per healthy server, in the same order.

        Raises:
            MCPAuthError: If a server rejected the credentials.
            MCPConnectionError: If a server could not be reached.
            MCPHealthError: If a server did not pass the health check.

        """
        if not settings:
            return []

        capabilities: list[MCP] = []
        for setting in settings:
            capability = await MCPFactory.build_capability(setting)
            if capability is not None:
                capabilities.append(capability)
        return capabilities
