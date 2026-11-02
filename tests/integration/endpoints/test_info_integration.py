"""Integration tests for the /info endpoint."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import Request
from ogx_client import ApiException
from pytest_mock import AsyncMockType, MockerFixture

from app.endpoints.info import info_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from version import __version__


@pytest.fixture(name="mock_get_ogx_client")
def mock_get_ogx_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock the accessor of the external OGX client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call. The /info endpoint must
    not use it.

    Parameters:
    ----------
        mocker (pytest_mock.MockerFixture): The pytest-mock fixture used to apply the patch.

    Yields:
    ------
        Mock: The patched AsyncOgxClientHolder.get_client.

    """
    yield mocker.patch("client.ogx.AsyncOgxClientHolder.get_client")


@pytest.mark.asyncio
async def test_info_endpoint_returns_service_information(
    test_config: AppConfig,
    mock_get_ogx_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that info endpoint returns correct service information.

    This integration test verifies:
    - Endpoint handler integrates with configuration system
    - Configuration values are correctly accessed
    - OGX client is not called
    - Real noop authentication is used
    - Response structure matches expected format

    Parameters:
    ----------
        test_config: Loads real configuration (required for endpoint to access config)
        mock_get_ogx_client: Mocked OGX client accessor
        test_request: FastAPI request
        test_auth: noop authentication tuple

    Returns:
    -------
        None

    """
    # Fixtures with side effects (needed but not directly used)
    _ = test_config

    response = await info_endpoint_handler(auth=test_auth, request=test_request)

    # Verify values from real configuration
    assert response.name == "foo bar baz"  # From lightspeed-stack.yaml
    assert response.service_version == __version__

    # Verify the response has nothing else in it
    assert set(response.model_dump()) == {"name", "service_version"}

    # Verify the OGX client was not used
    mock_get_ogx_client.assert_not_called()


@pytest.mark.asyncio
async def test_info_endpoint_does_not_depend_on_ogx(
    test_config: AppConfig,
    mock_get_ogx_client: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that info endpoint answers while OGX is unavailable.

    This integration test verifies:
    - A failing OGX connection does not reach the endpoint
    - The service identity is still returned

    Parameters:
    ----------
        test_config: Loads real configuration (required for endpoint to access config)
        mock_get_ogx_client: Mocked OGX client accessor
        test_request: FastAPI request
        test_auth: noop authentication tuple

    """
    # Configure mock to raise connection error
    mock_get_ogx_client.side_effect = ApiException(status=None)

    response = await info_endpoint_handler(auth=test_auth, request=test_request)

    assert response.name == test_config.configuration.name
    assert response.service_version == __version__


@pytest.mark.asyncio
async def test_info_endpoint_uses_configuration_values(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that info endpoint correctly uses configuration values.

    This integration test verifies:
    - Configuration is properly loaded and accessible
    - Endpoint reads configuration values correctly
    - Service name from config appears in response

    Parameters:
    ----------
        test_config: Loads real configuration (required for endpoint to access config)
        test_request: Real FastAPI request
        test_auth: Real noop authentication tuple

    """
    response = await info_endpoint_handler(auth=test_auth, request=test_request)

    # Verify service name comes from configuration
    assert response.name == test_config.configuration.name
    assert response.name == "foo bar baz"
