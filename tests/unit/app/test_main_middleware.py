"""Unit tests for the global exception middleware in main.py."""

import json
from typing import cast
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.requests import Request as StarletteRequest

from models.responses import InternalServerErrorResponse
from app.main import global_exception_middleware


@pytest.mark.asyncio
async def test_global_exception_middleware_catches_unexpected_exception() -> None:
    """Test that global exception middleware catches unexpected exceptions."""

    mock_request = Mock(spec=StarletteRequest)
    mock_request.url.path = "/test"

    async def mock_call_next_raises_error(request: Request) -> Response:
        """Mock call_next that raises an unexpected exception."""
        raise ValueError("This is an unexpected error for testing")

    response = await global_exception_middleware(
        mock_request, mock_call_next_raises_error
    )

    # Verify it returns a JSONResponse
    assert isinstance(response, JSONResponse)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # Parse the response body
    response_body_bytes = bytes(response.body)
    response_body = json.loads(response_body_bytes.decode("utf-8"))
    assert "detail" in response_body
    detail = response_body["detail"]
    assert isinstance(detail, dict)
    assert "response" in detail
    assert "cause" in detail

    # Verify it matches the generic InternalServerErrorResponse
    expected_response = InternalServerErrorResponse.generic()
    expected_detail = expected_response.model_dump()["detail"]
    detail_dict = cast(dict[str, str], detail)
    assert detail_dict["response"] == expected_detail["response"]
    assert detail_dict["cause"] == expected_detail["cause"]


@pytest.mark.asyncio
async def test_global_exception_middleware_passes_through_http_exception() -> None:
    """Test that global exception middleware passes through HTTPException unchanged."""

    mock_request = Mock(spec=StarletteRequest)
    mock_request.url.path = "/test"

    async def mock_call_next_raises_http_exception(request: Request) -> Response:
        """Mock call_next that raises HTTPException."""
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"response": "Test error", "cause": "This is a test"},
        )

    with pytest.raises(HTTPException) as exc_info:
        await global_exception_middleware(
            mock_request, mock_call_next_raises_http_exception
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["response"] == "Test error"
    assert detail["cause"] == "This is a test"
