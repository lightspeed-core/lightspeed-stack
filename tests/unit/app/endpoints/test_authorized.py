"""Unit tests for the /authorized REST API endpoint."""

from unittest.mock import AsyncMock

import pytest
from fastapi import Request, HTTPException

from app.endpoints.authorized import authorized_endpoint_handler


def test_authorized_endpoint(mocker):
    """Test the authorized endpoint handler."""
    # Mock the auth dependency to return a user ID and username
    auth_dependency_mock = AsyncMock()
    auth_dependency_mock.return_value = ("test-id", "test-user", None)
    mocker.patch(
        "app.endpoints.authorized.auth_dependency", side_effect=auth_dependency_mock
    )

    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
        }
    )

    response = authorized_endpoint_handler(request)

    assert response.model_dump() == {
        "user_id": "test-id",
        "username": "test-user",
    }


def test_authorized_unauthorized(mocker):
    """Test the authorized endpoint handler with a custom user ID."""
    auth_dependency_mock = AsyncMock()
    auth_dependency_mock.side_effect = HTTPException(
        status_code=403, detail="User is not authorized"
    )
    mocker.patch(
        "app.endpoints.authorized.auth_dependency", side_effect=auth_dependency_mock
    )

    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        authorized_endpoint_handler(request)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "User is not authorized"
