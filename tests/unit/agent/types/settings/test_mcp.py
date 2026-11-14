"""Unit tests for MCP settings built from a query request."""

import json
from pathlib import Path

from fastapi import Request
from pytest_mock import MockerFixture

import constants
from agent.types.settings.mcp import MCPSettings
from models.api.requests import QueryRequest
from models.config import ModelContextProtocolServer


def _request(headers: dict[str, str] | None = None) -> Request:
    """Build a request whose headers are a case-insensitive mapping."""
    raw = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request({"type": "http", "headers": raw})


def _server(
    authorization_headers: dict[str, str] | None = None,
    headers: list[str] | None = None,
    name: str = "filesystem-tools",
) -> ModelContextProtocolServer:
    """Build an MCP server with the given header configuration."""
    return ModelContextProtocolServer(
        name=name,
        url="http://mcp.example",
        authorization_headers=authorization_headers or {},
        headers=headers or [],
    )


def _settings(
    mocker: MockerFixture,
    servers: list[ModelContextProtocolServer],
    headers: dict[str, str] | None = None,
    *,
    no_tools: bool = False,
    token: str = "",
) -> list[MCPSettings]:
    """Build MCP settings from the given servers and request."""
    mock_configuration = mocker.Mock()
    mock_configuration.mcp_servers = servers
    mocker.patch("agent.types.settings.mcp.configuration", mock_configuration)
    return MCPSettings.from_query_request(
        _request(headers),
        QueryRequest(query="hello", no_tools=no_tools),
        token,
    )


def test_from_query_request_empty_configuration(mocker: MockerFixture) -> None:
    """Return no settings when no MCP servers are configured."""
    assert not _settings(mocker, [])


def test_from_query_request_server_without_headers(mocker: MockerFixture) -> None:
    """Leave headers empty and the server enabled when nothing is configured."""
    settings = _settings(mocker, [_server()])

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=True)]


def test_from_query_request_reads_secret_file(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Read an authorization header configured as a file path."""
    secret = tmp_path / "token"
    secret.write_text("  my-secret\n")

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": str(secret)})],
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"Authorization": "my-secret"},
            enabled=True,
        )
    ]


def test_from_query_request_missing_secret_disables_server(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Disable the server when a secret file cannot be read."""
    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": str(tmp_path / "missing")})],
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=False)]


def test_from_query_request_undecodable_secret_disables_server(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Disable the server when a secret file is not valid text."""
    secret = tmp_path / "token"
    secret.write_bytes(b"\xff")

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": str(secret)})],
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=False)]


def test_from_query_request_kubernetes_uses_user_token(
    mocker: MockerFixture,
) -> None:
    """Turn kubernetes auth into a bearer token from the user token."""
    settings = _settings(
        mocker,
        [
            _server(
                authorization_headers={"Authorization": constants.MCP_AUTH_KUBERNETES}
            )
        ],
        token="k8s-token",
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"Authorization": "Bearer k8s-token"},
            enabled=True,
        )
    ]


def test_from_query_request_kubernetes_without_token_is_omitted(
    mocker: MockerFixture,
) -> None:
    """Omit a kubernetes header when the user token is empty."""
    settings = _settings(
        mocker,
        [
            _server(
                authorization_headers={"Authorization": constants.MCP_AUTH_KUBERNETES}
            )
        ],
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=True)]


def test_from_query_request_client_header_is_taken_from_request(
    mocker: MockerFixture,
) -> None:
    """Use the MCP-HEADERS value for a header configured as client."""
    mcp_headers = json.dumps({"filesystem-tools": {"Authorization": "from-client"}})

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT})],
        {"MCP-HEADERS": mcp_headers},
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"Authorization": "from-client"},
            enabled=True,
        )
    ]


def test_from_query_request_missing_client_header_disables_server(
    mocker: MockerFixture,
) -> None:
    """Disable the server when a client header was not supplied."""
    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT})],
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=False)]


def test_from_query_request_oauth_header_is_taken_from_request(
    mocker: MockerFixture,
) -> None:
    """Use the MCP-HEADERS value for a header configured as oauth."""
    mcp_headers = json.dumps({"filesystem-tools": {"Authorization": "from-oauth"}})

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": constants.MCP_AUTH_OAUTH})],
        {"MCP-HEADERS": mcp_headers},
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"Authorization": "from-oauth"},
            enabled=True,
        )
    ]


def test_from_query_request_missing_oauth_header_stays_enabled(
    mocker: MockerFixture,
) -> None:
    """Leave the server enabled when an oauth header was not supplied."""
    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": constants.MCP_AUTH_OAUTH})],
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=True)]


def test_from_query_request_drops_non_string_client_headers(
    mocker: MockerFixture,
) -> None:
    """Ignore MCP-HEADERS entries that are not strings and disable client auth."""
    mcp_headers = json.dumps(
        {"filesystem-tools": {"Authorization": 1, "X-Extra": "kept"}}
    )

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT})],
        {"MCP-HEADERS": mcp_headers},
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=False)]


def test_from_query_request_ignores_other_servers(mocker: MockerFixture) -> None:
    """Ignore MCP-HEADERS entries for other servers."""
    mcp_headers = json.dumps({"other-server": {"Authorization": "from-client"}})

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT})],
        {"MCP-HEADERS": mcp_headers},
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=False)]


def test_from_query_request_ignores_non_dict_server_headers(
    mocker: MockerFixture,
) -> None:
    """Ignore an MCP-HEADERS server entry that is not an object."""
    mcp_headers = json.dumps({"filesystem-tools": "from-client"})

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": constants.MCP_AUTH_CLIENT})],
        {"MCP-HEADERS": mcp_headers},
    )

    assert settings == [MCPSettings(id="filesystem-tools", headers={}, enabled=False)]


def test_from_query_request_invalid_json_is_ignored(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Keep reading other header sources when MCP-HEADERS is not valid JSON."""
    secret = tmp_path / "token"
    secret.write_text("from-file")

    settings = _settings(
        mocker,
        [_server(authorization_headers={"X-Api-Key": str(secret)})],
        {"MCP-HEADERS": "not-json"},
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"X-Api-Key": "from-file"},
            enabled=True,
        )
    ]


