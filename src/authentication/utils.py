"""Authentication utility functions."""

from fastapi import HTTPException
from starlette.datastructures import Headers
from models.responses import UnauthorizedResponse


def extract_user_token(headers: Headers) -> str:
    """Extract the bearer token from an HTTP Authorization header.

    Args:
        headers: The request headers containing the Authorization value.

    Returns:
        The extracted bearer token.

    Raises:
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
