"""Manage authentication flow for FastAPI endpoints with no-op auth and provided user token.

Intended for local/dev use only — do not use in production.

Behavior:
- Reads a user token from request headers via `authentication.utils.extract_user_token`.
- Reads `user_id` from query params (falls back to `DEFAULT_USER_UID`) and
  pairs it with `DEFAULT_USER_NAME`.
- Returns a tuple: (user_id, DEFAULT_USER_NAME, user_token).
"""

import time

from fastapi import HTTPException, Request

from authentication.interface import AuthInterface
from authentication.utils import extract_user_token, record_auth_metrics
from constants import (
    AUTH_MOD_NOOP_WITH_TOKEN,
    DEFAULT_USER_NAME,
    DEFAULT_USER_UID,
    DEFAULT_VIRTUAL_PATH,
)
from log import get_logger

logger = get_logger(__name__)


class NoopWithTokenAuthDependency(
    AuthInterface
):  # pylint: disable=too-few-public-methods
    """No-op AuthDependency class that bypasses authentication and authorization checks."""

    def __init__(self, virtual_path: str = DEFAULT_VIRTUAL_PATH) -> None:
        """Initialize the required allowed paths for authorization checks.

        Parameters:
        ----------
            virtual_path (str): Virtual base path used for authorization
            context; defaults to DEFAULT_VIRTUAL_PATH.

        Notes:
        -----
            Sets the instance attribute `virtual_path` and sets `skip_userid_check` to True.
        """
        self.virtual_path = virtual_path
        self.skip_userid_check = True

    async def __call__(self, request: Request) -> tuple[str, str, bool, str]:
        """Validate FastAPI Requests for authentication and authorization.

        Parameters:
        ----------
            request: The FastAPI request object.

        Returns:
        -------
            tuple[str, str, bool, str]: A 4-tuple containing:
                - user_id: The value of the "user_id" query parameter or
                           DEFAULT_USER_UID if absent.
                - username: DEFAULT_USER_NAME.
                - skip_userid_check: True to indicate user-id checks are skipped.
                - user_token: Token extracted from the request headers.
        """
        start_time = time.monotonic()

        logger.warning(
            "No-op with token authentication dependency is being used. "
            "The service is running in insecure mode intended solely for development purposes"
        )
        # try to extract user token from request
        try:
            user_token = extract_user_token(request.headers)
        except HTTPException:
            record_auth_metrics(
                AUTH_MOD_NOOP_WITH_TOKEN, "failure", "missing_token", start_time
            )
            raise
        # try to extract user ID from request
        user_id = request.query_params.get("user_id", DEFAULT_USER_UID)
        if not user_id:
            record_auth_metrics(
                AUTH_MOD_NOOP_WITH_TOKEN, "failure", "empty_user_id", start_time
            )
            raise HTTPException(status_code=400, detail="user_id cannot be empty")
        logger.debug("Retrieved user ID: %s", user_id)
        record_auth_metrics(
            AUTH_MOD_NOOP_WITH_TOKEN, "skipped", "no_auth_required", start_time
        )
        return user_id, DEFAULT_USER_NAME, self.skip_userid_check, user_token
