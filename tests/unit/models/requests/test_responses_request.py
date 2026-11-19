"""Unit tests for ResponsesRequest body-size validation."""

import json

import pytest
from pydantic import ValidationError

from constants import RESPONSES_REQUEST_MAX_SIZE
from models.api.requests import ResponsesRequest

_LIMIT = RESPONSES_REQUEST_MAX_SIZE
_OVERHEAD = len(json.dumps({"input": ""}))  # 13
_AT_LIMIT_PADDING = _LIMIT - _OVERHEAD


class TestResponsesRequestBodySize:
    """Tests for the fixed body-size guard on ResponsesRequest."""

    def test_normal_request_accepted(self) -> None:
        """A small, normal request must be accepted without raising."""
        req = ResponsesRequest(input="hello")  # pyright: ignore[reportCallIssue]
        assert req.input == "hello"

    def test_request_above_previous_default_accepted(self) -> None:
        """A request above the previous 128 KiB default is accepted."""
        payload = "x" * (131_073 - _OVERHEAD)

        req = ResponsesRequest(input=payload)  # pyright: ignore[reportCallIssue]
        assert req.input == payload

    def test_at_limit_request_accepted(self) -> None:
        """A request whose JSON serialization is exactly at the limit is accepted."""
        payload = "x" * _AT_LIMIT_PADDING
        assert len(json.dumps({"input": payload})) == _LIMIT

        req = ResponsesRequest(input=payload)  # pyright: ignore[reportCallIssue]
        assert req.input == payload

    def test_one_over_limit_rejected(self) -> None:
        """A request one character above the default limit raises ValidationError."""
        payload = "x" * (_AT_LIMIT_PADDING + 1)
        serialized = json.dumps({"input": payload})
        assert len(serialized) == _LIMIT + 1

        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest(input=payload)  # pyright: ignore[reportCallIssue]

        error_text = str(exc_info.value)
        assert f"allowed size of {_LIMIT} characters" in error_text
        assert str(_LIMIT + 1) in error_text

    def test_large_list_input_rejected(self) -> None:
        """A request with a list input above the default limit is rejected."""
        long_item_text = "a" * (_LIMIT // 100)
        large_list = [{"role": "user", "content": long_item_text}] * 100

        raw = {"input": large_list}
        assert len(json.dumps(raw)) > _LIMIT

        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest(input=large_list)  # pyright: ignore[reportCallIssue]

        error_text = str(exc_info.value)
        assert str(len(json.dumps(raw))) in error_text

    def test_model_validation_normal_request_accepted(self) -> None:
        """A small, normal request must be accepted without raising."""
        req = ResponsesRequest.model_validate(
            {
                "input": "hello",
            }
        )
        assert req.input == "hello"

    def test_model_validation_over_limit(self) -> None:
        """A request one character above the default limit raises ValidationError."""
        payload = "x" * (_AT_LIMIT_PADDING + 1)
        serialized = json.dumps({"input": payload})
        assert len(serialized) == _LIMIT + 1

        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest.model_validate(
                {
                    "input": payload,
                }
            )

        error_text = str(exc_info.value)
        assert f"allowed size of {_LIMIT} characters" in error_text
        assert str(_LIMIT + 1) in error_text
