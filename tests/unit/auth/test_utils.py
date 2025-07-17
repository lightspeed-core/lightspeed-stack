"""Unit tests for functions defined in auth/utils.py"""

from fastapi import HTTPException
from starlette.datastructures import Headers

from auth.utils import extract_user_token


def test_extract_user_token():
    """Test extracting user token from headers."""
    headers = Headers({"Authorization": "Bearer abcdef123"})
    token = extract_user_token(headers)
    assert token == "abcdef123"


def test_extract_user_token_no_header():
    """Test extracting user token when no Authorization header is present."""
    headers = Headers({})
    try:
        extract_user_token(headers)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "No Authorization header found"


def test_extract_user_token_invalid_format():
    """Test extracting user token with invalid Authorization header format."""
    headers = Headers({"Authorization": "InvalidFormat"})
    try:
        extract_user_token(headers)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "No token found in Authorization header"
