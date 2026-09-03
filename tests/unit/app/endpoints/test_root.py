"""Unit tests for the / endpoint handler."""

import pytest
from fastapi import Request
from pytest_mock import MockerFixture

from app.endpoints.root import root_endpoint_handler
from authentication.interface import AuthTuple
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_root_endpoint(mocker: MockerFixture) -> None:
    """Test the root endpoint handler."""
    mock_authorization_resolvers(mocker)

    auth = AuthTuple(("test_user_id", "test_user_name", False, "token"))
    request = Request(
        scope={
            "type": "http",
        }
    )
    response = await root_endpoint_handler(auth=auth, request=request)
    assert response is not None
