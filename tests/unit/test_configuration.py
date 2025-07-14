"""Unit tests for functions defined in src/configuration.py."""

import pytest
from configuration import AppConfig
from models.config import ModelContextProtocolServer


def test_default_configuration() -> None:
    """
    Verify that accessing any configuration-related property on an uninitialized AppConfig instance raises an exception indicating the configuration is not loaded.
    """
    cfg = AppConfig()
    assert cfg is not None

    # configuration is not loaded
    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        cfg.configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        cfg.service_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        cfg.llama_stack_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        cfg.user_data_collection_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        cfg.mcp_servers  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        cfg.authentication_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        cfg.customization  # pylint: disable=pointless-statement


def test_configuration_is_singleton() -> None:
    """
    Verify that multiple instances of AppConfig refer to the same singleton configuration object.
    """
    cfg1 = AppConfig()
    cfg2 = AppConfig()
    assert cfg1 == cfg2


def test_init_from_dict() -> None:
    """
    Verify that initializing AppConfig from a dictionary correctly sets all configuration subsections and their attributes.
    """
    config_dict = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_disabled": True,
        },
        "mcp_servers": [],
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    # check for all subsections
    assert cfg.configuration is not None
    assert cfg.llama_stack_configuration is not None
    assert cfg.service_configuration is not None
    assert cfg.user_data_collection_configuration is not None

    # check for configuration subsection
    assert cfg.configuration.name == "foo"

    # check for llama_stack_configuration subsection
    assert cfg.llama_stack_configuration.api_key == "xyzzy"
    assert cfg.llama_stack_configuration.url == "http://x.y.com:1234"
    assert cfg.llama_stack_configuration.use_as_library_client is False

    # check for service_configuration subsection
    assert cfg.service_configuration.host == "localhost"
    assert cfg.service_configuration.port == 8080
    assert cfg.service_configuration.auth_enabled is False
    assert cfg.service_configuration.workers == 1
    assert cfg.service_configuration.color_log is True
    assert cfg.service_configuration.access_log is True

    # check for user data collection subsection
    assert cfg.user_data_collection_configuration.feedback_disabled is True


def test_init_from_dict_with_mcp_servers() -> None:
    """Test initialization with MCP servers configuration."""
    config_dict = {
        "name": "foo",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "xyzzy",
            "url": "http://x.y.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_disabled": True,
        },
        "mcp_servers": [
            {
                "name": "server1",
                "url": "http://localhost:8080",
            },
            {
                "name": "server2",
                "provider_id": "custom-provider",
                "url": "https://api.example.com",
            },
        ],
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    assert len(cfg.mcp_servers) == 2
    assert cfg.mcp_servers[0].name == "server1"
    assert cfg.mcp_servers[0].provider_id == "model-context-protocol"
    assert cfg.mcp_servers[0].url == "http://localhost:8080"
    assert cfg.mcp_servers[1].name == "server2"
    assert cfg.mcp_servers[1].provider_id == "custom-provider"
    assert cfg.mcp_servers[1].url == "https://api.example.com"


def test_load_proper_configuration(tmpdir) -> None:
    """
    Test that a valid YAML configuration file can be loaded and all configuration subsections are accessible.
    
    Creates a sample configuration file, loads it using `AppConfig`, and asserts that the main configuration and its subsections are properly initialized.
    """
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write(
            """
name: foo bar baz
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  use_as_library_client: false
  url: http://localhost:8321
  api_key: xyzzy
user_data_collection:
  feedback_disabled: true
mcp_servers: []
            """
        )

    cfg = AppConfig()
    cfg.load_configuration(cfg_filename)
    assert cfg.configuration is not None
    assert cfg.llama_stack_configuration is not None
    assert cfg.service_configuration is not None
    assert cfg.user_data_collection_configuration is not None


def test_load_configuration_with_mcp_servers(tmpdir) -> None:
    """
    Test that loading a YAML configuration file with multiple MCP servers correctly initializes the `mcp_servers` property, including handling of default and custom `provider_id` values.
    """
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write(
            """
name: test service
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  use_as_library_client: false
  url: http://localhost:8321
  api_key: test-key
user_data_collection:
  feedback_disabled: true
mcp_servers:
  - name: filesystem-server
    url: http://localhost:3000
  - name: git-server
    provider_id: custom-git-provider
    url: https://git.example.com/mcp
            """
        )

    cfg = AppConfig()
    cfg.load_configuration(cfg_filename)

    assert len(cfg.mcp_servers) == 2
    assert cfg.mcp_servers[0].name == "filesystem-server"
    assert cfg.mcp_servers[0].provider_id == "model-context-protocol"
    assert cfg.mcp_servers[0].url == "http://localhost:3000"
    assert cfg.mcp_servers[1].name == "git-server"
    assert cfg.mcp_servers[1].provider_id == "custom-git-provider"
    assert cfg.mcp_servers[1].url == "https://git.example.com/mcp"


def test_mcp_servers_property_empty() -> None:
    """Test mcp_servers property returns empty list when no servers configured."""
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://localhost:8321",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_disabled": True,
        },
        "mcp_servers": [],
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    servers = cfg.mcp_servers
    assert isinstance(servers, list)
    assert len(servers) == 0


