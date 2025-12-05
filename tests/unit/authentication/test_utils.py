"""Unit tests for functions defined in authentication/utils.py"""

from typing import cast
from fastapi import HTTPException
from starlette.datastructures import Headers

from authentication.utils import extract_user_token


def test_extract_user_token() -> None:
    """Test extracting user token from headers."""
    headers = Headers({"Authorization": "Bearer abcdef123"})
    token = extract_user_token(headers)
    assert token == "abcdef123"


def test_extract_user_token_no_header() -> None:
    """Test extracting user token when no Authorization header is present."""
    headers = Headers({})
    try:
        extract_user_token(headers)
    except HTTPException as exc:
        assert exc.status_code == 401
        detail = cast(dict[str, str], exc.detail)
        assert detail["response"] == (
            "Missing or invalid credentials provided by client"
        )
        assert detail["cause"] == "No Authorization header found"


def test_extract_user_token_invalid_format() -> None:
    """Test extracting user token with invalid Authorization header format."""
    headers = Headers({"Authorization": "InvalidFormat"})
    try:
        extract_user_token(headers)
    except HTTPException as exc:
        assert exc.status_code == 401
        detail = cast(dict[str, str], exc.detail)
        assert detail["response"] == (
            "Missing or invalid credentials provided by client"
        )
        assert detail["cause"] == "No token found in Authorization header"
