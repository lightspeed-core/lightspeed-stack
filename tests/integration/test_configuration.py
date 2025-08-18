"""Integration tests for configuration loading and handling."""

import pytest
from configuration import configuration

from models.config import ModelContextProtocolServer


@pytest.fixture(name="configuration_filename")
def configuration_filename_fixture() -> str:
    """Retrieve configuration file name to be used by integration tests."""
    return "tests/configuration/lightspeed-stack.yaml"


def test_default_configuration() -> None:
    """Test that exception is raised when configuration is not loaded."""
    cfg = configuration
    assert cfg is not None
    with pytest.raises(Exception, match="logic error: configuration is not loaded"):
        configuration.configuration  # pylint: disable=pointless-statement


def test_loading_proper_configuration(configuration_filename: str) -> None:
    """Test the configuration loading."""
    cfg = configuration
    cfg.load_configuration(configuration_filename)

    # check if configuration is loaded
    assert cfg is not None

    # check that all configuration sections exist
    assert cfg.configuration is not None
    assert cfg.llama_stack_configuration is not None
    assert cfg.service_configuration is not None
    assert cfg.user_data_collection_configuration is not None
    assert cfg.mcp_servers is not None

    # check 'configuration' section
    name = cfg.configuration.name
    assert name == "foo bar baz"

    # check 'service' section
    svc_config = cfg.service_configuration
    assert svc_config.host == "localhost"
    assert svc_config.auth_enabled is False
    assert svc_config.workers == 1
    assert svc_config.color_log is True
    assert svc_config.access_log is True

    # check 'service.cors' section
    cors_config = cfg.service_configuration.cors
    assert cors_config.allow_origins == ["foo_origin", "bar_origin", "baz_origin"]
    assert cors_config.allow_credentials is False
    assert cors_config.allow_methods == ["foo_method", "bar_method", "baz_method"]
    assert cors_config.allow_headers == ["foo_header", "bar_header", "baz_header"]

    # check 'llama_stack' section
    ls_config = cfg.llama_stack_configuration
    assert ls_config.use_as_library_client is False
    assert ls_config.url == "http://localhost:8321"
    assert ls_config.api_key == "xyzzy"

    # check 'user_data_collection' section
    udc_config = cfg.user_data_collection_configuration
    assert udc_config.feedback_enabled is True
    assert udc_config.feedback_storage == "/tmp/data/feedback"

    # check MCP servers section
    mcp_servers = cfg.mcp_servers
    assert mcp_servers != []  # pylint: disable=use-implicit-booleaness-not-comparison
    assert len(mcp_servers) == 3
    assert mcp_servers[0] == ModelContextProtocolServer(
        name="server1", provider_id="provider1", url="http://url.com:1"
    )
    assert mcp_servers[1] == ModelContextProtocolServer(
        name="server2", provider_id="provider2", url="http://url.com:2"
    )
    assert mcp_servers[2] == ModelContextProtocolServer(
        name="server3", provider_id="provider3", url="http://url.com:3"
    )
