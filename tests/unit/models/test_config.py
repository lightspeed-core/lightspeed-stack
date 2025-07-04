"""Unit tests for functions defined in src/models/config.py."""

import json
import pytest

from pathlib import Path

from constants import AUTH_MOD_NOOP, AUTH_MOD_K8S
from models.config import (
    Configuration,
    LLamaStackConfiguration,
    ServiceConfiguration,
    UserDataCollection,
    TLSConfiguration,
    ModelContextProtocolServer,
)


def test_service_configuration_constructor() -> None:
    """Test the ServiceConfiguration constructor."""
    s = ServiceConfiguration()
    assert s is not None

    assert s.host == "localhost"
    assert s.port == 8080
    assert s.auth_enabled is False
    assert s.workers == 1
    assert s.color_log is True
    assert s.access_log is True
    assert s.tls_config == TLSConfiguration()


def test_service_configuration_port_value() -> None:
    """Test the ServiceConfiguration port value validation."""
    with pytest.raises(ValueError, match="Port value should not be negative"):
        ServiceConfiguration(port=-1)

    with pytest.raises(ValueError, match="Port value should be less than 65536"):
        ServiceConfiguration(port=100000)


def test_service_configuration_workers_value() -> None:
    """Test the ServiceConfiguration workers value validation."""
    with pytest.raises(ValueError, match="Workers must be set to at least 1"):
        ServiceConfiguration(workers=-1)


def test_llama_stack_configuration_constructor() -> None:
    """Test the LLamaStackConfiguration constructor."""
    llama_stack_configuration = LLamaStackConfiguration(
        use_as_library_client=True, library_client_config_path="foo"
    )
    assert llama_stack_configuration is not None

    llama_stack_configuration = LLamaStackConfiguration(
        use_as_library_client=False, url="http://localhost"
    )
    assert llama_stack_configuration is not None

    llama_stack_configuration = LLamaStackConfiguration(url="http://localhost")
    assert llama_stack_configuration is not None

    llama_stack_configuration = LLamaStackConfiguration(
        use_as_library_client=False, url="http://localhost", api_key="foo"
    )
    assert llama_stack_configuration is not None


def test_llama_stack_wrong_configuration_constructor_no_url() -> None:
    """Test the LLamaStackConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="LLama stack URL is not specified and library client mode is not specified",
    ):
        LLamaStackConfiguration()


def test_llama_stack_wrong_configuration_constructor_library_mode_off() -> None:
    """Test the LLamaStackConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="LLama stack URL is not specified and library client mode is not enabled",
    ):
        LLamaStackConfiguration(use_as_library_client=False)


