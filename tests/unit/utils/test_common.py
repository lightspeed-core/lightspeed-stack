"""Test module for utils/common.py."""

from unittest.mock import Mock, AsyncMock
from logging import Logger

import pytest

from utils.common import (
    retrieve_user_id,
    register_mcp_servers_async,
)
from models.config import (
    Configuration,
    ServiceConfiguration,
    LLamaStackConfiguration,
    UserDataCollection,
    ModelContextProtocolServer,
)


# TODO(lucasagomes): Implement this test when the retrieve_user_id function is implemented
def test_retrieve_user_id():
    """Test that retrieve_user_id returns a user ID."""
    user_id = retrieve_user_id(None)
    assert user_id == "user_id_placeholder"


@pytest.mark.asyncio
async def test_register_mcp_servers_empty_list(mocker):
    """Test register_mcp_servers with empty MCP servers list."""
    # Mock the logger
    mock_logger = Mock(spec=Logger)

    # Mock the LlamaStack client (shouldn't be called since no MCP servers)
    mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")

    # Create configuration with empty MCP servers
    config = Configuration(
        name="test",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=False, url="http://localhost:8321"
        ),
        user_data_collection=UserDataCollection(feedback_disabled=True),
        mcp_servers=[],
        customization=None,
    )
    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify get_llama_stack_client was NOT called since no MCP servers
    mock_lsc.assert_not_called()
    # Verify debug message was logged
    mock_logger.debug.assert_called_with(
        "No MCP servers configured, skipping registration"
    )


@pytest.mark.asyncio
async def test_register_mcp_servers_single_server_not_registered(mocker):
    """Test register_mcp_servers with single MCP server that is not yet registered."""
    # Mock the logger
    mock_logger = Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = Mock()
    mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_tool = Mock()
    mock_tool.provider_resource_id = "existing-server"
    mock_client.toolgroups.list.return_value = [mock_tool]
    mock_client.toolgroups.register.return_value = None

    # Create configuration with one MCP server
    mcp_server = ModelContextProtocolServer(
        name="new-server", url="http://localhost:8080"
    )
    config = Configuration(
        name="test",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=False, url="http://localhost:8321"
        ),
        user_data_collection=UserDataCollection(feedback_disabled=True),
        mcp_servers=[mcp_server],
        customization=None,
    )

    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify client.toolgroups.list was called
    mock_client.toolgroups.list.assert_called_once()
    # Verify client.toolgroups.register was called with correct parameters
    mock_client.toolgroups.register.assert_called_once_with(
        toolgroup_id="new-server",
        provider_id="model-context-protocol",
        mcp_endpoint={"uri": "http://localhost:8080"},
    )
    # Verify debug logging was called
    mock_logger.debug.assert_called()


@pytest.mark.asyncio
async def test_register_mcp_servers_single_server_already_registered(mocker):
    """Test register_mcp_servers with single MCP server that is already registered."""
    # Mock the logger
    mock_logger = Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = Mock()
    mock_tool = Mock()
    mock_tool.provider_resource_id = "existing-server"
    mock_client.toolgroups.list.return_value = [mock_tool]
    mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client

    # Create configuration with MCP server that matches existing toolgroup
    mcp_server = ModelContextProtocolServer(
        name="existing-server", url="http://localhost:8080"
    )
    config = Configuration(
        name="test",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=False, url="http://localhost:8321"
        ),
        user_data_collection=UserDataCollection(feedback_disabled=True),
        mcp_servers=[mcp_server],
        customization=None,
    )

    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify client.tools.list was called
    mock_client.toolgroups.list.assert_called_once()
    # Verify client.toolgroups.register was NOT called since server already registered
    assert not mock_client.toolgroups.register.called


