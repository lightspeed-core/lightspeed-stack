"""Unit tests for RHEL Lightspeed rlsapi v1 /infer request and response models."""

import pytest
from pydantic import ValidationError

from models.requests import RlsapiV1InferRequest
from models.responses import RlsapiV1InferResponse


class TestRlsapiV1InferRequest:
    """Tests for RlsapiV1InferRequest model."""

    def test_v1_infer_request_minimal(self) -> None:
        """Test creating request with just question (no context)."""
        request = RlsapiV1InferRequest(question="How do I list files?")

        assert request.question == "How do I list files?"
        assert request.context is None

    def test_v1_infer_request_with_context_dict(self) -> None:
        """Test creating request with context dictionary."""
        context = {
            "system_info": "RHEL 9.3",
            "terminal_output": "bash: command not found",
            "stdin": "user input",
        }
        request = RlsapiV1InferRequest(
            question="What does this error mean?", context=context
        )

        assert request.question == "What does this error mean?"
        assert request.context == context
        assert request.context["system_info"] == "RHEL 9.3"
        assert request.context["terminal_output"] == "bash: command not found"
        assert request.context["stdin"] == "user input"

    def test_v1_infer_request_missing_question(self) -> None:
        """Test that request without question raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            RlsapiV1InferRequest()  # type: ignore

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("question",)
        assert errors[0]["type"] == "missing"

    def test_v1_infer_request_rejects_extra_fields(self) -> None:
        """Test that extra fields are rejected (extra='forbid')."""
        with pytest.raises(ValidationError) as exc_info:
            RlsapiV1InferRequest(
                question="How do I list files?",
                extra_field="should be rejected",  # type: ignore
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "extra_forbidden"


class TestRlsapiV1InferResponse:
    """Tests for RlsapiV1InferResponse model."""

    def test_v1_infer_response_creation(self) -> None:
        """Test creating response with data dictionary."""
        response = RlsapiV1InferResponse(
            data={
                "text": "To list files in Linux, use the `ls` command.",
                "request_id": "01JDKR8N7QW9ZMXVGK3PB5TQWZ",
            }
        )

        assert response.data["text"] == "To list files in Linux, use the `ls` command."
        assert response.data["request_id"] == "01JDKR8N7QW9ZMXVGK3PB5TQWZ"

    def test_v1_infer_response_serialization(self) -> None:
        """Test that response can be serialized to dict/JSON."""
        response = RlsapiV1InferResponse(
            data={
                "text": "Use the ls command",
                "request_id": "01JDKR8N7QW9ZMXVGK3PB5TQWZ",
            }
        )

        # Test model_dump (Pydantic v2)
        data = response.model_dump()
        assert data["data"]["text"] == "Use the ls command"
        assert data["data"]["request_id"] == "01JDKR8N7QW9ZMXVGK3PB5TQWZ"

        # Test model_dump_json (Pydantic v2)
        json_str = response.model_dump_json()
        assert "Use the ls command" in json_str
        assert "01JDKR8N7QW9ZMXVGK3PB5TQWZ" in json_str