def test_mcp_servers_property_with_servers() -> None:
    """Test mcp_servers property returns correct list of ModelContextProtocolServer objects."""
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://localhost:8321",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "feedback_disabled": True,
        },
        "mcp_servers": [
            {
                "name": "test-server",
                "url": "http://localhost:8080",
            },
        ],
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    servers = cfg.mcp_servers
    assert isinstance(servers, list)
    assert len(servers) == 1
    assert isinstance(servers[0], ModelContextProtocolServer)
    assert servers[0].name == "test-server"
    assert servers[0].url == "http://localhost:8080"


def test_configuration_not_loaded():
    """
    Test that accessing the `configuration` property on an uninitialized `AppConfig` instance raises an AssertionError with the expected message.
    """
    cfg = AppConfig()
    with pytest.raises(
        AssertionError, match="logic error: configuration is not loaded"
    ):
        cfg.configuration  # pylint: disable=pointless-statement


def test_service_configuration_not_loaded():
    """
    Test that accessing the service_configuration property on an uninitialized AppConfig instance raises an AssertionError with the expected message.
    """
    cfg = AppConfig()
    with pytest.raises(
        AssertionError, match="logic error: configuration is not loaded"
    ):
        cfg.service_configuration  # pylint: disable=pointless-statement


def test_llama_stack_configuration_not_loaded():
    """
    Test that accessing the llama_stack_configuration property on an uninitialized AppConfig instance raises an AssertionError with the expected message.
    """
    cfg = AppConfig()
    with pytest.raises(
        AssertionError, match="logic error: configuration is not loaded"
    ):
        cfg.llama_stack_configuration  # pylint: disable=pointless-statement


def test_user_data_collection_configuration_not_loaded():
    """
    Test that accessing the user data collection configuration property before loading raises an AssertionError with the expected message.
    """
    cfg = AppConfig()
    with pytest.raises(
        AssertionError, match="logic error: configuration is not loaded"
    ):
        cfg.user_data_collection_configuration  # pylint: disable=pointless-statement


def test_mcp_servers_not_loaded():
    """
    Test that accessing the `mcp_servers` property on an uninitialized `AppConfig` instance raises an AssertionError with the expected message.
    """
    cfg = AppConfig()
    with pytest.raises(
        AssertionError, match="logic error: configuration is not loaded"
    ):
        cfg.mcp_servers  # pylint: disable=pointless-statement


def test_authentication_configuration_not_loaded():
    """
    Test that accessing the authentication_configuration property on an uninitialized AppConfig instance raises an AssertionError with the expected message.
    """
    cfg = AppConfig()
    with pytest.raises(
        AssertionError, match="logic error: configuration is not loaded"
    ):
        cfg.authentication_configuration  # pylint: disable=pointless-statement


def test_customization_not_loaded():
    """
    Test that accessing the `customization` property on an uninitialized `AppConfig` instance raises an AssertionError with the expected message.
    """
    cfg = AppConfig()
    with pytest.raises(
        AssertionError, match="logic error: configuration is not loaded"
    ):
        cfg.customization  # pylint: disable=pointless-statement


def test_load_configuration_with_customization_system_prompt_path(tmpdir) -> None:
    """
    Test that loading a YAML configuration file with a customization section specifying a system prompt file path correctly loads the system prompt content from the referenced file.
    
    Parameters:
        tmpdir: Temporary directory fixture provided by pytest for file operations.
    """
    system_prompt_filename = tmpdir / "system_prompt.txt"
    with open(system_prompt_filename, "w", encoding="utf-8") as fout:
        fout.write("this is system prompt")

    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write(
            f"""
name: test service
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  use_as_library_client: false
  url: http://localhost:8321
  api_key: test-key
user_data_collection:
  feedback_disabled: true
mcp_servers:
  - name: filesystem-server
    url: http://localhost:3000
  - name: git-server
    provider_id: custom-git-provider
    url: https://git.example.com/mcp
customization:
  disable_query_system_prompt: true
  system_prompt_path: {system_prompt_filename}
            """
        )

    cfg = AppConfig()
    cfg.load_configuration(cfg_filename)

    assert cfg.customization is not None
    assert cfg.customization.system_prompt is not None
    assert cfg.customization.system_prompt == "this is system prompt"


def test_load_configuration_with_customization_system_prompt(tmpdir) -> None:
    """
    Test that loading a YAML configuration file with an inline `system_prompt` in the customization section correctly sets the `system_prompt` property of the loaded configuration.
    """
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write(
            """
name: test service
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  use_as_library_client: false
  url: http://localhost:8321
  api_key: test-key
user_data_collection:
  feedback_disabled: true
mcp_servers:
  - name: filesystem-server
    url: http://localhost:3000
  - name: git-server
    provider_id: custom-git-provider
    url: https://git.example.com/mcp
customization:
  system_prompt: |-
    this is system prompt in the customization section
            """
        )

    cfg = AppConfig()
    cfg.load_configuration(cfg_filename)

    assert cfg.customization is not None
    assert cfg.customization.system_prompt is not None
    assert (
        cfg.customization.system_prompt.strip()
        == "this is system prompt in the customization section"
    )
