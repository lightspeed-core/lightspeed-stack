"""Unit tests for the / endpoint handler."""

import pytest
from fastapi import Request

from app.endpoints.root import root_endpoint_handler
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_root_endpoint(mocker):
    """Test the root endpoint handler."""
    mock_authorization_resolvers(mocker)

    auth = ("test_user", "token", {})
    request = Request(
        scope={
            "type": "http",
        }
    )
    response = await root_endpoint_handler(auth=auth, request=request)
    assert response is not None
