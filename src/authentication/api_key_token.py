"""Authentication flow for FastAPI endpoints with a provided API key.

Behavior:
- Reads a user token from request headers via `authentication.utils.extract_user_token` and verifies
the value equals to the API Key, given from configuration parameter.
- Returns a tuple: (DEFAULT_USER_NAME, DEFAULT_USER_NAME, skip_userid_check, user_token).
"""

import secrets

from fastapi import Request, HTTPException, status

from constants import (
    DEFAULT_USER_NAME,
    DEFAULT_VIRTUAL_PATH,
    DEFAULT_USER_UID,
)
from authentication.interface import AuthInterface
from authentication.utils import extract_user_token
from log import get_logger
from models.config import APIKeyTokenConfiguration

logger = get_logger(__name__)


class APIKeyTokenAuthDependency(
    AuthInterface
):  # pylint: disable=too-few-public-methods
    """FastAPI dependency for API key token authentication.

    Validates bearer tokens against a configured API key and returns
    user authentication information for authorized requests.
    """

    def __init__(
        self, config: APIKeyTokenConfiguration, virtual_path: str = DEFAULT_VIRTUAL_PATH
    ) -> None:
        """Initialize the API key token authentication dependency.

        Args:
            config: The API key token configuration containing the API key.
            virtual_path: The virtual path for the service (default: DEFAULT_VIRTUAL_PATH).
        """
        self.virtual_path: str = virtual_path
        self.config: APIKeyTokenConfiguration = config
        self.skip_userid_check = True

    async def __call__(self, request: Request) -> tuple[str, str, bool, str]:
        """Validate FastAPI Requests for authentication and authorization.

        Args:
            request: The FastAPI request object.

        Returns:
            A tuple containing (user_uid, username, skip_userid_check, user_token)
            if authentication succeeds.

        Raises:
            HTTPException: If the bearer token is missing or
            doesn't match the configured API key (HTTP 401).
        """
        # try to extract user token from request
        user_token = extract_user_token(request.headers)

        # API Key validation. Use secrets.compare_digest for constant-time comparison
        if not secrets.compare_digest(
            user_token, self.config.api_key.get_secret_value()
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API Key",
            )

        return DEFAULT_USER_UID, DEFAULT_USER_NAME, self.skip_userid_check, user_token
