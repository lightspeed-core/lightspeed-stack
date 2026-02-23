"""Unit tests for ModelContextProtocolServer model."""

# pyright: reportCallIssue=false

from pathlib import Path

import pytest

from pydantic import ValidationError

from models.config import (  # type: ignore[import-not-found]
    AuthenticationConfiguration,
    Configuration,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    ServiceConfiguration,
    UserDataCollection,
)


def test_model_context_protocol_server_constructor() -> None:
    """Test the ModelContextProtocolServer constructor."""
    mcp = ModelContextProtocolServer(name="test-server", url="http://localhost:8080")
    assert mcp is not None
    assert mcp.name == "test-server"
    assert mcp.provider_id == "model-context-protocol"
    assert mcp.url == "http://localhost:8080"
    assert mcp.authorization_headers == {}  # Default should be empty dict


def test_model_context_protocol_server_custom_provider() -> None:
    """Test the ModelContextProtocolServer constructor with custom provider."""
    mcp = ModelContextProtocolServer(
        name="custom-server",
        provider_id="custom-provider",
        url="https://api.example.com",
    )
    assert mcp is not None
    assert mcp.name == "custom-server"
    assert mcp.provider_id == "custom-provider"
    assert mcp.url == "https://api.example.com"


def test_model_context_protocol_server_required_fields() -> None:
    """Test that ModelContextProtocolServer requires name and url."""

    with pytest.raises(ValidationError):
        ModelContextProtocolServer()  # pyright: ignore[reportCallIssue]

    with pytest.raises(ValidationError):
        ModelContextProtocolServer(
            name="test-server"
        )  # pyright: ignore[reportCallIssue]

    with pytest.raises(ValidationError):
        ModelContextProtocolServer(
            url="http://localhost:8080"
        )  # pyright: ignore[reportCallIssue]


def test_configuration_empty_mcp_servers() -> None:
    """
    Test that a Configuration object can be created with an empty
    list of MCP servers.

    Verifies that the Configuration instance is constructed
    successfully and that the mcp_servers attribute is empty.
    """
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=[],
        customization=None,
    )
    assert cfg is not None
    assert not cfg.mcp_servers


def test_configuration_single_mcp_server() -> None:
    """
    Test that a Configuration object can be created with a single
    MCP server and verifies its properties.
    """
    mcp_server = ModelContextProtocolServer(
        name="test-server", url="http://localhost:8080"
    )
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=[mcp_server],
        customization=None,
    )
    assert cfg is not None
    assert len(cfg.mcp_servers) == 1
    assert cfg.mcp_servers[0].name == "test-server"
    assert cfg.mcp_servers[0].url == "http://localhost:8080"


def test_configuration_multiple_mcp_servers() -> None:
    """
    Verify that the Configuration object correctly handles multiple
    ModelContextProtocolServer instances in its mcp_servers list,
    including custom provider IDs.
    """
    mcp_servers = [
        ModelContextProtocolServer(name="server1", url="http://localhost:8080"),
        ModelContextProtocolServer(
            name="server2", url="http://localhost:8081", provider_id="custom-provider"
        ),
        ModelContextProtocolServer(name="server3", url="https://api.example.com"),
    ]
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=mcp_servers,
        customization=None,
    )
    assert cfg is not None
    assert len(cfg.mcp_servers) == 3
    assert cfg.mcp_servers[0].name == "server1"
    assert cfg.mcp_servers[1].name == "server2"
    assert cfg.mcp_servers[1].provider_id == "custom-provider"
    assert cfg.mcp_servers[2].name == "server3"


def test_model_context_protocol_server_with_authorization_headers(
    tmp_path: Path,
) -> None:
    """Test ModelContextProtocolServer with authorization headers."""
    auth_file = tmp_path / "auth.txt"
    auth_file.write_text("my-secret")
    api_key_file = tmp_path / "api_key.txt"
    api_key_file.write_text("api-key-secret")

    mcp = ModelContextProtocolServer(
        name="auth-server",
        url="http://localhost:8080",
        authorization_headers={
            "Authorization": str(auth_file),
            "X-API-Key": str(api_key_file),
        },
    )
    assert mcp is not None
    assert mcp.name == "auth-server"
    assert mcp.url == "http://localhost:8080"
    assert mcp.authorization_headers == {
        "Authorization": str(auth_file),
        "X-API-Key": str(api_key_file),
    }
    assert mcp.resolved_authorization_headers == {
        "Authorization": "my-secret",
        "X-API-Key": "api-key-secret",
    }


