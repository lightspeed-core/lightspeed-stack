"""Manage authentication flow for FastAPI endpoints with JWK based JWT auth."""

import json
from asyncio import Lock
from typing import Any, Callable

import aiohttp
from authlib.jose import JsonWebKey, Key, KeySet, jwt
from authlib.jose.errors import (
    BadSignatureError,
    DecodeError,
    ExpiredTokenError,
    JoseError,
)
from cachetools import TTLCache
from fastapi import HTTPException, Request

from authentication.interface import NO_AUTH_TUPLE, AuthInterface, AuthTuple
from authentication.utils import extract_user_token
from constants import (
    DEFAULT_VIRTUAL_PATH,
)
from models.config import JwkConfiguration
from models.responses import UnauthorizedResponse
from log import get_logger

logger = get_logger(__name__)

# Global JWK registry to avoid re-fetching JWKs for each request. Cached for 1
# hour, keys are unlikely to change frequently.
_jwk_cache: TTLCache[str, KeySet] = TTLCache(maxsize=3, ttl=3600)
# Ideally this would be an RWLock, but it would require adding a dependency on
# aiorwlock
_jwk_cache_lock = Lock()


async def get_jwk_set(url: str) -> KeySet:
    """Fetch the JWK set from the cache, or fetch it from the URL if not cached.

    Retrieve a JWK KeySet from the in-memory cache or fetch and cache it from the provided URL.

    Returns:
        KeySet: The JWK `KeySet` corresponding to the URL.
    """
    async with _jwk_cache_lock:
        if url not in _jwk_cache:
            async with aiohttp.ClientSession() as session:
                # TODO(omertuc): handle connection errors, timeouts, etc.
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    _jwk_cache[url] = JsonWebKey.import_key_set(await resp.json())
        return _jwk_cache[url]


class KeyNotFoundError(Exception):
    """Exception raised when a key is not found in the JWK set based on kid/alg."""


def key_resolver_func(
    jwk_set: KeySet,
) -> Callable[[dict[str, Any], dict[str, Any]], Key]:
    """
    Create a JWK key resolver used to locate the verification key from a KeySet.

    The returned callable accepts a JWT header and payload and selects a key from the provided
    jwk_set. If the header contains a `kid`, the resolver returns the single key with that `kid`
    and verifies the key's `alg` matches the header `alg`. If `kid` is absent, the resolver
    returns the first key that matches the header `alg`. The resolver raises `KeyNotFoundError`
    if no suitable key is found or if multiple keys are found for the same `kid`.

    Parameters:
        jwk_set (KeySet): JWK set to search for verification keys.

    Returns:
        callable: A function `header, payload -> Key` that resolves and returns
                  the verification key.
        Raises `KeyNotFoundError` when resolution fails.
    """

    def _internal(header: dict[str, Any], _payload: dict[str, Any]) -> Key:
        """Match kid and alg from the JWT header to the JWK set.

        Resolve the key from the JWK set based on the JWT header. Also
        match the algorithm to make sure the algorithm stated by the user
        is the same algorithm the key itself expects.

        We intentionally do not use find_by_kid because it's a bad function
        that doesn't take the alg into account

        Returns:
            key (Key): The JWK matching the header's selection criteria.

        Raises:
            KeyNotFoundError: If the header is missing `alg`, no matching key
            is found, multiple keys match a `kid`, or a found key's algorithm
            does not match the header's `alg`.
        """
        if "alg" not in header:
            raise KeyNotFoundError("Token header missing 'alg' field")

        if "kid" in header:
            keys = [key for key in jwk_set.keys if key.kid == header.get("kid")]

            if len(keys) == 0:
                raise KeyNotFoundError(
                    "No key found matching kid and alg in the JWK set"
                )

            if len(keys) > 1:
                # This should never happen! Bad JWK set!
                raise KeyNotFoundError(
                    "Internal server error, multiple keys found matching this kid"
                )

            key = keys[0]

            if key["alg"] != header["alg"]:
                raise KeyNotFoundError(
                    "Key found by kid does not match the algorithm in the token header"
                )

            return key

        # No kid in the token header, we will try to find a key by alg
        keys = [key for key in jwk_set.keys if key["alg"] == header["alg"]]

        if len(keys) == 0:
            raise KeyNotFoundError("No key found matching alg in the JWK set")

        # Token has no kid and even we have more than one key with this algorithm - we will
        # return the first key which matches the algorithm, hopefully it will
        # match the token, but if not, unlucky - we're not going to brute-force all
        # keys until we find the one that matches, that makes us more vulnerable to DoS
        return keys[0]

    return _internal


