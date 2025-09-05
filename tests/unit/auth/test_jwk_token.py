# pylint: disable=redefined-outer-name

"""Unit tests for functions defined in auth/jwk_token.py"""

import time

import pytest
from fastapi import HTTPException, Request
from pydantic import AnyHttpUrl
from authlib.jose import JsonWebKey, JsonWebToken

from auth.jwk_token import JwkTokenAuthDependency, _jwk_cache
from constants import DEFAULT_USER_NAME, DEFAULT_USER_UID, NO_USER_TOKEN
from models.config import JwkConfiguration, JwtConfiguration

TEST_USER_ID = "test-user-123"
TEST_USER_NAME = "testuser"


@pytest.fixture
def token_header(single_key_set):
    """A sample token header."""
    return {"alg": "RS256", "typ": "JWT", "kid": single_key_set[0]["kid"]}


@pytest.fixture
def token_payload():
    """A sample token payload with the default user_id and username claims."""
    return {
        "user_id": TEST_USER_ID,
        "username": TEST_USER_NAME,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }


def make_key():
    """Generate a key pair for testing purposes."""
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    return {
        "private_key": key,
        "public_key": key.get_public_key(),
        "kid": key.thumbprint(),
    }


@pytest.fixture
def single_key_set():
    """Default single-key set for signing tokens."""
    return [make_key()]


@pytest.fixture
def another_single_key_set():
    """Same as single_key_set, but generates a different key pair by being its own fixture."""
    return [make_key()]


@pytest.fixture
def valid_token(single_key_set, token_header, token_payload):
    """A token that is valid and signed with the signing keys."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    return jwt_instance.encode(
        token_header, token_payload, single_key_set[0]["private_key"]
    ).decode()


@pytest.fixture(autouse=True)
def clear_jwk_cache():
    """Clear the global JWK cache before each test."""
    _jwk_cache.clear()
    yield
    _jwk_cache.clear()


def make_signing_server(mocker, key_set, algorithms):
    """A fake server to serve our signing keys as JWKs."""
    mock_session_class = mocker.patch("aiohttp.ClientSession")
    mock_response = mocker.AsyncMock()

    # Create JWK dict from private key as public key
    keys = [
        {
            **key["private_key"].as_dict(private=False),
            "kid": key["kid"],
            "alg": alg,
        }
        for alg, key in zip(algorithms, key_set)
    ]
    mock_response.json.return_value = {
        "keys": keys,
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
def mocked_signing_keys_server(mocker, single_key_set):
    """Single-key signing server."""
    return make_signing_server(mocker, single_key_set, ["RS256"])


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


def dummy_request(token):
    """Generate a dummy request with a given token."""
    return Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        },
    )


@pytest.fixture
def no_token_request():
    """Dummy request with no token."""
    return Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [],
        },
    )


@pytest.fixture
def not_bearer_token_request():
    """Dummy request with no token."""
    return Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [(b"authorization", b"NotBearer anything")],
        },
    )


def set_auth_header(request: Request, token: str):
    """Helper function to set the Authorization header in a request."""
    new_headers = [
        (k, v) for k, v in request.scope["headers"] if k.lower() != b"authorization"
    ]
    new_headers.append((b"authorization", token.encode()))
    request.scope["headers"] = new_headers


def ensure_test_user_id_and_name(auth_tuple, expected_token):
    """Utility to ensure that the values in the auth tuple match the test values."""
    user_id, username, skip_userid_check, token = auth_tuple
    assert user_id == TEST_USER_ID
    assert username == TEST_USER_NAME
    assert skip_userid_check is False
    assert token == expected_token


async def test_valid(
    default_jwk_configuration,
    mocked_signing_keys_server,
    valid_token,
):
    """Test with a valid token."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)
    auth_tuple = await dependency(dummy_request(valid_token))

    # Assert the expected values
    ensure_test_user_id_and_name(auth_tuple, valid_token)


@pytest.fixture
def expired_token(single_key_set, token_header, token_payload):
    """An well-signed yet expired token."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    token_payload["exp"] = int(time.time()) - 3600  # Set expiration in the past
    return jwt_instance.encode(
        token_header, token_payload, single_key_set[0]["private_key"]
    ).decode()


async def test_expired(
    default_jwk_configuration,
    mocked_signing_keys_server,
    expired_token,
):
    """Test with an expired token."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    # Assert that an HTTPException is raised when the token is expired
    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request(expired_token))

    assert "Token has expired" in str(exc_info.value)
    assert exc_info.value.status_code == 401


