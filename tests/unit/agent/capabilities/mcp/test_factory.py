"""Unit tests for MCP capability construction and session probes."""

# pylint: disable=protected-access

from types import SimpleNamespace
from typing import cast

import httpx
import pytest
from fastmcp.exceptions import AuthorizationError
from mcp.client.auth.exceptions import OAuthFlowError
from pydantic_ai.capabilities import MCP
from pytest_mock import MockerFixture

from agent.capabilities.mcp.factory import (
    MCPFactory,
    _classify_mcp_failure,
    _flatten_exceptions,
    _process_headers,
    _validate_mcp_capability,
)
from agent.types.errors.mcp import (
    MCPAuthError,
    MCPConnectionError,
    MCPHealthError,
)
from agent.types.settings import MCPSettings
from models.config import ModelContextProtocolServer


class _ProbeToolset:
    """Async context manager standing in for an MCP toolset."""

    def __init__(
        self,
        *,
        error: BaseException | None = None,
        server_info: object = "docs",
        missing_info: bool = False,
    ) -> None:
        """Store the probe result the validation code will observe."""
        self._error = error
        self._server_info = server_info
        self._missing_info = missing_info

    async def __aenter__(self) -> "_ProbeToolset":
        """Enter the fake session, or raise the configured probe error."""
        if self._error is not None:
            raise self._error
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> None:
        """Leave the fake session."""

    @property
    def server_info(self) -> object:
        """Return the configured server info, or fail as an uninitialized session."""
        if self._missing_info:
            raise AttributeError("server_info")
        return self._server_info


def _capability(local: object, *, capability_id: str = "mcp.example-sse") -> MCP:
    """Build a capability-shaped object for the probe."""
    return cast(
        MCP,
        SimpleNamespace(
            id=capability_id,
            url="https://mcp.example/sse",
            local=local,
        ),
    )


def _http_error(
    status_code: int, www_authenticate: str | None = None
) -> httpx.HTTPStatusError:
    """Build an HTTP status error from a failed MCP request."""
    request = httpx.Request("GET", "https://mcp.example/sse")
    headers = {} if www_authenticate is None else {"WWW-Authenticate": www_authenticate}
    response = httpx.Response(status_code, headers=headers, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=request, response=response
    )


def _server(name: str, url: str | None = None) -> ModelContextProtocolServer:
    """Build an MCP server configuration entry."""
    return ModelContextProtocolServer(
        name=name,
        url=url or f"https://mcp.example/{name}",
    )


def _install_servers(
    mocker: MockerFixture, *servers: ModelContextProtocolServer
) -> list[dict[str, object]]:
    """Patch configuration and record the MCP capability constructor arguments."""
    mocker.patch(
        "agent.capabilities.mcp.factory.configuration",
        SimpleNamespace(mcp_servers=list(servers)),
    )
    mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
    captured: list[dict[str, object]] = []

    def fake_mcp(**kwargs: object) -> SimpleNamespace:
        captured.append(kwargs)
        return SimpleNamespace(
            id=kwargs["id"],
            url=kwargs["url"],
            local=_ProbeToolset(server_info="docs"),
        )

    mocker.patch("agent.capabilities.mcp.factory.MCP", side_effect=fake_mcp)
    return captured


class TestProcessHeaders:
    """Separation of the Authorization header from the remaining MCP headers."""

    def test_missing_headers_stay_empty(self) -> None:
        """No headers produce no token and no remaining header map."""
        assert _process_headers(None) == (None, None)
        assert _process_headers({}) == (None, None)

    def test_authorization_header_is_case_insensitive(self) -> None:
        """The authorization token is removed from the remaining headers."""
        token, remaining = _process_headers(
            {
                "Authorization": "first",
                "X-Trace": "trace",
                "authorization": "second",
            }
        )

        assert token == "second"
        assert remaining == {"X-Trace": "trace"}

    def test_headers_without_authorization_are_preserved(self) -> None:
        """A header map with no authorization entry is returned unchanged."""
        token, remaining = _process_headers({"X-Trace": "trace"})

        assert token is None
        assert remaining == {"X-Trace": "trace"}


