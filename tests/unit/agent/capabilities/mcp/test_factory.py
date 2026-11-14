"""Unit tests for MCP capability construction and health checks."""

import httpx
import pytest
from fastmcp.exceptions import AuthorizationError
from mcp.client.auth.exceptions import OAuthFlowError
from mcp.types import Implementation
from pydantic_ai.capabilities import MCP
from pydantic_ai.mcp import MCPToolset
from pytest_mock import MockerFixture

from agent.capabilities.mcp.errors import (
    MCPAuthError,
    MCPConnectionError,
    MCPHealthError,
)
from agent.capabilities.mcp.factory import MCPFactory, _validate_mcp_capability
from agent.types.settings import MCPSettings
from models.config import ModelContextProtocolServer


def _server(
    name: str = "filesystem-tools",
    url: str = "http://mcp.example/mcp",
) -> ModelContextProtocolServer:
    """Build an MCP server configuration."""
    return ModelContextProtocolServer(name=name, url=url)


def _patch_servers(
    mocker: MockerFixture, servers: list[ModelContextProtocolServer]
) -> None:
    """Replace configured MCP servers for the duration of a test."""
    mock_configuration = mocker.Mock()
    mock_configuration.mcp_servers = servers
    mocker.patch(
        "agent.capabilities.mcp.factory.configuration",
        mock_configuration,
    )


def _http_status(
    status_code: int, www_authenticate: str | None = None
) -> httpx.HTTPStatusError:
    """Build an HTTP status error for a failed MCP request."""
    request = httpx.Request("POST", "http://mcp.example/mcp")
    headers = {}
    if www_authenticate is not None:
        headers["WWW-Authenticate"] = www_authenticate
    response = httpx.Response(status_code, headers=headers, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=request, response=response
    )


def _server_info_property(present: bool) -> property:
    """Build a ``server_info`` property for a stubbed MCP session."""

    def _present(_self: MCPToolset) -> Implementation:
        return Implementation(name="filesystem-tools", version="1.0.0")

    def _missing(_self: MCPToolset) -> Implementation:
        raise AttributeError("server info")

    return property(_present if present else _missing)


def _patch_session(
    mocker: MockerFixture,
    side_effect: BaseException | None = None,
    *,
    server_info: bool = True,
) -> None:
    """Stub the MCP session so the health check does not open a connection."""
    mocker.patch(
        "pydantic_ai.mcp.MCPToolset.__aexit__",
        new=mocker.AsyncMock(return_value=None),
    )

    if side_effect is not None:
        mocker.patch(
            "pydantic_ai.mcp.MCPToolset.__aenter__",
            new=mocker.AsyncMock(side_effect=side_effect),
        )
        return

    async def _enter(self: MCPToolset) -> MCPToolset:
        return self

    mocker.patch("pydantic_ai.mcp.MCPToolset.__aenter__", _enter)
    mocker.patch.object(
        MCPToolset,
        "server_info",
        new=_server_info_property(server_info),
    )


@pytest.mark.asyncio
async def test_build_capability_returns_capability_when_session_opens(
    mocker: MockerFixture,
) -> None:
    """Return the capability after the server identifies itself."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker)

    capability = await MCPFactory.build_capability(
        MCPSettings(
            id="filesystem-tools",
            headers={"Authorization": "secret", "X-Trace": "1"},
            enabled=["read_file"],
        )
    )

    assert capability is not None
    assert capability.url == "http://mcp.example/mcp"
    assert capability.authorization_token == "secret"
    assert capability.headers == {"X-Trace": "1"}
    assert capability.allowed_tools == ["read_file"]


@pytest.mark.asyncio
async def test_build_capability_raises_connection_error(
    mocker: MockerFixture,
) -> None:
    """Raise MCPConnectionError when the server cannot be reached."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, side_effect=httpx.ConnectError("refused"))

    with pytest.raises(MCPConnectionError, match="refused") as exc_info:
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert exc_info.value.capability_id == "mcp.example-mcp"
    assert exc_info.value.url == "http://mcp.example/mcp"
    assert exc_info.value.message == "refused"
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_build_capability_raises_connection_error_from_exception_group(
    mocker: MockerFixture,
) -> None:
    """Classify a transport ExceptionGroup as a connection failure."""
    _patch_servers(mocker, [_server()])
    _patch_session(
        mocker,
        side_effect=ExceptionGroup("connect", [httpx.ConnectError("down")]),
    )

    with pytest.raises(MCPConnectionError, match="down"):
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))


