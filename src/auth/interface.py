"""Abstract base class for authentication methods."""

from abc import ABC, abstractmethod

from fastapi import Request


class AuthInterface(ABC):  # pylint: disable=too-few-public-methods
    """Base class for all authentication method implementations."""

    @abstractmethod
    async def __call__(self, request: Request) -> tuple[str, str, str]:
        """Validate FastAPI Requests for authentication and authorization."""
