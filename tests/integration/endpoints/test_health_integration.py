"""Integration tests for the /health endpoint."""

from typing import Generator, Any
import pytest
from pytest_mock import MockerFixture, AsyncMockType
from llama_stack.providers.datatypes import HealthStatus

from fastapi import Response, status
from authentication.interface import AuthTuple

from configuration import AppConfig
from app.endpoints.health import (
    liveness_probe_get_method,
    readiness_probe_get_method,
    get_providers_health_statuses,
)


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
async def test_health_readiness_provider_statuses(
    mock_llama_stack_client_health: AsyncMockType,
    mocker: MockerFixture,
) -> None:
    """Test that get_providers_health_statuses correctly retrieves and returns
       provider health statuses.

    This integration test verifies:
    - Function correctly retrieves provider list from Llama Stack client
    - Both healthy and unhealthy providers are properly processed
    - Provider health status, ID, and error messages are correctly mapped
    - Multiple providers with different health states are handled correctly

    Args:
        mock_llama_stack_client_health: Mocked Llama Stack client
        mocker: pytest-mock fixture for creating mock objects
    """
    # Arrange: Set up mock provider list with mixed health statuses
    mock_llama_stack_client_health.providers.list.return_value = [
        mocker.Mock(
            provider_id="unhealthy-provider-1",
            health={
                "status": HealthStatus.ERROR.value,
                "message": "Database connection failed",
            },
        ),
        mocker.Mock(
            provider_id="unhealthy-provider-2",
            health={
                "status": HealthStatus.ERROR.value,
                "message": "Service unavailable",
            },
        ),
        mocker.Mock(
            provider_id="healthy-provider", health={"status": "ok", "message": ""}
        ),
    ]

    # Call the function to retrieve provider health statuses
    result = await get_providers_health_statuses()

    # Verify providers
    assert result[0].provider_id == "unhealthy-provider-1"
    assert result[0].status == "Error"
    assert result[0].message == "Database connection failed"

    assert result[1].provider_id == "unhealthy-provider-2"
    assert result[1].status == "Error"
    assert result[1].message == "Service unavailable"

    assert result[2].provider_id == "healthy-provider"
    assert result[2].status == "ok"
    assert result[2].message == ""


@pytest.mark.asyncio
async def test_health_readiness_client_error(
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
