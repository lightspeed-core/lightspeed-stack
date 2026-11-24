"""Integration tests for the /root endpoint."""

import pytest
from fastapi import Request, status

from app.endpoints.root import root_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig


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
