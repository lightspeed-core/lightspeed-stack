"""Abstract base class for all authentication method implementations.

Defines the abstract base class used by all authentication method implementations.
Contract: subclasses must implement `__call__(request: Request) -> AuthTuple`
where `AuthTuple = (UserID, UserName, Token)`.
"""

from abc import ABC, abstractmethod

from fastapi import Request

from constants import (
    DEFAULT_SKIP_USER_ID_CHECK,
    DEFAULT_USER_NAME,
    DEFAULT_USER_UID,
    NO_USER_TOKEN,
)

UserID = str
UserName = str
SkipUserIdCheck = bool
Token = str

AuthTuple = tuple[UserID, UserName, SkipUserIdCheck, Token]

NO_AUTH_TUPLE: AuthTuple = (
    DEFAULT_USER_UID,
    DEFAULT_USER_NAME,
    DEFAULT_SKIP_USER_ID_CHECK,
    NO_USER_TOKEN,
)


class AuthInterface(ABC):  # pylint: disable=too-few-public-methods
    """Base class for all authentication method implementations."""

    @abstractmethod
    async def __call__(self, request: Request) -> AuthTuple:
        """Validate FastAPI Requests for authentication and authorization.

        Returns:
            AuthTuple: A 4-tuple (user_id, user_name, skip_user_id_check, token) where
                user_id (str): authenticated user's unique identifier,
                user_name (str): authenticated user's display name,
                skip_user_id_check (bool): whether downstream handlers should
                                           skip user-id verification,
                token (str): authentication token or NO_USER_TOKEN when no token is present.
        """
