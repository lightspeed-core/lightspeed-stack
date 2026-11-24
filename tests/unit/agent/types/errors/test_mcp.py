"""Unit tests for MCP probe errors."""

from agent.types.errors.mcp import (
    MCPAuthError,
    MCPConnectionError,
    MCPError,
    MCPHealthError,
)


def test_mcp_error_records_the_failed_probe() -> None:
    """The base error keeps the capability id, URL, and failure message."""
    error = MCPError("docs-sse", "https://mcp.example/sse", "down")

    assert isinstance(error, Exception)
    assert error.capability_id == "docs-sse"
    assert error.url == "https://mcp.example/sse"
    assert error.message == "down"
    assert (
        str(error)
        == "MCP server 'docs-sse' at https://mcp.example/sse failed health check: down"
    )


def test_mcp_error_accepts_missing_capability_identity() -> None:
    """A probe that has no id or URL still produces a message."""
    error = MCPError(None, None, "down")

    assert error.capability_id is None
    assert error.url is None
    assert str(error) == "MCP server None at None failed health check: down"


def test_auth_error_records_the_www_authenticate_challenge() -> None:
    """Authentication failures keep the server's challenge header."""
    error = MCPAuthError(
        "docs-sse",
        "https://mcp.example/sse",
        "HTTP 401",
        www_authenticate='Bearer realm="mcp"',
    )

    assert isinstance(error, MCPError)
    assert error.www_authenticate == 'Bearer realm="mcp"'
    assert error.message == "HTTP 401"


def test_auth_error_challenge_defaults_to_none() -> None:
    """Credential failures without an HTTP challenge leave the header unset."""
    error = MCPAuthError("docs-sse", "https://mcp.example/sse", "denied")

    assert error.www_authenticate is None


def test_connection_and_health_errors_are_mcp_errors() -> None:
    """Connection and health failures share the base probe error."""
    connection = MCPConnectionError("docs-sse", "https://mcp.example/sse", "refused")
    health = MCPHealthError("docs-sse", "https://mcp.example/sse", "no server info")

    assert isinstance(connection, MCPError)
    assert isinstance(health, MCPError)
    assert not isinstance(connection, MCPAuthError)
    assert connection.message == "refused"
    assert health.message == "no server info"
