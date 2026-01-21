"""Authentication utility functions."""

import logging

from fastapi import HTTPException
from starlette.datastructures import Headers
from models.responses import UnauthorizedResponse

logger = logging.getLogger(__name__)


def extract_user_token(headers: Headers) -> str:
    """Extract the bearer token from an HTTP Authorization header.

    Parameters:
        headers (Headers): Incoming request headers from which the
        Authorization header will be read.

    Returns:
        str: The bearer token string extracted from the header.

    Raises:
        HTTPException: If the Authorization header is missing or malformed.
    """
    # Log all header names (not values) for debugging
    header_names = list(headers.keys())
    logger.debug("Received request headers: %s", header_names)

    authorization_header = headers.get("Authorization")
    if not authorization_header:
        logger.debug(
            "Authentication failed: No Authorization header found. "
            "Available headers: %s",
            header_names,
        )
        response = UnauthorizedResponse(cause="No Authorization header found")
        raise HTTPException(**response.model_dump())

    scheme_and_token = authorization_header.strip().split()
    if len(scheme_and_token) != 2 or scheme_and_token[0].lower() != "bearer":
        logger.debug(
            "Authentication failed: Authorization header malformed. "
            "Expected 'Bearer <token>', got scheme='%s' with %d parts",
            scheme_and_token[0] if scheme_and_token else "empty",
            len(scheme_and_token),
        )
        response = UnauthorizedResponse(cause="No token found in Authorization header")
        raise HTTPException(**response.model_dump())

    # Log token presence without exposing the actual token
    token = scheme_and_token[1]
    logger.debug(
        "Successfully extracted bearer token (length=%d, first_chars=%s...)",
        len(token),
        token[:10] if len(token) > 10 else token[:4] + "...",
    )
    return token
