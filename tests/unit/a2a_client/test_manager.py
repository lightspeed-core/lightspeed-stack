"""Unit tests for A2AClientManager."""

# pylint: disable=redefined-outer-name
# pylint: disable=protected-access
# pylint: disable=too-few-public-methods

from typing import Any

import pytest
from pytest_mock import MockerFixture

from a2a_client.manager import A2AClientManager, _BearerTokenInterceptor


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    """Reset the singleton between tests."""
    from utils.types import Singleton  # pylint: disable=import-outside-toplevel

    if A2AClientManager in Singleton._instances:
        del Singleton._instances[A2AClientManager]
    yield
    if A2AClientManager in Singleton._instances:
        del Singleton._instances[A2AClientManager]


@pytest.fixture
def a2a_config(mocker: MockerFixture) -> Any:
    """Create a mock A2AAgentsConfiguration."""
    agent1 = mocker.MagicMock()
    agent1.name = "test-agent"
    agent1.url = "https://agent.example.com"
    agent1.auth_token = None

    config = mocker.MagicMock()
    config.agents = [agent1]
    return config


@pytest.fixture
def a2a_config_with_token(mocker: MockerFixture) -> Any:
    """Create a mock config with auth token."""
    agent1 = mocker.MagicMock()
    agent1.name = "secure-agent"
    agent1.url = "https://secure.example.com"
    agent1.auth_token.get_secret_value.return_value = "test-token-123"

    config = mocker.MagicMock()
    config.agents = [agent1]
    return config


class TestA2AClientManager:
    """Tests for the A2AClientManager singleton."""

    def test_not_initialized_by_default(self) -> None:
        """Test that manager starts uninitialized."""
        manager = A2AClientManager()
        assert not manager.is_initialized
        assert manager.list_agents() == {}

    @pytest.mark.asyncio
    async def test_initialize_connects_to_agents(
        self, mocker: MockerFixture, a2a_config: Any
    ) -> None:
        """Test that initialize discovers agents and creates clients."""
        mock_card = mocker.MagicMock()
        mock_card.description = "A test agent"
        mock_client = mocker.AsyncMock()
        mock_client.get_card = mocker.AsyncMock(return_value=mock_card)

        connect_mock = mocker.patch(
            "a2a_client.manager.ClientFactory.connect",
            new=mocker.AsyncMock(return_value=mock_client),
        )

        manager = A2AClientManager()
        await manager.initialize(a2a_config)

        assert manager.is_initialized
        assert "test-agent" in manager.list_agents()
        assert manager.get_client("test-agent") is mock_client
        assert manager.get_card("test-agent") is mock_card
        connect_mock.assert_awaited_once()
        assert "agent.example.com" in str(connect_mock.call_args[0][0])

    @pytest.mark.asyncio
    async def test_initialize_with_auth_token(
        self, mocker: MockerFixture, a2a_config_with_token: Any
    ) -> None:
        """Test that auth token is passed as interceptor."""
        mock_card = mocker.MagicMock()
        mock_client = mocker.AsyncMock()
        mock_client.get_card = mocker.AsyncMock(return_value=mock_card)

        connect_mock = mocker.patch(
            "a2a_client.manager.ClientFactory.connect",
            new=mocker.AsyncMock(return_value=mock_client),
        )

        manager = A2AClientManager()
        await manager.initialize(a2a_config_with_token)

        call_kwargs = connect_mock.call_args[1]
        interceptors = call_kwargs.get("interceptors")
        assert interceptors is not None
        assert len(interceptors) == 1
        assert isinstance(interceptors[0], _BearerTokenInterceptor)
        assert interceptors[0]._token == "test-token-123"

    @pytest.mark.asyncio
    async def test_initialize_handles_connection_failure(
        self, mocker: MockerFixture, a2a_config: Any
    ) -> None:
        """Test that failed connections are logged but don't crash."""
        from a2a.client import A2AClientError  # pylint: disable=import-outside-toplevel

        mocker.patch(
            "a2a_client.manager.ClientFactory.connect",
            new=mocker.AsyncMock(side_effect=A2AClientError("Connection refused")),
        )

        manager = A2AClientManager()
        await manager.initialize(a2a_config)

        assert manager.is_initialized
        assert manager.list_agents() == {}
        assert manager.get_client("test-agent") is None

    @pytest.mark.asyncio
    async def test_initialize_idempotent(
        self, mocker: MockerFixture, a2a_config: Any
    ) -> None:
        """Test that calling initialize twice is a no-op."""
        mock_client = mocker.AsyncMock()
        mock_client.get_card = mocker.AsyncMock(return_value=mocker.MagicMock())

        connect_mock = mocker.patch(
            "a2a_client.manager.ClientFactory.connect",
            new=mocker.AsyncMock(return_value=mock_client),
        )

        manager = A2AClientManager()
        await manager.initialize(a2a_config)
        await manager.initialize(a2a_config)

        assert connect_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_close_cleans_up(
        self, mocker: MockerFixture, a2a_config: Any
    ) -> None:
        """Test that close disconnects all clients and resets state."""
        mock_client = mocker.AsyncMock()
        mock_client.get_card = mocker.AsyncMock(return_value=mocker.MagicMock())

        mocker.patch(
            "a2a_client.manager.ClientFactory.connect",
            new=mocker.AsyncMock(return_value=mock_client),
        )

        manager = A2AClientManager()
        await manager.initialize(a2a_config)
        assert manager.is_initialized

        await manager.close()
        assert not manager.is_initialized
        assert manager.list_agents() == {}
        mock_client.close.assert_awaited_once()

    def test_get_client_unknown_agent(self) -> None:
        """Test that get_client returns None for unknown agent."""
        manager = A2AClientManager()
        assert manager.get_client("nonexistent") is None


class TestBearerTokenInterceptor:
    """Tests for the bearer token interceptor."""

    @pytest.mark.asyncio
    async def test_adds_authorization_header(self) -> None:
        """Test that interceptor adds Bearer token header."""
        interceptor = _BearerTokenInterceptor("my-token")
        payload: dict[str, Any] = {"method": "test"}
        http_kwargs: dict[str, Any] = {}

        result_payload, result_kwargs = await interceptor.intercept(
            "message/send", payload, http_kwargs, None, None
        )

        assert result_kwargs["headers"]["Authorization"] == "Bearer my-token"
        assert result_payload == payload