class JwkTokenAuthDependency(AuthInterface):  # pylint: disable=too-few-public-methods
    """JWK AuthDependency class for JWK-based JWT authentication."""

    def __init__(
        self, config: JwkConfiguration, virtual_path: str = DEFAULT_VIRTUAL_PATH
    ) -> None:
        """Initialize the required allowed paths for authorization checks.

        Create a JWK-based token authentication dependency configured for a specific virtual path.

        Parameters:
            config (JwkConfiguration): Configuration containing the JWK URL,
                                       claim names, and validation settings.
            virtual_path (str): Virtual authorization scope path used when
                                resolving authorization rules; defaults to DEFAULT_VIRTUAL_PATH.

        Notes:
            Initializes the instance and sets `skip_userid_check` to False.
        """
        self.virtual_path: str = virtual_path
        self.config: JwkConfiguration = config
        self.skip_userid_check = False

    async def __call__(self, request: Request) -> AuthTuple:
        """Authenticate the JWT in the headers against the keys from the JWK url.

        If the Authorization header is missing, returns NO_AUTH_TUPLE. On token
        verification or validation failures this function raises HTTPException
        with appropriate HTTP status codes:
        - 401 for unknown signing key/algorithm, bad signature, expired token,
              or missing required claims;
        - 400 for token decode or other JOSE-related decode/validation errors;
        - 500 for unexpected internal errors.

        Parameters:
            request (Request): The incoming FastAPI request containing the Authorization header.

        Returns:
            AuthTuple: A tuple (user_id, username, skip_userid_check, token)
            extracted from the validated token, or NO_AUTH_TUPLE when no
            Authorization header is present.
        """
        if not request.headers.get("Authorization"):
            return NO_AUTH_TUPLE

        user_token = extract_user_token(request.headers)

        try:
            jwk_set = await get_jwk_set(str(self.config.url))
        except aiohttp.ClientError as exc:
            logger.error("Failed to fetch JWK set: %s", exc)
            response = UnauthorizedResponse(
                cause="Unable to reach authentication key server"
            )
            raise HTTPException(**response.model_dump()) from exc
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in JWK set response: %s", exc)
            response = UnauthorizedResponse(
                cause="Authentication key server returned invalid data"
            )
            raise HTTPException(**response.model_dump()) from exc
        except JoseError as exc:
            logger.error("Invalid JWK set format: %s", exc)
            response = UnauthorizedResponse(cause="Authentication keys are malformed")
            raise HTTPException(**response.model_dump()) from exc

        try:
            claims = jwt.decode(user_token, key=key_resolver_func(jwk_set))
        except (KeyNotFoundError, BadSignatureError, DecodeError, JoseError) as exc:
            logger.warning("Token decode error: %s", exc)
            cause_map = {
                KeyNotFoundError: "Token signed by unknown key",
                BadSignatureError: "Invalid token signature",
                DecodeError: "Token could not be decoded",
                JoseError: "Token format error",
            }
            response = UnauthorizedResponse(
                cause=cause_map.get(type(exc), "Unknown token error")
            )
            raise HTTPException(**response.model_dump()) from exc

        try:
            claims.validate()
        except ExpiredTokenError as exc:
            response = UnauthorizedResponse(cause="Token has expired")
            raise HTTPException(**response.model_dump()) from exc
        except JoseError as exc:
            response = UnauthorizedResponse(cause="Token validation failed")
            raise HTTPException(**response.model_dump()) from exc

        try:
            user_id: str = claims[self.config.jwt_configuration.user_id_claim]
        except KeyError as exc:
            missing_claim = self.config.jwt_configuration.user_id_claim
            response = UnauthorizedResponse(
                cause=f"Token missing claim: {missing_claim}"
            )
            raise HTTPException(**response.model_dump()) from exc

        try:
            username: str = claims[self.config.jwt_configuration.username_claim]
        except KeyError as exc:
            missing_claim = self.config.jwt_configuration.username_claim
            response = UnauthorizedResponse(
                cause=f"Token missing claim: {missing_claim}"
            )
            raise HTTPException(**response.model_dump()) from exc

        logger.info("Successfully authenticated user %s (ID: %s)", username, user_id)

        return user_id, username, self.skip_userid_check, user_token
