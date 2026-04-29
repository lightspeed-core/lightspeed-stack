"""Authentication utility functions."""

import time

from fastapi import HTTPException
from starlette.datastructures import Headers

from metrics import recording
from models.responses import UnauthorizedResponse


def extract_user_token(headers: Headers) -> str:
    """Extract the bearer token from an HTTP Authorization header.

    Parameters:
    ----------
        headers (Headers): Incoming request headers from which the
        Authorization header will be read.

    Returns:
    -------
        str: The bearer token string extracted from the header.

    Raises:
    ------
        HTTPException: If the Authorization header is missing or malformed.
    """
    authorization_header = headers.get("Authorization")
    if not authorization_header:
        response = UnauthorizedResponse(cause="No Authorization header found")
        raise HTTPException(**response.model_dump())

    scheme_and_token = authorization_header.strip().split()
    if len(scheme_and_token) != 2 or scheme_and_token[0].lower() != "bearer":
        response = UnauthorizedResponse(cause="No token found in Authorization header")
        raise HTTPException(**response.model_dump())

    return scheme_and_token[1]


def record_auth_metrics(
    auth_module: str, result: str, reason: str, start_time: float
) -> None:
    """Record authentication attempt and duration metrics together.

    Args:
        auth_module: Configured authentication module name.
        result: Bounded result label, such as ``success`` or ``failure``.
        reason: Bounded reason label for the result.
        start_time: Monotonic clock time captured at the start of auth handling.
    """
    recording.record_auth_attempt(auth_module, result, reason)
    recording.record_auth_duration(auth_module, result, time.monotonic() - start_time)
