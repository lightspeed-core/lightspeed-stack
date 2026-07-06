"""Unit tests for utils/streaming_sse.py."""

import json

import pytest
from pydantic import AnyUrl
from pytest_mock import MockerFixture

from constants import (
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
)
from models.api.responses.error import InternalServerErrorResponse
from models.common.turn_summary import ReferencedDocument
from utils.streaming_sse import (
    shield_violation_generator,
    stream_end_event,
    stream_event,
    stream_http_error_event,
    stream_start_event,
)
from utils.token_counter import TokenCounter


class TestOLSStreamEventFormatting:
    """Test the stream_event function for both media types (OLS compatibility)."""

    def test_stream_event_json_token(self) -> None:
        """Test token event formatting for JSON media type."""
        data = {"id": 0, "token": "Hello"}
        result = stream_event(data, LLM_TOKEN_EVENT, MEDIA_TYPE_JSON)

        expected = 'data: {"event": "token", "data": {"id": 0, "token": "Hello"}}\n\n'
        assert result == expected

    def test_stream_event_text_token(self) -> None:
        """Test token event formatting for text media type."""
        data = {"id": 0, "token": "Hello"}
        result = stream_event(data, LLM_TOKEN_EVENT, MEDIA_TYPE_TEXT)

        assert result == "Hello"

    def test_stream_event_json_tool_call(self) -> None:
        """Test tool call event formatting for JSON media type."""
        data = {
            "id": 0,
            "token": {"tool_name": "search", "arguments": {"query": "test"}},
        }
        result = stream_event(data, LLM_TOOL_CALL_EVENT, MEDIA_TYPE_JSON)

        expected = (
            'data: {"event": "tool_call", "data": {"id": 0, "token": '
            '{"tool_name": "search", "arguments": {"query": "test"}}}}\n\n'
        )
        assert result == expected

    def test_stream_event_text_tool_call(self) -> None:
        """Test tool call event formatting for text media type."""
        data = {
            "id": 0,
            "function_name": "search",
            "arguments": {"query": "test"},
        }
        result = stream_event(data, LLM_TOOL_CALL_EVENT, MEDIA_TYPE_TEXT)

        expected = "[Tool Call: search]\n"
        assert result == expected

    def test_stream_event_json_tool_result(self) -> None:
        """Test tool result event formatting for JSON media type."""
        data = {
            "id": 0,
            "token": {"tool_name": "search", "response": "Found results"},
        }
        result = stream_event(data, LLM_TOOL_RESULT_EVENT, MEDIA_TYPE_JSON)

        expected = (
            'data: {"event": "tool_result", "data": {"id": 0, "token": '
            '{"tool_name": "search", "response": "Found results"}}}\n\n'
        )
        assert result == expected

    def test_stream_event_text_tool_result(self) -> None:
        """Test tool result event formatting for text media type."""
        data = {
            "id": 0,
            "tool_name": "search",
            "response": "Found results",
        }
        result = stream_event(data, LLM_TOOL_RESULT_EVENT, MEDIA_TYPE_TEXT)

        expected = "[Tool Result]\n"
        assert result == expected

    def test_stream_event_unknown_type(self) -> None:
        """Test handling of unknown event types."""
        data = {"id": 0, "token": "test"}
        result = stream_event(data, "unknown_event", MEDIA_TYPE_TEXT)

        assert result == ""


class TestOLSStreamEndEvent:
    """Test the stream_end_event function for both media types (OLS compatibility)."""

    def test_stream_end_event_json(self) -> None:
        """Test end event formatting for JSON media type."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents = [
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc1"), doc_title="Test Doc 1"
            ),
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc2"), doc_title="Test Doc 2"
            ),
        ]
        result = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_JSON,
        )

        data_part = result.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "end"
        assert "referenced_documents" in parsed["data"]
        assert len(parsed["data"]["referenced_documents"]) == 2
        assert parsed["data"]["referenced_documents"][0]["doc_title"] == "Test Doc 1"
        assert (
            parsed["data"]["referenced_documents"][0]["doc_url"]
            == "https://example.com/doc1"
        )
        assert "available_quotas" in parsed

    def test_stream_end_event_text(self) -> None:
        """Test end event formatting for text media type."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents = [
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc1"), doc_title="Test Doc 1"
            ),
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc2"), doc_title="Test Doc 2"
            ),
        ]
        result = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_TEXT,
        )

        expected = (
            "\n\n---\n\nTest Doc 1: https://example.com/doc1\n"
            "Test Doc 2: https://example.com/doc2"
        )
        assert result == expected

    def test_stream_end_event_text_no_docs(self) -> None:
        """Test end event formatting for text media type with no documents."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents: list[ReferencedDocument] = []
        result = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_TEXT,
        )

        assert result == ""

    def test_ols_end_event_structure(self) -> None:
        """Test that end event follows OLS structure."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents = [
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc"), doc_title="Test Doc"
            ),
        ]
        end_event = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_JSON,
        )
        data_part = end_event.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "end"
        assert "referenced_documents" in parsed["data"]
        assert "truncated" in parsed["data"]
        assert "input_tokens" in parsed["data"]
        assert "output_tokens" in parsed["data"]
        assert "available_quotas" in parsed


class TestStreamHttpErrorEvent:
    """Tests for stream_http_error_event function."""

    def test_stream_http_error_event_json(self, mocker: MockerFixture) -> None:
        """Test HTTP error event formatting for JSON media type."""
        error = InternalServerErrorResponse.query_failed("Test error")
        mocker.patch("utils.streaming_sse.logger")

        result = stream_http_error_event(error, MEDIA_TYPE_JSON)

        assert "error" in result
        assert "Test error" in result

    def test_stream_http_error_event_text(self, mocker: MockerFixture) -> None:
        """Test HTTP error event formatting for text media type."""
        error = InternalServerErrorResponse.query_failed("Test error")
        mocker.patch("utils.streaming_sse.logger")

        result = stream_http_error_event(error, MEDIA_TYPE_TEXT)

        assert "Status:" in result
        assert "500" in result
        assert "Test error" in result

    def test_stream_http_error_event_default(self, mocker: MockerFixture) -> None:
        """Test HTTP error event formatting with default media type."""
        error = InternalServerErrorResponse.query_failed("Test error")
        mocker.patch("utils.streaming_sse.logger")

        result = stream_http_error_event(error)

        assert "error" in result
        assert "500" in result or "status_code" in result


class TestStreamStartEvent:  # pylint: disable=too-few-public-methods
    """Tests for stream_start_event function."""

    def test_stream_start_event(self) -> None:
        """Test start event formatting."""
        result = stream_start_event("conv_123", "123e4567-e89b-12d3-a456-426614174000")

        assert "start" in result
        assert "conv_123" in result
        assert "123e4567-e89b-12d3-a456-426614174000" in result


class TestShieldViolationGenerator:
    """Tests for shield_violation_generator function."""

    @pytest.mark.asyncio
    async def test_shield_violation_generator_json(self) -> None:
        """Test shield violation generator for JSON media type."""
        result = []
        async for item in shield_violation_generator(
            "Violation message", MEDIA_TYPE_JSON
        ):
            result.append(item)

        assert len(result) > 0
        assert any("Violation message" in item for item in result)

    @pytest.mark.asyncio
    async def test_shield_violation_generator_text(self) -> None:
        """Test shield violation generator for text media type."""
        result = []
        async for item in shield_violation_generator(
            "Violation message", MEDIA_TYPE_TEXT
        ):
            result.append(item)

        assert len(result) > 0
