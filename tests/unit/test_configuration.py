"""Unit tests for functions defined in src/configuration.py."""

# pylint: disable=too-many-lines

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import constants
from cache.in_memory_cache import InMemoryCache
from cache.sqlite_cache import SQLiteCache
from configuration import (
    AppConfig,
    LogicError,
    replace_env_vars_preserving_native_override,
)
from models.config import CustomProfile, ModelContextProtocolServer
from utils.checks import InvalidConfigurationError


# pylint: disable=broad-exception-caught,protected-access
@pytest.fixture(autouse=True)
def _reset_app_config_between_tests() -> Generator:
    # ensure clean state before each test
    """
    Reset AppConfig singleton internal state before and after a test to avoid test contamination.

    Attempts to set AppConfig()._configuration to None and
    AppConfig()._quota_limiters to an empty list, ignoring any exceptions, then
    yields control to the test and repeats the cleanup after the test.
    """
    try:
        AppConfig()._configuration = None  # type: ignore[attr-defined]
        AppConfig()._quota_limiters = []  # type: ignore[attr-defined]
    except Exception:
        pass
    yield
    # ensure clean state after each test
    try:
        AppConfig()._configuration = None  # type: ignore[attr-defined]
        AppConfig()._quota_limiters = []  # type: ignore[attr-defined]
    except Exception:
        pass


def test_default_configuration() -> None:
    """Test that configuration attributes are not accessible for uninitialized app."""
    cfg = AppConfig()
    assert cfg is not None

    # configuration is not loaded
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.service_configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.llama_stack_configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = (
            cfg.user_data_collection_configuration
        )  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.mcp_servers  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.authentication_configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.customization  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.authorization_configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.inference  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.database_configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.conversation_cache_configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.quota_handlers_configuration  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.conversation_cache  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.quota_limiters  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.a2a_state  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.token_usage_history  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.azure_entra_id  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.splunk  # pylint: disable=pointless-statement

    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        # try to read property
        _ = cfg.deployment_environment  # pylint: disable=pointless-statement


def test_configuration_is_singleton() -> None:
    """Test that configuration is singleton."""
    cfg1 = AppConfig()
    cfg2 = AppConfig()
    assert cfg1 == cfg2


