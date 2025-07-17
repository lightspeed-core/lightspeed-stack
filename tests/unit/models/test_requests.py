"""Test the QueryRequest, Attachment, and FeedbackRequest models."""

from unittest.mock import Mock
from logging import Logger

import pytest
from pydantic import ValidationError
from models.requests import QueryRequest, Attachment, FeedbackRequest


class TestAttachment:
    """Test cases for the Attachment model."""

    def test_constructor(self) -> None:
        """Test the Attachment with custom values."""
        a = Attachment(
            attachment_type="configuration",
            content_type="application/yaml",
            content="kind: Pod\n metadata:\n name:    private-reg",
        )
        assert a.attachment_type == "configuration"
        assert a.content_type == "application/yaml"
        assert a.content == "kind: Pod\n metadata:\n name:    private-reg"

    def test_constructor_unknown_attachment_type(self) -> None:
        """Test the Attachment with custom values."""
        # for now we allow any content type
        a = Attachment(
            attachment_type="configuration",
            content_type="unknown/type",
            content="kind: Pod\n metadata:\n name:    private-reg",
        )
        assert a.attachment_type == "configuration"
        assert a.content_type == "unknown/type"
        assert a.content == "kind: Pod\n metadata:\n name:    private-reg"


class TestQueryRequest:
    """Test cases for the QueryRequest model."""

    def test_constructor(self) -> None:
        """Test the QueryRequest constructor."""
        qr = QueryRequest(query="Tell me about Kubernetes")

        assert qr.query == "Tell me about Kubernetes"
        assert qr.conversation_id is None
        assert qr.provider is None
        assert qr.model is None
        assert qr.system_prompt is None
        assert qr.attachments is None

    def test_with_attachments(self) -> None:
        """Test the QueryRequest with attachments."""
        attachments = [
            Attachment(
                attachment_type="log",
                content_type="text/plain",
                content="this is attachment",
            ),
            Attachment(
                attachment_type="configuration",
                content_type="application/yaml",
                content="kind: Pod\n metadata:\n name:    private-reg",
            ),
        ]
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            attachments=attachments,
        )
        assert qr.attachments is not None
        assert len(qr.attachments) == 2

        # the following warning is false positive
        # pylint: disable=unsubscriptable-object
        assert qr.attachments[0].attachment_type == "log"
        assert qr.attachments[0].content_type == "text/plain"
        assert qr.attachments[0].content == "this is attachment"
        assert qr.attachments[1].attachment_type == "configuration"
        assert qr.attachments[1].content_type == "application/yaml"
        assert (
            qr.attachments[1].content == "kind: Pod\n metadata:\n name:    private-reg"
        )

    def test_with_optional_fields(self) -> None:
        """Test the QueryRequest with optional fields."""
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            provider="OpenAI",
            model="gpt-3.5-turbo",
            system_prompt="You are a helpful assistant",
        )
        assert qr.query == "Tell me about Kubernetes"
        assert qr.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert qr.provider == "OpenAI"
        assert qr.model == "gpt-3.5-turbo"
        assert qr.system_prompt == "You are a helpful assistant"
        assert qr.attachments is None

    def test_get_documents(self) -> None:
        """Test the get_documents method."""
        attachments = [
            Attachment(
                attachment_type="log",
                content_type="text/plain",
                content="this is attachment",
            ),
            Attachment(
                attachment_type="configuration",
                content_type="application/yaml",
                content="kind: Pod\n metadata:\n name:    private-reg",
            ),
        ]
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            attachments=attachments,
        )
        documents = qr.get_documents()
        assert len(documents) == 2
        assert documents[0]["content"] == "this is attachment"
        assert documents[0]["mime_type"] == "text/plain"
        assert documents[1]["content"] == "kind: Pod\n metadata:\n name:    private-reg"
        assert documents[1]["mime_type"] == "application/yaml"

    def test_validate_provider_and_model(self) -> None:
        """Test the validate_provider_and_model method."""
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            provider="OpenAI",
            model="gpt-3.5-turbo",
        )
        assert qr is not None
        validated_qr = qr.validate_provider_and_model()
        assert validated_qr.provider == "OpenAI"
        assert validated_qr.model == "gpt-3.5-turbo"

        # Test with missing provider
        with pytest.raises(
            ValueError, match="Provider must be specified if model is specified"
        ):
            QueryRequest(query="Tell me about Kubernetes", model="gpt-3.5-turbo")

        # Test with missing model
        with pytest.raises(
            ValueError, match="Model must be specified if provider is specified"
        ):
            QueryRequest(query="Tell me about Kubernetes", provider="OpenAI")

    def test_validate_media_type(self, mocker) -> None:
        """Test the validate_media_type method."""

        # Mock the logger
        mock_logger = Mock(spec=Logger)
        mocker.patch("models.requests.logger", mock_logger)

        qr = QueryRequest(
            query="Tell me about Kubernetes",
            provider="OpenAI",
            model="gpt-3.5-turbo",
            media_type="text/plain",
        )
        assert qr is not None
        assert qr.provider == "OpenAI"
        assert qr.model == "gpt-3.5-turbo"
        assert qr.media_type == "text/plain"

        mock_logger.warning.assert_called_once_with(
            "media_type was set in the request but is not supported. The value will be ignored."
        )


class TestFeedbackRequest:
    """Test cases for the FeedbackRequest model."""

    def test_constructor(self) -> None:
        """Test the FeedbackRequest constructor."""
        fr = FeedbackRequest(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            user_question="What is OpenStack?",
            llm_response="OpenStack is a cloud computing platform.",
            sentiment=1,
            user_feedback="This is a great response!",
        )
        assert fr.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert fr.user_question == "What is OpenStack?"
        assert fr.llm_response == "OpenStack is a cloud computing platform."
        assert fr.sentiment == 1
        assert fr.user_feedback == "This is a great response!"

    def test_check_invalid_uuid_format(self) -> None:
        """Test the UUID format check."""
        with pytest.raises(ValueError, match="Improper conversation ID invalid-uuid"):
            FeedbackRequest(
                conversation_id="invalid-uuid",
                user_question="What is OpenStack?",
                llm_response="OpenStack is a cloud computing platform.",
            )

    def test_check_sentiment(self) -> None:
        """Test the sentiment value check."""
        with pytest.raises(
            ValueError, match="Improper sentiment value of 99, needs to be -1 or 1"
        ):
            FeedbackRequest(
                conversation_id="123e4567-e89b-12d3-a456-426614174000",
                user_question="What is OpenStack?",
                llm_response="OpenStack is a cloud computing platform.",
                sentiment=99,  # Invalid sentiment
            )

    def test_check_sentiment_or_user_feedback(self) -> None:
        """Test that at least one of sentiment or user_feedback is provided."""
        with pytest.raises(
            ValueError, match="Either 'sentiment' or 'user_feedback' must be set"
        ):
            FeedbackRequest(
                conversation_id="123e4567-e89b-12d3-a456-426614174000",
                user_question="What is OpenStack?",
                llm_response="OpenStack is a cloud computing platform.",
                sentiment=None,
                user_feedback=None,
            )

    def test_feedback_too_long(self) -> None:
        """Test that user feedback is limited to 4096 characters."""
        with pytest.raises(
            ValidationError, match="should have at most 4096 characters"
        ):
            FeedbackRequest(
                conversation_id="12345678-abcd-0000-0123-456789abcdef",
                user_question="What is this?",
                llm_response="Some response",
                user_feedback="a" * 4097,
            )
