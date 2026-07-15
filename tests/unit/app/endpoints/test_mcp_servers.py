# pylint: disable=protected-access,redefined-outer-name

"""Unit tests for the MCP servers dynamic registration endpoint."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException, status
from pydantic import AnyHttpUrl, SecretStr
from pytest_mock import MockerFixture

from app.endpoints import mcp_servers
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import MCPServerRegistrationRequest
from models.api.responses.successful import (
    MCPServerDeleteResponse,
    MCPServerListResponse,
    MCPServerRegistrationResponse,
)
from models.config import (
    Configuration,
    CORSConfiguration,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    ServiceConfiguration,
    TLSConfiguration,
    UserDataCollection,
)

MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


@pytest.fixture
def mock_configuration() -> Configuration:
    """Create a mock configuration with one static MCP server."""
    return Configuration(
        name="test",
        service=ServiceConfiguration(
            tls_config=TLSConfiguration(
                tls_certificate_path=Path("tests/configuration/server.crt"),
                tls_key_path=Path("tests/configuration/server.key"),
                tls_key_password=Path("tests/configuration/password"),
            ),
            cors=CORSConfiguration(
                allow_origins=["*"],
                allow_credentials=False,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
            host="localhost",
            port=1234,
            base_url=".",
            auth_enabled=False,
            workers=1,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            url=AnyHttpUrl("http://localhost:8321"),
            api_key=SecretStr("xyzzy"),
            use_as_library_client=False,
            library_client_config_path=".",
            timeout=10,
        ),
        user_data_collection=UserDataCollection(
            transcripts_enabled=False,
            feedback_enabled=False,
            transcripts_storage=".",
            feedback_storage=".",
        ),
        mcp_servers=[
            ModelContextProtocolServer(
                name="static-mcp",
                provider_id="model-context-protocol",
                url="http://localhost:3000",
            ),
        ],
        customization=None,
    )


def _make_app_config(mocker: MockerFixture, config: Configuration) -> AppConfig:
    """Create an AppConfig with the given configuration and patch it."""
    app_config = AppConfig()
    app_config._configuration = config
    app_config._dynamic_mcp_server_names = set()
    mocker.patch("app.endpoints.mcp_servers.configuration", app_config)
    mocker.patch("app.endpoints.mcp_servers.authorize", lambda _: lambda func: func)
    return app_config


@pytest.mark.asyncio
async def test_register_mcp_server_success(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Register a dynamic MCP server in local configuration only."""
    app_config = _make_app_config(mocker, mock_configuration)

    body = MCPServerRegistrationRequest(
        name="new-mcp-server",
        url="http://localhost:4000",
        provider_id="model-context-protocol",
    )
    request = mocker.Mock()

    response = await mcp_servers.register_mcp_server_handler(
        request=request,
        body=body,
        auth=MOCK_AUTH,
    )

    assert isinstance(response, MCPServerRegistrationResponse)
    assert response.name == "new-mcp-server"
    assert response.url == "http://localhost:4000"
    assert response.provider_id == "model-context-protocol"
    assert "registered successfully" in response.message
    assert app_config.is_dynamic_mcp_server("new-mcp-server")
    assert any(server.name == "new-mcp-server" for server in app_config.mcp_servers)


