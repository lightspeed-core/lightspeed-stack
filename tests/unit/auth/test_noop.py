"""Unit tests for functions defined in auth/noop.py"""

from fastapi import Request
from auth.noop import NoopAuthDependency
from constants import DEFAULT_USER_NAME, DEFAULT_USER_UID, NO_USER_TOKEN


async def test_noop_auth_dependency():
    """Test the NoopAuthDependency class with default user ID."""
    dependency = NoopAuthDependency()

    # Create a mock request without user_id
    request = Request(scope={"type": "http", "query_string": b""})

    # Call the dependency
    user_id, username, skip_userid_check, user_token = await dependency(request)

    # Assert the expected values
    assert user_id == DEFAULT_USER_UID
    assert username == DEFAULT_USER_NAME
    assert skip_userid_check is True
    assert user_token == NO_USER_TOKEN


async def test_noop_auth_dependency_custom_user_id():
    """Test the NoopAuthDependency class."""
    dependency = NoopAuthDependency()

    # Create a mock request
    request = Request(scope={"type": "http", "query_string": b"user_id=test-user"})

    # Call the dependency
    user_id, username, skip_userid_check, user_token = await dependency(request)

    # Assert the expected values
    assert user_id == "test-user"
    assert username == DEFAULT_USER_NAME
    assert skip_userid_check is True
    assert user_token == NO_USER_TOKEN