def test_model_context_protocol_server_kubernetes_special_case() -> None:
    """Test ModelContextProtocolServer with kubernetes special case."""
    mcp = ModelContextProtocolServer(
        name="k8s-server",
        url="http://localhost:8080",
        authorization_headers={"Authorization": "kubernetes"},
    )
    assert mcp is not None
    assert mcp.authorization_headers == {"Authorization": "kubernetes"}


def test_model_context_protocol_server_client_special_case() -> None:
    """Test ModelContextProtocolServer with client special case."""
    mcp = ModelContextProtocolServer(
        name="client-server",
        url="http://localhost:8080",
        authorization_headers={"Authorization": "client"},
    )
    assert mcp is not None
    assert mcp.authorization_headers == {"Authorization": "client"}


def test_model_context_protocol_server_oauth_special_case() -> None:
    """Test ModelContextProtocolServer with oauth special case."""
    mcp = ModelContextProtocolServer(
        name="oauth-server",
        url="http://localhost:8080",
        authorization_headers={"Authorization": "oauth"},
    )
    assert mcp is not None
    assert mcp.authorization_headers == {"Authorization": "oauth"}


def test_configuration_mcp_servers_with_mixed_auth_headers(tmp_path: Path) -> None:
    """
    Test Configuration with MCP servers having mixed authorization headers.

    Verifies backward compatibility (servers without auth headers) and
    new functionality (servers with auth headers) work together.
    """
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("my-secret")

    mcp_servers = [
        ModelContextProtocolServer(name="server-no-auth", url="http://localhost:8080"),
        ModelContextProtocolServer(
            name="server-with-secret",
            url="http://localhost:8081",
            authorization_headers={"Authorization": str(secret_file)},
        ),
        ModelContextProtocolServer(
            name="server-with-k8s",
            url="http://localhost:8082",
            authorization_headers={"Authorization": "kubernetes"},
        ),
        ModelContextProtocolServer(
            name="server-with-client",
            url="http://localhost:8083",
            authorization_headers={"Authorization": "client"},
        ),
    ]
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=mcp_servers,
        authentication=AuthenticationConfiguration(module="k8s"),
        customization=None,
    )
    assert cfg is not None
    assert len(cfg.mcp_servers) == 4

    # Server without auth headers (backward compatibility)
    assert cfg.mcp_servers[0].name == "server-no-auth"
    assert cfg.mcp_servers[0].authorization_headers == {}

    # Server with secret reference
    assert cfg.mcp_servers[1].name == "server-with-secret"
    assert cfg.mcp_servers[1].authorization_headers == {
        "Authorization": str(secret_file)
    }
    assert cfg.mcp_servers[1].resolved_authorization_headers == {
        "Authorization": "my-secret"
    }

    # Server with kubernetes special case
    assert cfg.mcp_servers[2].name == "server-with-k8s"
    assert cfg.mcp_servers[2].authorization_headers == {"Authorization": "kubernetes"}

    # Server with client special case
    assert cfg.mcp_servers[3].name == "server-with-client"
    assert cfg.mcp_servers[3].authorization_headers == {"Authorization": "client"}


def test_model_context_protocol_server_resolved_headers_with_special_values() -> None:
    """Test that resolved_authorization_headers preserves special values."""
    mcp = ModelContextProtocolServer(
        name="test-server",
        url="http://localhost:8080",
        authorization_headers={
            "Authorization": "kubernetes",
            "X-Custom": "client",
        },
    )
    assert mcp is not None
    # Special values should be preserved in resolved headers
    assert mcp.resolved_authorization_headers == {
        "Authorization": "kubernetes",
        "X-Custom": "client",
    }


def test_model_context_protocol_server_resolved_headers_with_file(
    tmp_path: Path,
) -> None:
    """Test that resolved_authorization_headers reads from files."""
    # Create a temporary secret file
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("my-secret-value")

    mcp = ModelContextProtocolServer(
        name="test-server",
        url="http://localhost:8080",
        authorization_headers={"Authorization": str(secret_file)},
    )
    assert mcp is not None
    # File content should be read into resolved headers
    assert mcp.resolved_authorization_headers == {"Authorization": "my-secret-value"}


def test_model_context_protocol_server_resolved_headers_empty() -> None:
    """Test that resolved_authorization_headers is empty when no auth headers."""
    mcp = ModelContextProtocolServer(
        name="test-server",
        url="http://localhost:8080",
    )
    assert mcp is not None
    assert not mcp.resolved_authorization_headers
