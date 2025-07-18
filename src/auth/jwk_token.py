"""Manage authentication flow for FastAPI endpoints with no-op auth."""

import logging
from asyncio import Lock
from typing import Any

from fastapi import Request, HTTPException, status
from authlib.jose import JsonWebKey, KeySet, jwt
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
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    _jwk_cache[url] = JsonWebKey.import_key_set(await resp.json())
        return _jwk_cache[url]


class KeyNotFoundError(Exception):
    """Exception raised when a key is not found in the JWK set based on kid/alg."""


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

        def resolve_key(header: dict[str, Any], _payload: dict[str, Any]) -> JsonWebKey:
            """Match kid and alg from the JWT header to the JWK set.

            Resolve the key from the JWK set based on the JWT header. Also
            match the algorithm to make sure the algorithm stated by the user
            is the same algorithm the key itself expects.
            """
            key = jwk_set.find_by_kid(header["kid"])

            if header["alg"] != key["alg"]:
                raise KeyNotFoundError

            return key

        if not user_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header is missing or invalid",
            )

        try:
            claims = jwt.decode(user_token, key=resolve_key)
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

        return user_id, username, user_token
