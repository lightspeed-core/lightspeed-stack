"""Unit tests for functions defined in auth/noop_with_token.py"""

from fastapi import Request, HTTPException
import pytest

from auth.noop_with_token import NoopWithTokenAuthDependency
from constants import DEFAULT_USER_NAME, DEFAULT_USER_UID


async def test_noop_with_token_auth_dependency():
    """Test the NoopWithTokenAuthDependency class with default user ID."""
    dependency = NoopWithTokenAuthDependency()

    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer spongebob-token"),
            ],
        },
    )

    # Call the dependency
    user_id, username, skip_userid_check, user_token = await dependency(request)

    # Assert the expected values
    assert user_id == DEFAULT_USER_UID
    assert username == DEFAULT_USER_NAME
    assert skip_userid_check is True
    assert user_token == "spongebob-token"


async def test_noop_with_token_auth_dependency_custom_user_id():
    """Test the NoopWithTokenAuthDependency class with custom user ID."""
    dependency = NoopWithTokenAuthDependency()

    # Create a mock request
    request = Request(
        scope={
            "type": "http",
            "query_string": b"user_id=test-user",
            "headers": [
                (b"authorization", b"Bearer spongebob-token"),
            ],
        },
    )

    # Call the dependency
    user_id, username, skip_userid_check, user_token = await dependency(request)

    # Assert the expected values
    assert user_id == "test-user"
    assert username == DEFAULT_USER_NAME
    assert skip_userid_check is True
    assert user_token == "spongebob-token"


async def test_noop_with_token_auth_dependency_no_token():
    """
    Test if checks for Authorization header is in place.

    Test that NoopWithTokenAuthDependency raises an HTTPException when no
    Authorization header is present in the request.

    Asserts that the exception has a status code of 400 and the detail message
    "No Authorization header found".
    """
    dependency = NoopWithTokenAuthDependency()

    # Create a mock request without token
    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [],
        },
    )

    # Assert that an HTTPException is raised when no Authorization header is found
    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No Authorization header found"


async def test_noop_with_token_auth_dependency_no_bearer():
    """Test the NoopWithTokenAuthDependency class with no token."""
    dependency = NoopWithTokenAuthDependency()

    # Create a mock request without token
    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [(b"authorization", b"NotBearer anything")],
        },
    )

    # Assert that an HTTPException is raised when no Authorization header is found
    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No token found in Authorization header"