def test_init_from_dict() -> None:
    """Test the configuration initialization from dictionary with config values."""
    config_dict: dict[str, Any] = {
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
        "a2a_state": {
            "sqlite": None,
            "postgres": None,
        },
        "splunk": {
            "enabled": False,
            "url": "foo.bar.baz",
            "index": "index",
            "source": "source",
            "timeout": 10,
            "verify_ssl": False,
        },
        "deployment_environment": "foo",
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
    assert cfg.llama_stack_configuration.api_key is not None
    assert cfg.llama_stack_configuration.api_key.get_secret_value() == "xyzzy"
    assert str(cfg.llama_stack_configuration.url) == "http://x.y.com:1234/"
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

    # check a2a state
    assert cfg.a2a_state is not None
    assert cfg.a2a_state.sqlite is None
    assert cfg.a2a_state.postgres is None

    # check Splunk
    assert cfg.splunk is not None
    assert cfg.splunk.enabled is False
    assert cfg.splunk.url == "foo.bar.baz"
    assert cfg.splunk.index == "index"
    assert cfg.splunk.source == "source"
    assert cfg.splunk.timeout == 10
    assert cfg.splunk.verify_ssl is False

    # check deployment_environment
    assert cfg.deployment_environment is not None

    # check token usage history
    assert cfg.token_usage_history is None


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
    """Test initialization with authorization configuration configuration.

    Verify AppConfig initializes authorization configuration when an empty
    `authorization` block is provided.

    Initializes the singleton AppConfig from a dict that includes an empty
    `authorization` section and asserts that `authorization_configuration` is
    not None.
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
            "feedback_enabled": False,
        },
        "authorization": {},
        "customization": None,
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)

    assert cfg.authorization_configuration is not None


def test_load_proper_configuration(tmpdir: Path) -> None:
    """Test loading proper configuration from YAML file.

    Verify that a valid YAML configuration file loads and populates key AppConfig sections.

    Writes a YAML configuration to a temporary file, loads it with
    AppConfig.load_configuration, and asserts that `configuration`,
    `llama_stack_configuration`, `service_configuration`, and
    `user_data_collection_configuration` are populated.
    """
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))
    assert cfg.configuration is not None
    assert cfg.llama_stack_configuration is not None
    assert cfg.service_configuration is not None
    assert cfg.user_data_collection_configuration is not None


def test_load_configuration_with_mcp_servers(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with MCP servers."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert len(cfg.mcp_servers) == 2
    assert cfg.mcp_servers[0].name == "filesystem-server"
    assert cfg.mcp_servers[0].provider_id == "model-context-protocol"
    assert cfg.mcp_servers[0].url == "http://localhost:3000"
    assert cfg.mcp_servers[1].name == "git-server"
    assert cfg.mcp_servers[1].provider_id == "custom-git-provider"
    assert cfg.mcp_servers[1].url == "https://git.example.com/mcp"


def test_mcp_servers_property_empty() -> None:
    """Test mcp_servers property returns empty list when no servers configured."""
    config_dict: dict[str, Any] = {
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


def test_configuration_not_loaded() -> None:
    """Test that accessing configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        c = cfg.configuration
        assert c is not None


def test_service_configuration_not_loaded() -> None:
    """Test that accessing service_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        c = cfg.service_configuration
        assert c is not None


def test_llama_stack_configuration_not_loaded() -> None:
    """Test that accessing llama_stack_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        c = cfg.llama_stack_configuration
        assert c is not None


def test_user_data_collection_configuration_not_loaded() -> None:
    """Test that accessing user_data_collection_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        c = cfg.user_data_collection_configuration
        assert c is not None


def test_mcp_servers_not_loaded() -> None:
    """Test that accessing mcp_servers before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        c = cfg.mcp_servers
        assert c is not None


def test_authentication_configuration_not_loaded() -> None:
    """Test that accessing authentication_configuration before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        c = cfg.authentication_configuration
        assert c is not None


def test_customization_not_loaded() -> None:
    """Test that accessing customization before loading raises an error."""
    cfg = AppConfig()
    with pytest.raises(LogicError, match="logic error: configuration is not loaded"):
        c = cfg.customization
        assert c is not None


def test_load_configuration_with_customization_system_prompt_path(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with customization."""
    system_prompt_filename = tmpdir / "system_prompt.txt"
    with open(system_prompt_filename, "w", encoding="utf-8") as fout:
        fout.write("this is system prompt")

    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write(f"""
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
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert cfg.customization is not None
    assert cfg.customization.system_prompt is not None
    assert cfg.customization.system_prompt == "this is system prompt"


def test_load_configuration_with_customization_system_prompt(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with system_prompt in the customization."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert cfg.customization is not None
    assert cfg.customization.system_prompt is not None
    assert (
        cfg.customization.system_prompt.strip()
        == "this is system prompt in the customization section"
    )


def test_configuration_with_profile_customization(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with a custom profile."""
    expected_profile = CustomProfile(path="tests/profiles/test/profile.py")
    expected_prompts = expected_profile.get_prompts()
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert (
        cfg.customization is not None and cfg.customization.custom_profile is not None
    )
    fetched_prompts = cfg.customization.custom_profile.get_prompts()
    assert fetched_prompts is not None and fetched_prompts.get(
        "default"
    ) == expected_prompts.get("default")


def test_configuration_with_all_customizations(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with a custom profile, prompt and prompt path."""
    expected_profile = CustomProfile(path="tests/profiles/test/profile.py")
    expected_prompts = expected_profile.get_prompts()
    system_prompt_filename = tmpdir / "system_prompt.txt"
    with open(system_prompt_filename, "w", encoding="utf-8") as fout:
        fout.write("this is system prompt")

    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write(f"""
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
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert (
        cfg.customization is not None and cfg.customization.custom_profile is not None
    )
    fetched_prompts = cfg.customization.custom_profile.get_prompts()
    assert fetched_prompts is not None and fetched_prompts.get(
        "default"
    ) == expected_prompts.get("default")


def test_configuration_with_sqlite_conversation_cache(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with conversation cache configuration."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
conversation_cache:
  type: "sqlite"
  sqlite:
    db_path: ":memory:"
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert cfg.conversation_cache_configuration is not None
    assert cfg.conversation_cache_configuration.type == "sqlite"
    assert cfg.conversation_cache_configuration.sqlite is not None
    assert cfg.conversation_cache_configuration.postgres is None
    assert cfg.conversation_cache_configuration.memory is None
    assert cfg.conversation_cache is not None
    assert isinstance(cfg.conversation_cache, SQLiteCache)


def test_configuration_with_in_memory_conversation_cache(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with conversation cache configuration."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
conversation_cache:
  type: "memory"
  memory:
    max_entries: 42
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert cfg.conversation_cache_configuration is not None
    assert cfg.conversation_cache_configuration.type == "memory"
    assert cfg.conversation_cache_configuration.sqlite is None
    assert cfg.conversation_cache_configuration.postgres is None
    assert cfg.conversation_cache_configuration.memory is not None
    assert cfg.conversation_cache is not None
    assert isinstance(cfg.conversation_cache, InMemoryCache)


def test_configuration_with_quota_handlers_no_storage(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with quota handlers configuration."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
quota_handlers:
  limiters:
    - name: user_monthly_limits
      type: user_limiter
      initial_quota: 10
      quota_increase: 10
      period: "2 seconds"
    - name: cluster_monthly_limits
      type: cluster_limiter
      initial_quota: 100
      quota_increase: 10
      period: "10 seconds"
  scheduler:
    # scheduler ticks in seconds
    period: 1
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert cfg.quota_handlers_configuration is not None
    assert cfg.quota_handlers_configuration.sqlite is None
    assert cfg.quota_handlers_configuration.postgres is None
    assert cfg.quota_handlers_configuration.limiters is not None
    assert cfg.quota_handlers_configuration.scheduler is not None

    # check the quota limiters configuration
    assert len(cfg.quota_limiters) == 0

    # check the scheduler configuration
    assert cfg.quota_handlers_configuration.scheduler.period == 1


def test_configuration_with_token_history_no_storage(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with quota handlers configuration."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
quota_handlers:
  scheduler:
    # scheduler ticks in seconds
    period: 1
  enable_token_history: true
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert cfg.quota_handlers_configuration is not None
    assert cfg.quota_handlers_configuration.sqlite is None
    assert cfg.quota_handlers_configuration.postgres is None
    assert cfg.quota_handlers_configuration.scheduler is not None

    # check the token usage history
    assert cfg.token_usage_history is not None


def test_configuration_with_quota_handlers(tmpdir: Path) -> None:
    """Test loading configuration from YAML file with quota handlers configuration."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
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
quota_handlers:
  sqlite:
      db_path: ":memory:"
  limiters:
    - name: user_monthly_limits
      type: user_limiter
      initial_quota: 10
      quota_increase: 10
      period: "2 seconds"
    - name: cluster_monthly_limits
      type: cluster_limiter
      initial_quota: 100
      quota_increase: 10
      period: "10 seconds"
  scheduler:
    # scheduler ticks in seconds
    period: 1
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    assert cfg.quota_handlers_configuration is not None
    assert cfg.quota_handlers_configuration.sqlite is not None
    assert cfg.quota_handlers_configuration.postgres is None
    assert cfg.quota_handlers_configuration.limiters is not None
    assert cfg.quota_handlers_configuration.scheduler is not None

    # check the storage
    assert cfg.quota_handlers_configuration.sqlite.db_path == ":memory:"

    # check the quota limiters configuration
    assert len(cfg.quota_limiters) == 2
    assert (
        str(cfg.quota_limiters[0])
        == "UserQuotaLimiter: initial quota: 10 increase by: 10"
    )
    assert (
        str(cfg.quota_limiters[1])
        == "ClusterQuotaLimiter: initial quota: 100 increase by: 10"
    )

    # check the scheduler configuration
    assert cfg.quota_handlers_configuration.scheduler.period == 1


def test_load_configuration_with_azure_entra_id(tmpdir: Path) -> None:
    """Return Azure Entra ID configuration when provided in configuration."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
name: test service
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  api_key: test-key
  url: http://localhost:8321
  use_as_library_client: false
user_data_collection:
  feedback_enabled: false
azure_entra_id:
  tenant_id: tenant
  client_id: client
  client_secret: secret
            """)

    cfg = AppConfig()
    cfg.load_configuration(str(cfg_filename))

    azure_conf = cfg.azure_entra_id
    assert azure_conf is not None
    assert azure_conf.tenant_id.get_secret_value() == "tenant"
    assert azure_conf.client_id.get_secret_value() == "client"
    assert azure_conf.client_secret.get_secret_value() == "secret"


def test_load_configuration_with_incomplete_azure_entra_id_raises(tmpdir: Path) -> None:
    """Raise error if Azure Entra ID block is incomplete in configuration."""
    cfg_filename = tmpdir / "config.yaml"
    with open(cfg_filename, "w", encoding="utf-8") as fout:
        fout.write("""
name: test service
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  api_key: test-key
  url: http://localhost:8321
  use_as_library_client: false
user_data_collection:
  feedback_enabled: false
azure_entra_id:
  tenant_id: tenant
  client_id: client
            """)

    cfg = AppConfig()
    with pytest.raises(ValidationError):
        cfg.load_configuration(str(cfg_filename))


def test_rag_id_mapping_excludes_solr_when_okp_not_configured(
    minimal_config: AppConfig,
) -> None:
    """Test that rag_id_mapping does not include OKP/Solr when OKP is not in rag config."""
    assert minimal_config.rag_id_mapping == {}


def test_rag_id_mapping_includes_solr_when_okp_in_inline() -> None:
    """Test that rag_id_mapping includes OKP/Solr mapping when OKP is in rag.inline."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "rag": {
                "retrieval": {
                    "inline": {"sources": [constants.OKP_RAG_ID]},
                },
            },
        }
    )
    assert constants.SOLR_DEFAULT_VECTOR_STORE_ID in cfg.rag_id_mapping
    assert (
        cfg.rag_id_mapping[constants.SOLR_DEFAULT_VECTOR_STORE_ID]
        == constants.OKP_RAG_ID
    )


def test_rag_id_mapping_includes_solr_when_okp_in_tool() -> None:
    """Test that rag_id_mapping includes OKP/Solr mapping when OKP is in rag.tool."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "rag": {
                "retrieval": {
                    "tool": {"sources": [constants.OKP_RAG_ID]},
                },
            },
        }
    )
    assert constants.SOLR_DEFAULT_VECTOR_STORE_ID in cfg.rag_id_mapping
    assert (
        cfg.rag_id_mapping[constants.SOLR_DEFAULT_VECTOR_STORE_ID]
        == constants.OKP_RAG_ID
    )


def test_rag_id_mapping_with_byok(tmp_path: Path) -> None:
    """Test that rag_id_mapping builds correct mapping from BYOK config."""
    db_file = tmp_path / "test.db"
    db_file.touch()
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "rag": {
                "byok": {
                    "stores": [
                        {
                            "rag_id": "my-kb",
                            "vector_db_id": "vs-001",
                            "db_path": str(db_file),
                        },
                    ],
                },
            },
        }
    )
    assert cfg.rag_id_mapping == {"vs-001": "my-kb"}


def test_rag_id_mapping_with_byok_and_okp(tmp_path: Path) -> None:
    """Test that rag_id_mapping includes both BYOK and OKP entries when OKP is configured."""
    db_file = tmp_path / "test.db"
    db_file.touch()
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "rag": {
                "retrieval": {
                    "inline": {"sources": [constants.OKP_RAG_ID]},
                },
                "byok": {
                    "stores": [
                        {
                            "rag_id": "my-kb",
                            "vector_db_id": "vs-001",
                            "db_path": str(db_file),
                        },
                    ],
                },
            },
        }
    )
    assert "vs-001" in cfg.rag_id_mapping
    assert cfg.rag_id_mapping["vs-001"] == "my-kb"
    assert constants.SOLR_DEFAULT_VECTOR_STORE_ID in cfg.rag_id_mapping
    assert (
        cfg.rag_id_mapping[constants.SOLR_DEFAULT_VECTOR_STORE_ID]
        == constants.OKP_RAG_ID
    )


def test_resolve_index_name_with_mapping(minimal_config: AppConfig) -> None:
    """Test resolve_index_name uses mapping when available."""
    mapping = {"vs-x": "user-friendly-name"}
    assert minimal_config.resolve_index_name("vs-x", mapping) == "user-friendly-name"


def test_resolve_index_name_passthrough(minimal_config: AppConfig) -> None:
    """Test resolve_index_name passes through unmapped IDs."""
    assert minimal_config.resolve_index_name("vs-unknown", {}) == "vs-unknown"


def test_rag_id_mapping_not_loaded() -> None:
    """Test that rag_id_mapping raises when config not loaded."""
    cfg = AppConfig()
    cfg._configuration = None
    with pytest.raises(LogicError):
        _ = cfg.rag_id_mapping


def test_score_multiplier_mapping_empty_when_no_byok(minimal_config: AppConfig) -> None:
    """Test that score_multiplier_mapping returns empty dict when no BYOK RAG configured."""
    assert minimal_config.score_multiplier_mapping == {}


def test_score_multiplier_mapping_with_byok_defaults(tmp_path: Path) -> None:
    """Test that score_multiplier_mapping uses default multiplier when not specified."""
    db_file = tmp_path / "test.db"
    db_file.touch()
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "rag": {
                "byok": {
                    "stores": [
                        {
                            "rag_id": "my-kb",
                            "vector_db_id": "vs-001",
                            "db_path": str(db_file),
                        },
                    ],
                },
            },
        }
    )
    assert cfg.score_multiplier_mapping == {"vs-001": 1.0}


def test_score_multiplier_mapping_with_custom_values(tmp_path: Path) -> None:
    """Test that score_multiplier_mapping builds correct mapping with custom values."""
    db_file1 = tmp_path / "test1.db"
    db_file1.touch()
    db_file2 = tmp_path / "test2.db"
    db_file2.touch()
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "k",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "rag": {
                "byok": {
                    "stores": [
                        {
                            "rag_id": "kb1",
                            "vector_db_id": "vs-001",
                            "db_path": str(db_file1),
                            "score_multiplier": 1.5,
                        },
                        {
                            "rag_id": "kb2",
                            "vector_db_id": "vs-002",
                            "db_path": str(db_file2),
                            "score_multiplier": 0.75,
                        },
                    ],
                },
            },
        }
    )
    assert cfg.score_multiplier_mapping == {"vs-001": 1.5, "vs-002": 0.75}


def test_score_multiplier_mapping_not_loaded() -> None:
    """Test that score_multiplier_mapping raises when config not loaded."""
    cfg = AppConfig()
    cfg._configuration = None
    with pytest.raises(LogicError):
        _ = cfg.score_multiplier_mapping


wrong_configurations = [
    {
        "name": "Colin Adams",
        "service": {
            "host": "Serve control majority quite approach step.",
            "port": 378,
            "base_url": "Or blood represent beat.",
            "auth_enabled": False,
            "workers": 896,
            "color_log": True,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": None,
                "tls_key_path": None,
                "tls_key_password": None,
            },
            "root_path": "Word especially structure.",
            "cors": {
                "allow_origins": [
                    "Last drop work less really sister.",
                    "Body light risk edge.",
                ],
                "allow_credentials": True,
                "allow_methods": ["Great teach very staff."],
                "allow_headers": [
                    "Avoid eye space tree minute.",
                    "Wall they realize. Data teach which seek policy ri",
                    "New week public how. Room of line good fire leave.",
                ],
            },
        },
        "llama_stack": {
            "url": "https://www.west.com/",
            "api_key": "api_key",
            "use_as_library_client": False,
            "library_client_config_path": "Strategy stand return catch range professor.",
            "timeout": 486,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": None,
            "transcripts_enabled": True,
            "transcripts_storage": "Must risk kid just.",
        },
        "database": {
            "sqlite": {"db_path": "Shake stuff particularly move. Military center sug"},
            "postgres": {
                "host": "Rock either measure leg carry.",
                "port": 91,
                "db": "Institution.",
                "user": "Action production item hour option reflect.",
                "password": "3+37w9K!#3Bk",
                "namespace": None,
                "ssl_mode": "Seek very sell whom. Order dog ready away.",
                "gss_encmode": "A pressure leave but past drive some.",
                "ca_cert_path": None,
            },
        },
        "mcp_servers": [
            {
                "name": "Sherry Greene",
                "provider_id": "Stage tell north despite tell. Such institution ra",
                "url": "https://wilkins.net/",
                "authorization_headers": {
                    "their": "Size right huge both wall financial."
                },
                "headers": [
                    "Throughout speak next.",
                    "Least may discuss name. Whatever bad take.",
                ],
                "timeout": "10",
            },
            {
                "name": "Christopher Cain",
                "provider_id": "Hair raise risk career traditional.",
                "url": "https://cruz.com/",
                "authorization_headers": {
                    "surface": "Whose over special suddenly why. Candidate nearly ",
                    "general": "Others effort analysis significant car maintain.",
                    "return": "Wide enter ago name vote.",
                },
                "headers": ["Him keep finally."],
                "timeout": "10",
            },
            {
                "name": "Eric Martin",
                "provider_id": "Food assume per stop fear lay.",
                "url": "https://solis-porter.com/",
                "authorization_headers": {
                    "us": "Wall building officer father success.",
                    "PM": "Medical perhaps him impact affect.",
                },
                "headers": [
                    "Test owner too side.",
                    "Girl year process team.",
                    "Able computer anyone keep must back finish century",
                ],
                "timeout": "10",
            },
        ],
        "authentication": {
            "module": "Fast learn describe.",
            "skip_tls_verification": True,
            "skip_for_health_probes": False,
            "skip_for_metrics": True,
            "k8s_cluster_api": "http://1.2.3.4",
            "k8s_ca_cert_path": None,
            "jwk_config": None,
            "api_key_config": {"api_key": "key"},
            "rh_identity_config": None,
        },
        "authorization": None,
        "customization": None,
        "inference": {
            "default_model": "Exist important land left peace.",
            "default_provider": "Much us fight suggest.",
        },
        "conversation_cache": {
            "type": None,
            "memory": {"max_entries": 447},
            "sqlite": None,
            "postgres": {
                "host": "View price final number individual. Under directio",
                "port": 343,
                "db": "Quickly lay health stock whose gas born.",
                "user": "From bill attack none.",
                "password": "#4$uLlS2CNSP",
                "namespace": "Task to including nice author.",
                "ssl_mode": "His yard question issue attorney.",
                "gss_encmode": "Decision ability else base pay.",
                "ca_cert_path": "file",
            },
        },
        "a2a_state": {"sqlite": None, "postgres": None},
        "quota_handlers": {
            "sqlite": {"db_path": "Experience five able citizen work member call cond"},
            "postgres": {
                "host": "Name garden ready finally century.",
                "port": 722,
                "db": "Fire into list can or.",
                "user": "Collection scientist evening consumer suddenly fac",
                "password": "&#drK6YgvGNh",
                "namespace": "Technology chance quality parent.",
                "ssl_mode": "Simple safe ten general along pull.",
                "gss_encmode": "Listen population.",
                "ca_cert_path": None,
            },
            "limiters": [
                {
                    "type": "user_limiter",
                    "name": "Katelyn Everett",
                    "initial_quota": 651,
                    "quota_increase": 427,
                    "period": "Coach develop ever happen.",
                },
                {
                    "type": "user_limiter",
                    "name": "Alec Sullivan",
                    "initial_quota": 819,
                    "quota_increase": 13,
                    "period": "Enough table best. Work final imagine learn tax su",
                },
            ],
            "scheduler": {
                "period": 415,
                "database_reconnection_count": 545,
                "database_reconnection_delay": 150,
            },
            "enable_token_history": True,
        },
        "azure_entra_id": {
            "tenant_id": "tenant_id",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scope": "Because its own above.",
        },
        "rlsapi_v1": {
            "allow_verbose_infer": False,
            "quota_subject": "user_id",
        },
        "splunk": {
            "enabled": False,
            "url": "https://cordova-moss.net/",
            "token_path": None,
            "index": "Company but couple or.",
            "source": "Page cell data mission you player. Leg development",
            "timeout": 187,
            "verify_ssl": False,
        },
        "deployment_environment": "Second say body know music while.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Weight message strong wind land bar.",
                        "backend": "Learn person tell increase dog even.",
                        "embedding_model": "By our television. Southern full a course.",
                        "embedding_dimension": 753,
                        "vector_db_id": "Indicate see door specific hard region one.",
                        "db_path": "A none owner visit wish medical cut Mrs. Later nig",
                        "score_multiplier": 388.45,
                    }
                ],
            },
            "okp": {
                "rhokp_url": None,
                "offline": True,
                "chunk_filter_query": "Foreign space system.",
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Local authority pressure pretty. Travel something ",
                        "Watch meet able such.",
                        "Different apply size.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Full develop under his.",
                        "Black political father project become.",
                        "Once however son place.",
                    ],
                },
            },
        },
    },
    {
        "name": "Nathaniel Williams",
        "service": {
            "host": "Response although crime less.",
            "port": 275,
            "base_url": None,
            "auth_enabled": False,
            "workers": 218,
            "color_log": False,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": None,
                "tls_key_path": None,
                "tls_key_password": "password",
            },
            "root_path": "Model something information strong focus.",
            "cors": {
                "allow_origins": [
                    "Clear yes hand language.",
                    "Expect will research bag. Standard exist property ",
                    "Cultural their pass explain.",
                ],
                "allow_credentials": False,
                "allow_methods": [
                    "Wind hit work arm man.",
                    "Cost food serve national education. Painting wide ",
                ],
                "allow_headers": ["At professor seek hospital eat."],
            },
        },
        "llama_stack": {
            "url": None,
            "api_key": None,
            "use_as_library_client": None,
            "library_client_config_path": None,
            "timeout": 890,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": "Travel consider themselves trouble there budget.",
            "transcripts_enabled": True,
            "transcripts_storage": None,
        },
        "database": {
            "sqlite": {"db_path": "Will yet other need."},
            "postgres": {
                "host": "Bar various source each.",
                "port": 236,
                "db": "Positive federal organization between knowledge so",
                "user": "Score girl far party example care leave.",
                "password": "mOW_ES5n7TB6",
                "namespace": "If act test financial.",
                "ssl_mode": "Whether bad still use.",
                "gss_encmode": "Easy agreement authority again rest.",
                "ca_cert_path": None,
            },
        },
        "mcp_servers": [
            {
                "name": "William Roberts",
                "provider_id": "Represent surface stuff.",
                "url": "https://www.rodriguez-cross.com/",
                "authorization_headers": {
                    "a": "Technology sure event third go for institution mon",
                    "yourself": "Physical will coach.",
                    "size": "Start wife body.",
                },
                "headers": [
                    "Be recognize civil.",
                    "Senior system give.",
                    "Son often them resource her star thus.",
                ],
                "timeout": None,
            },
            {
                "name": "William Maldonado",
                "provider_id": "Yet our town hope.",
                "url": "https://collins.com/",
                "authorization_headers": {
                    "then": "Water we provide those leader less chance.",
                    "whom": "Theory single common sing what for.",
                    "manage": "Keep thousand ground.",
                },
                "headers": [
                    "Those manage area light. Large authority lawyer le",
                    "Bed speech adult imagine office.",
                    "Decide analysis.",
                ],
                "timeout": "-10",
            },
            {
                "name": "Ashley Walker",
                "provider_id": "Case film eight early.",
                "url": "https://www.davis-wilson.net/",
                "authorization_headers": {
                    "amount": "Customer religious let ever.",
                    "deep": "Nothing indeed but argue single.",
                },
                "headers": ["Call street easy lawyer quite enjoy once task. Mil"],
                "timeout": "-10",
            },
        ],
        "authentication": {
            "module": "Arrive blue lose rock.",
            "skip_tls_verification": False,
            "skip_for_health_probes": True,
            "skip_for_metrics": False,
            "k8s_cluster_api": None,
            "k8s_ca_cert_path": None,
            "jwk_config": {
                "url": "https://davis.org/",
                "jwt_configuration": {
                    "user_id_claim": "Reason million financial raise environmental.",
                    "username_claim": "Wonder activity yes.",
                    "role_rules": [
                        {
                            "jsonpath": "Social bank buy.",
                            "operator": "-10",
                            "negate": True,
                            "value": "any_value_placeholder",
                            "roles": ["Part house prevent story."],
                        },
                        {
                            "jsonpath": "Outside how note when. Mr entire affect usually.",
                            "operator": "-10",
                            "negate": False,
                            "value": "any_value_placeholder",
                            "roles": [
                                "Store child serious.",
                                "Song plant sense technology though consider. Paren",
                            ],
                        },
                        {
                            "jsonpath": "Family light power color number. Treat court stuff",
                            "operator": "-10",
                            "negate": False,
                            "value": "any_value_placeholder",
                            "roles": [
                                "Television set over offer task north card those."
                            ],
                        },
                    ],
                },
            },
            "api_key_config": None,
            "rh_identity_config": None,
        },
        "authorization": {
            "access_rules": [
                {"role": "Perhaps idea nothing attorney word.", "actions": ["action1"]},
                {
                    "role": "Somebody operation involve alone. Born example sea",
                    "actions": ["action1", "action2"],
                },
                {
                    "role": "Watch most resource word information allow ability",
                    "actions": ["action1"],
                },
            ]
        },
        "customization": {
            "profile_path": None,
            "disable_query_system_prompt": False,
            "disable_shield_ids_override": True,
            "system_prompt_path": "/",
            "system_prompt": None,
            "agent_card_path": "/",
            "agent_card_config": None,
            "custom_profile": "/",
        },
        "inference": {
            "default_model": "Fill popular near avoid family year.",
            "default_provider": "Pressure former operation table start president.",
        },
        "conversation_cache": {
            "type": "noop",
            "memory": None,
            "sqlite": {"db_path": "Own relationship back production."},
            "postgres": {
                "host": "Religious author little. Thought bring agency rais",
                "port": 146,
                "db": "Other safe resource stop.",
                "user": "Concern center once music activity bad thousand.",
                "password": "zHDCzco5^S2Z",
                "namespace": None,
                "ssl_mode": "Run claim process large.",
                "gss_encmode": "Tv east art pattern.",
                "ca_cert_path": "certs",
            },
        },
        "a2a_state": {"sqlite": None, "postgres": None},
        "quota_handlers": {
            "sqlite": None,
            "postgres": {
                "host": "List fund yes kitchen meet southern.",
                "port": 337,
                "db": "Five rest behavior tonight couple.",
                "user": "Message accept whom authority.",
                "password": "B28qYhFt$nnI",
                "namespace": None,
                "ssl_mode": "Teach wide worry tend.",
                "gss_encmode": "Example weight window.",
                "ca_cert_path": "/",
            },
            "limiters": [
                {
                    "type": "user_limiter",
                    "name": "Michael Jackson",
                    "initial_quota": 371,
                    "quota_increase": 210,
                    "period": "Start skill miss economy know.",
                },
                {
                    "type": "user_limiter",
                    "name": "Richard Moore",
                    "initial_quota": 189,
                    "quota_increase": 83,
                    "period": "Another maybe certainly week trouble.",
                },
                {
                    "type": "user_limiter",
                    "name": "Charlene Perez",
                    "initial_quota": 387,
                    "quota_increase": 8,
                    "period": "Music difficult enough.",
                },
            ],
            "scheduler": {
                "period": 825,
                "database_reconnection_count": 896,
                "database_reconnection_delay": 669,
            },
            "enable_token_history": False,
        },
        "azure_entra_id": {
            "tenant_id": "id",
            "client_id": "id",
            "client_secret": "secrer",
            "scope": "Claim thought seat use.",
        },
        "rlsapi_v1": {"allow_verbose_infer": False, "quota_subject": None},
        "splunk": {
            "enabled": True,
            "url": "https://george-ferguson.org/",
            "token_path": "/",
            "index": None,
            "source": "Successful impact understand least generation cust",
            "timeout": 850,
            "verify_ssl": False,
        },
        "deployment_environment": "Vote mean answer simply turn project.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Tonight relate there record.",
                        "backend": "Politics development real play main chair capital ",
                        "embedding_model": "Prepare memory outside.",
                        "embedding_dimension": 449,
                        "vector_db_id": "Political right gun law public group rock.",
                        "db_path": "Consider still recognize church. Area suggest noth",
                        "score_multiplier": 183.85,
                    },
                    {
                        "rag_id": "One again under respond poor beyond.",
                        "backend": "Six base physical.",
                        "embedding_model": "Surface that choice.",
                        "embedding_dimension": 736,
                        "vector_db_id": "Forget level other agreement.",
                        "db_path": "Argue pull out race town.",
                        "score_multiplier": 225.21,
                    },
                ],
            },
            "okp": {
                "rhokp_url": None,
                "offline": False,
                "chunk_filter_query": None,
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Billion job provide take other.",
                        "Eight total figure surface development include out",
                        "Which from cover not choice bring sister front.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Ground appear group institution.",
                    ],
                },
            },
        },
    },
    {
        "name": "Patricia Henderson",
        "service": {
            "host": "High politics role market party factor yourself. H",
            "port": 65,
            "base_url": "Song list by notice decide politics.",
            "auth_enabled": True,
            "workers": 248,
            "color_log": True,
            "access_log": False,
            "tls_config": {
                "tls_certificate_path": None,
                "tls_key_path": None,
                "tls_key_password": "xyzzy",
            },
            "root_path": "Another budget miss with my pretty.",
            "cors": {
                "allow_origins": ["Edge yes right already."],
                "allow_credentials": True,
                "allow_methods": ["Include game information. Become mother today."],
                "allow_headers": [
                    "Recent crime seem ten.",
                    "Yeah fear design few.",
                    "Information story.",
                ],
            },
        },
        "llama_stack": {
            "url": "http://www.cameron.com/",
            "api_key": "xyzzy",
            "use_as_library_client": False,
            "library_client_config_path": "Write past admit hand area surface.",
            "timeout": 237,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": "Poor have happen.",
            "transcripts_enabled": True,
            "transcripts_storage": "Ask sport choice along. Ever concern table traditi",
        },
        "database": {"sqlite": None, "postgres": None},
        "mcp_servers": [
            {
                "name": "Colleen Villanueva",
                "provider_id": "Every present recently.",
                "url": "https://www.taylor.com/",
                "authorization_headers": {
                    "four": "Have camera third when across too.",
                    "dinner": "Field run hair.",
                    "machine": "Time find prove war.",
                },
                "headers": [
                    "Author heavy now start allow focus.",
                    "Eat before by.",
                    "Serious best talk never.",
                ],
                "timeout": None,
            }
        ],
        "authentication": {
            "module": "Offer to trouble off chance personal.",
            "skip_tls_verification": False,
            "skip_for_health_probes": False,
            "skip_for_metrics": True,
            "k8s_cluster_api": None,
            "k8s_ca_cert_path": "xyzzy",
            "jwk_config": None,
            "api_key_config": None,
            "rh_identity_config": None,
        },
        "authorization": {
            "access_rules": [
                {
                    "role": "Nothing development house computer.",
                    "actions": ["xyzzy", "xyzzy", "xyzzy"],
                },
                {
                    "role": "Sea coach without wide audience pretty fine.",
                    "actions": ["xyzzy", "xyzzy"],
                },
                {
                    "role": "Will Congress style picture deal. Explain set assu",
                    "actions": ["xyzzy"],
                },
            ]
        },
        "customization": {
            "profile_path": None,
            "disable_query_system_prompt": False,
            "disable_shield_ids_override": False,
            "system_prompt_path": "xyzzy",
            "system_prompt": None,
            "agent_card_path": "xyzzy",
            "agent_card_config": None,
            "custom_profile": None,
        },
        "inference": {
            "default_model": "Television someone about wall join.",
            "default_provider": None,
        },
        "conversation_cache": {
            "type": None,
            "memory": None,
            "sqlite": None,
            "postgres": None,
        },
        "a2a_state": {"sqlite": None, "postgres": None},
        "quota_handlers": {
            "sqlite": None,
            "postgres": None,
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Jerry Brown",
                    "initial_quota": 532,
                    "quota_increase": 509,
                    "period": "After determine almost make yeah support. Away tak",
                },
                {
                    "type": "xyzzy",
                    "name": "James Martin",
                    "initial_quota": 167,
                    "quota_increase": 278,
                    "period": "Book gas exist these.",
                },
                {
                    "type": "xyzzy",
                    "name": "Mr. Douglas Kelly DDS",
                    "initial_quota": 210,
                    "quota_increase": 930,
                    "period": "Section many southern new.",
                },
            ],
            "scheduler": {
                "period": 984,
                "database_reconnection_count": 118,
                "database_reconnection_delay": 961,
            },
            "enable_token_history": False,
        },
        "azure_entra_id": {
            "tenant_id": "xyzzy",
            "client_id": "xyzzy",
            "client_secret": "xyzzy",
            "scope": "Spring billion represent town actually serious mor",
        },
        "rlsapi_v1": {"allow_verbose_infer": False, "quota_subject": "xyzzy"},
        "splunk": {
            "enabled": False,
            "url": "http://www.bell.com/",
            "token_path": "xyzzy",
            "index": None,
            "source": "Risk condition boy conference particularly control",
            "timeout": 398,
            "verify_ssl": False,
        },
        "deployment_environment": "Mouth view form.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Something worker campaign war through.",
                        "backend": "Check simple since next then statement.",
                        "embedding_model": "Class third author series.",
                        "embedding_dimension": 211,
                        "vector_db_id": "Less put site alone amount.",
                        "db_path": "Live child most throughout.",
                        "score_multiplier": 252.41,
                    }
                ],
            },
            "okp": {
                "rhokp_url": "xyzzy",
                "offline": False,
                "chunk_filter_query": "Beautiful society within.",
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Interesting during product himself attack Democrat",
                        "Decision I order particularly.",
                        "Couple reflect relate two agree local.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Her society move lay.",
                        "Network material like.",
                    ],
                },
            },
        },
    },
    {
        "name": "Sheila Cabrera",
        "service": {
            "host": "Woman price everyone bed ask.",
            "port": 1,
            "base_url": None,
            "auth_enabled": False,
            "workers": 897,
            "color_log": False,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": "xyzzy",
                "tls_key_path": "xyzzy",
                "tls_key_password": None,
            },
            "root_path": "Spring break along appear court ground table.",
            "cors": {
                "allow_origins": ["However Democrat at. Safe modern nothing this smil"],
                "allow_credentials": False,
                "allow_methods": [
                    "Tell bit appear.",
                    "Phone right page oil pass weight final.",
                    "Go hand service. Knowledge close west part.",
                ],
                "allow_headers": ["Experience east herself outside."],
            },
        },
        "llama_stack": {
            "url": "https://www.savage.com/",
            "api_key": "xyzzy",
            "use_as_library_client": False,
            "library_client_config_path": None,
            "timeout": 117,
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": None,
            "transcripts_enabled": True,
            "transcripts_storage": "Despite different develop traditional member out.",
        },
        "database": {"sqlite": None, "postgres": None},
        "mcp_servers": [
            {
                "name": "Jorge Hanson",
                "provider_id": "A young travel center item I above.",
                "url": "https://tran.com/",
                "authorization_headers": {
                    "while": "Figure rock certain law.",
                    "cultural": "Opportunity leader open until improve turn.",
                    "already": "Today happy book along member born. Woman yard sin",
                },
                "headers": ["Short green whatever season."],
                "timeout": None,
            }
        ],
        "authentication": {
            "module": "Able tax east short town ball past.",
            "skip_tls_verification": True,
            "skip_for_health_probes": False,
            "skip_for_metrics": False,
            "k8s_cluster_api": None,
            "k8s_ca_cert_path": "xyzzy",
            "jwk_config": {
                "url": "https://www.craig.biz/",
                "jwt_configuration": {
                    "user_id_claim": "Matter far chance approach citizen strategy.",
                    "username_claim": "Again design gun break future oil.",
                    "role_rules": [
                        {
                            "jsonpath": "Result street yourself allow five.",
                            "operator": "xyzzy",
                            "negate": False,
                            "value": "any_value_placeholder",
                            "roles": [
                                "Into bad arm indicate simply world.",
                                "Without together determine student True use base.",
                            ],
                        },
                        {
                            "jsonpath": "Growth police position.",
                            "operator": "xyzzy",
                            "negate": True,
                            "value": "any_value_placeholder",
                            "roles": ["Simply smile war article attorney."],
                        },
                    ],
                },
            },
            "api_key_config": None,
            "rh_identity_config": None,
        },
        "authorization": None,
        "customization": {
            "profile_path": None,
            "disable_query_system_prompt": True,
            "disable_shield_ids_override": True,
            "system_prompt_path": "xyzzy",
            "system_prompt": "Join music develop let.",
            "agent_card_path": None,
            "agent_card_config": {
                "him": "any_value_placeholder",
                "section": "any_value_placeholder",
            },
            "custom_profile": None,
        },
        "inference": {
            "default_model": "Happy share answer ready money.",
            "default_provider": "Relate do leader. More attention article our.",
        },
        "conversation_cache": {
            "type": "xyzzy",
            "memory": {"max_entries": 648},
            "sqlite": {"db_path": "Any discover sign music. Value north success growt"},
            "postgres": {
                "host": "Piece week health occur onto bar.",
                "port": 356,
                "db": "Recently decision cut treatment message push read.",
                "user": "Business election man treatment. Physical what ins",
                "password": "B8svtzzW(szI",
                "namespace": "Own book possible walk.",
                "ssl_mode": "With station plant region political too nothing.",
                "gss_encmode": "Assume they so city.",
                "ca_cert_path": None,
            },
        },
        "a2a_state": {
            "sqlite": {"db_path": "Write herself each generation finally attorney."},
            "postgres": None,
        },
        "quota_handlers": {
            "sqlite": {"db_path": "Around paper step read."},
            "postgres": {
                "host": "By cell color state arrive.",
                "port": 803,
                "db": "This whatever time require eye.",
                "user": "Term fund me not. Southern until also.",
                "password": "#ooW^bFTB$a1",
                "namespace": None,
                "ssl_mode": "Story may pressure.",
                "gss_encmode": "Already but brother.",
                "ca_cert_path": "xyzzy",
            },
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Kathleen Livingston",
                    "initial_quota": 953,
                    "quota_increase": 640,
                    "period": "World enough bad agent.",
                },
                {
                    "type": "xyzzy",
                    "name": "Ana Williams",
                    "initial_quota": 567,
                    "quota_increase": 124,
                    "period": "Car traditional present. Traditional usually raise",
                },
            ],
            "scheduler": {
                "period": 265,
                "database_reconnection_count": 535,
                "database_reconnection_delay": 430,
            },
            "enable_token_history": True,
        },
        "azure_entra_id": {
            "tenant_id": "xyzzy",
            "client_id": "xyzzy",
            "client_secret": "xyzzy",
            "scope": "Hair social blood dream Mr.",
        },
        "rlsapi_v1": {"allow_verbose_infer": True, "quota_subject": "xyzzy"},
        "splunk": {
            "enabled": True,
            "url": "https://taylor.org/",
            "token_path": "xyzzy",
            "index": None,
            "source": "Probably small develop admit ever. Lot four method",
            "timeout": 283,
            "verify_ssl": False,
        },
        "deployment_environment": "Want hair product.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Ever analysis three perhaps.",
                        "backend": "Ever truth skin.",
                        "embedding_model": "Type toward never hair relate before.",
                        "embedding_dimension": 619,
                        "vector_db_id": "Learn computer positive nor yet notice.",
                        "db_path": "Sort rule soldier relationship. Wife front kid cit",
                        "score_multiplier": 310.63,
                    },
                    {
                        "rag_id": "Question to front often.",
                        "backend": "But catch hear happy.",
                        "embedding_model": "Hard message wait least focus left daughter reflec",
                        "embedding_dimension": 97,
                        "vector_db_id": "Create visit green. Throw more tend throw game.",
                        "db_path": "Rest could recent test door.",
                        "score_multiplier": 224.06,
                    },
                    {
                        "rag_id": "Read hand over fight president feel letter. Over h",
                        "backend": "Set visit describe seat space play.",
                        "embedding_model": "Lawyer early term direction.",
                        "embedding_dimension": 119,
                        "vector_db_id": "Day store girl writer have would participant.",
                        "db_path": "Later research explain first lose probably.",
                        "score_multiplier": 627.97,
                    },
                ],
            },
            "okp": {
                "rhokp_url": "xyzzy",
                "offline": False,
                "chunk_filter_query": "Industry as appear us. Lead dream public compare.",
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Himself fear read here finally ask teacher.",
                        "Enjoy standard off.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Them author financial production.",
                    ],
                },
            },
        },
    },
    {
        "name": "Marisa Johnson",
        "service": {
            "host": "Service visit sort name. Democratic increase desig",
            "port": 260,
            "base_url": "Deal level four maintain yeah arrive.",
            "auth_enabled": False,
            "workers": 448,
            "color_log": True,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": None,
                "tls_key_path": "xyzzy",
                "tls_key_password": None,
            },
            "root_path": "War under seem wide itself present.",
            "cors": {
                "allow_origins": ["However performance serve city close season."],
                "allow_credentials": True,
                "allow_methods": ["Official send ground.", "She sort drug heavy."],
                "allow_headers": [
                    "Vote already window four still talk among lawyer.",
                    "Fly fact then five.",
                    "Bad factor she sort.",
                ],
            },
        },
        "llama_stack": {
            "url": None,
            "api_key": "xyzzy",
            "use_as_library_client": True,
            "library_client_config_path": "Spend difficult identify go.",
            "timeout": 689,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": "Seem have part movie.",
            "transcripts_enabled": True,
            "transcripts_storage": None,
        },
        "database": {
            "sqlite": {"db_path": "Book arrive hair seat popular."},
            "postgres": None,
        },
        "mcp_servers": [
            {
                "name": "Pamela Frazier",
                "provider_id": "Policy kind among effort.",
                "url": "https://www.austin-richards.biz/",
                "authorization_headers": {
                    "indeed": "Design kid official along lead nice trial.",
                    "spend": "Yourself sit continue.",
                },
                "headers": [
                    "Official end industry challenge system these cell.",
                    "Others cultural notice friend. Number air you insi",
                    "Nothing argue use like game.",
                ],
                "timeout": None,
            },
            {
                "name": "James Chavez",
                "provider_id": "May smile develop TV. Trouble child piece same.",
                "url": "https://www.harper.com/",
                "authorization_headers": {"month": "Himself coach letter recently."},
                "headers": ["Ago around car after too.", "Lawyer foot media standard."],
                "timeout": "xyzzy",
            },
        ],
        "authentication": {
            "module": "May American industry available. Language off word",
            "skip_tls_verification": False,
            "skip_for_health_probes": True,
            "skip_for_metrics": True,
            "k8s_cluster_api": "xyzzy",
            "k8s_ca_cert_path": None,
            "jwk_config": None,
            "api_key_config": None,
            "rh_identity_config": None,
        },
        "authorization": {
            "access_rules": [
                {
                    "role": "Oil add these though. Plan nothing dark.",
                    "actions": ["xyzzy", "xyzzy"],
                },
                {
                    "role": "Sister where owner west policy stop entire. From t",
                    "actions": ["xyzzy", "xyzzy"],
                },
            ]
        },
        "customization": {
            "profile_path": None,
            "disable_query_system_prompt": False,
            "disable_shield_ids_override": False,
            "system_prompt_path": "xyzzy",
            "system_prompt": None,
            "agent_card_path": "xyzzy",
            "agent_card_config": None,
            "custom_profile": None,
        },
        "inference": {
            "default_model": "Continue try science sense rich name.",
            "default_provider": "Report whether hear chair.",
        },
        "conversation_cache": {
            "type": "xyzzy",
            "memory": {"max_entries": 666},
            "sqlite": {"db_path": "Court size your eye choose."},
            "postgres": None,
        },
        "a2a_state": {
            "sqlite": {"db_path": "Green example walk become return front."},
            "postgres": {
                "host": "Culture stop finally break.",
                "port": 854,
                "db": "Like direction music.",
                "user": "Newspaper compare color indicate lay.",
                "password": "(5BuFj&vKMmV",
                "namespace": "Summer risk where attention music mean recently.",
                "ssl_mode": "Local run already walk. Manager contain eight rais",
                "gss_encmode": "Economy picture long level seek. Learn hair foreig",
                "ca_cert_path": "xyzzy",
            },
        },
        "quota_handlers": {
            "sqlite": {"db_path": "Good score hospital create son."},
            "postgres": None,
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Matthew Saunders",
                    "initial_quota": 987,
                    "quota_increase": 279,
                    "period": "Pass style back item.",
                }
            ],
            "scheduler": {
                "period": 288,
                "database_reconnection_count": 475,
                "database_reconnection_delay": 526,
            },
            "enable_token_history": False,
        },
        "azure_entra_id": {
            "tenant_id": "xyzzy",
            "client_id": "xyzzy",
            "client_secret": "xyzzy",
            "scope": "Clearly fact general study.",
        },
        "rlsapi_v1": {"allow_verbose_infer": True, "quota_subject": "xyzzy"},
        "splunk": {
            "enabled": True,
            "url": None,
            "token_path": None,
            "index": "Ok them various ok sit board.",
            "source": "Interest degree foreign already.",
            "timeout": 948,
            "verify_ssl": False,
        },
        "deployment_environment": "Consumer center sign skin total.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Authority kind apply arm manager local reveal.",
                        "backend": "Seem authority miss.",
                        "embedding_model": "Have news quality.",
                        "embedding_dimension": 310,
                        "vector_db_id": "Education hot full her. Serve mention save executi",
                        "db_path": "Every popular bit.",
                        "score_multiplier": 918.43,
                    },
                    {
                        "rag_id": "Avoid baby miss want education.",
                        "backend": "Sing answer rule soon.",
                        "embedding_model": "Year let example you paper develop tough.",
                        "embedding_dimension": 985,
                        "vector_db_id": "Operation conference phone.",
                        "db_path": "All effort True see.",
                        "score_multiplier": 788.57,
                    },
                ],
            },
            "okp": {
                "rhokp_url": None,
                "offline": True,
                "chunk_filter_query": "And drug brother tell specific realize hit.",
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "True four lawyer sound. Light fund former art.",
                        "Perhaps theory remain. Marriage person put food.",
                        "Run behind single material else media.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Another Congress part seat bit.",
                        "Able main door under. Early consumer speech less c",
                        "Eat read shake three. Development cell mission.",
                    ],
                },
            },
        },
    },
    {
        "name": "Sarah Austin",
        "service": {
            "host": "Our marriage even information note allow.",
            "port": 57,
            "base_url": "Must ok worker plan.",
            "auth_enabled": True,
            "workers": 310,
            "color_log": True,
            "access_log": False,
            "tls_config": {
                "tls_certificate_path": "xyzzy",
                "tls_key_path": None,
                "tls_key_password": None,
            },
            "root_path": "Decade send whether trial various.",
            "cors": {
                "allow_origins": [
                    "Service effort water small individual.",
                    "Level call family yeah.",
                ],
                "allow_credentials": True,
                "allow_methods": [
                    "Read here only.",
                    "Effect work professor. Guess about expect consumer",
                ],
                "allow_headers": [
                    "Wish follow administration manage structure democr",
                    "Sit imagine agree spend.",
                ],
            },
        },
        "llama_stack": {
            "url": None,
            "api_key": "xyzzy",
            "use_as_library_client": None,
            "library_client_config_path": None,
            "timeout": 182,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": "Media director fight with. Lay shake unit news.",
            "transcripts_enabled": True,
            "transcripts_storage": "Speech catch doctor organization.",
        },
        "database": {
            "sqlite": None,
            "postgres": {
                "host": "Beat move hospital same.",
                "port": 669,
                "db": "Could focus find reduce.",
                "user": "Interest while take. Doctor high example.",
                "password": "DEBi6$q4Q#!q",
                "namespace": "Speak family difference alone them ball.",
                "ssl_mode": "Group decision about.",
                "gss_encmode": "Her choice all.",
                "ca_cert_path": None,
            },
        },
        "mcp_servers": [
            {
                "name": "Anthony Brown",
                "provider_id": "Over main son rich drive wife couple.",
                "url": "http://newman.net/",
                "authorization_headers": {
                    "movie": "Future by season.",
                    "food": "Important tax compare parent top. Many point someb",
                },
                "headers": ["Center arrive grow day because customer."],
                "timeout": "xyzzy",
            },
            {
                "name": "Mike Orozco",
                "provider_id": "Song game interesting animal.",
                "url": "https://www.mason.info/",
                "authorization_headers": {
                    "adult": "Character account popular defense require.",
                    "medical": "Last federal buy word significant.",
                    "education": "Away try various long.",
                },
                "headers": [
                    "Mean several sell eye.",
                    "Catch similar exist. More mother dream involve beg",
                    "Top with provide movie rule two and draw.",
                ],
                "timeout": "xyzzy",
            },
        ],
        "authentication": {
            "module": "Chair difficult record safe find establish.",
            "skip_tls_verification": True,
            "skip_for_health_probes": True,
            "skip_for_metrics": False,
            "k8s_cluster_api": None,
            "k8s_ca_cert_path": "xyzzy",
            "jwk_config": {
                "url": "http://peterson.com/",
                "jwt_configuration": {
                    "user_id_claim": "That approach.",
                    "username_claim": "Too agent put truth then.",
                    "role_rules": [
                        {
                            "jsonpath": "Seven north system market.",
                            "operator": "xyzzy",
                            "negate": False,
                            "value": "any_value_placeholder",
                            "roles": ["Also try live serve create buy believe."],
                        },
                        {
                            "jsonpath": "Care audience our hear your media.",
                            "operator": "xyzzy",
                            "negate": False,
                            "value": "any_value_placeholder",
                            "roles": [
                                "Talk strategy interest instead them anyone wrong."
                            ],
                        },
                        {
                            "jsonpath": "Early art bank about senior leg possible.",
                            "operator": "xyzzy",
                            "negate": True,
                            "value": "any_value_placeholder",
                            "roles": [
                                "Water car guy even cultural threat.",
                                "State page adult spring. Over Mrs firm magazine.",
                                "Answer exist group cover measure various actually ",
                            ],
                        },
                    ],
                },
            },
            "api_key_config": None,
            "rh_identity_config": {
                "required_entitlements": None,
                "max_header_size": 729,
            },
        },
        "authorization": {
            "access_rules": [
                {
                    "role": "Owner bit mother federal something. Its memory sit",
                    "actions": ["xyzzy"],
                },
                {
                    "role": "Small pretty ok figure prepare describe see.",
                    "actions": ["xyzzy", "xyzzy"],
                },
            ]
        },
        "customization": {
            "profile_path": None,
            "disable_query_system_prompt": True,
            "disable_shield_ids_override": True,
            "system_prompt_path": None,
            "system_prompt": "Wonder wind often doctor.",
            "agent_card_path": "xyzzy",
            "agent_card_config": None,
            "custom_profile": None,
        },
        "inference": {
            "default_model": "Which stop task language.",
            "default_provider": None,
        },
        "conversation_cache": {
            "type": "xyzzy",
            "memory": {"max_entries": 332},
            "sqlite": None,
            "postgres": None,
        },
        "a2a_state": {
            "sqlite": None,
            "postgres": {
                "host": "Occur meet pay dog decade sense. Rule discover top",
                "port": 191,
                "db": "Whatever democratic unit class recent affect.",
                "user": "Worker feeling vote happen.",
                "password": "zu7HYMtol+#F",
                "namespace": None,
                "ssl_mode": "Just leader family.",
                "gss_encmode": "Billion suffer need parent her class.",
                "ca_cert_path": None,
            },
        },
        "quota_handlers": {
            "sqlite": {"db_path": "Subject culture laugh sea finish moment."},
            "postgres": None,
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "David Richardson",
                    "initial_quota": 470,
                    "quota_increase": 353,
                    "period": "Here onto which president today.",
                },
                {
                    "type": "xyzzy",
                    "name": "Daniel Young",
                    "initial_quota": 963,
                    "quota_increase": 566,
                    "period": "Nation nearly hold skin culture she.",
                },
            ],
            "scheduler": {
                "period": 817,
                "database_reconnection_count": 153,
                "database_reconnection_delay": 932,
            },
            "enable_token_history": True,
        },
        "azure_entra_id": {
            "tenant_id": "xyzzy",
            "client_id": "xyzzy",
            "client_secret": "xyzzy",
            "scope": "Make seven condition keep bag change ask.",
        },
        "rlsapi_v1": {"allow_verbose_infer": True, "quota_subject": None},
        "splunk": {
            "enabled": False,
            "url": "https://www.taylor-bartlett.com/",
            "token_path": "xyzzy",
            "index": None,
            "source": "Sure floor level.",
            "timeout": 393,
            "verify_ssl": True,
        },
        "deployment_environment": "Successful cut arrive ever against maybe.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Nor reduce physical section serious. She still rep",
                        "backend": "Hospital political recognize operation tree.",
                        "embedding_model": "Drug concern old job discover firm imagine.",
                        "embedding_dimension": 192,
                        "vector_db_id": "Relationship training argue body market old per.",
                        "db_path": "Consumer while positive. Why because quite respons",
                        "score_multiplier": 283.58,
                    },
                    {
                        "rag_id": "Past detail as star. Teacher spend sit push maybe ",
                        "backend": "After good nature. War option science approach.",
                        "embedding_model": "Air serve court measure most play item.",
                        "embedding_dimension": 491,
                        "vector_db_id": "Other open wonder.",
                        "db_path": "Car everybody during. Nor believe audience tax soo",
                        "score_multiplier": 159.31,
                    },
                    {
                        "rag_id": "Fire feeling person real party game method.",
                        "backend": "Middle together second money need fly.",
                        "embedding_model": "Do item when politics.",
                        "embedding_dimension": 896,
                        "vector_db_id": "Reason decision region past research.",
                        "db_path": "Every any nice vote civil.",
                        "score_multiplier": 776.23,
                    },
                ],
            },
            "okp": {
                "rhokp_url": "xyzzy",
                "offline": True,
                "chunk_filter_query": None,
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Themselves scene just.",
                        "Sport develop particular when. Task agreement walk",
                    ],
                },
                "tool": {
                    "sources": [
                        "Anything visit late.",
                    ],
                },
            },
        },
    },
    {
        "name": "Mr. Michael Wilson",
        "service": {
            "host": "Treat surface can cup green. Congress forward capi",
            "port": 450,
            "base_url": "Despite above may foot official first decision.",
            "auth_enabled": True,
            "workers": 2,
            "color_log": True,
            "access_log": False,
            "tls_config": {
                "tls_certificate_path": "xyzzy",
                "tls_key_path": None,
                "tls_key_password": "xyzzy",
            },
            "root_path": "Set step bill begin loss until store.",
            "cors": {
                "allow_origins": [
                    "When seat share nor. Accept could model add.",
                    "Time family their fund.",
                    "Toward happy class back.",
                ],
                "allow_credentials": False,
                "allow_methods": [
                    "Design account nature civil.",
                    "Fund budget population. Country staff vote cover o",
                    "Consumer young believe head song.",
                ],
                "allow_headers": [
                    "Affect sport require hotel draw song find.",
                    "Month one line Mr character student.",
                ],
            },
        },
        "llama_stack": {
            "url": "http://fowler-webb.com/",
            "api_key": "xyzzy",
            "use_as_library_client": None,
            "library_client_config_path": "To history chance benefit wall look budget might.",
            "timeout": 948,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": "Option like serious.",
            "transcripts_enabled": True,
            "transcripts_storage": "Democrat movement station rule past.",
        },
        "database": {"sqlite": None, "postgres": None},
        "mcp_servers": [
            {
                "name": "Larry Mason",
                "provider_id": "West result land much. Lose along staff author cho",
                "url": "http://www.castro-aguilar.com/",
                "authorization_headers": {
                    "section": "Instead plan light fund require majority.",
                    "discuss": "Bar the one.",
                    "bank": "Forward bring over end popular.",
                },
                "headers": [
                    "Use but study machine to must certainly.",
                    "How church truth life despite field.",
                    "Get Mrs young value sound on avoid. Law me green a",
                ],
                "timeout": None,
            },
            {
                "name": "Monica Brown",
                "provider_id": "Southern eight too tax.",
                "url": "http://www.page.com/",
                "authorization_headers": {"involve": "Wrong able nothing."},
                "headers": ["Hold know factor east."],
                "timeout": "xyzzy",
            },
            {
                "name": "Joseph Estrada",
                "provider_id": "Shoulder door realize.",
                "url": "https://chapman.com/",
                "authorization_headers": {
                    "around": "Recent lot explain film.",
                    "car": "Beyond matter woman exist. Help small future reduc",
                    "artist": "Wide safe message adult.",
                },
                "headers": [
                    "Song sure science strategy bring thus.",
                    "Election once part.",
                ],
                "timeout": "xyzzy",
            },
        ],
        "authentication": {
            "module": "Site of method money.",
            "skip_tls_verification": False,
            "skip_for_health_probes": True,
            "skip_for_metrics": True,
            "k8s_cluster_api": None,
            "k8s_ca_cert_path": None,
            "jwk_config": {
                "url": "http://www.parker.net/",
                "jwt_configuration": {
                    "user_id_claim": "Free old treat range remember democratic.",
                    "username_claim": "Ten mouth art newspaper.",
                    "role_rules": [
                        {
                            "jsonpath": "New note several. Any piece per.",
                            "operator": "xyzzy",
                            "negate": True,
                            "value": "any_value_placeholder",
                            "roles": ["Age official spend run soon hotel."],
                        }
                    ],
                },
            },
            "api_key_config": None,
            "rh_identity_config": {
                "required_entitlements": [
                    "Need man defense effort television market what.",
                    "Live century least light couple.",
                    "Leg forward analysis he everyone.",
                ],
                "max_header_size": 741,
            },
        },
        "authorization": None,
        "customization": None,
        "inference": {
            "default_model": None,
            "default_provider": "Unit guy agree reason.",
        },
        "conversation_cache": {
            "type": None,
            "memory": None,
            "sqlite": None,
            "postgres": None,
        },
        "a2a_state": {
            "sqlite": None,
            "postgres": {
                "host": "Certainly realize walk kind action.",
                "port": 756,
                "db": "Plant involve because break.",
                "user": "Spend medical report pull. Bank view word maybe.",
                "password": "U)W92To1*^FF",
                "namespace": "Important everyone one song.",
                "ssl_mode": "Same ground media those.",
                "gss_encmode": "Rather task week stage model.",
                "ca_cert_path": "xyzzy",
            },
        },
        "quota_handlers": {
            "sqlite": {"db_path": "Kind expect sell when."},
            "postgres": {
                "host": "Population plan short concern marriage.",
                "port": 218,
                "db": "Administration minute remember.",
                "user": "Including certainly city police.",
                "password": "lhxJKs_b%7$2",
                "namespace": None,
                "ssl_mode": "Ok continue newspaper talk.",
                "gss_encmode": "Nature certain that recent. Across we issue blue n",
                "ca_cert_path": "xyzzy",
            },
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Shelia Soto",
                    "initial_quota": 942,
                    "quota_increase": 622,
                    "period": "Page only recently range glass himself.",
                },
                {
                    "type": "xyzzy",
                    "name": "James Long",
                    "initial_quota": 196,
                    "quota_increase": 446,
                    "period": "Apply great whatever factor.",
                },
            ],
            "scheduler": {
                "period": 602,
                "database_reconnection_count": 33,
                "database_reconnection_delay": 816,
            },
            "enable_token_history": False,
        },
        "azure_entra_id": {
            "tenant_id": "xyzzy",
            "client_id": "xyzzy",
            "client_secret": "xyzzy",
            "scope": "Blue author defense. Such visit challenge all loss",
        },
        "rlsapi_v1": {"allow_verbose_infer": True, "quota_subject": None},
        "splunk": None,
        "deployment_environment": "Must no land member.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Sometimes once win young bar right. Star keep cult",
                        "backend": "Produce energy skill art.",
                        "embedding_model": "Beautiful series message.",
                        "embedding_dimension": 739,
                        "vector_db_id": "Visit night city.",
                        "db_path": "Paper investment game.",
                        "score_multiplier": 962.12,
                    },
                    {
                        "rag_id": "Standard might new national produce thank bill.",
                        "backend": "Bar else center dinner great. Wrong ability big.",
                        "embedding_model": "Building try left general.",
                        "embedding_dimension": 973,
                        "vector_db_id": "Issue never physical stuff edge fire research.",
                        "db_path": "Help hope our would discussion. Than plan task.",
                        "score_multiplier": 732.93,
                    },
                    {
                        "rag_id": "Air culture explain child.",
                        "backend": "Reach must moment.",
                        "embedding_model": "Manage anyone police someone church.",
                        "embedding_dimension": 691,
                        "vector_db_id": "Far tough individual painting send minute.",
                        "db_path": "Head major down soon.",
                        "score_multiplier": 485.53,
                    },
                ],
            },
            "okp": {
                "rhokp_url": None,
                "offline": False,
                "chunk_filter_query": None,
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Image police section carry. Order walk state commu",
                        "Society be night participant seat.",
                        "Minute skin again.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Use hotel often deal light teacher. Improve more m",
                    ],
                },
            },
        },
    },
    {
        "name": "Ruth Davidson",
        "service": {
            "host": "Owner key exist last.",
            "port": 606,
            "base_url": None,
            "auth_enabled": False,
            "workers": 350,
            "color_log": True,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": "xyzzy",
                "tls_key_path": None,
                "tls_key_password": "xyzzy",
            },
            "root_path": "Vote help need quickly.",
            "cors": {
                "allow_origins": [
                    "Already pressure through away.",
                    "Religious type list.",
                    "Fish floor glass land.",
                ],
                "allow_credentials": True,
                "allow_methods": ["Player project anyone century group save represent"],
                "allow_headers": [
                    "End chance last natural million.",
                    "Produce administration effort ask.",
                    "Whatever show material.",
                ],
            },
        },
        "llama_stack": {
            "url": None,
            "api_key": "xyzzy",
            "use_as_library_client": True,
            "library_client_config_path": None,
            "timeout": 520,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": None,
            "transcripts_enabled": True,
            "transcripts_storage": None,
        },
        "database": {
            "sqlite": {"db_path": "Pull owner night machine artist especially."},
            "postgres": {
                "host": "Run feel near matter sense. Just arm thought.",
                "port": 129,
                "db": "Girl number writer.",
                "user": "Back participant present prevent.",
                "password": "*iHe0lRhsA%G",
                "namespace": "Heavy industry sound than capital high.",
                "ssl_mode": "Left exist travel somebody four can policy candida",
                "gss_encmode": "Be machine buy guy we.",
                "ca_cert_path": None,
            },
        },
        "mcp_servers": [
            {
                "name": "Regina Trujillo",
                "provider_id": "Clear account voice rather if.",
                "url": "https://www.stanley.com/",
                "authorization_headers": {
                    "apply": "Accept practice great.",
                    "where": "Building suffer fear. Age True rule seat radio hus",
                },
                "headers": ["Audience age decide both."],
                "timeout": "xyzzy",
            },
            {
                "name": "Michele Forbes",
                "provider_id": "Scientist consider state side line.",
                "url": "http://smith.com/",
                "authorization_headers": {
                    "world": "Put final foreign air address each mission."
                },
                "headers": [
                    "Summer current close.",
                    "Must camera when most. Left water information four",
                    "Detail find bring lead change same simple.",
                ],
                "timeout": "xyzzy",
            },
        ],
        "authentication": {
            "module": "Per hope building others front between.",
            "skip_tls_verification": True,
            "skip_for_health_probes": True,
            "skip_for_metrics": True,
            "k8s_cluster_api": "xyzzy",
            "k8s_ca_cert_path": "xyzzy",
            "jwk_config": None,
            "api_key_config": {"api_key": "xyzzy"},
            "rh_identity_config": None,
        },
        "authorization": None,
        "customization": None,
        "inference": {
            "default_model": "Five age short.",
            "default_provider": "Ok administration cup film.",
        },
        "conversation_cache": {
            "type": "xyzzy",
            "memory": None,
            "sqlite": None,
            "postgres": {
                "host": "Deal raise everything.",
                "port": 193,
                "db": "Opportunity agency capital theory itself big case.",
                "user": "Value themselves color country. Newspaper meet buy",
                "password": "1oBsK^NVvDV*",
                "namespace": "Explain drop partner American director.",
                "ssl_mode": "Environment coach station.",
                "gss_encmode": "Manager from police player Democrat surface descri",
                "ca_cert_path": None,
            },
        },
        "a2a_state": {
            "sqlite": {"db_path": "Air pretty Democrat husband make travel statement."},
            "postgres": {
                "host": "Laugh community return education across join.",
                "port": 836,
                "db": "That cause old thing type customer scene.",
                "user": "Care bill paper almost if.",
                "password": "^y5jHqyZ6AhD",
                "namespace": None,
                "ssl_mode": "Third wish amount get full.",
                "gss_encmode": "Generation notice item order minute food seven roc",
                "ca_cert_path": None,
            },
        },
        "quota_handlers": {
            "sqlite": None,
            "postgres": None,
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Ashley Weaver",
                    "initial_quota": 998,
                    "quota_increase": 711,
                    "period": "Range trade what suddenly seek table million.",
                },
                {
                    "type": "xyzzy",
                    "name": "Angela Thompson",
                    "initial_quota": 187,
                    "quota_increase": 906,
                    "period": "Forget scientist address manage research probably.",
                },
            ],
            "scheduler": {
                "period": 431,
                "database_reconnection_count": 135,
                "database_reconnection_delay": 153,
            },
            "enable_token_history": False,
        },
        "azure_entra_id": None,
        "rlsapi_v1": {"allow_verbose_infer": True, "quota_subject": None},
        "splunk": None,
        "deployment_environment": "Second window action enter until very low provide.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Raise real rather walk product against.",
                        "backend": "Whose mind serve public character letter.",
                        "embedding_model": "Miss act loss camera.",
                        "embedding_dimension": 276,
                        "vector_db_id": "Return generation beat.",
                        "db_path": "Discover professional really group.",
                        "score_multiplier": 546.8,
                    },
                    {
                        "rag_id": "Those sit there reason.",
                        "backend": "Keep third nothing throw.",
                        "embedding_model": "Like movie lead since traditional for daughter. Re",
                        "embedding_dimension": 148,
                        "vector_db_id": "Sure statement only authority.",
                        "db_path": "Top social suggest she yourself heavy. Use low bud",
                        "score_multiplier": 623.44,
                    },
                    {
                        "rag_id": "Ability who manager several.",
                        "backend": "About ago spend poor event.",
                        "embedding_model": "Be energy lead.",
                        "embedding_dimension": 14,
                        "vector_db_id": "Region behind law affect note.",
                        "db_path": "View within able over sit. Part eat among appear.",
                        "score_multiplier": 306.05,
                    },
                ],
            },
            "okp": {
                "rhokp_url": "xyzzy",
                "offline": False,
                "chunk_filter_query": "Much when find smile try.",
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Consider once budget author trade federal.",
                        "Knowledge the option positive. Court its effect me",
                        "Add these care drive want and.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Guess know picture.",
                    ],
                },
            },
        },
    },
    {
        "name": "Thomas Werner",
        "service": {
            "host": "Pick response must why resource wish physical.",
            "port": 541,
            "base_url": "Job foot believe not.",
            "auth_enabled": False,
            "workers": 824,
            "color_log": False,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": "xyzzy",
                "tls_key_path": None,
                "tls_key_password": "xyzzy",
            },
            "root_path": "Car become want several share live. What film do q",
            "cors": {
                "allow_origins": [
                    "Size hear term writer.",
                    "Appear class professor trial father public.",
                    "Stock prepare themselves under see.",
                ],
                "allow_credentials": True,
                "allow_methods": [
                    "Drive generation save tough expert.",
                    "You gas bring character.",
                ],
                "allow_headers": ["Form figure letter far."],
            },
        },
        "llama_stack": {
            "url": "https://murphy-thomas.com/",
            "api_key": None,
            "use_as_library_client": False,
            "library_client_config_path": None,
            "timeout": 521,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": None,
            "transcripts_enabled": False,
            "transcripts_storage": "Measure stop in whole store our.",
        },
        "database": {
            "sqlite": {"db_path": "Hard much mind member career talk all effort."},
            "postgres": {
                "host": "Both positive True case.",
                "port": 241,
                "db": "Conference interest picture alone cultural agree e",
                "user": "Interesting president structure yet develop ready ",
                "password": "^jS4^DpZ^6KE",
                "namespace": None,
                "ssl_mode": "Feeling recognize seat often crime. People step he",
                "gss_encmode": "Mother finally among attorney citizen.",
                "ca_cert_path": "xyzzy",
            },
        },
        "mcp_servers": [
            {
                "name": "Alyssa Parks",
                "provider_id": "Turn listen feel send inside party.",
                "url": "https://martin-lee.com/",
                "authorization_headers": {"discuss": "Which fly instead picture."},
                "headers": [
                    "Small foot seven inside reality require bed.",
                    "Born yard religious focus effect.",
                ],
                "timeout": None,
            },
            {
                "name": "Jacob Miller",
                "provider_id": "Hair because culture foreign name crime.",
                "url": "http://www.brown.com/",
                "authorization_headers": {
                    "road": "Book kid vote catch change discussion word. Mother"
                },
                "headers": [
                    "Speech its right watch program.",
                    "Or water control some.",
                ],
                "timeout": "xyzzy",
            },
        ],
        "authentication": {
            "module": "College important personal draw pay room.",
            "skip_tls_verification": False,
            "skip_for_health_probes": True,
            "skip_for_metrics": False,
            "k8s_cluster_api": "xyzzy",
            "k8s_ca_cert_path": None,
            "jwk_config": None,
            "api_key_config": {"api_key": "xyzzy"},
            "rh_identity_config": {
                "required_entitlements": None,
                "max_header_size": 850,
            },
        },
        "authorization": None,
        "customization": {
            "profile_path": None,
            "disable_query_system_prompt": True,
            "disable_shield_ids_override": False,
            "system_prompt_path": "xyzzy",
            "system_prompt": None,
            "agent_card_path": "xyzzy",
            "agent_card_config": None,
            "custom_profile": "xyzzy",
        },
        "inference": {"default_model": None, "default_provider": None},
        "conversation_cache": {
            "type": "xyzzy",
            "memory": {"max_entries": 964},
            "sqlite": {"db_path": "Suggest gun standard fast note stay their."},
            "postgres": None,
        },
        "a2a_state": {"sqlite": None, "postgres": None},
        "quota_handlers": {
            "sqlite": {"db_path": "Suffer best free prove quickly to degree."},
            "postgres": None,
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Thomas Cross",
                    "initial_quota": 813,
                    "quota_increase": 472,
                    "period": "Per explain form sit morning.",
                },
                {
                    "type": "xyzzy",
                    "name": "Tamara Gregory",
                    "initial_quota": 666,
                    "quota_increase": 519,
                    "period": "Player wind eat during.",
                },
                {
                    "type": "xyzzy",
                    "name": "David Barton",
                    "initial_quota": 247,
                    "quota_increase": 590,
                    "period": "Around whole science.",
                },
            ],
            "scheduler": {
                "period": 733,
                "database_reconnection_count": 815,
                "database_reconnection_delay": 481,
            },
            "enable_token_history": False,
        },
        "azure_entra_id": None,
        "rlsapi_v1": {"allow_verbose_infer": True, "quota_subject": None},
        "splunk": {
            "enabled": False,
            "url": "https://harris.com/",
            "token_path": None,
            "index": "Read seem event.",
            "source": "Thus difficult including notice cover. Conference ",
            "timeout": 493,
            "verify_ssl": True,
        },
        "deployment_environment": "Maybe really go court.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Hope enough nature. Forward season agreement espec",
                        "backend": "Everyone finish task worry little we.",
                        "embedding_model": "Third choice enter blue baby behind its.",
                        "embedding_dimension": 514,
                        "vector_db_id": "Board how fight.",
                        "db_path": "Black can heavy write home.",
                        "score_multiplier": 817.0,
                    },
                    {
                        "rag_id": "Fish medical really owner different carry.",
                        "backend": "Order window meeting feel.",
                        "embedding_model": "Occur international consumer.",
                        "embedding_dimension": 912,
                        "vector_db_id": "Full tell us century development network scene spe",
                        "db_path": "Today boy kind key center Mr. Contain reduce coach",
                        "score_multiplier": 233.12,
                    },
                    {
                        "rag_id": "Note dog the audience work. We though name.",
                        "backend": "Bad career deep affect.",
                        "embedding_model": "Budget much see ask.",
                        "embedding_dimension": 939,
                        "vector_db_id": "South positive might film control peace seem.",
                        "db_path": "Go for can player camera.",
                        "score_multiplier": 268.06,
                    },
                ],
            },
            "okp": {
                "rhokp_url": "xyzzy",
                "offline": True,
                "chunk_filter_query": None,
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Without rock staff have campaign.",
                        "Particular her six.",
                        "These where I product.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Kind ability hope way.",
                        "Mean hot pressure onto purpose however.",
                    ],
                },
            },
        },
    },
    {
        "name": "William Riley",
        "service": {
            "host": "Guy perform turn hundred college sometimes.",
            "port": 976,
            "base_url": None,
            "auth_enabled": True,
            "workers": 264,
            "color_log": False,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": None,
                "tls_key_path": None,
                "tls_key_password": None,
            },
            "root_path": "Know if board difference.",
            "cors": {
                "allow_origins": ["Wish garden where make middle."],
                "allow_credentials": False,
                "allow_methods": ["Challenge rule range beautiful compare. Ok picture"],
                "allow_headers": ["Site build professor affect consider."],
            },
        },
        "llama_stack": {
            "url": None,
            "api_key": "xyzzy",
            "use_as_library_client": False,
            "library_client_config_path": "Effect wonder century for.",
            "timeout": 306,
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": "Watch argue issue these space may. Positive feel s",
            "transcripts_enabled": False,
            "transcripts_storage": "Thousand argue place reach.",
        },
        "database": {"sqlite": None, "postgres": None},
        "mcp_servers": [
            {
                "name": "Patricia Moore",
                "provider_id": "Quite official social necessary use.",
                "url": "http://www.curry.com/",
                "authorization_headers": {
                    "special": "Outside such just firm mention.",
                    "out": "Democrat mouth country author view.",
                },
                "headers": [
                    "Not report to road however up once shoulder. Stand",
                    "Writer nation various so within.",
                    "Goal democratic night simple treat cause marriage.",
                ],
                "timeout": "xyzzy",
            },
            {
                "name": "Kayla Lopez",
                "provider_id": "Environmental card evening go wish foot.",
                "url": "http://irwin-vang.com/",
                "authorization_headers": {
                    "decade": "Manager military party just east growth. House add",
                    "foot": "Training probably including.",
                    "organization": "Care in live response member of discuss later.",
                },
                "headers": [
                    "Animal now effort tonight player after.",
                    "Various risk pressure social mean.",
                ],
                "timeout": "xyzzy",
            },
            {
                "name": "Katie Davis",
                "provider_id": "Almost teacher itself property appear later style.",
                "url": "https://hill.com/",
                "authorization_headers": {"view": "Young something spend."},
                "headers": [
                    "Purpose family good coach family beat area.",
                    "Somebody head agent language.",
                ],
                "timeout": "xyzzy",
            },
        ],
        "authentication": {
            "module": "Author someone behind.",
            "skip_tls_verification": False,
            "skip_for_health_probes": True,
            "skip_for_metrics": True,
            "k8s_cluster_api": None,
            "k8s_ca_cert_path": None,
            "jwk_config": None,
            "api_key_config": None,
            "rh_identity_config": None,
        },
        "authorization": {
            "access_rules": [
                {
                    "role": "Culture spend science site change local.",
                    "actions": ["xyzzy", "xyzzy", "xyzzy"],
                },
                {
                    "role": "Civil window house expert spend hope card dog.",
                    "actions": ["xyzzy", "xyzzy", "xyzzy"],
                },
            ]
        },
        "customization": None,
        "inference": {
            "default_model": None,
            "default_provider": "Ask center garden race thing.",
        },
        "conversation_cache": {
            "type": None,
            "memory": {"max_entries": 845},
            "sqlite": None,
            "postgres": None,
        },
        "a2a_state": {
            "sqlite": None,
            "postgres": {
                "host": "Ball drug fight place.",
                "port": 273,
                "db": "Like unit money every.",
                "user": "Once offer fire loss one.",
                "password": "XsI3UvH9%#V5",
                "namespace": "House establish network.",
                "ssl_mode": "Agree within describe have.",
                "gss_encmode": "Give choose challenge away.",
                "ca_cert_path": None,
            },
        },
        "quota_handlers": {
            "sqlite": {"db_path": "Speak maintain here among."},
            "postgres": {
                "host": "Him agree successful should.",
                "port": 976,
                "db": "In possible once food happy.",
                "user": "Much military four.",
                "password": "J58*k!chxA%R",
                "namespace": "Ground instead tax seven True make industry.",
                "ssl_mode": "Five so take continue.",
                "gss_encmode": "Add piece you brother on.",
                "ca_cert_path": "xyzzy",
            },
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Jonathan Clark",
                    "initial_quota": 720,
                    "quota_increase": 955,
                    "period": "Relationship the study whether try sell.",
                },
                {
                    "type": "xyzzy",
                    "name": "Robert Smith",
                    "initial_quota": 363,
                    "quota_increase": 907,
                    "period": "Later health agreement.",
                },
                {
                    "type": "xyzzy",
                    "name": "Emily Perry",
                    "initial_quota": 138,
                    "quota_increase": 495,
                    "period": "Middle day he result performance.",
                },
            ],
            "scheduler": {
                "period": 564,
                "database_reconnection_count": 904,
                "database_reconnection_delay": 407,
            },
            "enable_token_history": True,
        },
        "azure_entra_id": None,
        "rlsapi_v1": {"allow_verbose_infer": False, "quota_subject": "xyzzy"},
        "splunk": {
            "enabled": True,
            "url": "https://www.thompson-wright.com/",
            "token_path": None,
            "index": None,
            "source": "Entire wear several sit.",
            "timeout": 402,
            "verify_ssl": False,
        },
        "deployment_environment": "Wonder though writer allow instead.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Charge herself where impact say billion.",
                        "backend": "Blood thus member soldier.",
                        "embedding_model": "Sound hotel save.",
                        "embedding_dimension": 922,
                        "vector_db_id": "Down simple suffer civil. Modern service scene pas",
                        "db_path": "Ten fall fine firm.",
                        "score_multiplier": 671.28,
                    },
                    {
                        "rag_id": "Include space evidence benefit loss skin.",
                        "backend": "Green anyone be.",
                        "embedding_model": "Focus clearly physical six.",
                        "embedding_dimension": 237,
                        "vector_db_id": "Company put eight.",
                        "db_path": "Step at let oil leave agreement this.",
                        "score_multiplier": 368.33,
                    },
                ],
            },
            "okp": {
                "rhokp_url": "xyzzy",
                "offline": True,
                "chunk_filter_query": None,
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Onto political artist.",
                        "Trip writer half. Amount south give parent.",
                        "We thought American exist. Nearly cell case partic",
                    ],
                },
                "tool": {
                    "sources": [
                        "School of book next man short responsibility able.",
                    ],
                },
            },
        },
    },
    {
        "name": "Rodney Scott",
        "service": {
            "host": "Account blue each real child guy. Thing tree expec",
            "port": 481,
            "base_url": "Learn development choice matter.",
            "auth_enabled": True,
            "workers": 106,
            "color_log": True,
            "access_log": True,
            "tls_config": {
                "tls_certificate_path": "xyzzy",
                "tls_key_path": None,
                "tls_key_password": None,
            },
            "root_path": "Foot anything coach window return wife.",
            "cors": {
                "allow_origins": ["Option table world friend.", "Maybe reality want."],
                "allow_credentials": True,
                "allow_methods": [
                    "Article resource skill include. Scene center huge ",
                    "Maintain home newspaper fish.",
                    "Smile yourself make career.",
                ],
                "allow_headers": [
                    "Writer change building brother test.",
                    "Draw less customer with data product.",
                    "Mrs however purpose so performance.",
                ],
            },
        },
        "llama_stack": {
            "url": "http://willis-jensen.com/",
            "api_key": "xyzzy",
            "use_as_library_client": None,
            "library_client_config_path": None,
            "timeout": 365,
        },
        "user_data_collection": {
            "feedback_enabled": True,
            "feedback_storage": None,
            "transcripts_enabled": True,
            "transcripts_storage": None,
        },
        "database": {
            "sqlite": None,
            "postgres": {
                "host": "Positive once activity scientist possible rise art",
                "port": 991,
                "db": "Would indeed another defense song.",
                "user": "One finally size product.",
                "password": "$C7KCoSKvh_f",
                "namespace": "Night surface whom.",
                "ssl_mode": "Affect federal thing accept party perform.",
                "gss_encmode": "Soon easy manager arm suffer.",
                "ca_cert_path": "xyzzy",
            },
        },
        "mcp_servers": [
            {
                "name": "Wendy Ramirez",
                "provider_id": "Else speak time recent.",
                "url": "http://hahn.org/",
                "authorization_headers": {
                    "politics": "Free teach dark born. Sport spend hair require eco"
                },
                "headers": [
                    "Hair team school.",
                    "Oil war ok much war movement.",
                    "Example arm test hundred.",
                ],
                "timeout": None,
            },
            {
                "name": "Ronnie Johnson",
                "provider_id": "Turn kind body draw will again.",
                "url": "http://www.cannon.biz/",
                "authorization_headers": {
                    "baby": "Discover manage democratic how.",
                    "daughter": "Of firm everybody project. Language interest metho",
                },
                "headers": ["They financial artist."],
                "timeout": None,
            },
        ],
        "authentication": {
            "module": "Nearly local really commercial.",
            "skip_tls_verification": True,
            "skip_for_health_probes": False,
            "skip_for_metrics": True,
            "k8s_cluster_api": None,
            "k8s_ca_cert_path": None,
            "jwk_config": None,
            "api_key_config": None,
            "rh_identity_config": {
                "required_entitlements": [
                    "Shake parent degree turn wind language.",
                    "Military several move least realize.",
                    "Word these group tax spend yes.",
                ],
                "max_header_size": 19,
            },
        },
        "authorization": {
            "access_rules": [
                {
                    "role": "Per charge white street painting continue yet choo",
                    "actions": ["xyzzy"],
                },
                {"role": "Model evening life.", "actions": ["xyzzy"]},
                {
                    "role": "Should explain join father expert able minute stoc",
                    "actions": ["xyzzy", "xyzzy", "xyzzy"],
                },
            ]
        },
        "customization": None,
        "inference": {"default_model": None, "default_provider": None},
        "conversation_cache": {
            "type": "xyzzy",
            "memory": {"max_entries": 138},
            "sqlite": {"db_path": "Also describe later garden."},
            "postgres": {
                "host": "Apply attention board century.",
                "port": 940,
                "db": "Often boy also never.",
                "user": "Financial a program matter.",
                "password": "K78mJGlP(#qV",
                "namespace": "Relationship science team business same wall.",
                "ssl_mode": "There base meet.",
                "gss_encmode": "Why realize five view.",
                "ca_cert_path": "xyzzy",
            },
        },
        "a2a_state": {
            "sqlite": {"db_path": "Trouble stop speech traditional."},
            "postgres": {
                "host": "Buy change blue despite.",
                "port": 252,
                "db": "Lot kitchen start fire challenge build.",
                "user": "Mission new grow people prepare too new. Blood may",
                "password": "F4LJgEg#leA+",
                "namespace": None,
                "ssl_mode": "Home worry beautiful camera economy.",
                "gss_encmode": "Tend none vote image. North identify power.",
                "ca_cert_path": None,
            },
        },
        "quota_handlers": {
            "sqlite": {"db_path": "Movement great always True."},
            "postgres": None,
            "limiters": [
                {
                    "type": "xyzzy",
                    "name": "Ricardo Collier",
                    "initial_quota": 741,
                    "quota_increase": 379,
                    "period": "Hotel whatever important its society take add ente",
                },
                {
                    "type": "xyzzy",
                    "name": "Nicole Turner",
                    "initial_quota": 571,
                    "quota_increase": 166,
                    "period": "Newspaper parent get result.",
                },
            ],
            "scheduler": {
                "period": 99,
                "database_reconnection_count": 132,
                "database_reconnection_delay": 701,
            },
            "enable_token_history": False,
        },
        "azure_entra_id": None,
        "rlsapi_v1": {"allow_verbose_infer": False, "quota_subject": "xyzzy"},
        "splunk": {
            "enabled": False,
            "url": None,
            "token_path": "xyzzy",
            "index": None,
            "source": "Anyone wrong increase over hundred.",
            "timeout": 155,
            "verify_ssl": True,
        },
        "deployment_environment": "West local subject clearly. Push question in.",
        "rag": {
            "byok": {
                "stores": [
                    {
                        "rag_id": "Stop choice sing prepare our both traditional.",
                        "backend": "Four account action. Herself measure speech full t",
                        "embedding_model": "Positive now since middle.",
                        "embedding_dimension": 799,
                        "vector_db_id": "Movie word mouth major identify law manage they.",
                        "db_path": "Finally hot investment role attorney meet husband.",
                        "score_multiplier": 515.98,
                    },
                    {
                        "rag_id": "Throw two action station store respond among.",
                        "backend": "Accept exist also happy.",
                        "embedding_model": "Box structure arrive. Front suffer civil fund invo",
                        "embedding_dimension": 443,
                        "vector_db_id": "Begin born decade instead.",
                        "db_path": "Interest easy remember here fast win. Despite budg",
                        "score_multiplier": 2.92,
                    },
                ],
            },
            "okp": {
                "rhokp_url": "xyzzy",
                "offline": False,
                "chunk_filter_query": "Maybe assume region thus.",
            },
            "retrieval": {
                "inline": {
                    "sources": [
                        "Garden up certain success student others may.",
                        "Face can produce.",
                    ],
                },
                "tool": {
                    "sources": [
                        "Though appear collection night message high.",
                        "Knowledge cup fact.",
                    ],
                },
            },
        },
    },
    {
        "name": "Mary Strong",
        "service": {
            "host": "Air customer red.",
            "port": 590,
            "base_url": None,
            "auth_enabled": True,
            "workers": 389,
            "color_log": True,
            "access_log": False,
            "tls_config": {
                "tls_certificate_path": None,
                "tls_key_path": "/",
                "tls_key_password": None,
            },
            "root_path": "Close him reach political two while throw.",
            "cors": {
                "allow_origins": [
                    "Everybody now each clearly my hold receive.",
                    "Nature past high middle.",
                    "What have police activity.",
                ],
                "allow_credentials": False,
                "allow_methods": [
                    "Assume apply traditional. Himself radio for build.",
                    "Resource almost I difference long spend.",
                    "Goal world positive long.",
                ],
                "allow_headers": [
                    "Paper save of others between we.",
                    "Look until clear up look.",
                    "Out paper pick race.",
                ],
            },
        },
        "llama_stack": {
            "url": "https://carroll.com/",
            "api_key": "/",
            "use_as_library_client": None,
            "library_client_config_path": None,
            "timeout": 683,
            "max_retries": 624,
            "retry_delay": 497,
            "allow_degraded_mode": None,
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": None,
            "transcripts_enabled": True,
            "transcripts_storage": "Air commercial.",
        },
        "database": {
            "sqlite": {"db_path": "Goal majority summer environmental thing sell visi"},
            "postgres": {
                "host": "Pretty become instead.",
                "port": 679,
                "db": "Black hear again blood.",
                "user": "Administration represent compare official contain.",
                "password": "VSP#VO*jt)13",
                "namespace": "By mind industry box memory. See step window bar P",
                "ssl_mode": "disable",
                "gss_encmode": "prefer",
                "ca_cert_path": "/",
            },
        },
        "mcp_servers": [
            {
                "name": "Christopher Davis",
                "provider_id": "Able tonight pretty author try finally. Act operat",
                "url": "http://www.alvarez.com/",
                "authorization_headers": {
                    "he": "TV board give town.",
                    "contain": "Away carry role by. Style majority case.",
                    "data": "North attack every than.",
                },
                "headers": [
                    "Child expect put.",
                    "Better cultural indeed True hear.",
                    "Including those choose.",
                ],
                "require_approval": "always",
                "timeout": "10",
            },
            {
                "name": "Isaac Fry",
                "provider_id": "Voice account car gun wear.",
                "url": "http://torres.com/",
                "authorization_headers": {
                    "tax": "Dog father outside according onto.",
                    "system": "Ground while both else break. You believe ask visi",
                },
                "headers": [
                    "Shake water be.",
                    "Fine whether pass can question identify.",
                    "Area realize pay son also loss.",
                ],
                "require_approval": "always",
                "timeout": None,
            },
        ],
        "authentication": {
            "module": "Commercial important.",
            "skip_tls_verification": True,
            "skip_for_health_probes": True,
            "skip_for_metrics": True,
            "k8s_cluster_api": "/",
            "k8s_ca_cert_path": None,
            "jwk_config": None,
            "api_key_config": None,
            "rh_identity_config": {
                "required_entitlements": [
                    "Interview magazine summer start smile beyond.",
                    "Reflect reduce cause various.",
                    "Imagine not cold change.",
                ],
                "max_header_size": 47,
            },
        },
        "authorization": None,
        "customization": None,
        "inference": {
            "default_model": None,
            "default_provider": None,
            "context_windows": {
                "we": "10",
                "when": "20",
            },
        },
        "conversation_cache": {
            "type": None,
            "memory": {"max_entries": 5},
            "sqlite": {"db_path": "Argue total again party."},
            "postgres": {
                "host": "Like bad land difference force hope. Fine movie if",
                "port": 515,
                "db": "Keep shoulder reason more can you street. Fly spen",
                "user": "Structure feel sea last task human.",
                "password": "P@F*6PwbB2HI",
                "namespace": None,
                "ssl_mode": "allow",
                "gss_encmode": "disable",
                "ca_cert_path": "/",
            },
        },
        "compaction": {
            "enabled": True,
            "threshold_ratio": 933.66,
            "token_floor": 998,
            "buffer_turns": 998,
            "buffer_max_ratio": 743.59,
        },
        "approvals": {"approval_timeout_seconds": 898, "approval_retention_days": 414},
        "a2a_state": {
            "sqlite": {"db_path": "Theory that enough party child."},
            "postgres": {
                "host": "Never enjoy present letter.",
                "port": 106,
                "db": "Item control one than store word. Word social issu",
                "user": "Question body building believe.",
                "password": "@ist@dmIfs7G",
                "namespace": "Run fall family best whose.",
                "ssl_mode": "allow",
                "gss_encmode": "require",
                "ca_cert_path": None,
            },
        },
        "quota_handlers": {
            "sqlite": {"db_path": "Word push guess mind."},
            "postgres": None,
            "limiters": [
                {
                    "type": "user_limiter",
                    "name": "Sarah Lyons",
                    "initial_quota": 291,
                    "quota_increase": 630,
                    "period": "Not power manage trial task south within.",
                },
                {
                    "type": "cluster_limiter",
                    "name": "Rachel Jackson",
                    "initial_quota": 134,
                    "quota_increase": 978,
                    "period": "Ready concern everybody skin present natural.",
                },
            ],
            "scheduler": {
                "period": 623,
                "database_reconnection_count": 172,
                "database_reconnection_delay": 267,
            },
            "enable_token_history": True,
        },
        "azure_entra_id": {
            "tenant_id": "tenant",
            "client_id": "client",
            "client_secret": "secret",
            "scope": "High ability soon of still worry nice.",
        },
        "rlsapi_v1": {"allow_verbose_infer": True, "quota_subject": None},
        "splunk": None,
        "deployment_environment": "Father hit rise.",
        "rag": {
            "inline": ["Raise explain traditional boy world medical."],
            "tool": ["North prepare recognize.", "Cold including arm tough pull."],
        },
        "okp": {"rhokp_url": None, "offline": True, "chunk_filter_query": None},
        "skills": {
            "paths": [
                "/",
                "/foo",
                "/bar",
            ]
        },
    },
]


@pytest.mark.parametrize("config_dict", wrong_configurations)
def test_init_from_dict_fake_data(config_dict: dict[str, Any]) -> None:
    """Test the configuration initialization from dictionary with config values."""
    with pytest.raises((ValueError, InvalidConfigurationError)):
        # try to initialize the app config and load configuration from a Python
        # dictionary
        cfg = AppConfig()
        cfg.init_from_dict(config_dict)


def test_native_override_env_refs_not_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """${env.*} inside native_override is kept as a reference, not resolved.

    Everything else in the config still resolves. This keeps LCORE from
    eagerly resolving (and then logging at startup) secrets that belong to
    Llama Stack's own raw schema.
    """
    monkeypatch.setenv("LCORE_TEST_SECRET", "supersecret")
    monkeypatch.setenv("LCORE_TEST_MODEL", "gpt-4o-mini")
    config_dict = {
        "inference": {"default_model": "${env.LCORE_TEST_MODEL}"},
        "llama_stack": {
            "config": {
                "baseline": "empty",
                "native_override": {
                    "providers": {
                        "inference": [
                            {"config": {"api_key": "${env.LCORE_TEST_SECRET}"}}
                        ]
                    }
                },
            }
        },
    }

    resolved = replace_env_vars_preserving_native_override(config_dict)

    # native_override keeps the reference verbatim — the secret never resolved
    override_api_key = resolved["llama_stack"]["config"]["native_override"][
        "providers"
    ]["inference"][0]["config"]["api_key"]
    assert override_api_key == "${env.LCORE_TEST_SECRET}"
    assert "supersecret" not in str(resolved["llama_stack"])
    # everything outside native_override still resolves
    assert resolved["inference"]["default_model"] == "gpt-4o-mini"


def test_replace_env_vars_without_native_override_resolves_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no native_override, the helper resolves env refs like the plain call."""
    monkeypatch.setenv("LCORE_TEST_MODEL", "gpt-4o-mini")
    config_dict = {"inference": {"default_model": "${env.LCORE_TEST_MODEL}"}}
    resolved = replace_env_vars_preserving_native_override(config_dict)
    assert resolved["inference"]["default_model"] == "gpt-4o-mini"
