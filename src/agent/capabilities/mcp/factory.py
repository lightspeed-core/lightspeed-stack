"""Factory for building MCP capabilities from MCP server settings."""

from typing import Final, Optional, cast

import httpx
from fastmcp.exceptions import AuthorizationError
from mcp.client.auth.exceptions import OAuthFlowError
from pydantic_ai.capabilities import MCP
from pydantic_ai.mcp import MCPToolset

from agent.types.errors.mcp import (
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


def _flatten_exceptions(exc: BaseException) -> list[BaseException]:
    """Flatten nested exception groups into a single list.

    Parameters:
        exc: Exception raised while opening an MCP session.

    Returns:
        The exception and any nested causes, with groups expanded in place.
        An authentication failure later in the list still wins over an
        earlier connection error.

    """
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
    return causes


def _is_auth_failure(cause: BaseException) -> bool:
    """Return whether one probe failure is an authentication error.

    Parameters:
        cause: One exception from the failed MCP session.

    Returns:
        ``True`` when the cause is an authorization error, an OAuth error,
        or an HTTP 401 or 403 response.

    """
    if isinstance(cause, (AuthorizationError, OAuthFlowError)):
        return True
    return isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code in (
        401,
        403,
    )


def _classify_mcp_failure(
    causes: list[BaseException], fallback: BaseException
) -> tuple[type[MCPError], BaseException]:
    """Choose the MCP error type that best matches the probe failure.

    Parameters:
        causes: Flattened exceptions from the failed session.
        fallback: Exception to use when ``causes`` is empty.

    Returns:
        The error class and the cause that determined it. Authentication
        wins over a connection error. Anything else is a health failure.

    """
    auth_cause: BaseException | None = None
    connection_cause: BaseException | None = None
    for cause in causes:
        if _is_auth_failure(cause):
            auth_cause = cause
            break
        if connection_cause is None and isinstance(
            cause, (httpx.RequestError, OSError)
        ):
            connection_cause = cause

    if auth_cause is not None:
        return MCPAuthError, auth_cause
    if connection_cause is not None:
        return MCPConnectionError, connection_cause
    return MCPHealthError, causes[0] if causes else fallback


def _failure_message(cause: BaseException) -> tuple[str, Optional[str]]:
    """Build the probe failure message and optional auth challenge.

    Parameters:
        cause: Exception selected as the reason the probe failed.

    Returns:
        A short failure message and the ``WWW-Authenticate`` header value
        when the cause is an HTTP error that sent one.

    """
    if not isinstance(cause, httpx.HTTPStatusError):
        return str(cause), None

    www_authenticate = cause.response.headers.get("WWW-Authenticate")
    message = f"HTTP {cause.response.status_code}"
    if www_authenticate:
        message = f"{message}: {www_authenticate}"
    return message, www_authenticate


def _mcp_probe_error(capability: MCP, exc: BaseException) -> MCPError:
    """Build the MCP error that matches a failed session probe.

    Parameters:
        capability: MCP capability that was probed.
        exc: Exception raised while opening the session. Nested groups are
            flattened. An authentication failure wins when a group contains
            both an auth failure and a connection failure.

    Returns:
        The auth, connection, or health error for this probe failure.

    """
    error_type, cause = _classify_mcp_failure(_flatten_exceptions(exc), exc)
    message, www_authenticate = _failure_message(cause)
    logger.warning(
        "MCP probe failed for %s at %s: %s",
        capability.id,
        capability.url,
        message,
    )
    if error_type is MCPAuthError:
        return MCPAuthError(
            capability.id,
            capability.url,
            message,
            www_authenticate=www_authenticate,
        )
    return error_type(capability.id, capability.url, message)


def _require_server_info(capability: MCP, toolset: MCPToolset) -> None:
    """Require the open MCP session to report server info.

    Parameters:
        capability: MCP capability being probed.
        toolset: Open local toolset for that capability.

    Raises:
        MCPHealthError: If the session opened without server info.

    """
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
            _require_server_info(capability, toolset)
    except MCPError:
        raise
    except (Exception, ExceptionGroup) as exc:
        # Any failure to open the session is a failed health check.
        raise _mcp_probe_error(capability, exc) from exc


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
            id=mcp.name,
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
