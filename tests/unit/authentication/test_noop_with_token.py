"""Unit tests for functions defined in authentication/noop_with_token.py"""

from typing import cast
from fastapi import Request, HTTPException
import pytest

from authentication.noop_with_token import NoopWithTokenAuthDependency
from constants import DEFAULT_USER_NAME, DEFAULT_USER_UID


async def test_noop_with_token_auth_dependency() -> None:
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


async def test_noop_with_token_auth_dependency_custom_user_id() -> None:
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


async def test_noop_with_token_auth_dependency_no_token() -> None:
    """
    Test if checks for Authorization header is in place.

    Test that NoopWithTokenAuthDependency raises an HTTPException when no
    Authorization header is present in the request.

    Asserts that the exception has a status code of 401 and a structured
    detail message indicating that no Authorization header was found.
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

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["response"] == ("Missing or invalid credentials provided by client")
    assert detail["cause"] == "No Authorization header found"


async def test_noop_with_token_auth_dependency_no_bearer() -> None:
    """Test the NoopWithTokenAuthDependency class with no token.

    Verify that NoopWithTokenAuthDependency raises an HTTPException when the
    Authorization header does not contain a Bearer token.

    Asserts the exception has status code 401 and that the detail contains:
    - response: "Missing or invalid credentials provided by client"
    - cause: "No token found in Authorization header"
    """
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

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["response"] == ("Missing or invalid credentials provided by client")
    assert detail["cause"] == "No token found in Authorization header"