@pytest.mark.asyncio
async def test_build_capability_raises_auth_error(mocker: MockerFixture) -> None:
    """Raise MCPAuthError when the server returns 401."""
    _patch_servers(mocker, [_server()])
    _patch_session(
        mocker,
        side_effect=_http_status(401, 'Bearer realm="mcp"'),
    )

    with pytest.raises(MCPAuthError, match="Bearer realm") as exc_info:
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert exc_info.value.message == 'HTTP 401: Bearer realm="mcp"'
    assert exc_info.value.www_authenticate == 'Bearer realm="mcp"'
    assert exc_info.value.capability_id == "mcp.example-mcp"


@pytest.mark.asyncio
async def test_build_capability_raises_auth_error_for_forbidden(
    mocker: MockerFixture,
) -> None:
    """Raise MCPAuthError when the server returns 403."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, side_effect=_http_status(403))

    with pytest.raises(MCPAuthError, match="HTTP 403") as exc_info:
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert exc_info.value.www_authenticate is None


@pytest.mark.asyncio
async def test_build_capability_raises_health_error_for_server_status(
    mocker: MockerFixture,
) -> None:
    """Raise MCPHealthError when the server responds with a non-auth status."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, side_effect=_http_status(500))

    with pytest.raises(MCPHealthError, match="HTTP 500"):
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))


@pytest.mark.asyncio
async def test_build_capability_raises_when_server_info_is_missing(
    mocker: MockerFixture,
) -> None:
    """Raise MCPHealthError when the session has no server info."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, server_info=False)

    with pytest.raises(MCPHealthError, match="Server info not available") as exc_info:
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert exc_info.value.message == "Server info not available"


@pytest.mark.asyncio
async def test_build_capability_skips_disabled_server(mocker: MockerFixture) -> None:
    """Skip the health check when the server is disabled."""
    enter = mocker.patch(
        "pydantic_ai.mcp.MCPToolset.__aenter__", new=mocker.AsyncMock()
    )

    capability = await MCPFactory.build_capability(
        MCPSettings(id="filesystem-tools", enabled=False)
    )

    assert capability is None
    enter.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_capability_skips_unknown_server(mocker: MockerFixture) -> None:
    """Skip the health check when the server is not configured."""
    _patch_servers(mocker, [])
    enter = mocker.patch(
        "pydantic_ai.mcp.MCPToolset.__aenter__", new=mocker.AsyncMock()
    )

    capability = await MCPFactory.build_capability(MCPSettings(id="missing"))

    assert capability is None
    enter.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_capabilities_keeps_healthy_servers_in_order(
    mocker: MockerFixture,
) -> None:
    """Health-check enabled servers and preserve their order."""
    _patch_servers(
        mocker,
        [
            _server("one", "http://one.example/mcp"),
            _server("two", "http://two.example/mcp"),
        ],
    )
    _patch_session(mocker)

    capabilities = await MCPFactory.build_capabilities(
        [
            MCPSettings(id="one"),
            MCPSettings(id="skipped", enabled=False),
            MCPSettings(id="missing"),
            MCPSettings(id="two"),
        ]
    )

    assert [capability.url for capability in capabilities] == [
        "http://one.example/mcp",
        "http://two.example/mcp",
    ]


@pytest.mark.asyncio
async def test_build_capabilities_empty_settings() -> None:
    """Return no capabilities when no MCP settings are supplied."""
    assert await MCPFactory.build_capabilities(None) == []
    assert await MCPFactory.build_capabilities([]) == []


@pytest.mark.asyncio
async def test_build_capability_without_headers_leaves_token_unset(
    mocker: MockerFixture,
) -> None:
    """Leave the authorization token unset when no headers are configured."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker)

    capability = await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert capability is not None
    assert capability.authorization_token is None
    assert capability.headers is None
    assert capability.allowed_tools is None


