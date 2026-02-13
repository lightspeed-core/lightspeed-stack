"""Unit tests for the pure ASGI middlewares in main.py."""

import json
from typing import cast
from unittest.mock import patch

import pytest
from fastapi import HTTPException, status
from starlette.types import Message, Receive, Scope, Send

from app.main import GlobalExceptionMiddleware, RestApiMetricsMiddleware
from models.responses import InternalServerErrorResponse


def _make_scope(path: str = "/test") -> dict:
    """Build a minimal HTTP ASGI scope."""
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
    }


async def _noop_receive() -> dict:
    """Minimal ASGI receive callable."""
    return {"type": "http.request", "body": b""}


class _ResponseCollector:
    """Accumulate ASGI messages so tests can inspect them."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def __call__(self, message: Message) -> None:
        self.messages.append(message)

    @property
    def status_code(self) -> int:
        """Return the HTTP status code from the collected response."""
        for msg in self.messages:
            if msg["type"] == "http.response.start":
                return msg["status"]
        raise AssertionError("No http.response.start message")

    @property
    def body_json(self) -> dict:
        """Return the response body decoded as JSON."""
        body = b""
        for msg in self.messages:
            if msg["type"] == "http.response.body":
                body += msg.get("body", b"")
        return json.loads(body)


# ---------------------------------------------------------------------------
# GlobalExceptionMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_exception_middleware_catches_unexpected_exception() -> None:
    """Test that GlobalExceptionMiddleware catches unexpected exceptions."""

    async def failing_app(scope: Scope, receive: Receive, send: Send) -> None:
        raise ValueError("This is an unexpected error for testing")

    middleware = GlobalExceptionMiddleware(failing_app)
    collector = _ResponseCollector()

    await middleware(_make_scope(), _noop_receive, collector)

    assert collector.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    detail = collector.body_json["detail"]
    assert isinstance(detail, dict)

    expected_response = InternalServerErrorResponse.generic()
    expected_detail = expected_response.model_dump()["detail"]
    detail_dict = cast(dict[str, str], detail)
    assert detail_dict["response"] == expected_detail["response"]
    assert detail_dict["cause"] == expected_detail["cause"]


@pytest.mark.asyncio
async def test_global_exception_middleware_passes_through_http_exception() -> None:
    """Test that GlobalExceptionMiddleware passes through HTTPException."""

    async def http_error_app(scope: Scope, receive: Receive, send: Send) -> None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"response": "Test error", "cause": "This is a test"},
        )

    middleware = GlobalExceptionMiddleware(http_error_app)
    collector = _ResponseCollector()

    with pytest.raises(HTTPException) as exc_info:
        await middleware(_make_scope(), _noop_receive, collector)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["response"] == "Test error"
    assert detail["cause"] == "This is a test"


@pytest.mark.asyncio
async def test_global_exception_middleware_reraises_when_response_started() -> None:
    """Test that exceptions after response headers are sent are re-raised."""

    async def partial_response_app(
        _scope: Scope, _receive: Receive, send: Send
    ) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("error after headers sent")

    middleware = GlobalExceptionMiddleware(partial_response_app)
    collector = _ResponseCollector()

    with pytest.raises(RuntimeError, match="error after headers sent"):
        await middleware(_make_scope(), _noop_receive, collector)


@pytest.mark.asyncio
async def test_global_exception_middleware_skips_non_http() -> None:
    """Test that non-HTTP scopes pass through untouched."""
    called = False

    async def inner_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    middleware = GlobalExceptionMiddleware(inner_app)
    await middleware({"type": "websocket"}, _noop_receive, _ResponseCollector())
    assert called


# ---------------------------------------------------------------------------
# RestApiMetricsMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rest_api_metrics_skips_non_http() -> None:
    """Test that non-HTTP scopes pass through untouched."""
    called = False

    async def inner_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    middleware = RestApiMetricsMiddleware(inner_app)
    await middleware({"type": "websocket"}, _noop_receive, _ResponseCollector())
    assert called


@pytest.mark.asyncio
@patch("app.main.app_routes_paths", ["/v1/infer"])
async def test_rest_api_metrics_increments_counter_on_exception() -> None:
    """Counter must be incremented even when the inner app raises."""

    async def failing_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise RuntimeError("boom")

    with patch("app.main.metrics") as mock_metrics:
        middleware = RestApiMetricsMiddleware(failing_app)

        with pytest.raises(RuntimeError, match="boom"):
            await middleware(
                _make_scope("/v1/infer"), _noop_receive, _ResponseCollector()
            )

    mock_metrics.response_duration_seconds.labels.assert_called_once_with("/v1/infer")
    mock_metrics.rest_api_calls_total.labels.assert_called_once_with("/v1/infer", 500)
    mock_metrics.rest_api_calls_total.labels.return_value.inc.assert_called_once()