@pytest.fixture
def invalid_token(another_single_key_set, token_header, token_payload):
    """A token that is signed with different keys than the signing keys."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    return jwt_instance.encode(
        token_header, token_payload, another_single_key_set[0]["private_key"]
    ).decode()


async def test_invalid(
    default_jwk_configuration,
    mocked_signing_keys_server,
    invalid_token,
):
    """Test with an invalid token."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request(invalid_token))

    assert "Invalid token" in str(exc_info.value)
    assert exc_info.value.status_code == 401


async def test_no_auth_header(
    default_jwk_configuration,
    mocked_signing_keys_server,
    no_token_request,
):
    """Test with no Authorization header."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    user_id, username, skip_userid_check, token_claims = await dependency(
        no_token_request
    )

    assert user_id == DEFAULT_USER_UID
    assert username == DEFAULT_USER_NAME
    assert skip_userid_check is True
    assert token_claims == NO_USER_TOKEN


async def test_no_bearer(
    default_jwk_configuration,
    mocked_signing_keys_server,
    not_bearer_token_request,
):
    """Test with Authorization header that does not start with Bearer."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(not_bearer_token_request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No token found in Authorization header"


@pytest.fixture
def no_user_id_token(single_key_set, token_payload, token_header):
    """Token without a user_id claim."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    # Modify the token payload to include different claims
    del token_payload["user_id"]

    return jwt_instance.encode(
        token_header, token_payload, single_key_set[0]["private_key"]
    ).decode()


async def test_no_user_id(
    default_jwk_configuration,
    mocked_signing_keys_server,
    no_user_id_token,
):
    """Test with a token that has no user_id claim."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request(no_user_id_token))

    assert exc_info.value.status_code == 401
    assert "user_id" in str(exc_info.value.detail) and "missing" in str(
        exc_info.value.detail
    )


@pytest.fixture
def no_username_token(single_key_set, token_payload, token_header):
    """Token without a username claim."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])
    # Modify the token payload to include different claims
    del token_payload["username"]

    return jwt_instance.encode(
        token_header, token_payload, single_key_set[0]["private_key"]
    ).decode()


async def test_no_username(
    default_jwk_configuration,
    mocked_signing_keys_server,
    no_username_token,
):
    """Test with a token that has no username claim."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request(no_username_token))

    assert exc_info.value.status_code == 401
    assert "username" in str(exc_info.value.detail) and "missing" in str(
        exc_info.value.detail
    )


@pytest.fixture
def custom_claims_token(single_key_set, token_payload, token_header):
    """Token with custom claims."""
    jwt_instance = JsonWebToken(algorithms=["RS256"])

    del token_payload["user_id"]
    del token_payload["username"]

    # Add custom claims
    token_payload["id_of_the_user"] = TEST_USER_ID
    token_payload["name_of_the_user"] = TEST_USER_NAME

    return jwt_instance.encode(
        token_header, token_payload, single_key_set[0]["private_key"]
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
    custom_claims_token,
):
    """Test with a token that has custom claims."""
    _ = mocked_signing_keys_server

    dependency = JwkTokenAuthDependency(custom_claims_configuration)

    auth_tuple = await dependency(dummy_request(custom_claims_token))

    # Assert the expected values
    ensure_test_user_id_and_name(auth_tuple, custom_claims_token)


@pytest.fixture
def token_header_256_1(multi_key_set):
    """A sample token header for RS256 using multi_key_set."""
    return {"alg": "RS256", "typ": "JWT", "kid": multi_key_set[0]["kid"]}


@pytest.fixture
def token_header_256_2(multi_key_set):
    """A sample token header for RS256 using multi_key_set."""
    return {"alg": "RS256", "typ": "JWT", "kid": multi_key_set[1]["kid"]}


@pytest.fixture
def token_header_384(multi_key_set):
    """A sample token header."""
    return {"alg": "RS384", "typ": "JWT", "kid": multi_key_set[2]["kid"]}


@pytest.fixture
def token_header_256_no_kid():
    """RS256 no kid."""
    return {"alg": "RS256", "typ": "JWT"}


