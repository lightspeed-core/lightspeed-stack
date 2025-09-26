"""Unit tests for functions defined in src/configuration.py."""

import pytest
from configuration import AppConfig, LogicError
from models.config import CustomProfile, ModelContextProtocolServer


# pylint: disable=broad-exception-caught,protected-access
@pytest.fixture(autouse=True)
def _reset_app_config_between_tests():
    # ensure clean state before each test
    try:
        AppConfig()._configuration = None  # type: ignore[attr-defined]
    except Exception:
        pass
    yield
    # ensure clean state after each test
    try:
        AppConfig()._configuration = None  # type: ignore[attr-defined]
    except Exception:
        pass


def test_default_configuration() -> None:
    """Test that configuration attributes are not accessible for uninitialized app."""
    cfg = AppConfig()
    assert cfg is not None

    # configuration is not loaded
    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.service_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.llama_stack_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = (
            cfg.user_data_collection_configuration
        )  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.mcp_servers  # pylint: disable=pointless-statement

    # Test is_loaded method
    assert cfg.is_loaded() is False

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.authentication_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.customization  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.authorization_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.inference  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.database_configuration  # pylint: disable=pointless-statement

    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.conversation_cache_configuration  # pylint: disable=pointless-statement


def test_configuration_is_singleton() -> None:
    """Test that configuration is singleton."""
    cfg1 = AppConfig()
    cfg2 = AppConfig()
    assert cfg1 == cfg2


def test_init_from_dict() -> None:
    """Test the configuration initialization from dictionary with config values."""
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
            "feedback_enabled": False,
        },
        "mcp_servers": [],
        "customization": None,
        "authentication": {
            "module": "noop",
        },
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
    assert cfg.llama_stack_configuration.api_key.get_secret_value() == "xyzzy"
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
    assert cfg.user_data_collection_configuration.feedback_enabled is False

    # check authentication_configuration
    assert cfg.authentication_configuration is not None
    assert cfg.authentication_configuration.module == "noop"

    # check authorization configuration - default value
    assert cfg.authorization_configuration is not None

    # check database configuration
    assert cfg.database_configuration is not None

    # check inference configuration
    assert cfg.inference is not None

    # check conversation cache
    assert cfg.conversation_cache_configuration is not None


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
            "feedback_enabled": False,
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


def test_init_from_dict_with_authorization_configuration() -> None:
    """Test initialization with authorization configuration configuration."""
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
            "feedback_enabled": False,
        },
        "authorization": {},
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    assert cfg.authorization_configuration is not None


def test_load_proper_configuration(tmpdir) -> None:
    """Test loading proper configuration from YAML file."""
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
  feedback_enabled: false
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
    """Test loading configuration from YAML file with MCP servers."""
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
  feedback_enabled: false
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
            "feedback_enabled": False,
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
            "feedback_enabled": False,
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
    """Test that accessing configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        cfg.configuration  # pylint: disable=pointless-statement


def test_service_configuration_not_loaded():
    """Test that accessing service_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        cfg.service_configuration  # pylint: disable=pointless-statement


def test_llama_stack_configuration_not_loaded():
    """Test that accessing llama_stack_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        cfg.llama_stack_configuration  # pylint: disable=pointless-statement


def test_user_data_collection_configuration_not_loaded():
    """Test that accessing user_data_collection_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        cfg.user_data_collection_configuration  # pylint: disable=pointless-statement


def test_mcp_servers_not_loaded():
    """Test that accessing mcp_servers before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        cfg.mcp_servers  # pylint: disable=pointless-statement


def test_authentication_configuration_not_loaded():
    """Test that accessing authentication_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        cfg.authentication_configuration  # pylint: disable=pointless-statement


def test_customization_not_loaded():
    """Test that accessing customization before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        cfg.customization  # pylint: disable=pointless-statement


def test_load_configuration_with_customization_system_prompt_path(tmpdir) -> None:
    """Test loading configuration from YAML file with customization."""
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
  feedback_enabled: false
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
    """Test loading configuration from YAML file with system_prompt in the customization."""
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
  feedback_enabled: false
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


def test_configuration_with_profile_customization(tmpdir) -> None:
    """Test loading configuration from YAML file with a custom profile."""
    expected_profile = CustomProfile(path="tests/profiles/test/profile.py")
    expected_prompts = expected_profile.get_prompts()
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
  feedback_enabled: false
customization:
  profile_path: tests/profiles/test/profile.py
            """
        )

    cfg = AppConfig()
    cfg.load_configuration(cfg_filename)

    assert (
        cfg.customization is not None and cfg.customization.custom_profile is not None
    )
    fetched_prompts = cfg.customization.custom_profile.get_prompts()
    assert fetched_prompts is not None and fetched_prompts.get(
        "default"
    ) == expected_prompts.get("default")


def test_is_loaded_method():
    """Test the is_loaded method behavior."""
    cfg = AppConfig()
    
    # Initially not loaded
    assert cfg.is_loaded() is False
    
    # Load a valid configuration
    cfg.load_configuration("tests/configuration/lightspeed-stack.yaml")
    
    # Should now be loaded
    assert cfg.is_loaded() is True
    
    # Reset and verify not loaded again
    cfg._configuration = None  # type: ignore[attr-defined]
    assert cfg.is_loaded() is False


def test_configuration_with_all_customizations(tmpdir) -> None:
    """Test loading configuration from YAML file with a custom profile, prompt and prompt path."""
    expected_profile = CustomProfile(path="tests/profiles/test/profile.py")
    expected_prompts = expected_profile.get_prompts()
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
  feedback_enabled: false
customization:
  profile_path: tests/profiles/test/profile.py
  system_prompt: custom prompt
  system_prompt_path: {system_prompt_filename}
            """
        )

    cfg = AppConfig()
    cfg.load_configuration(cfg_filename)

    assert (
        cfg.customization is not None and cfg.customization.custom_profile is not None
    )
    fetched_prompts = cfg.customization.custom_profile.get_prompts()
    assert fetched_prompts is not None and fetched_prompts.get(
        "default"
    ) == expected_prompts.get("default")
