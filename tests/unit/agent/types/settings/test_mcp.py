"""Unit tests for MCP settings built from a query and request."""

import json
import logging
from pathlib import Path
from typing import cast

import pytest
from fastapi import Request
from pytest_mock import MockerFixture

import constants
from agent.types.settings.mcp import MCPSettings
from models.api.requests import QueryRequest
from models.config import ModelContextProtocolServer


def _uninterned(value: str) -> str:
    """Return a new string equal to ``value``.

    Config values loaded from YAML are not the interned constant objects.
    """
    return "".join(value)


def _server(
    name: str,
    *,
    authorization_headers: dict[str, str] | None = None,
    headers: list[str] | None = None,
) -> ModelContextProtocolServer:
    """Build an MCP server configuration for settings tests."""
    return ModelContextProtocolServer(
        name=name,
        url=f"https://mcp.example/{name}",
        authorization_headers=authorization_headers or {},
        headers=headers or [],
    )


def _build(
    mocker: MockerFixture,
    servers: list[ModelContextProtocolServer],
    *,
    token: str | None = "user-token",
    headers: dict[str, str] | None = None,
    no_tools: bool | None = False,
) -> list[MCPSettings]:
    """Build MCP settings for ``servers`` from a synthetic request."""
    mocker.patch(
        "agent.types.settings.mcp.configuration",
        mocker.Mock(mcp_servers=servers),
    )
    request = mocker.Mock(spec=Request)
    request.headers = {} if headers is None else headers
    return MCPSettings.from_query_request(
        cast(Request, request),
        QueryRequest(query="What is Kubernetes?", no_tools=no_tools),
        token,
    )


def test_no_configured_servers_produce_no_settings(mocker: MockerFixture) -> None:
    """An empty MCP server list yields no settings."""
    assert _build(mocker, []) == []


def test_server_without_headers_stays_enabled(mocker: MockerFixture) -> None:
    """A server with no auth configuration is enabled with empty headers."""
    settings = _build(mocker, [_server("docs")], headers={"MCP-HEADERS": "{}"})

    assert settings == [MCPSettings(id="docs", headers={}, enabled=True)]


def test_no_tools_disables_servers_after_headers_are_resolved(
    mocker: MockerFixture,
) -> None:
    """``no_tools`` disables every server without dropping resolved headers."""
    settings = _build(
        mocker,
        [
            _server(
                "docs",
                authorization_headers={"Authorization": constants.MCP_AUTH_KUBERNETES},
            )
        ],
        token="cluster-token",
        headers={"MCP-HEADERS": "{}"},
        no_tools=True,
    )

    assert settings == [
        MCPSettings(
            id="docs",
            headers={"Authorization": "Bearer cluster-token"},
            enabled=False,
        )
    ]


def test_omitted_no_tools_leaves_the_server_enabled(mocker: MockerFixture) -> None:
    """``no_tools`` of ``None`` does not disable MCP servers."""
    settings = _build(mocker, [_server("docs")], no_tools=None)

    assert settings[0].enabled is True