def test_llama_stack_wrong_configuration_no_config_file() -> None:
    """Test the LLamaStackConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="LLama stack library client mode is enabled but a configuration file path is not specified",
    ):
        LLamaStackConfiguration(use_as_library_client=True)


def test_user_data_collection_feedback_enabled() -> None:
    """Test the UserDataCollection constructor for feedback."""
    # correct configuration
    cfg = UserDataCollection(feedback_disabled=True, feedback_storage=None)
    assert cfg is not None
    assert cfg.feedback_disabled is True
    assert cfg.feedback_storage is None


def test_user_data_collection_feedback_disabled() -> None:
    """Test the UserDataCollection constructor for feedback."""
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="feedback_storage is required when feedback is enabled",
    ):
        UserDataCollection(feedback_disabled=False, feedback_storage=None)


def test_user_data_collection_transcripts_enabled() -> None:
    """Test the UserDataCollection constructor for transcripts."""
    # correct configuration
    cfg = UserDataCollection(transcripts_disabled=True, transcripts_storage=None)
    assert cfg is not None


def test_user_data_collection_transcripts_disabled() -> None:
    """Test the UserDataCollection constructor for transcripts."""
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="transcripts_storage is required when transcripts is enabled",
    ):
        UserDataCollection(transcripts_disabled=False, transcripts_storage=None)


def test_tls_configuration() -> None:
    """Test the TLS configuration."""
    cfg = TLSConfiguration(
        tls_certificate_path="tests/configuration/server.crt",
        tls_key_path="tests/configuration/server.key",
        tls_key_password="tests/configuration/password",
    )
    assert cfg is not None
    assert cfg.tls_certificate_path == Path("tests/configuration/server.crt")
    assert cfg.tls_key_path == Path("tests/configuration/server.key")
    assert cfg.tls_key_password == Path("tests/configuration/password")


def test_tls_configuration_wrong_certificate_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="this-is-wrong",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_wrong_key_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="this-is-wrong",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_wrong_password_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="this-is-wrong",
        )


def test_tls_configuration_certificate_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_key_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="tests/",
            tls_key_password="tests/configuration/password",
        )


def test_tls_configuration_password_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path="tests/configurationserver.crt",
            tls_key_path="tests/configuration/server.key",
            tls_key_password="tests/",
        )


def test_model_context_protocol_server_constructor() -> None:
    """Test the ModelContextProtocolServer constructor."""
    mcp = ModelContextProtocolServer(name="test-server", url="http://localhost:8080")
    assert mcp is not None
    assert mcp.name == "test-server"
    assert mcp.provider_id == "model-context-protocol"
    assert mcp.url == "http://localhost:8080"


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
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ModelContextProtocolServer()

    with pytest.raises(ValidationError):
        ModelContextProtocolServer(name="test-server")

    with pytest.raises(ValidationError):
        ModelContextProtocolServer(url="http://localhost:8080")


def test_configuration_empty_mcp_servers() -> None:
    """Test Configuration with empty MCP servers list."""
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True, library_client_config_path="foo"
        ),
        user_data_collection=UserDataCollection(
            feedback_disabled=True, feedback_storage=None
        ),
        mcp_servers=[],
    )
    assert cfg is not None
    assert cfg.mcp_servers == []


def test_configuration_single_mcp_server() -> None:
    """Test Configuration with a single MCP server."""
    mcp_server = ModelContextProtocolServer(
        name="test-server", url="http://localhost:8080"
    )
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True, library_client_config_path="foo"
        ),
        user_data_collection=UserDataCollection(
            feedback_disabled=True, feedback_storage=None
        ),
        mcp_servers=[mcp_server],
    )
    assert cfg is not None
    assert len(cfg.mcp_servers) == 1
    assert cfg.mcp_servers[0].name == "test-server"
    assert cfg.mcp_servers[0].url == "http://localhost:8080"


def test_configuration_multiple_mcp_servers() -> None:
    """Test Configuration with multiple MCP servers."""
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
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True, library_client_config_path="foo"
        ),
        user_data_collection=UserDataCollection(
            feedback_disabled=True, feedback_storage=None
        ),
        mcp_servers=mcp_servers,
    )
    assert cfg is not None
    assert len(cfg.mcp_servers) == 3
    assert cfg.mcp_servers[0].name == "server1"
    assert cfg.mcp_servers[1].name == "server2"
    assert cfg.mcp_servers[1].provider_id == "custom-provider"
    assert cfg.mcp_servers[2].name == "server3"


def test_dump_configuration(tmp_path) -> None:
    """Test the ability to dump configuration."""
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True, library_client_config_path="foo"
        ),
        user_data_collection=UserDataCollection(
            feedback_disabled=True, feedback_storage=None
        ),
        mcp_servers=[],
    )
    assert cfg is not None
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        # content should be loaded
        assert content is not None

        # all sections must exists
        assert "name" in content
        assert "service" in content
        assert "llama_stack" in content
        assert "user_data_collection" in content
        assert "mcp_servers" in content
        assert "authentication" in content

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": None,
                    "tls_key_path": None,
                    "tls_key_password": None,
                },
            },
            "llama_stack": {
                "url": None,
                "api_key": None,
                "use_as_library_client": True,
                "library_client_config_path": "foo",
            },
            "user_data_collection": {
                "feedback_disabled": True,
                "feedback_storage": None,
                "transcripts_disabled": True,
                "transcripts_storage": None,
            },
            "mcp_servers": [],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
            },
        }


def test_dump_configuration_with_one_mcp_server(tmp_path) -> None:
    """Test the ability to dump configuration with one MCP server configured."""
    mcp_servers = [
        ModelContextProtocolServer(name="test-server", url="http://localhost:8080"),
    ]
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True, library_client_config_path="foo"
        ),
        user_data_collection=UserDataCollection(
            feedback_disabled=True, feedback_storage=None
        ),
        mcp_servers=mcp_servers,
    )
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        assert content is not None
        assert "mcp_servers" in content
        assert len(content["mcp_servers"]) == 1
        assert content["mcp_servers"][0]["name"] == "test-server"
        assert content["mcp_servers"][0]["url"] == "http://localhost:8080"
        assert content["mcp_servers"][0]["provider_id"] == "model-context-protocol"

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": None,
                    "tls_key_path": None,
                    "tls_key_password": None,
                },
            },
            "llama_stack": {
                "url": None,
                "api_key": None,
                "use_as_library_client": True,
                "library_client_config_path": "foo",
            },
            "user_data_collection": {
                "feedback_disabled": True,
                "feedback_storage": None,
                "transcripts_disabled": True,
                "transcripts_storage": None,
            },
            "mcp_servers": [
                {
                    "name": "test-server",
                    "provider_id": "model-context-protocol",
                    "url": "http://localhost:8080",
                },
            ],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
            },
        }


def test_dump_configuration_with_more_mcp_servers(tmp_path) -> None:
    """Test the ability to dump configuration with more MCP servers configured."""
    mcp_servers = [
        ModelContextProtocolServer(name="test-server-1", url="http://localhost:8081"),
        ModelContextProtocolServer(name="test-server-2", url="http://localhost:8082"),
        ModelContextProtocolServer(name="test-server-3", url="http://localhost:8083"),
    ]
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True, library_client_config_path="foo"
        ),
        user_data_collection=UserDataCollection(
            feedback_disabled=True, feedback_storage=None
        ),
        mcp_servers=mcp_servers,
    )
    dump_file = tmp_path / "test.json"
    cfg.dump(dump_file)

    with open(dump_file, "r", encoding="utf-8") as fin:
        content = json.load(fin)
        assert content is not None
        assert "mcp_servers" in content
        assert len(content["mcp_servers"]) == 3
        assert content["mcp_servers"][0]["name"] == "test-server-1"
        assert content["mcp_servers"][0]["url"] == "http://localhost:8081"
        assert content["mcp_servers"][0]["provider_id"] == "model-context-protocol"
        assert content["mcp_servers"][1]["name"] == "test-server-2"
        assert content["mcp_servers"][1]["url"] == "http://localhost:8082"
        assert content["mcp_servers"][1]["provider_id"] == "model-context-protocol"
        assert content["mcp_servers"][2]["name"] == "test-server-3"
        assert content["mcp_servers"][2]["url"] == "http://localhost:8083"
        assert content["mcp_servers"][2]["provider_id"] == "model-context-protocol"

        # check the whole deserialized JSON file content
        assert content == {
            "name": "test_name",
            "service": {
                "host": "localhost",
                "port": 8080,
                "auth_enabled": False,
                "workers": 1,
                "color_log": True,
                "access_log": True,
                "tls_config": {
                    "tls_certificate_path": None,
                    "tls_key_path": None,
                    "tls_key_password": None,
                },
            },
            "llama_stack": {
                "url": None,
                "api_key": None,
                "use_as_library_client": True,
                "library_client_config_path": "foo",
            },
            "user_data_collection": {
                "feedback_disabled": True,
                "feedback_storage": None,
                "transcripts_disabled": True,
                "transcripts_storage": None,
            },
            "mcp_servers": [
                {
                    "name": "test-server-1",
                    "provider_id": "model-context-protocol",
                    "url": "http://localhost:8081",
                },
                {
                    "name": "test-server-2",
                    "provider_id": "model-context-protocol",
                    "url": "http://localhost:8082",
                },
                {
                    "name": "test-server-3",
                    "provider_id": "model-context-protocol",
                    "url": "http://localhost:8083",
                },
            ],
            "authentication": {
                "module": "noop",
                "skip_tls_verification": False,
                "k8s_ca_cert_path": None,
                "k8s_cluster_api": None,
            },
        }


def test_authentication_configuration() -> None:
    """Test the AuthenticationConfiguration constructor."""
    from models.config import AuthenticationConfiguration

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_NOOP,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_NOOP
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None


def test_authentication_configuration_supported() -> None:
    """Test the AuthenticationConfiguration constructor."""
    from models.config import AuthenticationConfiguration

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_K8S,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_K8S
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None


def test_authentication_configuration_module_unsupported() -> None:
    """Test the AuthenticationConfiguration constructor with module as None."""
    from models.config import AuthenticationConfiguration
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Unsupported authentication module"):
        AuthenticationConfiguration(
            module="non-existing-module",
            skip_tls_verification=False,
            k8s_ca_cert_path=None,
            k8s_cluster_api=None,
        )
