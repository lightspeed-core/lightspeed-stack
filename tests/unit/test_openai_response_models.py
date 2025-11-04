"""Unit tests for OpenAI response models."""

import pytest
from pydantic import ValidationError

from models.responses import (
    OpenAIResponse,
    ResponseOutput,
    ResponseMessage,
    ResponseContent,
    ResponseUsage,
)


class TestResponseContent:
    """Test cases for ResponseContent model."""

    def test_response_content_text_valid(self):
        """Test creating ResponseContent with valid text type."""
        content = ResponseContent(type="text", text="This is a test response")
        assert content.type == "text"
        assert content.text == "This is a test response"

    def test_response_content_text_missing_text_field(self):
        """Test that text type requires text field."""
        with pytest.raises(ValidationError):
            ResponseContent(type="text")

    def test_response_content_text_empty_text(self):
        """Test that text field cannot be empty for text type."""
        with pytest.raises(ValidationError):
            ResponseContent(type="text", text="")

    def test_response_content_invalid_type(self):
        """Test that invalid content type raises ValidationError."""
        with pytest.raises(ValidationError):
            ResponseContent(type="invalid_type", text="test")


class TestResponseMessage:
    """Test cases for ResponseMessage model."""

    def test_response_message_valid(self):
        """Test creating ResponseMessage with valid content."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        assert message.role == "assistant"
        assert len(message.content) == 1
        assert message.content[0].text == "Test response"

    def test_response_message_invalid_role(self):
        """Test that invalid role raises ValidationError."""
        content = ResponseContent(type="text", text="Test response")
        with pytest.raises(ValidationError):
            ResponseMessage(role="invalid_role", content=[content])

    def test_response_message_empty_content(self):
        """Test that empty content array raises ValidationError."""
        with pytest.raises(ValidationError):
            ResponseMessage(role="assistant", content=[])


class TestResponseOutput:
    """Test cases for ResponseOutput model."""

    def test_response_output_valid(self):
        """Test creating ResponseOutput with valid message."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        output = ResponseOutput(message=message, finish_reason="stop")
        assert output.message.role == "assistant"  # pylint: disable=no-member
        assert output.finish_reason == "stop"

    def test_response_output_invalid_finish_reason(self):
        """Test that invalid finish_reason raises ValidationError."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        with pytest.raises(ValidationError):
            ResponseOutput(message=message, finish_reason="invalid_reason")


class TestResponseUsage:
    """Test cases for ResponseUsage model."""

    def test_response_usage_valid(self):
        """Test creating ResponseUsage with valid token counts."""
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_response_usage_negative_tokens(self):
        """Test that negative token counts raise ValidationError."""
        with pytest.raises(ValidationError):
            ResponseUsage(prompt_tokens=-1, completion_tokens=50, total_tokens=150)

    def test_response_usage_zero_tokens(self):
        """Test that zero token counts are allowed."""
        usage = ResponseUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_response_usage_total_tokens_mismatch(self):
        """Test that total_tokens should match sum when validation is implemented."""
        # This is a placeholder - we may add validation later
        usage = ResponseUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=200,  # Intentionally wrong sum
        )
        # Currently no validation, but we might add it later
        assert usage.total_tokens == 200  # pylint: disable=no-member


class TestOpenAIResponse:
    """Test cases for OpenAIResponse model."""

    def test_openai_response_valid_minimal(self):
        """Test creating OpenAIResponse with minimal required fields."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        output = ResponseOutput(message=message, finish_reason="stop")
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        response = OpenAIResponse(
            id="resp_123",
            object="response",
            created_at=1640995200,
            status="completed",
            model="gpt-4",
            output=[output],
            usage=usage,
        )

        assert response.id == "resp_123"
        assert response.object == "response"
        assert response.created_at == 1640995200
        assert response.status == "completed"
        assert response.model == "gpt-4"
        assert len(response.output) == 1
        assert response.usage.total_tokens == 150  # pylint: disable=no-member
        assert response.metadata is None

    def test_openai_response_with_metadata(self):
        """Test creating OpenAIResponse with metadata for referenced documents."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        output = ResponseOutput(message=message, finish_reason="stop")
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        metadata = {
            "referenced_documents": [
                {
                    "doc_url": "https://docs.openshift.com/container-platform/"
                    "4.15/operators/olm/index.html",
                    "doc_title": "Operator Lifecycle Manager (OLM)",
                }
            ]
        }

        response = OpenAIResponse(
            id="resp_123",
            object="response",
            created_at=1640995200,
            status="completed",
            model="gpt-4",
            output=[output],
            usage=usage,
            metadata=metadata,
        )

        assert response.metadata is not None
        assert "referenced_documents" in response.metadata
        assert len(response.metadata["referenced_documents"]) == 1
        assert (
            response.metadata["referenced_documents"][0]["doc_title"]
            == "Operator Lifecycle Manager (OLM)"
        )

    def test_openai_response_invalid_status(self):
        """Test that invalid status raises ValidationError."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        output = ResponseOutput(message=message, finish_reason="stop")
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        with pytest.raises(ValidationError):
            OpenAIResponse(
                id="resp_123",
                object="response",
                created_at=1640995200,
                status="invalid_status",
                model="gpt-4",
                output=[output],
                usage=usage,
            )

    def test_openai_response_invalid_object(self):
        """Test that invalid object type raises ValidationError."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        output = ResponseOutput(message=message, finish_reason="stop")
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        with pytest.raises(ValidationError):
            OpenAIResponse(
                id="resp_123",
                object="invalid_object",
                created_at=1640995200,
                status="completed",
                model="gpt-4",
                output=[output],
                usage=usage,
            )

    def test_openai_response_empty_output(self):
        """Test that empty output array raises ValidationError."""
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        with pytest.raises(ValidationError):
            OpenAIResponse(
                id="resp_123",
                object="response",
                created_at=1640995200,
                status="completed",
                model="gpt-4",
                output=[],
                usage=usage,
            )

    def test_openai_response_empty_id(self):
        """Test that empty ID raises ValidationError."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        output = ResponseOutput(message=message, finish_reason="stop")
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        with pytest.raises(ValidationError):
            OpenAIResponse(
                id="",
                object="response",
                created_at=1640995200,
                status="completed",
                model="gpt-4",
                output=[output],
                usage=usage,
            )

    def test_openai_response_empty_model(self):
        """Test that empty model raises ValidationError."""
        content = ResponseContent(type="text", text="Test response")
        message = ResponseMessage(role="assistant", content=[content])
        output = ResponseOutput(message=message, finish_reason="stop")
        usage = ResponseUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

        with pytest.raises(ValidationError):
            OpenAIResponse(
                id="resp_123",
                object="response",
                created_at=1640995200,
                status="completed",
                model="",
                output=[output],
                usage=usage,
            )