class TestMCPAuthorizationHeaders:
    """Authorization header keywords and secret files."""

    def test_kubernetes_token_is_sent_as_a_bearer_header(
        self, mocker: MockerFixture
    ) -> None:
        """A kubernetes authorization header uses the authenticated token."""
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={
                        "Authorization": constants.MCP_AUTH_KUBERNETES
                    },
                )
            ],
            token="cluster-token",
            headers={"MCP-HEADERS": "{}"},
        )

        assert settings[0].enabled is True
        assert settings[0].headers == {"Authorization": "Bearer cluster-token"}

    def test_client_header_is_copied_from_the_request(
        self, mocker: MockerFixture
    ) -> None:
        """A client authorization header is taken from MCP-HEADERS."""
        keyword = _uninterned(constants.MCP_AUTH_CLIENT)
        assert keyword is not constants.MCP_AUTH_CLIENT
        settings = _build(
            mocker,
            [_server("docs", authorization_headers={"Authorization": keyword})],
            headers={
                "MCP-HEADERS": json.dumps({"docs": {"Authorization": "client-token"}})
            },
        )

        assert settings[0].enabled is True
        assert settings[0].headers == {"Authorization": "client-token"}

    def test_missing_client_header_disables_the_server(
        self, mocker: MockerFixture
    ) -> None:
        """A missing client header disables that server."""
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={
                        "Authorization": _uninterned(constants.MCP_AUTH_CLIENT)
                    },
                )
            ],
            headers={"MCP-HEADERS": "{}"},
        )

        assert settings[0].enabled is False
        assert settings[0].headers == {}

    def test_missing_oauth_header_leaves_the_server_enabled(
        self, mocker: MockerFixture
    ) -> None:
        """A missing oauth header does not disable the server."""
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={
                        "Authorization": _uninterned(constants.MCP_AUTH_OAUTH)
                    },
                )
            ],
            headers={"MCP-HEADERS": "{}"},
        )

        assert settings[0].enabled is True
        assert settings[0].headers == {}

    def test_oauth_header_is_copied_when_the_client_supplied_it(
        self, mocker: MockerFixture
    ) -> None:
        """An oauth authorization header is taken from MCP-HEADERS."""
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={"Authorization": constants.MCP_AUTH_OAUTH},
                )
            ],
            headers={
                "MCP-HEADERS": json.dumps({"docs": {"Authorization": "oauth-token"}})
            },
        )

        assert settings[0].enabled is True
        assert settings[0].headers == {"Authorization": "oauth-token"}

    def test_headers_are_resolved_per_server(self, mocker: MockerFixture) -> None:
        """Each server receives only the MCP-HEADERS entry keyed by its name."""
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT},
                ),
                _server(
                    "search",
                    authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT},
                ),
            ],
            headers={
                "MCP-HEADERS": json.dumps(
                    {
                        "docs": {"Authorization": "docs-token"},
                        "search": {"Authorization": "search-token"},
                    }
                )
            },
        )

        assert [setting.id for setting in settings] == ["docs", "search"]
        assert settings[0].headers == {"Authorization": "docs-token"}
        assert settings[1].headers == {"Authorization": "search-token"}
        assert all(setting.enabled for setting in settings)

    def test_secret_file_is_stripped(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """A secret file is read, stripped, and sent as the header value."""
        secret = tmp_path / "token.txt"
        secret.write_text("  secret-value\n", encoding="utf-8")
        settings = _build(
            mocker,
            [_server("docs", authorization_headers={"X-Token": str(secret)})],
            headers={"MCP-HEADERS": "{}"},
        )

        assert settings[0].enabled is True
        assert settings[0].headers == {"X-Token": "secret-value"}

    def test_unreadable_secret_disables_the_server(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A secret that cannot be read disables the server."""
        readable = tmp_path / "ok.txt"
        readable.write_text("kept", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            settings = _build(
                mocker,
                [
                    _server(
                        "docs",
                        authorization_headers={
                            "X-Ok": str(readable),
                            "X-Missing": str(tmp_path / "missing"),
                        },
                    )
                ],
                headers={"MCP-HEADERS": "{}"},
            )

        assert settings[0].enabled is False
        assert settings[0].headers["X-Ok"] == "kept"
        assert "X-Missing" not in settings[0].headers
        assert "could not be read" in caplog.text

    def test_undecodable_secret_disables_the_server(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A secret that is not UTF-8 disables the server."""
        secret = tmp_path / "bad.bin"
        secret.write_bytes(b"\xff\xfe")
        with caplog.at_level(logging.WARNING):
            settings = _build(
                mocker,
                [_server("docs", authorization_headers={"X-Token": str(secret)})],
                headers={"MCP-HEADERS": "{}"},
            )

        assert settings[0].enabled is False
        assert settings[0].headers == {}
        assert "could not be read" in caplog.text


class TestMCPRequestHeaders:
    """MCP-HEADERS parsing and propagated request headers."""

    def test_invalid_mcp_headers_are_ignored(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Invalid JSON leaves client-supplied MCP headers empty."""
        with caplog.at_level(logging.ERROR):
            settings = _build(
                mocker,
                [
                    _server(
                        "docs",
                        authorization_headers={
                            "Authorization": constants.MCP_AUTH_CLIENT
                        },
                    )
                ],
                headers={"MCP-HEADERS": "{"},
            )

        assert settings[0].enabled is False
        assert settings[0].headers == {}
        assert "MCP headers decode error" in caplog.text

    def test_non_object_mcp_headers_are_ignored(
        self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A JSON value that is not an object is ignored."""
        with caplog.at_level(logging.ERROR):
            settings = _build(
                mocker,
                [_server("docs")],
                headers={"MCP-HEADERS": json.dumps(["not", "an", "object"])},
            )

        assert settings[0].headers == {}
        assert "wrong type" in caplog.text

    def test_non_string_header_entries_are_dropped(self, mocker: MockerFixture) -> None:
        """Only string header names and values are copied from MCP-HEADERS."""
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT},
                )
            ],
            headers={
                "MCP-HEADERS": json.dumps(
                    {
                        "docs": {"Authorization": 5, "X-Ok": "yes"},
                        "other": ["not-a-header-map"],
                    }
                )
            },
        )

        assert settings[0].enabled is False
        assert settings[0].headers == {}

    def test_propagated_request_headers_are_added(self, mocker: MockerFixture) -> None:
        """Allowlisted request headers are forwarded when not already set."""
        settings = _build(
            mocker,
            [_server("docs", headers=["X-Rh-Identity", "X-Missing"])],
            headers={"MCP-HEADERS": "{}", "X-Rh-Identity": "identity-value"},
        )

        assert settings[0].headers == {"X-Rh-Identity": "identity-value"}

    def test_propagated_header_does_not_replace_a_resolved_header(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """A resolved authorization header wins over the propagated request header."""
        secret = tmp_path / "token.txt"
        secret.write_text("from-file", encoding="utf-8")
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={"X-Token": str(secret)},
                    headers=["X-Token"],
                )
            ],
            headers={"MCP-HEADERS": "{}", "X-Token": "from-request"},
        )

        assert settings[0].headers == {"X-Token": "from-file"}

    def test_propagated_header_fills_a_blank_resolved_header(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """A blank secret does not block the allowlisted request header."""
        secret = tmp_path / "blank.txt"
        secret.write_text("  \n", encoding="utf-8")
        settings = _build(
            mocker,
            [
                _server(
                    "docs",
                    authorization_headers={"X-Token": str(secret)},
                    headers=["X-Token"],
                )
            ],
            headers={"MCP-HEADERS": "{}", "X-Token": "from-request"},
        )

        assert settings[0].headers == {"X-Token": "from-request"}

    def test_empty_propagated_header_is_not_forwarded(
        self, mocker: MockerFixture
    ) -> None:
        """An empty allowlisted request header is not sent to the server."""
        settings = _build(
            mocker,
            [_server("docs", headers=["X-Rh-Identity"])],
            headers={"MCP-HEADERS": "{}", "X-Rh-Identity": ""},
        )

        assert settings[0].headers == {}
