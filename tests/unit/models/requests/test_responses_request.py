"""Unit tests for ResponsesRequest body-size validation."""

import json

import pytest
from pydantic import ValidationError

from constants import RESPONSES_REQUEST_MAX_SIZE
from models.api.requests import ResponsesRequest

_LIMIT = RESPONSES_REQUEST_MAX_SIZE
_OVERHEAD = len(json.dumps({"input": ""}))  # 13
_AT_LIMIT_PADDING = _LIMIT - _OVERHEAD  # 65,523


class TestResponsesRequestBodySize:
    """Tests for the 65,536-character body-size guard on ResponsesRequest."""

    def test_normal_request_accepted(self) -> None:
        """A small, normal request must be accepted without raising."""
        req = ResponsesRequest(input="hello")  # pyright: ignore[reportCallIssue]
        assert req.input == "hello"

    def test_at_limit_request_accepted(self) -> None:
        """A request whose JSON serialization is exactly 65,536 chars is accepted."""
        payload = "x" * _AT_LIMIT_PADDING
        assert len(json.dumps({"input": payload})) == _LIMIT

        req = ResponsesRequest(input=payload)  # pyright: ignore[reportCallIssue]
        assert req.input == payload

    def test_one_over_limit_rejected(self) -> None:
        """A request whose JSON serialization is 65,537 chars raises ValidationError."""
        payload = "x" * (_AT_LIMIT_PADDING + 1)
        serialized = json.dumps({"input": payload})
        assert len(serialized) == _LIMIT + 1

        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest(input=payload)  # pyright: ignore[reportCallIssue]

        error_text = str(exc_info.value)
        assert "65536" in error_text
        assert str(_LIMIT + 1) in error_text

    def test_large_list_input_rejected(self) -> None:
        """A request with a list input that exceeds 64 KB is rejected."""
        long_item_text = "a" * 1000
        large_list = [{"role": "user", "content": long_item_text}] * 100

        raw = {"input": large_list}
        assert len(json.dumps(raw)) > _LIMIT

        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest(input=large_list)  # pyright: ignore[reportCallIssue]

        error_text = str(exc_info.value)
        assert "65536" in error_text

    def test_model_validation_normal_request_accepted(self) -> None:
        """A small, normal request must be accepted without raising."""
        req = ResponsesRequest.model_validate(
            {
                "input": "hello",
            }
        )
        assert req.input == "hello"

    def test_model_validation_normal_request_accepted_configurable_limit(self) -> None:
        """A small, normal request must be accepted without raising."""
        req = ResponsesRequest.model_validate(
            {
                "input": "hello",
            },
            context={"responses_request_max_size": _LIMIT*2},
        )
        assert req.input == "hello"

    def test_model_validation_over_limit(self) -> None:
        """A request whose JSON serialization is 65,537 chars raises ValidationError."""
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
        assert "65536" in error_text
        assert str(_LIMIT + 1) in error_text

    def test_model_validation_over_standard_limit_not_reached_threshold(self) -> None:
        """Validation for custom limit."""
        payload = "x" * (_AT_LIMIT_PADDING + 1)
        serialized = json.dumps({"input": payload})
        assert len(serialized) == _LIMIT + 1

        req = ResponsesRequest.model_validate(
            {
                "input": payload,
            },
            context={"responses_request_max_size": _LIMIT*2},
        )
        assert req.input is not None
        assert "xxxx" in req.input

    def test_model_validation_over_limit_reached_threshold(self) -> None:
        """A request whose JSON serialization is longer than max size raises ValidationError."""
        payload = "x" * (110_000 - _OVERHEAD)

        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest.model_validate(
                {
                    "input": payload,
                },
                context={"responses_request_max_size": 100_000},
            )

        error_text = str(exc_info.value)
        assert "110000" in error_text
        assert "100000" in error_text