@pytest.mark.asyncio
async def test_build_capability_raises_auth_error_for_authorization_failure(
    mocker: MockerFixture,
) -> None:
    """Raise MCPAuthError when the client reports an authorization failure."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, side_effect=AuthorizationError("denied"))

    with pytest.raises(MCPAuthError, match="denied") as exc_info:
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert exc_info.value.www_authenticate is None


@pytest.mark.asyncio
async def test_build_capability_raises_auth_error_for_oauth_flow(
    mocker: MockerFixture,
) -> None:
    """Raise MCPAuthError when the OAuth flow fails."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, side_effect=OAuthFlowError("oauth failed"))

    with pytest.raises(MCPAuthError, match="oauth failed"):
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))


@pytest.mark.asyncio
async def test_build_capability_raises_connection_error_for_os_error(
    mocker: MockerFixture,
) -> None:
    """Raise MCPConnectionError when the socket layer fails."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, side_effect=OSError("network unreachable"))

    with pytest.raises(MCPConnectionError, match="network unreachable"):
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))


@pytest.mark.asyncio
async def test_build_capability_prefers_auth_error_inside_exception_group(
    mocker: MockerFixture,
) -> None:
    """Classify a group as an auth failure when it also contains a transport error."""
    _patch_servers(mocker, [_server()])
    _patch_session(
        mocker,
        side_effect=ExceptionGroup(
            "probe",
            [
                ExceptionGroup("connect", [httpx.ConnectError("down")]),
                _http_status(401, 'Bearer realm="mcp"'),
            ],
        ),
    )

    with pytest.raises(MCPAuthError, match='HTTP 401: Bearer realm="mcp"') as exc_info:
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert exc_info.value.www_authenticate == 'Bearer realm="mcp"'


@pytest.mark.asyncio
async def test_build_capability_raises_health_error_for_unexpected_failure(
    mocker: MockerFixture,
) -> None:
    """Raise MCPHealthError when the session fails for another reason."""
    _patch_servers(mocker, [_server()])
    _patch_session(mocker, side_effect=RuntimeError("boom"))

    with pytest.raises(MCPHealthError, match="boom") as exc_info:
        await MCPFactory.build_capability(MCPSettings(id="filesystem-tools"))

    assert isinstance(exc_info.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_build_capabilities_raises_when_a_later_server_fails(
    mocker: MockerFixture,
) -> None:
    """Stop when a later server fails its health check."""
    _patch_servers(
        mocker,
        [
            _server("one", "http://one.example/mcp"),
            _server("two", "http://two.example/mcp"),
        ],
    )
    entered = 0

    async def _enter(self: MCPToolset) -> MCPToolset:
        nonlocal entered
        entered += 1
        if entered == 2:
            raise httpx.ConnectError("down")
        return self

    mocker.patch("pydantic_ai.mcp.MCPToolset.__aenter__", _enter)
    mocker.patch.object(
        MCPToolset,
        "server_info",
        new=_server_info_property(True),
    )
    mocker.patch(
        "pydantic_ai.mcp.MCPToolset.__aexit__",
        new=mocker.AsyncMock(return_value=None),
    )

    with pytest.raises(MCPConnectionError, match="down"):
        await MCPFactory.build_capabilities(
            [MCPSettings(id="one"), MCPSettings(id="two")]
        )


@pytest.mark.asyncio
async def test_validate_mcp_capability_requires_local_toolset() -> None:
    """Raise ValueError when the capability has no local MCP toolset."""
    capability = MCP(url="http://mcp.example/mcp", local=lambda: None)

    with pytest.raises(ValueError, match="no local toolset"):
        await _validate_mcp_capability(capability)
