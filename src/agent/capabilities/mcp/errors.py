"""Errors raised while probing MCP servers."""


class MCPError(Exception):
    """An MCP server failed its health check."""

    def __init__(
        self, capability_id: str | None, url: str | None, message: str
    ) -> None:
        """Record which capability failed and why.

        Parameters:
            capability_id: Capability id derived from the server URL.
            url: MCP server URL that was probed.
            message: Why the probe failed.

        """
        super().__init__(
            f"MCP server {capability_id!r} at {url} failed health check: {message}"
        )
        self.capability_id = capability_id
        self.url = url
        self.message = message


class MCPAuthError(MCPError):
    """The MCP server rejected the credentials used to open a session."""

    def __init__(
        self,
        capability_id: str | None,
        url: str | None,
        message: str,
        www_authenticate: str | None = None,
    ) -> None:
        """Record the authentication challenge from the server.

        Parameters:
            capability_id: Capability id derived from the server URL.
            url: MCP server URL that was probed.
            message: Why the probe failed.
            www_authenticate: ``WWW-Authenticate`` header value, when the
                server sent one.

        """
        super().__init__(capability_id, url, message)
        self.www_authenticate = www_authenticate


class MCPConnectionError(MCPError):
    """The MCP server could not be reached."""


class MCPHealthError(MCPError):
    """The MCP server did not pass the session health check."""
