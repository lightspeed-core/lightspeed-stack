# pylint: disable=redefined-outer-name

"""Unit tests for functions defined in auth/noop_with_token.py"""

import time

import pytest
from fastapi import HTTPException, Request
from pydantic import AnyHttpUrl
from authlib.jose import JsonWebKey, JsonWebToken

from auth.jwk_token import JwkTokenAuthDependency, _jwk_cache
from models.config import JwkConfiguration, JwtConfiguration

TEST_USER_ID = "test-user-123"
TEST_USER_NAME = "testuser"


@pytest.fixture
def token_header(signing_keys):
    """A sample token header."""
    return {"alg": "RS256", "typ": "JWT", "kid": signing_keys["kid"]}


@pytest.fixture
def token_payload():
    """A sample token payload with the default user_id and username claims."""
    return {
        "user_id": TEST_USER_ID,
        "username": TEST_USER_NAME,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }


def make_keys():
    """Generate a key pair for testing purposes."""
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    return {
        "private_key": key,
        "public_key": key.get_public_key(),
        "kid": key.thumbprint(),
    }


@pytest.fixture
def signing_keys():
    """Default key pair for signing tokens."""
    return make_keys()


@pytest.fixture
def other_signing_keys():
    """Same as signing_keys, but generates a different key pair by being its own fixture."""
    return make_keys()


@pytest.fixture
def valid_token(signing_keys, token_header, token_payload):
    """A token that is valid and signed with the signing keys."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    return jwt_instance.encode(
        token_header, token_payload, signing_keys["private_key"]
    ).decode()


@pytest.fixture(autouse=True)
def clear_jwk_cache():
    """Clear the global JWK cache before each test."""
    _jwk_cache.clear()
    yield
    _jwk_cache.clear()


@pytest.fixture
def mocked_signing_keys_server(mocker, signing_keys):
    """A fake server to serve our signing keys as JWKs."""
    mock_session_class = mocker.patch("aiohttp.ClientSession")
    mock_response = mocker.AsyncMock()

    # Create JWK dict from private key as public key
    jwk_dict = signing_keys["private_key"].as_dict(private=False)
    jwk_dict["kid"] = signing_keys["kid"]
    jwk_dict["alg"] = "RS256"
    mock_response.json.return_value = {
        "keys": [jwk_dict],
    }
    mock_response.raise_for_status = mocker.MagicMock(return_value=None)

    # Create mock session instance that acts as async context manager
    mock_session_instance = mocker.AsyncMock()
    mock_session_instance.__aenter__ = mocker.AsyncMock(
        return_value=mock_session_instance
    )
    mock_session_instance.__aexit__ = mocker.AsyncMock(return_value=None)

    # Mock the get method to return a context manager
    mock_get_context = mocker.AsyncMock()
    mock_get_context.__aenter__ = mocker.AsyncMock(return_value=mock_response)
    mock_get_context.__aexit__ = mocker.AsyncMock(return_value=None)

    mock_session_instance.get = mocker.MagicMock(return_value=mock_get_context)
    mock_session_class.return_value = mock_session_instance

    return mock_session_class


@pytest.fixture
def default_jwk_configuration():
    """Default JwkConfiguration for testing."""
    return JwkConfiguration(
        url=AnyHttpUrl("https://this#isgonnabemocked.com/jwks.json"),
        jwt_configuration=JwtConfiguration(
            # Should default to:
            # user_id_claim="user_id", username_claim="username"
        ),
    )


@pytest.fixture
def dummy_request():
    """A dummy request object for testing. Headers will be set later."""
    return Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [],
        },
    )


def set_auth_header(request, token):
    """Helper function to set the Authorization header in a request."""
    request.scope["headers"].append((b"authorization", f"Bearer {token}".encode()))


def ensure_test_user_id_and_name(auth_tuple, token):
    """Utility to ensure that the values in the auth tuple match the test values."""
    user_id, username, tuple_token = auth_tuple
    assert user_id == TEST_USER_ID
    assert username == TEST_USER_NAME
    assert tuple_token == token


async def test_valid(
    default_jwk_configuration,
    mocked_signing_keys_server,
    dummy_request,
    valid_token,
):
    """Test with a valid token."""
    _ = mocked_signing_keys_server

    set_auth_header(dummy_request, valid_token)

    dependency = JwkTokenAuthDependency(default_jwk_configuration)
    auth_tuple = await dependency(dummy_request)

    # Assert the expected values
    ensure_test_user_id_and_name(auth_tuple, valid_token)


@pytest.fixture
def expired_token(signing_keys, token_header, token_payload):
    """Fixture to provide an expired token."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    token_payload["exp"] = int(time.time()) - 3600  # Set expiration in the past
    return jwt_instance.encode(
        token_header, token_payload, signing_keys["private_key"]
    ).decode()


