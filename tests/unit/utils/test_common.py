"""Test module for utils/common.py."""

from logging import Logger

import pytest
from llama_stack_client import APIConnectionError
from pydantic import AnyHttpUrl
from pytest_mock import MockerFixture

from models.config import (
    Configuration,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    ServiceConfiguration,
    UserDataCollection,
)
from utils.common import (
    _register_mcp_toolgroups_async,
    register_mcp_servers_async,
)


@pytest.mark.asyncio
async def test_register_mcp_servers_empty_list(mocker: MockerFixture) -> None:
    """Test register_mcp_servers with empty MCP servers list."""
    mock_logger = mocker.Mock(spec=Logger)

    # Mock the LlamaStack client (shouldn't be called since no MCP servers)
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")

    # Create configuration with empty MCP servers
    config = Configuration(
        name="test",
        service=ServiceConfiguration(
            host="localhost",
            port=1234,
            base_url=None,
            auth_enabled=True,
            workers=10,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=False,
            url=AnyHttpUrl("http://localhost:8321"),
            library_client_config_path=None,
            api_key=None,
            timeout=60,
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False,
            feedback_storage=None,
            transcripts_enabled=False,
            transcripts_storage=None,
        ),
        mcp_servers=[],
        customization=None,
    )  # pyright: ignore[reportCallIssue]
    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify get_llama_stack_client was NOT called since no MCP servers
    mock_lsc.assert_not_called()
    # Verify debug message was logged
    mock_logger.debug.assert_called_with(
        "No MCP servers configured, skipping registration"
    )


@pytest.mark.asyncio
async def test_register_mcp_servers_single_server_not_registered(
    mocker: MockerFixture,
) -> None:
    """Test register_mcp_servers with single MCP server that is not yet registered."""
    # Mock the logger
    mock_logger = mocker.Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = mocker.AsyncMock()
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_tool = mocker.Mock()
    mock_tool.provider_resource_id = "existing-server"
    mock_client.toolgroups.list.return_value = [mock_tool]
    mock_client.toolgroups.register.return_value = None

    # Create configuration with one MCP server
    mcp_server = ModelContextProtocolServer(
        name="new-server",
        url="http://localhost:8080",
        provider_id="model-context-protocol",
    )
    config = Configuration(
        name="test",
        service=ServiceConfiguration(
            host="localhost",
            port=1234,
            base_url=None,
            auth_enabled=True,
            workers=10,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=False,
            url=AnyHttpUrl("http://localhost:8321"),
            library_client_config_path=None,
            api_key=None,
            timeout=60,
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False,
            feedback_storage=None,
            transcripts_enabled=False,
            transcripts_storage=None,
        ),
        mcp_servers=[mcp_server],
        customization=None,
    )  # pyright: ignore[reportCallIssue]

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
async def test_register_mcp_servers_single_server_already_registered(
    mocker: MockerFixture,
) -> None:
    """Test register_mcp_servers with single MCP server that is already registered."""
    # Mock the logger
    mock_logger = mocker.Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = mocker.AsyncMock()
    mock_tool = mocker.Mock()
    mock_tool.provider_resource_id = "existing-server"
    mock_client.toolgroups.list.return_value = [mock_tool]
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client

    # Create configuration with MCP server that matches existing toolgroup
    mcp_server = ModelContextProtocolServer(
        name="existing-server", url="http://localhost:8080", provider_id="qwe"
    )
    config = Configuration(
        name="test",
        service=ServiceConfiguration(
            host="localhost",
            port=1234,
            base_url=None,
            auth_enabled=True,
            workers=10,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=False,
            url=AnyHttpUrl("http://localhost:8321"),
            library_client_config_path=None,
            api_key=None,
            timeout=60,
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False,
            feedback_storage=None,
            transcripts_enabled=False,
            transcripts_storage=None,
        ),
        mcp_servers=[mcp_server],
        customization=None,
    )  # pyright: ignore[reportCallIssue]

    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify client.tools.list was called
    mock_client.toolgroups.list.assert_called_once()
    # Verify client.toolgroups.register was NOT called since server already registered
    assert not mock_client.toolgroups.register.called


