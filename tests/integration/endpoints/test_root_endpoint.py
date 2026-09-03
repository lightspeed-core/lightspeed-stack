"""Integration tests for the /root endpoint."""

from collections.abc import Generator
from typing import Any

import pytest
from fastapi import Request, status
from ogx_client.types import VersionInfo
from pytest_mock import MockerFixture

from app.endpoints.root import root_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig


@pytest.fixture(name="mock_ogx_client")
def mock_ogx_client_fixture(
    mocker: MockerFixture,
) -> Generator[Any, None, None]:
    """Mock only the external Llama Stack client.

    This is the only external dependency we mock for integration tests,
    as it represents an external service call.

    Parameters:
    ----------
        mocker (pytest_mock.MockerFixture): The pytest-mock fixture used to apply the patch.

    Yields:
    ------
        AsyncMock: A mocked Llama Stack client configured for tests.
    """
    mock_holder_class = mocker.patch("app.endpoints.info.AsyncOgxClientHolder")

    mock_client = mocker.AsyncMock()
    # Mock the version endpoint to return a known version
    mock_client.inspect.version.return_value = VersionInfo(version="0.2.22")

    # Create a mock holder instance
    mock_holder_instance = mock_holder_class.return_value
    mock_holder_instance.get_client.return_value = mock_client

    yield mock_client


@pytest.mark.asyncio
async def test_root_endpoint(
    test_config: AppConfig,
    test_request: Request,
    test_auth: AuthTuple,
) -> None:
    """Test that Root endpoint returns index HTML page.

    This integration test verifies:
    - Endpoint handler
    - No authentication is used
    - Response structure matches expected format

    Parameters:
    ----------
        test_config (AppConfig): Loads root configuration
        test_request (Request): FastAPI request
        test_auth (AuthTuple): noop authentication tuple
    """
    # Fixtures with side effects (needed but not directly used)
    _ = test_config

    response = await root_endpoint_handler(auth=test_auth, request=test_request)

    assert response.media_type == "text/html"
    assert response.status_code == status.HTTP_200_OK
    # retrieve response body as a string
    body = response.body.decode("utf-8")
    assert "<title>Lightspeed Core Stack</title>" in body
    assert "<h1>Lightspeed Core Stack</h1>" in body