def test_from_query_request_wrong_json_type_is_ignored(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Keep reading other header sources when MCP-HEADERS is not an object."""
    secret = tmp_path / "token"
    secret.write_text("from-file")

    settings = _settings(
        mocker,
        [_server(authorization_headers={"X-Api-Key": str(secret)})],
        {"MCP-HEADERS": json.dumps(["not", "a", "dict"])},
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"X-Api-Key": "from-file"},
            enabled=True,
        )
    ]


def test_from_query_request_file_secret_is_not_replaced_by_client_header(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Read a file secret even when MCP-HEADERS names the same header."""
    secret = tmp_path / "token"
    secret.write_text("from-file")
    mcp_headers = json.dumps({"filesystem-tools": {"Authorization": "from-client"}})

    settings = _settings(
        mocker,
        [_server(authorization_headers={"Authorization": str(secret)})],
        {"MCP-HEADERS": mcp_headers},
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"Authorization": "from-file"},
            enabled=True,
        )
    ]


def test_from_query_request_propagates_allowlisted_headers(
    mocker: MockerFixture,
) -> None:
    """Copy allowlisted request headers without overwriting resolved headers."""
    settings = _settings(
        mocker,
        [_server(headers=["x-rh-identity", "x-request-id", "authorization"])],
        {
            "X-Rh-Identity": "from-request",
            "X-Request-Id": "req-1",
            "Authorization": "from-request",
        },
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={
                "x-rh-identity": "from-request",
                "x-request-id": "req-1",
                "authorization": "from-request",
            },
            enabled=True,
        )
    ]


def test_from_query_request_propagated_header_does_not_overwrite(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Keep a resolved header when the same name is also allowlisted."""
    secret = tmp_path / "token"
    secret.write_text("from-file")

    settings = _settings(
        mocker,
        [
            _server(
                authorization_headers={"Authorization": str(secret)},
                headers=["Authorization"],
            )
        ],
        {"Authorization": "from-request"},
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"Authorization": "from-file"},
            enabled=True,
        )
    ]


def test_from_query_request_merges_every_source(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Combine kubernetes, file, client, and propagated headers."""
    secret = tmp_path / "api-key"
    secret.write_text("static-key")
    mcp_headers = json.dumps({"filesystem-tools": {"X-Client": "client-value"}})

    settings = _settings(
        mocker,
        [
            _server(
                authorization_headers={
                    "Authorization": constants.MCP_AUTH_KUBERNETES,
                    "X-Api-Key": str(secret),
                    "X-Client": constants.MCP_AUTH_CLIENT,
                },
                headers=["x-request-id"],
            )
        ],
        {"MCP-HEADERS": mcp_headers, "X-Request-Id": "req-123"},
        token="k8s-token",
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={
                "Authorization": "Bearer k8s-token",
                "X-Api-Key": "static-key",
                "X-Client": "client-value",
                "x-request-id": "req-123",
            },
            enabled=True,
        )
    ]


def test_from_query_request_no_tools_disables_servers(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """Disable every server when the query turns tools off, and still resolve headers."""
    secret = tmp_path / "token"
    secret.write_text("secret")

    settings = _settings(
        mocker,
        [
            _server(
                name="filesystem-tools",
                authorization_headers={"X-Api-Key": str(secret)},
            ),
            _server(name="other-tools"),
        ],
        no_tools=True,
    )

    assert settings == [
        MCPSettings(
            id="filesystem-tools",
            headers={"X-Api-Key": "secret"},
            enabled=False,
        ),
        MCPSettings(id="other-tools", headers={}, enabled=False),
    ]