@pytest.mark.asyncio
async def test_register_mcp_servers_multiple_servers_mixed_registration(
    mocker: MockerFixture,
) -> None:
    """Test register_mcp_servers with multiple MCP servers - some registered, some not."""
    # Mock the logger
    mock_logger = mocker.Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = mocker.AsyncMock()
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client
    mock_tool1 = mocker.Mock()
    mock_tool1.provider_resource_id = "existing-server"
    mock_tool2 = mocker.Mock()
    mock_tool2.provider_resource_id = "another-existing"
    mock_client.toolgroups.list.return_value = [mock_tool1, mock_tool2]
    mock_client.toolgroups.register.return_value = None

    # Create configuration with multiple MCP servers
    mcp_servers = [
        ModelContextProtocolServer(
            name="existing-server",
            url="http://localhost:8080",
        ),  # pyright: ignore[reportCallIssue]
        ModelContextProtocolServer(
            name="new-server",
            url="http://localhost:8081",
        ),  # pyright: ignore[reportCallIssue]
        ModelContextProtocolServer(
            name="another-new-server",
            provider_id="custom-provider",
            url="https://api.example.com",
        ),
    ]
    config = Configuration(
        name="test",
        service=ServiceConfiguration(
            host="localhost",
            port=1234,
            base_url=None,
            auth_enabled=True,
            workers=10,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=False,
            url=AnyHttpUrl("http://localhost:8321"),
            library_client_config_path=None,
            api_key=None,
            timeout=60,
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False,
            feedback_storage=None,
            transcripts_enabled=False,
            transcripts_storage=None,
        ),
        mcp_servers=mcp_servers,
        customization=None,
    )  # pyright: ignore[reportCallIssue]

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
async def test_register_mcp_servers_with_custom_provider(mocker: MockerFixture) -> None:
    """Test register_mcp_servers with MCP server using custom provider."""
    # Mock the logger
    mock_logger = mocker.Mock(spec=Logger)

    # Mock the LlamaStack client
    mock_client = mocker.AsyncMock()
    mock_client.toolgroups.list.return_value = []
    mock_client.toolgroups.register.return_value = None
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_client

    # Create configuration with MCP server using custom provider
    mcp_server = ModelContextProtocolServer(
        name="custom-server",
        provider_id="my-custom-provider",
        url="https://custom.example.com/mcp",
    )
    config = Configuration(
        name="test",
        service=ServiceConfiguration(
            host="localhost",
            port=1234,
            base_url=None,
            auth_enabled=True,
            workers=10,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=False,
            url=AnyHttpUrl("http://localhost:8321"),
            library_client_config_path=None,
            api_key=None,
            timeout=60,
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False,
            feedback_storage=None,
            transcripts_enabled=False,
            transcripts_storage=None,
        ),
        mcp_servers=[mcp_server],
        customization=None,
    )  # pyright: ignore[reportCallIssue]

    # Call the function
    await register_mcp_servers_async(mock_logger, config)

    # Verify client.toolgroups.register was called with custom provider
    mock_client.toolgroups.register.assert_called_once_with(
        toolgroup_id="custom-server",
        provider_id="my-custom-provider",
        mcp_endpoint={"uri": "https://custom.example.com/mcp"},
    )


@pytest.mark.asyncio
async def test_register_mcp_servers_async_with_library_client(
    mocker: MockerFixture,
) -> None:
    """
    Test that `register_mcp_servers_async` correctly registers MCP
    servers when using the library client configuration.

    This test verifies that the function initializes the async
    client, checks for existing toolgroups, and registers new MCP
    servers as needed when the configuration specifies the use of a
    library client.
    """
    # Mock the logger
    mock_logger = mocker.Mock(spec=Logger)

    # Mock the LlamaStackAsLibraryClient
    mock_async_client = mocker.AsyncMock()
    mock_async_client.initialize = mocker.AsyncMock()
    mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")
    mock_lsc.return_value = mock_async_client

    # Mock tools.list to return empty list
    mock_tool = mocker.Mock()
    mock_tool.provider_resource_id = "existing-tool"
    mock_async_client.toolgroups.list = mocker.AsyncMock(return_value=[mock_tool])
    mock_async_client.toolgroups.register = mocker.AsyncMock()

    # Create configuration with library client enabled
    mcp_server = ModelContextProtocolServer(
        name="test-server", url="http://localhost:8080"
    )  # pyright: ignore[reportCallIssue]
    config = Configuration(
        name="test",
        service=ServiceConfiguration(
            host="localhost",
            port=1234,
            base_url=None,
            auth_enabled=True,
            workers=10,
            color_log=True,
            access_log=True,
            root_path="/.",
        ),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            url=None,
            api_key=None,
            timeout=60,
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False,
            feedback_storage=None,
            transcripts_enabled=False,
            transcripts_storage=None,
        ),
        mcp_servers=[mcp_server],
        customization=None,
    )  # pyright: ignore[reportCallIssue]

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


@pytest.mark.asyncio
async def test_register_mcp_toolgroups_retries_on_connection_error(
    mocker: MockerFixture,
) -> None:
    """Test that _register_mcp_toolgroups_async retries on APIConnectionError."""
    mock_client = mocker.AsyncMock()
    mock_logger = mocker.Mock(spec=Logger)
    mock_sleep = mocker.patch("utils.common.asyncio.sleep")

    mock_tool = mocker.Mock()
    mock_tool.provider_resource_id = "existing-server"

    mock_client.toolgroups.list.side_effect = [
        APIConnectionError(request=mocker.MagicMock()),
        APIConnectionError(request=mocker.MagicMock()),
        [mock_tool],
    ]

    mcp_servers = [
        ModelContextProtocolServer(
            name="new-server",
            url="http://localhost:8080",
        ),  # pyright: ignore[reportCallIssue]
    ]

    await _register_mcp_toolgroups_async(
        mock_client, mcp_servers, mock_logger, max_retries=5, retry_delay=1
    )

    assert mock_client.toolgroups.list.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_called_with(1)
    assert mock_logger.warning.call_count == 2


