"""Integration tests for the /authorized endpoint."""

from typing import Generator, Any
import pytest
from pytest_mock import MockerFixture

from llama_stack_client.types import VersionInfo
from authentication.interface import AuthTuple

from configuration import AppConfig
from app.endpoints.authorized import authorized_endpoint_handler
from constants import DEFAULT_USER_UID, DEFAULT_USER_NAME, DEFAULT_SKIP_USER_ID_CHECK


@pytest.fixture(name="mock_llama_stack_client")
def mock_llama_stack_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.

    Parameters:
        mocker (pytest_mock.MockerFixture): The pytest-mock fixture used to apply the patch.

    Yields:
        AsyncMock: A mocked Llama Stack client configured for tests.
    """
    mock_holder_class = mocker.patch("app.endpoints.info.AsyncLlamaStackClientHolder")

    mock_client = mocker.AsyncMock()
    # Mock the version endpoint to return a known version
    mock_client.inspect.version.return_value = VersionInfo(version="0.2.22")

    # Create a mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client


@pytest.mark.asyncio
async def test_authorized_endpoint(
    test_config: AppConfig,
    test_auth: AuthTuple,
) -> None:
    """Test the authorized endpoint handler.

    This integration test verifies:
    - Endpoint handler
    - No authentication is used
    - Response structure matches expected format

    Parameters:
        test_config (AppConfig): Loads root configuration
        test_auth (AuthTuple): noop authentication tuple
    """
    # Fixtures with side effects (needed but not directly used)
    _ = test_config

    response = await authorized_endpoint_handler(auth=test_auth)

    assert response.user_id == DEFAULT_USER_UID
    assert response.username == DEFAULT_USER_NAME
    assert response.skip_userid_check is DEFAULT_SKIP_USER_ID_CHECK
