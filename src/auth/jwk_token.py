"""Manage authentication flow for FastAPI endpoints with JWK based JWT auth."""

import logging
import json
from asyncio import Lock
from typing import Any, Callable

from fastapi import Request, HTTPException, status
from authlib.jose import JsonWebKey, KeySet, jwt, Key
from authlib.jose.errors import (
    BadSignatureError,
    DecodeError,
    ExpiredTokenError,
    JoseError,
)
from cachetools import TTLCache
import aiohttp

from constants import (
    DEFAULT_VIRTUAL_PATH,
)
from auth.interface import AuthInterface
from auth.utils import extract_user_token
from models.config import JwkConfiguration

logger = logging.getLogger(__name__)

# Global JWK registry to avoid re-fetching JWKs for each request. Cached for 1
# hour, keys are unlikely to change frequently.
_jwk_cache: TTLCache[str, KeySet] = TTLCache(maxsize=3, ttl=3600)
# Ideally this would be an RWLock, but it would require adding a dependency on
# aiorwlock
_jwk_cache_lock = Lock()


async def get_jwk_set(url: str) -> KeySet:
    """Fetch the JWK set from the cache, or fetch it from the URL if not cached."""
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
    Create a key resolver function.

    Return a function to find a key in the given jwk_set. The function matches the
    signature expected by the jwt.decode key kwarg.
    """

    def _internal(header: dict[str, Any], _payload: dict[str, Any]) -> Key:
        """Match kid and alg from the JWT header to the JWK set.

        Resolve the key from the JWK set based on the JWT header. Also
        match the algorithm to make sure the algorithm stated by the user
        is the same algorithm the key itself expects.

        # We intentionally do not use find_by_kid because it's a bad function
        # that doesn't take the alg into account
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
        """Initialize the required allowed paths for authorization checks."""
        self.virtual_path: str = virtual_path
        self.config: JwkConfiguration = config

    async def __call__(self, request: Request) -> tuple[str, str, str]:
        """Authenticate the JWT in the headers against the keys from the JWK url."""
        user_token = extract_user_token(request.headers)

        jwk_set = await get_jwk_set(str(self.config.url))

        try:
            claims = jwt.decode(user_token, key=key_resolver_func(jwk_set))
        except KeyNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: signed by unknown key or algorithm mismatch",
            ) from exc
        except BadSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: bad signature",
            ) from exc
        except DecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token: decode error",
            ) from exc
        except JoseError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token: unknown error",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

        try:
            claims.validate()
        except ExpiredTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            ) from exc
        except JoseError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Error validating token",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during token validation",
            ) from exc

        try:
            user_id: str = claims[self.config.jwt_configuration.user_id_claim]
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token missing claim: {self.config.jwt_configuration.user_id_claim}",
            ) from exc

        try:
            username: str = claims[self.config.jwt_configuration.username_claim]
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token missing claim: {self.config.jwt_configuration.username_claim}",
            ) from exc

        logger.info("Successfully authenticated user %s (ID: %s)", username, user_id)

        return user_id, username, json.dumps(claims)
