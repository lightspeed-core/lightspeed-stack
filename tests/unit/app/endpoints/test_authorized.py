"""Unit tests for the /authorized REST API endpoint."""

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from app.endpoints.authorized import authorized_endpoint_handler
from authentication.utils import extract_user_token

MOCK_AUTH = ("test-id", "test-user", True, "token")


@pytest.mark.asyncio
async def test_authorized_endpoint() -> None:
    """Test the authorized endpoint handler."""
    response = await authorized_endpoint_handler(auth=MOCK_AUTH)

    assert response.model_dump() == {
        "user_id": "test-id",
        "username": "test-user",
        "skip_userid_check": True,
    }


@pytest.mark.asyncio
async def test_authorized_unauthorized() -> None:
    """Test the authorized endpoint handler behavior under unauthorized conditions.

    Note: In real scenarios, FastAPI's dependency injection would prevent the handler
    from being called if auth fails. This test simulates what would happen if somehow
    invalid auth data reached the handler.
    """
    # Test scenario 1: None auth data (complete auth failure)
    with pytest.raises(TypeError):
        # This would occur if auth dependency somehow returned None
        await authorized_endpoint_handler(
            auth=None  # pyright:ignore[reportArgumentType]
        )

    # Test scenario 2: Invalid auth tuple structure
    with pytest.raises(ValueError):
        # This would occur if auth dependency returned malformed data
        await authorized_endpoint_handler(
            auth=("incomplete-auth-data",)  # pyright:ignore[reportArgumentType]
        )


@pytest.mark.asyncio
async def test_authorized_dependency_unauthorized() -> None:
    """Test that auth dependency raises HTTPException with 403 for unauthorized access.

    Verify extract_user_token raises HTTPException with status code 401 and the
    expected detail for missing or malformed Authorization headers.

    Checks two scenarios:
    - Missing Authorization header: HTTPException.status_code == 401,
      detail["response"] == "Missing or invalid credentials provided by
      client", detail["cause"] == "No Authorization header found".
    - Invalid Authorization format: HTTPException.status_code == 401,
      detail["response"] == "Missing or invalid credentials provided by
      client", detail["cause"] == "No token found in Authorization header".
    """
    # Test the auth utility function that would be called by auth dependencies
    # This simulates the unauthorized scenario that would prevent the handler from being called

    headers_no_auth = Headers({})
    with pytest.raises(HTTPException) as exc_info:
        extract_user_token(headers_no_auth)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["response"] == (  # type: ignore
        "Missing or invalid credentials provided by client"
    )
    assert exc_info.value.detail["cause"] == (  # type: ignore
        "No Authorization header found"
    )

    headers_invalid_auth = Headers({"Authorization": "InvalidFormat"})
    with pytest.raises(HTTPException) as exc_info:
        extract_user_token(headers_invalid_auth)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["response"] == (  # type: ignore
        "Missing or invalid credentials provided by client"
    )
    assert exc_info.value.detail["cause"] == (  # type: ignore
        "No token found in Authorization header"
    )
