# pylint: disable=redefined-outer-name

"""Unit tests for functions defined in authentication/api_key_token.py"""

import pytest
from fastapi import HTTPException, Request
from pydantic import SecretStr

from authentication.api_key_token import APIKeyTokenAuthDependency
from constants import DEFAULT_USER_NAME, DEFAULT_USER_UID
from models.config import APIKeyTokenConfiguration


@pytest.fixture
def default_api_key_token_configuration() -> APIKeyTokenConfiguration:
    """Default APIKeyTokenConfiguration for testing.

    Provide a default APIKeyTokenConfiguration for tests.

    Returns:
        APIKeyTokenConfiguration: configuration with `api_key` set to
        `SecretStr("some-test-api-key")`.
    """
    return APIKeyTokenConfiguration(api_key=SecretStr("some-test-api-key"))


async def test_api_key_with_token_auth_dependency(
    default_api_key_token_configuration: APIKeyTokenConfiguration,
) -> None:
    """Test the APIKeyTokenAuthDependency class with default user ID."""
    dependency = APIKeyTokenAuthDependency(default_api_key_token_configuration)

    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer some-test-api-key"),
            ],
        },
    )

    # Call the dependency
    user_id, username, skip_userid_check, user_token = await dependency(request)

    # Assert the expected values
    assert user_id == DEFAULT_USER_UID
    assert username == DEFAULT_USER_NAME
    assert skip_userid_check is True
    assert user_token == default_api_key_token_configuration.api_key.get_secret_value()


async def test_api_key_with_token_auth_dependency_no_token(
    default_api_key_token_configuration: APIKeyTokenConfiguration,
) -> None:
    """
    Test if checks for Authorization header is in place.

    Test that APIKeyTokenConfiguration raises an HTTPException when no
    Authorization header is present in the request.

    Asserts that the exception has a status code of 401 and the detail message
    "No Authorization header found".
    """
    dependency = APIKeyTokenAuthDependency(default_api_key_token_configuration)

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
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["cause"] == "No Authorization header found"


async def test_api_key_with_token_auth_dependency_no_bearer(
    default_api_key_token_configuration: APIKeyTokenConfiguration,
) -> None:
    """Test the APIKeyTokenConfiguration class with no token."""
    dependency = APIKeyTokenAuthDependency(default_api_key_token_configuration)

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
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["cause"] == "No token found in Authorization header"


async def test_api_key_with_token_auth_dependency_invalid(
    default_api_key_token_configuration: APIKeyTokenConfiguration,
) -> None:
    """Test the APIKeyTokenAuthDependency class with default user ID,
    where token's value is not the one from configuration."""
    dependency = APIKeyTokenAuthDependency(default_api_key_token_configuration)

    request = Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [
                (b"authorization", b"Bearer another-test-api-key"),
            ],
        },
    )

    # Assert that an HTTPException is raised when the API key is invalid.
    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API Key"
