"""Integration tests for the /authorized endpoint."""

import pytest

from authentication.interface import AuthTuple

from configuration import AppConfig
from app.endpoints.authorized import authorized_endpoint_handler
from constants import DEFAULT_USER_UID, DEFAULT_USER_NAME, DEFAULT_SKIP_USER_ID_CHECK


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
