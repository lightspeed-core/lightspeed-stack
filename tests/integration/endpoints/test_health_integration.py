"""Integration tests for the /health endpoint."""

from typing import Generator, Any
import pytest
from pytest_mock import MockerFixture, AsyncMockType

from fastapi import Response, status
from authentication.interface import AuthTuple

from configuration import AppConfig
from app.endpoints.health import liveness_probe_get_method, readiness_probe_get_method


@pytest.fixture(name="mock_llama_stack_client_health")
def mock_llama_stack_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.
    """
    mock_holder_class = mocker.patch("app.endpoints.health.AsyncLlamaStackClientHolder")

    mock_client = mocker.AsyncMock()
    # Mock the version endpoint to return a known version
    mock_client.inspect.version.return_value = []

    # Create a mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client


@pytest.mark.asyncio
async def test_health_liveness(
    test_config: AppConfig,
    test_auth: AuthTuple,
) -> None:
    """Test that liveness probe endpoint is alive

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Real noop authentication is used
    - Response structure matches expected format

    Args:
        test_config: Loads test configuration
        test_auth: noop authentication tuple
    """
    _ = test_config

    response = await liveness_probe_get_method(auth=test_auth)

    # Verify that service is alive
    assert response.alive is True


@pytest.mark.asyncio
async def test_health_readiness_config_error(
    test_response: Response,
    test_auth: AuthTuple,
) -> None:
    """Test that readiness probe endpoint handles uninitialized client gracefully.

    This integration test verifies:
    - Endpoint handles missing client initialization gracefully
    - Error is caught and returned as proper health status
    - Service returns 503 status code for unhealthy state
    - Error message includes details about initialization failure

    Args:
        test_response: FastAPI response object
        test_auth: noop authentication tuple
    """
    result = await readiness_probe_get_method(auth=test_auth, response=test_response)

    # Verify HTTP status code is 503 (Service Unavailable)
    assert test_response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    # Verify that service returns error response when client not initialized
    assert result.ready is False
    assert "Providers not healthy" in result.reason
    assert "unknown" in result.reason

    # Verify the response includes provider error details
    assert len(result.providers) == 1
    assert result.providers[0].provider_id == "unknown"
    assert result.providers[0].status == "Error"
    assert (
        "AsyncLlamaStackClient has not been initialised" in result.providers[0].message
    )


@pytest.mark.asyncio
async def test_health_readiness(
    mock_llama_stack_client_health: AsyncMockType,
    test_response: Response,
    test_auth: AuthTuple,
) -> None:
    """Test that readiness probe endpoint returns readiness status.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Configuration values are correctly accessed
    - Real noop authentication is used
    - Response structure matches expected format

    Args:
        mock_llama_stack_client_health: Mocked Llama Stack client
        test_response: FastAPI response object
        test_auth: noop authentication tuple
    """
    _ = mock_llama_stack_client_health

    result = await readiness_probe_get_method(auth=test_auth, response=test_response)

    # Verify that service returns readiness response
    assert result.ready is True
    assert result.reason == "All providers are healthy"
    assert result.providers is not None