class TestFlattenExceptions:
    """Nested exception groups raised while opening an MCP session."""

    def test_plain_exception_is_unchanged(self) -> None:
        """An exception that is not a group is the only cause."""
        error = ValueError("plain")

        assert _flatten_exceptions(error) == [error]

    def test_nested_groups_expand_depth_first(self) -> None:
        """Groups are replaced by their children, with nested groups expanded first."""
        first = ValueError("first")
        second = TypeError("second")
        third = OSError("third")
        nested = ExceptionGroup("nested", [first, second])
        outer = ExceptionGroup("outer", [nested, third])

        assert _flatten_exceptions(outer) == [first, second, third]


class TestValidateMcpCapability:
    """Classification of a failed or successful MCP session probe."""

    @pytest.mark.asyncio
    async def test_requires_a_local_toolset(self, mocker: MockerFixture) -> None:
        """A capability without a local toolset cannot be probed."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)

        with pytest.raises(ValueError, match="no local toolset"):
            await _validate_mcp_capability(_capability(object()))

    @pytest.mark.asyncio
    async def test_accepts_a_session_that_reports_server_info(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A session that reports server info passes the probe."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)

        with caplog.at_level(
            "DEBUG", logger="lightspeed_stack.agent.capabilities.mcp.factory"
        ):
            await _validate_mcp_capability(
                _capability(_ProbeToolset(server_info="docs"))
            )

        assert "reported" in caplog.text

    @pytest.mark.asyncio
    async def test_missing_server_info_is_a_health_error(
        self, mocker: MockerFixture
    ) -> None:
        """A session that opened without server info fails the health check."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)

        with pytest.raises(MCPHealthError) as raised:
            await _validate_mcp_capability(
                _capability(_ProbeToolset(missing_info=True))
            )

        assert raised.value.message == "Server info not available"
        assert raised.value.capability_id == "mcp.example-sse"
        assert raised.value.url == "https://mcp.example/sse"
        assert raised.value.__cause__ is None

    @pytest.mark.asyncio
    async def test_mcp_error_is_reraised(self, mocker: MockerFixture) -> None:
        """An MCP error raised by the probe is not wrapped again."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        health = MCPHealthError("mcp.example-sse", "https://mcp.example/sse", "bad")

        with pytest.raises(MCPHealthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=health)))

        assert raised.value is health

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cause",
        [httpx.ConnectError("refused"), OSError("broken pipe")],
    )
    async def test_transport_failures_are_connection_errors(
        self, mocker: MockerFixture, cause: BaseException
    ) -> None:
        """Network and OS failures become connection errors."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)

        with pytest.raises(MCPConnectionError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=cause)))

        assert raised.value.message == str(cause)
        assert raised.value.__cause__ is cause
        assert not isinstance(raised.value, MCPAuthError)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cause",
        [AuthorizationError("denied"), OAuthFlowError("oauth failed")],
    )
    async def test_credential_failures_are_auth_errors(
        self, mocker: MockerFixture, cause: BaseException
    ) -> None:
        """Authorization and OAuth failures become auth errors without a challenge."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)

        with pytest.raises(MCPAuthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=cause)))

        assert raised.value.message == str(cause)
        assert raised.value.www_authenticate is None
        assert raised.value.__cause__ is cause

    @pytest.mark.asyncio
    async def test_http_401_includes_the_authenticate_challenge(
        self, mocker: MockerFixture
    ) -> None:
        """An HTTP 401 keeps the WWW-Authenticate challenge on the auth error."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        challenge = 'Bearer realm="mcp"'
        cause = _http_error(401, challenge)

        with pytest.raises(MCPAuthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=cause)))

        assert raised.value.message == f"HTTP 401: {challenge}"
        assert raised.value.www_authenticate == challenge
        assert raised.value.__cause__ is cause

    @pytest.mark.asyncio
    async def test_http_403_is_an_auth_error(self, mocker: MockerFixture) -> None:
        """An HTTP 403 is an authentication failure even without a challenge."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        cause = _http_error(403)

        with pytest.raises(MCPAuthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=cause)))

        assert raised.value.message == "HTTP 403"
        assert raised.value.www_authenticate is None

    @pytest.mark.asyncio
    async def test_http_500_is_a_health_error(self, mocker: MockerFixture) -> None:
        """An HTTP status other than 401 or 403 is a health failure."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        cause = _http_error(500)

        with pytest.raises(MCPHealthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=cause)))

        assert type(raised.value) is MCPHealthError
        assert raised.value.message == "HTTP 500"
        assert raised.value.__cause__ is cause

    @pytest.mark.asyncio
    async def test_unclassified_error_is_a_health_error(
        self, mocker: MockerFixture
    ) -> None:
        """A probe failure that is not auth or connectivity is a health error."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        cause = RuntimeError("unexpected")

        with pytest.raises(MCPHealthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=cause)))

        assert type(raised.value) is MCPHealthError
        assert raised.value.message == "unexpected"
        assert raised.value.__cause__ is cause

    @pytest.mark.asyncio
    async def test_auth_failure_wins_over_an_earlier_connection_error(
        self, mocker: MockerFixture
    ) -> None:
        """An authentication failure in a group wins over a connection error."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        auth = AuthorizationError("denied")
        group = ExceptionGroup("probe", [httpx.ConnectError("refused"), auth])

        with pytest.raises(MCPAuthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=group)))

        assert raised.value.message == str(auth)
        assert raised.value.__cause__ is group

    @pytest.mark.asyncio
    async def test_nested_group_still_prefers_auth(self, mocker: MockerFixture) -> None:
        """Authentication nested inside a group still wins over a sibling connection error."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        auth = OAuthFlowError("oauth failed")
        group = ExceptionGroup(
            "outer",
            [httpx.ConnectError("refused"), ExceptionGroup("inner", [auth])],
        )

        with pytest.raises(MCPAuthError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=group)))

        assert raised.value.message == str(auth)
        assert raised.value.__cause__ is group

    @pytest.mark.asyncio
    async def test_group_of_connection_errors_is_a_connection_error(
        self, mocker: MockerFixture
    ) -> None:
        """The first connection error in a group classifies the probe."""
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        first = httpx.ConnectError("refused")
        group = ExceptionGroup("probe", [first, OSError("reset")])

        with pytest.raises(MCPConnectionError) as raised:
            await _validate_mcp_capability(_capability(_ProbeToolset(error=group)))

        assert raised.value.message == str(first)
        assert raised.value.__cause__ is group

    def test_empty_cause_list_uses_the_fallback(self) -> None:
        """When a failure has no flattened cause, the original exception is used."""
        fallback = RuntimeError("fallback")

        error_type, cause = _classify_mcp_failure([], fallback)

        assert error_type is MCPHealthError
        assert cause is fallback


class TestMCPFactory:
    """Building MCP capabilities from per-request settings."""

    @pytest.mark.asyncio
    async def test_disabled_server_is_skipped(self, mocker: MockerFixture) -> None:
        """A disabled setting does not construct a capability."""
        captured = _install_servers(mocker, _server("docs"))

        assert (
            await MCPFactory.build_capability(MCPSettings(id="docs", enabled=False))
            is None
        )
        assert captured == []

    @pytest.mark.asyncio
    async def test_empty_tool_allowlist_skips_the_server(
        self, mocker: MockerFixture
    ) -> None:
        """An empty tool list is treated as disabled."""
        captured = _install_servers(mocker, _server("docs"))

        assert (
            await MCPFactory.build_capability(MCPSettings(id="docs", enabled=[]))
            is None
        )
        assert captured == []

    @pytest.mark.asyncio
    async def test_unknown_server_is_skipped(self, mocker: MockerFixture) -> None:
        """A setting whose id is not configured produces no capability."""
        captured = _install_servers(mocker, _server("other"))

        assert await MCPFactory.build_capability(MCPSettings(id="docs")) is None
        assert captured == []

    @pytest.mark.asyncio
    async def test_builds_a_probed_capability(self, mocker: MockerFixture) -> None:
        """An enabled server is built from its URL and probed before it is returned."""
        captured = _install_servers(mocker, _server("docs", "https://mcp.example/sse"))
        setting = MCPSettings(
            id="docs",
            enabled=["search", "read"],
            headers={"Authorization": "Bearer secret", "X-Trace": "trace"},
        )

        capability = await MCPFactory.build_capability(setting)

        assert capability is not None
        assert capability.id == "docs"
        assert captured == [
            {
                "id": "docs",
                "url": "https://mcp.example/sse",
                "authorization_token": "Bearer secret",
                "headers": {"X-Trace": "trace"},
                "allowed_tools": ["search", "read"],
            }
        ]

    @pytest.mark.asyncio
    async def test_probe_failure_propagates(self, mocker: MockerFixture) -> None:
        """A failed health check is raised to the caller."""
        mocker.patch(
            "agent.capabilities.mcp.factory.configuration",
            SimpleNamespace(mcp_servers=[_server("docs")]),
        )
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        cause = httpx.ConnectError("refused")

        def fake_mcp(**kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                id=kwargs["id"],
                url=kwargs["url"],
                local=_ProbeToolset(error=cause),
            )

        mocker.patch("agent.capabilities.mcp.factory.MCP", side_effect=fake_mcp)

        with pytest.raises(MCPConnectionError) as raised:
            await MCPFactory.build_capability(MCPSettings(id="docs"))

        assert raised.value.capability_id == "docs"
        assert raised.value.__cause__ is cause

    @pytest.mark.asyncio
    async def test_build_capabilities_skips_disabled_and_unknown_servers(
        self, mocker: MockerFixture
    ) -> None:
        """Only enabled, configured servers are returned, in settings order."""
        captured = _install_servers(
            mocker,
            _server("one", "https://mcp.example/one"),
            _server("two", "https://mcp.example/two"),
        )

        capabilities = await MCPFactory.build_capabilities(
            [
                MCPSettings(id="one"),
                MCPSettings(id="missing"),
                MCPSettings(id="two", enabled=False),
                MCPSettings(id="two", headers={"X-Trace": "two"}),
            ]
        )

        assert [capability.id for capability in capabilities] == ["one", "two"]
        assert [item["id"] for item in captured] == ["one", "two"]
        assert [item["url"] for item in captured] == [
            "https://mcp.example/one",
            "https://mcp.example/two",
        ]
        assert captured[0]["authorization_token"] is None
        assert captured[0]["headers"] is None
        assert captured[0]["allowed_tools"] is None
        assert captured[1]["headers"] == {"X-Trace": "two"}

    @pytest.mark.asyncio
    async def test_build_capabilities_without_settings_returns_empty(
        self, mocker: MockerFixture
    ) -> None:
        """Missing or empty settings produce no capabilities."""
        captured = _install_servers(mocker, _server("docs"))

        assert await MCPFactory.build_capabilities(None) == []
        assert await MCPFactory.build_capabilities([]) == []
        assert captured == []

    @pytest.mark.asyncio
    async def test_build_capabilities_stops_on_the_first_probe_failure(
        self, mocker: MockerFixture
    ) -> None:
        """A failed probe aborts the remaining servers."""
        mocker.patch(
            "agent.capabilities.mcp.factory.configuration",
            SimpleNamespace(
                mcp_servers=[
                    _server("one", "https://mcp.example/one"),
                    _server("two", "https://mcp.example/two"),
                ]
            ),
        )
        mocker.patch("agent.capabilities.mcp.factory.MCPToolset", _ProbeToolset)
        calls: list[str] = []

        def fake_mcp(**kwargs: object) -> SimpleNamespace:
            url = str(kwargs["url"])
            calls.append(url)
            error = httpx.ConnectError("refused") if url.endswith("/one") else None
            return SimpleNamespace(
                id=kwargs["id"],
                url=url,
                local=_ProbeToolset(error=error),
            )

        mocker.patch("agent.capabilities.mcp.factory.MCP", side_effect=fake_mcp)

        with pytest.raises(MCPConnectionError) as raised:
            await MCPFactory.build_capabilities(
                [MCPSettings(id="one"), MCPSettings(id="two")]
            )

        assert raised.value.capability_id == "one"
        assert calls == ["https://mcp.example/one"]
