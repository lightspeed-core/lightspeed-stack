# pylint: disable=protected-access,redefined-outer-name

"""Unit tests for the MCP servers dynamic registration endpoint."""

from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from llama_stack_client import APIConnectionError
from pydantic import AnyHttpUrl, SecretStr
from pytest_mock import MockerFixture

from app.endpoints import mcp_servers
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.config import (
    Configuration,
    CORSConfiguration,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    ServiceConfiguration,
    TLSConfiguration,
    UserDataCollection,
)
from models.requests import MCPServerRegistrationRequest
from models.responses import (
    MCPServerDeleteResponse,
    MCPServerListResponse,
    MCPServerRegistrationResponse,
)

MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


@pytest.fixture
def mock_configuration() -> Configuration:
    """Create a mock configuration with MCP servers."""
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
        authorization=None,
        deployment_environment=".",
    )


def _make_app_config(mocker: MockerFixture, config: Configuration) -> AppConfig:
    """Create an AppConfig with the given configuration and patch it."""
    app_config = AppConfig()
    app_config._configuration = config
    app_config._dynamic_mcp_server_names = set()
    mocker.patch("app.endpoints.mcp_servers.configuration", app_config)
    mocker.patch("app.endpoints.mcp_servers.authorize", lambda _: lambda func: func)
    return app_config


def _mock_client(mocker: MockerFixture) -> Any:
    """Create and patch a mock Llama Stack client."""
    mock_holder = mocker.patch("app.endpoints.mcp_servers.AsyncLlamaStackClientHolder")
    mock_client = mocker.AsyncMock()
    mock_holder.return_value.get_client.return_value = mock_client
    return mock_client