@pytest.mark.asyncio
async def test_register_mcp_servers_multiple_servers_mixed_registration(mocker):
    """Test register_mcp_servers with multiple MCP servers - some registered, some not."""
    # Mock the logger
    mock_logger = Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = Mock()
    mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_tool1 = Mock()
    mock_tool1.provider_resource_id = "existing-server"
    mock_tool2 = Mock()
    mock_tool2.provider_resource_id = "another-existing"
    mock_client.toolgroups.list.return_value = [mock_tool1, mock_tool2]
    mock_client.toolgroups.register.return_value = None

    # Create configuration with multiple MCP servers
    mcp_servers = [
        ModelContextProtocolServer(name="existing-server", url="http://localhost:8080"),
        ModelContextProtocolServer(name="new-server", url="http://localhost:8081"),
        ModelContextProtocolServer(
            name="another-new-server",
            provider_id="custom-provider",
            url="https://api.example.com",
        ),
    ]
    config = Configuration(
        name="test",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=False, url="http://localhost:8321"
        ),
        user_data_collection=UserDataCollection(feedback_disabled=True),
        mcp_servers=mcp_servers,
        customization=None,
    )

    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify client.tools.list was called
    mock_client.toolgroups.list.assert_called_once()
    # Verify client.toolgroups.register was called twice (for the two new servers)
    assert mock_client.toolgroups.register.call_count == 2

    # Check the specific calls
    expected_calls = [
        mocker.call(
            toolgroup_id="new-server",
            provider_id="model-context-protocol",
            mcp_endpoint={"uri": "http://localhost:8081"},
        ),
        mocker.call(
            toolgroup_id="another-new-server",
            provider_id="custom-provider",
            mcp_endpoint={"uri": "https://api.example.com"},
        ),
    ]
    mock_client.toolgroups.register.assert_has_calls(expected_calls, any_order=True)


@pytest.mark.asyncio
async def test_register_mcp_servers_with_custom_provider(mocker):
    """Test register_mcp_servers with MCP server using custom provider."""
    # Mock the logger
    mock_logger = Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = Mock()
    mock_client.toolgroups.list.return_value = []
    mock_client.toolgroups.register.return_value = None
    mock_lsc = mocker.patch("client.LlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client

    # Create configuration with MCP server using custom provider
    mcp_server = ModelContextProtocolServer(
        name="custom-server",
        provider_id="my-custom-provider",
        url="https://custom.example.com/mcp",
    )
    config = Configuration(
        name="test",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=False, url="http://localhost:8321"
        ),
        user_data_collection=UserDataCollection(feedback_disabled=True),
        mcp_servers=[mcp_server],
        customization=None,
    )

    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify client.toolgroups.register was called with custom provider
    mock_client.toolgroups.register.assert_called_once_with(
        toolgroup_id="custom-server",
        provider_id="my-custom-provider",
        mcp_endpoint={"uri": "https://custom.example.com/mcp"},
    )


@pytest.mark.asyncio
async def test_register_mcp_servers_async_with_library_client(mocker):
    """Test register_mcp_servers_async with library client configuration."""
    # Mock the logger
    mock_logger = Mock(spec=Logger)

    # Mock the LlamaStackAsLibraryClient
    mock_async_client = AsyncMock()
    mock_async_client.initialize = AsyncMock()
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_async_client

    # Mock tools.list to return empty list
    mock_tool = Mock()
    mock_tool.provider_resource_id = "existing-tool"
    mock_async_client.toolgroups.list = AsyncMock(return_value=[mock_tool])
    mock_async_client.toolgroups.register = AsyncMock()

    # Create configuration with library client enabled
    mcp_server = ModelContextProtocolServer(
        name="test-server", url="http://localhost:8080"
    )
    config = Configuration(
        name="test",
        service=ServiceConfiguration(),
        llama_stack=LLamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="/path/to/config.yaml",
        ),
        user_data_collection=UserDataCollection(feedback_disabled=True),
        mcp_servers=[mcp_server],
        customization=None,
    )

    # Call the async function
    await register_mcp_servers_async(mock_logger, config)

    # Verify initialization was called
    mock_async_client.initialize.assert_called_once()
    # Verify tools.list was called
    mock_async_client.toolgroups.list.assert_called_once()
    # Verify toolgroups.register was called for the new server
    mock_async_client.toolgroups.register.assert_called_once_with(
        toolgroup_id="test-server",
        provider_id="model-context-protocol",
        mcp_endpoint={"uri": "http://localhost:8080"},
    )
