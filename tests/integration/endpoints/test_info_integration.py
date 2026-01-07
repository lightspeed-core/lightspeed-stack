"""Integration tests for the /info endpoint."""

from typing import Generator, Any
import pytest
from pytest_mock import MockerFixture, AsyncMockType

from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError
from llama_stack_client.types import VersionInfo
from authentication.interface import AuthTuple

from configuration import AppConfig
from app.endpoints.info import info_endpoint_handler
from version import __version__


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
async def test_info_endpoint_returns_service_information(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that info endpoint returns correct service information.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Configuration values are correctly accessed
    - Llama Stack client is properly called
    - Real noop authentication is used
    - Response structure matches expected format

    Parameters:
        test_config: Loads real configuration (required for endpoint to access config)
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple

    Returns:
        None
    """
    # Fixtures with side effects (needed but not directly used)
    _ = test_config

    response = await info_endpoint_handler(auth=test_auth, request=test_request)

    # Verify values from real configuration
    assert response.name == "foo bar baz"  # From lightspeed-stack.yaml
    assert response.service_version == __version__
    assert response.llama_stack_version == "0.2.22"

    # Verify the Llama Stack client was called
    mock_llama_stack_client.inspect.version.assert_called_once()


@pytest.mark.asyncio
async def test_info_endpoint_handles_connection_error(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Test that info endpoint properly handles Llama Stack connection errors.

    This integration test verifies:
    - Error handling when external service is unavailable
    - HTTPException is raised with correct status code
    - Error response includes proper error details

    Parameters:
        test_config: Loads real configuration (required for endpoint to access config)
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: FastAPI request
        test_auth: noop authentication tuple
        mocker: pytest-mock fixture for creating mocks
    """
    # test_config fixture loads configuration, which is required for the endpoint
    _ = test_config
    # Configure mock to raise connection error
    mock_llama_stack_client.inspect.version.side_effect = APIConnectionError(
        request=mocker.Mock()
    )

    # Verify that HTTPException is raised
    with pytest.raises(HTTPException) as exc_info:
        await info_endpoint_handler(auth=test_auth, request=test_request)

    # Verify error details
    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert isinstance(exc_info.value.detail, dict)
    assert exc_info.value.detail["response"] == "Unable to connect to Llama Stack"  # type: ignore
    assert "cause" in exc_info.value.detail


@pytest.mark.asyncio
async def test_info_endpoint_uses_configuration_values(
    test_config: AppConfig,
    mock_llama_stack_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that info endpoint correctly uses configuration values.

    This integration test verifies:
    - Configuration is properly loaded and accessible
    - Endpoint reads configuration values correctly
    - Service name from config appears in response

    Parameters:
        test_config: Loads real configuration (required for endpoint to access config)
        mock_llama_stack_client: Mocked Llama Stack client
        test_request: Real FastAPI request
        test_auth: Real noop authentication tuple
    """
    # Fixtures with side effects (needed but not directly used)
    _ = mock_llama_stack_client

    response = await info_endpoint_handler(auth=test_auth, request=test_request)

    # Verify service name comes from configuration
    assert response.name == test_config.configuration.name
    assert response.name == "foo bar baz"