@pytest.mark.asyncio
async def test_register_mcp_server_success(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test successful MCP server registration."""
    app_config = _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.return_value = None

    body = MCPServerRegistrationRequest(
        name="new-mcp-server",
        url="http://localhost:8888/mcp",
        provider_id="MCP provider ID",
    )

    result = await mcp_servers.register_mcp_server_handler(
        request=mocker.Mock(), body=body, auth=MOCK_AUTH
    )

    assert isinstance(result, MCPServerRegistrationResponse)
    assert result.name == "new-mcp-server"
    assert result.url == "http://localhost:8888/mcp"
    assert result.provider_id == "MCP provider ID"
    assert "registered successfully" in result.message

    client.toolgroups.register.assert_called_once_with(
        toolgroup_id="new-mcp-server",
        provider_id="MCP provider ID",
        mcp_endpoint={"uri": "http://localhost:8888/mcp"},
    )

    assert app_config.is_dynamic_mcp_server("new-mcp-server")
    assert any(s.name == "new-mcp-server" for s in app_config.mcp_servers)


@pytest.mark.asyncio
async def test_register_mcp_server_duplicate_name(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test registration fails when name already exists."""
    _make_app_config(mocker, mock_configuration)
    _mock_client(mocker)

    body = MCPServerRegistrationRequest(
        name="static-mcp",
        url="http://localhost:9999/mcp",
        provider_id="MCP provider ID",
    )

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.register_mcp_server_handler(
            request=mocker.Mock(), body=body, auth=MOCK_AUTH
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_register_mcp_server_llama_stack_failure(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test registration rolls back on Llama Stack connection failure."""
    app_config = _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.side_effect = APIConnectionError(request=mocker.Mock())

    body = MCPServerRegistrationRequest(
        name="failing-server",
        url="http://localhost:8888/mcp",
        provider_id="MCP provider ID",
    )

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.register_mcp_server_handler(
            request=mocker.Mock(), body=body, auth=MOCK_AUTH
        )
    assert exc_info.value.status_code == 503

    assert not app_config.is_dynamic_mcp_server("failing-server")
    assert not any(s.name == "failing-server" for s in app_config.mcp_servers)


@pytest.mark.asyncio
async def test_register_mcp_server_toolgroup_failure_returns_500(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Registration returns generic 500 without leaking toolgroup exception text."""
    app_config = _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.side_effect = RuntimeError("upstream secret detail")

    body = MCPServerRegistrationRequest(
        name="boom-server",
        url="http://localhost:8888/mcp",
        provider_id="MCP provider ID",
    )

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.register_mcp_server_handler(
            request=mocker.Mock(), body=body, auth=MOCK_AUTH
        )
    assert exc_info.value.status_code == 500
    raw_detail = exc_info.value.detail
    assert isinstance(raw_detail, dict)
    detail: dict[str, Any] = raw_detail
    assert detail["response"] == "Failed to register MCP server"

    assert not app_config.is_dynamic_mcp_server("boom-server")
    assert not any(s.name == "boom-server" for s in app_config.mcp_servers)


@pytest.mark.asyncio
async def test_register_mcp_server_with_all_fields(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test registration with all optional fields provided."""
    _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.return_value = None

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
async def test_list_mcp_servers_empty(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test listing servers returns static servers."""
    _make_app_config(mocker, mock_configuration)

    result = await mcp_servers.list_mcp_servers_handler(
        request=mocker.Mock(), auth=MOCK_AUTH
    )

    assert isinstance(result, MCPServerListResponse)
    assert len(result.servers) == 1
    assert result.servers[0].name == "static-mcp"
    assert result.servers[0].source == "config"


@pytest.mark.asyncio
async def test_list_mcp_servers_with_dynamic(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test listing shows both static and dynamic servers."""
    _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.return_value = None

    body = MCPServerRegistrationRequest(
        name="dynamic-server",
        url="http://localhost:9999/mcp",
        provider_id="MCP provider ID",
    )
    await mcp_servers.register_mcp_server_handler(
        request=mocker.Mock(), body=body, auth=MOCK_AUTH
    )

    result = await mcp_servers.list_mcp_servers_handler(
        request=mocker.Mock(), auth=MOCK_AUTH
    )

    assert len(result.servers) == 2
    sources = {s.name: s.source for s in result.servers}
    assert sources["static-mcp"] == "config"
    assert sources["dynamic-server"] == "api"


@pytest.mark.asyncio
async def test_delete_dynamic_mcp_server_success(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test successful deletion of a dynamically registered server."""
    app_config = _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.return_value = None
    client.toolgroups.unregister.return_value = None

    body = MCPServerRegistrationRequest(
        name="to-delete",
        url="http://localhost:7777/mcp",
        provider_id="MCP provider ID",
    )
    await mcp_servers.register_mcp_server_handler(
        request=mocker.Mock(), body=body, auth=MOCK_AUTH
    )
    assert app_config.is_dynamic_mcp_server("to-delete")

    result = await mcp_servers.delete_mcp_server_handler(
        request=mocker.Mock(), name="to-delete", auth=MOCK_AUTH
    )

    assert isinstance(result, MCPServerDeleteResponse)
    assert result.name == "to-delete"
    assert result.deleted is True
    assert result.response == "MCP server deleted successfully"

    assert not app_config.is_dynamic_mcp_server("to-delete")
    assert not any(s.name == "to-delete" for s in app_config.mcp_servers)

    client.toolgroups.unregister.assert_called_once_with(toolgroup_id="to-delete")


@pytest.mark.asyncio
async def test_delete_static_mcp_server_forbidden(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test that deleting a statically configured server is forbidden."""
    _make_app_config(mocker, mock_configuration)
    _mock_client(mocker)

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.delete_mcp_server_handler(
            request=mocker.Mock(), name="static-mcp", auth=MOCK_AUTH
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_nonexistent_mcp_server(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Deleting an unknown name returns 200 with deleted=False (idempotent delete)."""
    _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)

    result = await mcp_servers.delete_mcp_server_handler(
        request=mocker.Mock(), name="no-such-server", auth=MOCK_AUTH
    )

    assert isinstance(result, MCPServerDeleteResponse)
    assert result.name == "no-such-server"
    assert result.deleted is False
    assert result.response == "MCP server not found"
    client.toolgroups.unregister.assert_called_once_with(toolgroup_id="no-such-server")


@pytest.mark.asyncio
async def test_delete_mcp_server_llama_stack_failure(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test deletion handles Llama Stack connection failure gracefully."""
    _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.return_value = None
    client.toolgroups.unregister.side_effect = APIConnectionError(request=mocker.Mock())

    body = MCPServerRegistrationRequest(
        name="to-delete-fail",
        url="http://localhost:7777/mcp",
        provider_id="MCP provider ID",
    )
    await mcp_servers.register_mcp_server_handler(
        request=mocker.Mock(), body=body, auth=MOCK_AUTH
    )

    with pytest.raises(HTTPException) as exc_info:
        await mcp_servers.delete_mcp_server_handler(
            request=mocker.Mock(), name="to-delete-fail", auth=MOCK_AUTH
        )
    assert exc_info.value.status_code == 503


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


@pytest.mark.asyncio
async def test_register_and_delete_roundtrip(
    mocker: MockerFixture,
    mock_configuration: Configuration,
) -> None:
    """Test full register -> list -> delete -> list cycle."""
    _make_app_config(mocker, mock_configuration)
    client = _mock_client(mocker)
    client.toolgroups.register.return_value = None
    client.toolgroups.unregister.return_value = None

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
