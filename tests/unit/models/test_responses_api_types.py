"""Unit tests for responses_api_types.py models."""

import pytest
from pydantic import ValidationError

from models.responses_api_types import ResponsesRequest


class TestResponsesRequestValidation:
    """Tests for ResponsesRequest validation."""

    def test_conversation_and_previous_response_id_mutually_exclusive(self) -> None:
        """Test that conversation and previous_response_id cannot both be provided."""
        # Use valid conversation ID format so field validation passes and model validator runs
        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest(
                input="test",
                conversation="conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
                previous_response_id="resp_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
            )
        # Check that the error is about mutual exclusivity
        error_str = str(exc_info.value).lower()
        assert (
            "mutually exclusive" in error_str or "cannot both be provided" in error_str
        )

    def test_conversation_or_previous_response_id_alone_allowed(self) -> None:
        """Test that conversation or previous_response_id can be provided alone."""
        # Only conversation
        valid_conv_id = "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"
        req1 = ResponsesRequest(input="test", conversation=valid_conv_id)
        assert req1.conversation == valid_conv_id
        assert req1.previous_response_id is None

        # Only previous_response_id (no validation on this field, so any string is fine)
        req2 = ResponsesRequest(input="test", previous_response_id="resp_456")
        assert req2.previous_response_id == "resp_456"
        assert req2.conversation is None

    def test_conversation_suid_validation_invalid(self) -> None:
        """Test that invalid conversation ID format raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            ResponsesRequest(input="test", conversation="invalid-id")
        assert "Improper conversation ID" in str(exc_info.value)

    def test_conversation_suid_validation_valid_openai_format(self) -> None:
        """Test that valid OpenAI format conversation ID is accepted."""
        req = ResponsesRequest(
            input="test",
            conversation="conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
        )
        assert (
            req.conversation == "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"
        )

    def test_conversation_suid_validation_valid_uuid_format(self) -> None:
        """Test that valid UUID format conversation ID is accepted."""
        req = ResponsesRequest(
            input="test",
            conversation="123e4567-e89b-12d3-a456-426614174000",
        )
        assert req.conversation == "123e4567-e89b-12d3-a456-426614174000"

    def test_get_mirrored_params(self) -> None:
        """Test that get_mirrored_params returns correct subset of fields."""
        req = ResponsesRequest(
            input="test query",
            model="openai/gpt-4",
            instructions="You are helpful",
            max_tool_calls=5,
            metadata={"key": "value"},
            parallel_tool_calls=True,
            temperature=0.7,
            tool_choice="auto",
        )
        mirrored = req.get_mirrored_params()

        # Check that mirrored params include expected fields
        assert "model" in mirrored
        assert "instructions" in mirrored
        assert "max_tool_calls" in mirrored
        assert "metadata" in mirrored
        assert "parallel_tool_calls" in mirrored
        assert "temperature" in mirrored
        assert "tool_choice" in mirrored

        # Check that input is NOT in mirrored params
        assert "input" not in mirrored
        assert "conversation" not in mirrored
        assert "stream" not in mirrored
        assert "store" not in mirrored

        # Check values
        assert mirrored["model"] == "openai/gpt-4"
        assert mirrored["instructions"] == "You are helpful"
        assert mirrored["max_tool_calls"] == 5
        assert mirrored["metadata"] == {"key": "value"}
        assert mirrored["parallel_tool_calls"] is True
        assert mirrored["temperature"] == 0.7
        assert mirrored["tool_choice"] == "auto"