async def test_expired(
    default_jwk_configuration,
    mocked_signing_keys_server,
    dummy_request,
    expired_token,
):
    """Test with an expired token."""
    _ = mocked_signing_keys_server

    set_auth_header(dummy_request, expired_token)

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    # Assert that an HTTPException is raised when the token is expired
    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request)

    assert "Token has expired" in str(exc_info.value)
    assert exc_info.value.status_code == 401


@pytest.fixture
def invalid_token(other_signing_keys, token_header, token_payload):
    """A token that is signed with different keys than the signing keys."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    return jwt_instance.encode(
        token_header, token_payload, other_signing_keys["private_key"]
    ).decode()


async def test_invalid(
    default_jwk_configuration,
    mocked_signing_keys_server,
    dummy_request,
    invalid_token,
):
    """Test with an invalid token."""
    _ = mocked_signing_keys_server

    set_auth_header(dummy_request, invalid_token)

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request)

    assert "Invalid token" in str(exc_info.value)
    assert exc_info.value.status_code == 401


async def test_no_auth_header(
    default_jwk_configuration,
    mocked_signing_keys_server,
    dummy_request,
):
    """Test with no Authorization header."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No Authorization header found"


async def test_no_bearer(
    default_jwk_configuration,
    mocked_signing_keys_server,
    dummy_request,
):
    """Test with Authorization header that does not start with Bearer."""
    _ = mocked_signing_keys_server

    dummy_request.scope["headers"].append((b"authorization", b"NotBearer anything"))

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No token found in Authorization header"


async def test_no_jwk_url(
    default_jwk_configuration,
):
    """Test with a JwkConfiguration that has no URL."""
    default_jwk_configuration.url = None

    with pytest.raises(ValueError) as exc_info:
        JwkConfiguration.model_validate(default_jwk_configuration)

    assert "JWK URL must be specified" in str(exc_info.value)


@pytest.fixture
def no_user_id_token(signing_keys, token_payload, token_header):
    """Token without a user_id claim."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    # Modify the token payload to include different claims
    del token_payload["user_id"]

    return jwt_instance.encode(
        token_header, token_payload, signing_keys["private_key"]
    ).decode()


async def test_no_user_id(
    default_jwk_configuration,
    mocked_signing_keys_server,
    dummy_request,
    no_user_id_token,
):
    """Test with a token that has no user_id claim."""
    _ = mocked_signing_keys_server

    set_auth_header(dummy_request, no_user_id_token)

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request)

    assert exc_info.value.status_code == 401
    assert "user_id" in str(exc_info.value.detail) and "missing" in str(
        exc_info.value.detail
    )


@pytest.fixture
def no_username_token(signing_keys, token_payload, token_header):
    """Token without a user_id claim."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    # Modify the token payload to include different claims
    del token_payload["username"]

    return jwt_instance.encode(
        token_header, token_payload, signing_keys["private_key"]
    ).decode()


async def test_no_username(
    default_jwk_configuration,
    mocked_signing_keys_server,
    dummy_request,
    no_username_token,
):
    """Test with a token that has no username claim."""
    _ = mocked_signing_keys_server

    set_auth_header(dummy_request, no_username_token)

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request)

    assert exc_info.value.status_code == 401
    assert "username" in str(exc_info.value.detail) and "missing" in str(
        exc_info.value.detail
    )


@pytest.fixture
def custom_claims_token(signing_keys, token_payload, token_header):
    """Token with custom claims."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])

    del token_payload["user_id"]
    del token_payload["username"]

    # Add custom claims
    token_payload["id_of_the_user"] = TEST_USER_ID
    token_payload["name_of_the_user"] = TEST_USER_NAME

    return jwt_instance.encode(
        token_header, token_payload, signing_keys["private_key"]
    ).decode()


@pytest.fixture
def custom_claims_configuration(default_jwk_configuration):
    """Configuration for custom claims."""
    # Create a copy of the default configuration
    custom_config = default_jwk_configuration.model_copy()

    # Set custom claims
    custom_config.jwt_configuration.user_id_claim = "id_of_the_user"
    custom_config.jwt_configuration.username_claim = "name_of_the_user"

    return custom_config


async def test_custom_claims(
    custom_claims_configuration,
    mocked_signing_keys_server,
    dummy_request,
    custom_claims_token,
):
    """Test with a token that has custom claims."""
    _ = mocked_signing_keys_server

    set_auth_header(dummy_request, custom_claims_token)

    dependency = JwkTokenAuthDependency(custom_claims_configuration)

    auth_tuple = await dependency(dummy_request)

    # Assert the expected values
    ensure_test_user_id_and_name(auth_tuple, custom_claims_token)
