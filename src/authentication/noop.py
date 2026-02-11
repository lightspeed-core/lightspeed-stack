"""Manage authentication flow for FastAPI endpoints with no-op auth."""

from fastapi import HTTPException, Request

from constants import (
    DEFAULT_USER_NAME,
    DEFAULT_USER_UID,
    NO_USER_TOKEN,
    DEFAULT_VIRTUAL_PATH,
)
from authentication.interface import AuthInterface
from log import get_logger

logger = get_logger(__name__)


class NoopAuthDependency(AuthInterface):  # pylint: disable=too-few-public-methods
    """No-op AuthDependency class that bypasses authentication and authorization checks."""

    def __init__(self, virtual_path: str = DEFAULT_VIRTUAL_PATH) -> None:
        """Initialize the required allowed paths for authorization checks.

        Create a NoopAuthDependency configured with a virtual path and with
        user-ID checking disabled.

        Parameters:
            virtual_path (str): Virtual path context used by the dependency
                                (defaults to DEFAULT_VIRTUAL_PATH).
        """
        self.virtual_path = virtual_path
        self.skip_userid_check = True

    async def __call__(self, request: Request) -> tuple[str, str, bool, str]:
        """Validate FastAPI Requests for authentication and authorization.

        Parameters:
            request (Request): FastAPI request whose query parameters may contain "user_id".

        Returns:
            tuple[str, str, bool, str]: A 4-tuple containing:
                - user_id: the value of the "user_id" query parameter if
                           present, otherwise DEFAULT_USER_UID.
                - username: DEFAULT_USER_NAME.
                - skip_userid_check: True to indicate the user ID check is skipped.
                - token: NO_USER_TOKEN.
        """
        logger.warning(
            "No-op authentication dependency is being used. "
            "The service is running in insecure mode intended solely for development purposes"
        )
        # try to extract user ID from request
        user_id = request.query_params.get("user_id", DEFAULT_USER_UID)
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id cannot be empty")
        logger.debug("Retrieved user ID: %s", user_id)
        return user_id, DEFAULT_USER_NAME, self.skip_userid_check, NO_USER_TOKEN