@pytest.fixture
def token_header_384_no_kid():
    """RS384 no kid."""
    return {"alg": "RS384", "typ": "JWT"}


@pytest.fixture
def multi_key_set():
    """Default multi-key set for signing tokens."""
    return [make_key(), make_key(), make_key()]


@pytest.fixture
def valid_tokens(
    multi_key_set,
    token_header_256_1,
    token_header_256_2,
    token_payload,
    token_header_384,
):
    """Generate valid tokens for each key in the multi-key set."""
    key_for_256_1 = multi_key_set[0]
    key_for_256_2 = multi_key_set[1]
    key_for_384 = multi_key_set[2]

    jwt_instance1 = JsonWebToken(algorithms=["RS256"])
    token1 = jwt_instance1.encode(
        token_header_256_1, token_payload, key_for_256_1["private_key"]
    ).decode()

    jwt_instance2 = JsonWebToken(algorithms=["RS256"])
    token2 = jwt_instance2.encode(
        token_header_256_2, token_payload, key_for_256_2["private_key"]
    ).decode()

    jwt_instance3 = JsonWebToken(algorithms=["RS384"])
    token3 = jwt_instance3.encode(
        token_header_384, token_payload, key_for_384["private_key"]
    ).decode()

    return token1, token2, token3


@pytest.fixture
def valid_tokens_no_kid(
    multi_key_set, token_header_256_no_kid, token_payload, token_header_384_no_kid
):
    """Generate valid tokens for each key in the multi-key set without a kid."""
    key_for_256_1 = multi_key_set[0]
    key_for_256_2 = multi_key_set[1]
    key_for_384 = multi_key_set[2]

    jwt_instance1 = JsonWebToken(algorithms=["RS256"])
    token1 = jwt_instance1.encode(
        token_header_256_no_kid, token_payload, key_for_256_1["private_key"]
    ).decode()

    jwt_instance2 = JsonWebToken(algorithms=["RS256"])
    token2 = jwt_instance2.encode(
        token_header_256_no_kid, token_payload, key_for_256_2["private_key"]
    ).decode()

    jwt_instance3 = JsonWebToken(algorithms=["RS384"])
    token3 = jwt_instance3.encode(
        token_header_384_no_kid, token_payload, key_for_384["private_key"]
    ).decode()

    return token1, token2, token3


@pytest.fixture
def multi_key_signing_server(mocker, multi_key_set):
    """Multi-key signing server."""
    return make_signing_server(mocker, multi_key_set, ["RS256", "RS256", "RS384"])


async def test_multi_key_valid(
    default_jwk_configuration,
    multi_key_signing_server,
    valid_tokens,
):
    """Test with valid tokens from a multi-key set."""
    _ = multi_key_signing_server

    token1, token2, token3 = valid_tokens

    dependency = JwkTokenAuthDependency(default_jwk_configuration)
    auth_tuple = await dependency(dummy_request(token1))
    ensure_test_user_id_and_name(auth_tuple, token1)

    auth_tuple = await dependency(dummy_request(token2))
    ensure_test_user_id_and_name(auth_tuple, token2)

    auth_tuple = await dependency(dummy_request(token3))
    ensure_test_user_id_and_name(auth_tuple, token3)


async def test_multi_key_no_kid(
    default_jwk_configuration,
    multi_key_signing_server,
    valid_tokens_no_kid,
):
    """Test with valid tokens from a multi-key set without a kid."""
    _ = multi_key_signing_server

    token1, token2, token3 = valid_tokens_no_kid

    dependency = JwkTokenAuthDependency(default_jwk_configuration)

    auth_tuple = await dependency(dummy_request(token1))
    ensure_test_user_id_and_name(auth_tuple, token1)

    # Token 2 should fail, as it has no kid and multiple keys for its algorithm are present
    # and the one that signed it is not the first key

    with pytest.raises(HTTPException) as exc_info:
        await dependency(dummy_request(token2))
    assert exc_info.value.status_code == 401

    # Token 3 will succeed, as it has a different algorithm (RS384) and there's only one key
    # for that algorithm in the multi-key set

    auth_tuple = await dependency(dummy_request(token3))
    ensure_test_user_id_and_name(auth_tuple, token3)
