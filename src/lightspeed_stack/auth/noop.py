"""Manage authentication flow for FastAPI endpoints with no-op auth."""

import logging

from fastapi import Request

from constants import (
    DEFAULT_USER_NAME,
    DEFAULT_USER_UID,
    NO_USER_TOKEN,
    DEFAULT_VIRTUAL_PATH,
)
from auth.interface import AuthInterface

logger = logging.getLogger(__name__)


class NoopAuthDependency(AuthInterface):  # pylint: disable=too-few-public-methods
    """No-op AuthDependency class that bypasses authentication and authorization checks."""

    def __init__(self, virtual_path: str = DEFAULT_VIRTUAL_PATH) -> None:
        """Initialize the required allowed paths for authorization checks."""
        self.virtual_path = virtual_path

    async def __call__(self, request: Request) -> tuple[str, str, str]:
        """Validate FastAPI Requests for authentication and authorization.

        Args:
            request: The FastAPI request object.

        Returns:
            The user's UID and username if authentication and authorization succeed
            user_id check is skipped with noop auth to allow consumers provide user_id
        """
        logger.warning(
            "No-op authentication dependency is being used. "
            "The service is running in insecure mode intended solely for development purposes"
        )
        # try to extract user ID from request
        user_id = request.query_params.get("user_id", DEFAULT_USER_UID)
        logger.debug("Retrieved user ID: %s", user_id)
        return user_id, DEFAULT_USER_NAME, NO_USER_TOKEN
