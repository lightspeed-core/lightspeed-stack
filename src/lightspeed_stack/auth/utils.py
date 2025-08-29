"""Authentication utility functions."""

from fastapi import HTTPException
from starlette.datastructures import Headers


def extract_user_token(headers: Headers) -> str:
    """Extract the bearer token from an HTTP authorization header.

    Args:
        header: The authorization header containing the token.

    Returns:
        The extracted token if present, else an empty string.
    """
    authorization_header = headers.get("Authorization")
    if not authorization_header:
        raise HTTPException(status_code=400, detail="No Authorization header found")

    scheme_and_token = authorization_header.strip().split()
    if len(scheme_and_token) != 2 or scheme_and_token[0].lower() != "bearer":
        raise HTTPException(
            status_code=400, detail="No token found in Authorization header"
        )

    return scheme_and_token[1]