@pytest.mark.asyncio
async def test_register_mcp_toolgroups_raises_after_max_retries(
    mocker: MockerFixture,
) -> None:
    """Test that _register_mcp_toolgroups_async raises after all retries are exhausted."""
    mock_client = mocker.AsyncMock()
    mock_logger = mocker.Mock(spec=Logger)
    mock_sleep = mocker.patch("utils.common.asyncio.sleep")

    mock_client.toolgroups.list.side_effect = APIConnectionError(
        request=mocker.MagicMock()
    )

    mcp_servers = [
        ModelContextProtocolServer(
            name="new-server",
            url="http://localhost:8080",
        ),  # pyright: ignore[reportCallIssue]
    ]

    with pytest.raises(APIConnectionError):
        await _register_mcp_toolgroups_async(
            mock_client, mcp_servers, mock_logger, max_retries=3, retry_delay=1
        )

    assert mock_client.toolgroups.list.call_count == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_register_mcp_toolgroups_retries_on_register_error(
    mocker: MockerFixture,
) -> None:
    """Test retry when register() raises APIConnectionError."""
    mock_client = mocker.AsyncMock()
    mock_logger = mocker.Mock(spec=Logger)
    mock_sleep = mocker.patch("utils.common.asyncio.sleep")

    mock_client.toolgroups.list.return_value = []
    mock_client.toolgroups.register.side_effect = [
        APIConnectionError(request=mocker.MagicMock()),
        None,
    ]

    mcp_servers = [
        ModelContextProtocolServer(
            name="new-server",
            url="http://localhost:8080",
        ),  # pyright: ignore[reportCallIssue]
    ]

    await _register_mcp_toolgroups_async(
        mock_client, mcp_servers, mock_logger, max_retries=3, retry_delay=1
    )

    assert mock_client.toolgroups.list.call_count == 2
    assert mock_client.toolgroups.register.call_count == 2
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(1)


@pytest.mark.asyncio
async def test_register_mcp_toolgroups_single_attempt_success(
    mocker: MockerFixture,
) -> None:
    """Test max_retries=1 with successful first attempt."""
    mock_client = mocker.AsyncMock()
    mock_logger = mocker.Mock(spec=Logger)
    mock_sleep = mocker.patch("utils.common.asyncio.sleep")

    mock_client.toolgroups.list.return_value = []
    mock_client.toolgroups.register.return_value = None

    mcp_servers = [
        ModelContextProtocolServer(
            name="new-server",
            url="http://localhost:8080",
        ),  # pyright: ignore[reportCallIssue]
    ]

    await _register_mcp_toolgroups_async(
        mock_client, mcp_servers, mock_logger, max_retries=1, retry_delay=1
    )

    mock_client.toolgroups.list.assert_called_once()
    mock_client.toolgroups.register.assert_called_once()
    mock_sleep.assert_not_called()
    mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_register_mcp_toolgroups_single_attempt_failure(
    mocker: MockerFixture,
) -> None:
    """Test max_retries=1 raises immediately without sleeping."""
    mock_client = mocker.AsyncMock()
    mock_logger = mocker.Mock(spec=Logger)
    mock_sleep = mocker.patch("utils.common.asyncio.sleep")

    mock_client.toolgroups.list.side_effect = APIConnectionError(
        request=mocker.MagicMock()
    )

    mcp_servers = [
        ModelContextProtocolServer(
            name="new-server",
            url="http://localhost:8080",
        ),  # pyright: ignore[reportCallIssue]
    ]

    with pytest.raises(APIConnectionError):
        await _register_mcp_toolgroups_async(
            mock_client, mcp_servers, mock_logger, max_retries=1, retry_delay=1
        )

    mock_client.toolgroups.list.assert_called_once()
    mock_sleep.assert_not_called()
    mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_register_mcp_toolgroups_non_connection_error_propagates(
    mocker: MockerFixture,
) -> None:
    """Test that non-APIConnectionError exceptions propagate without retry."""
    mock_client = mocker.AsyncMock()
    mock_logger = mocker.Mock(spec=Logger)
    mock_sleep = mocker.patch("utils.common.asyncio.sleep")

    mock_client.toolgroups.list.side_effect = RuntimeError("unexpected")

    mcp_servers = [
        ModelContextProtocolServer(
            name="new-server",
            url="http://localhost:8080",
        ),  # pyright: ignore[reportCallIssue]
    ]

    with pytest.raises(RuntimeError, match="unexpected"):
        await _register_mcp_toolgroups_async(
            mock_client, mcp_servers, mock_logger, max_retries=5, retry_delay=1
        )

    mock_client.toolgroups.list.assert_called_once()
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_register_mcp_toolgroups_invalid_max_retries(
    mocker: MockerFixture,
) -> None:
    """Test that max_retries < 1 raises ValueError."""
    mock_client = mocker.AsyncMock()
    mock_logger = mocker.Mock(spec=Logger)

    with pytest.raises(ValueError, match="max_retries must be >= 1"):
        await _register_mcp_toolgroups_async(
            mock_client, [], mock_logger, max_retries=0
        )