@pytest.mark.asyncio
async def test_register_mcp_server_conflict(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Return 409 when the MCP server name already exists."""
    _make_app_config(mocker, mock_configuration)

    body = MCPServerRegistrationRequest(
        name="static-mcp",
        url="http://localhost:4000",
        provider_id="model-context-protocol",
    )
    request = mocker.Mock()

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.register_mcp_server_handler(
            request=request,
            body=body,
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_register_mcp_server_with_all_fields(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test registration with all optional fields provided."""
    _make_app_config(mocker, mock_configuration)

    body = MCPServerRegistrationRequest(
        name="full-mcp-server",
        url="https://mcp.example.com/api",
        provider_id="custom-provider",
        authorization_headers={"Authorization": "client"},
        headers=["x-rh-identity"],
        timeout=30,
    )

    result = await mcp_servers.register_mcp_server_handler(
        request=mocker.Mock(), body=body, auth=MOCK_AUTH
    )

    assert result.name == "full-mcp-server"
    assert result.provider_id == "custom-provider"


@pytest.mark.asyncio
async def test_list_mcp_servers(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """List MCP servers from local configuration."""
    app_config = _make_app_config(mocker, mock_configuration)
    app_config.add_mcp_server(
        ModelContextProtocolServer(
            name="dynamic-mcp",
            provider_id="model-context-protocol",
            url="http://localhost:4001",
        )
    )

    request = mocker.Mock()
    response = await mcp_servers.list_mcp_servers_handler(
        request=request,
        auth=MOCK_AUTH,
    )

    assert isinstance(response, MCPServerListResponse)
    sources = {server.name: server.source for server in response.servers}
    assert sources["static-mcp"] == "config"
    assert sources["dynamic-mcp"] == "api"


@pytest.mark.asyncio
async def test_list_mcp_servers_empty(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test listing servers returns static servers only."""
    _make_app_config(mocker, mock_configuration)

    result = await mcp_servers.list_mcp_servers_handler(
        request=mocker.Mock(), auth=MOCK_AUTH
    )

    assert isinstance(result, MCPServerListResponse)
    assert len(result.servers) == 1
    assert result.servers[0].name == "static-mcp"
    assert result.servers[0].source == "config"


@pytest.mark.asyncio
async def test_delete_mcp_server_static_forbidden(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Reject deletion of statically configured MCP servers."""
    _make_app_config(mocker, mock_configuration)
    request = mocker.Mock()

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.delete_mcp_server_handler(
            request=request,
            name="static-mcp",
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_delete_mcp_server_dynamic_success(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Delete a dynamic MCP server from local configuration only."""
    app_config = _make_app_config(mocker, mock_configuration)
    app_config.add_mcp_server(
        ModelContextProtocolServer(
            name="dynamic-mcp",
            provider_id="model-context-protocol",
            url="http://localhost:4001",
        )
    )

    request = mocker.Mock()
    response = await mcp_servers.delete_mcp_server_handler(
        request=request,
        name="dynamic-mcp",
        auth=MOCK_AUTH,
    )

    assert isinstance(response, MCPServerDeleteResponse)
    assert response.deleted is True
    assert response.name == "dynamic-mcp"
    assert response.response == "MCP server deleted successfully"
    assert not app_config.is_dynamic_mcp_server("dynamic-mcp")
    assert not any(server.name == "dynamic-mcp" for server in app_config.mcp_servers)


@pytest.mark.asyncio
async def test_delete_nonexistent_mcp_server(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Deleting an unknown name returns 200 with deleted=False (idempotent delete)."""
    _make_app_config(mocker, mock_configuration)

    result = await mcp_servers.delete_mcp_server_handler(
        request=mocker.Mock(), name="no-such-server", auth=MOCK_AUTH
    )

    assert isinstance(result, MCPServerDeleteResponse)
    assert result.name == "no-such-server"
    assert result.deleted is False
    assert result.response == "MCP server not found"


@pytest.mark.asyncio
async def test_list_mcp_servers_configuration_not_loaded(
    mocker: MockerFixture,
) -> None:
    """Test listing MCP servers returns 500 when configuration is not loaded."""
    mock_config = AppConfig()
    mock_config._configuration = None  # pylint: disable=protected-access
    mocker.patch("app.endpoints.mcp_servers.configuration", mock_config)
    mocker.patch("app.endpoints.mcp_servers.authorize", lambda _: lambda func: func)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.list_mcp_servers_handler(
            request=mocker.Mock(), auth=MOCK_AUTH
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    raw_detail = exc_info.value.detail
    assert isinstance(raw_detail, dict)
    detail: dict[str, Any] = raw_detail
    assert detail["response"] == "Configuration is not loaded"


@pytest.mark.asyncio
async def test_register_and_delete_roundtrip(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test full register -> list -> delete -> list cycle."""
    _make_app_config(mocker, mock_configuration)

    body = MCPServerRegistrationRequest(
        name="roundtrip-server",
        url="http://localhost:5555/mcp",
        provider_id="MCP provider ID",
    )
    await mcp_servers.register_mcp_server_handler(
        request=mocker.Mock(), body=body, auth=MOCK_AUTH
    )

    list_result = await mcp_servers.list_mcp_servers_handler(
        request=mocker.Mock(), auth=MOCK_AUTH
    )
    assert len(list_result.servers) == 2

    await mcp_servers.delete_mcp_server_handler(
        request=mocker.Mock(), name="roundtrip-server", auth=MOCK_AUTH
    )

    list_result = await mcp_servers.list_mcp_servers_handler(
        request=mocker.Mock(), auth=MOCK_AUTH
    )
    assert len(list_result.servers) == 1
    assert list_result.servers[0].name == "static-mcp"


def test_mcp_server_registration_request_validation() -> None:
    """Test request model validation."""
    with pytest.raises(Exception):
        MCPServerRegistrationRequest(
            name="test",
            url="ftp://invalid-scheme",
            provider_id="MCP provider ID",
        )

    with pytest.raises(Exception):
        MCPServerRegistrationRequest(
            name="",
            url="http://valid.url",
            provider_id="MCP provider ID",
        )

    req = MCPServerRegistrationRequest(
        name="valid-server",
        url="http://localhost:8080/mcp",
    )  # pyright: ignore[reportCallIssue]
    assert req.provider_id == "model-context-protocol"


def test_mcp_server_registration_auth_keywords() -> None:
    """Test that all three supported auth keywords are accepted."""
    for keyword in ("client", "kubernetes", "oauth"):
        req = MCPServerRegistrationRequest(
            name=f"server-{keyword}",
            url="http://localhost:8080/mcp",
            authorization_headers={"Authorization": keyword},
            provider_id="MCP provider ID",
        )
        assert req.authorization_headers is not None
        assert req.authorization_headers["Authorization"] == keyword


def test_mcp_server_registration_rejects_file_path() -> None:
    """Test that file-path based auth headers are rejected for dynamic registration."""
    with pytest.raises(Exception, match="unsupported value"):
        MCPServerRegistrationRequest(
            name="bad-server",
            url="http://localhost:8080/mcp",
            authorization_headers={"Authorization": "/var/secrets/token"},
            provider_id="MCP provider ID",
        )


def test_mcp_server_registration_rejects_arbitrary_value() -> None:
    """Test that arbitrary auth header values are rejected."""
    with pytest.raises(Exception, match="unsupported value"):
        MCPServerRegistrationRequest(
            name="bad-server",
            url="http://localhost:8080/mcp",
            authorization_headers={"Authorization": "Bearer my-static-token"},
            provider_id="MCP provider ID",
        )
