"""Unit tests for QueryRequest model."""

from logging import Logger
from unittest.mock import Mock

import pytest

from models.requests import QueryRequest, Attachment


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

    def test_constructor_wrong_conversation_id(self) -> None:
        """Test the QueryRequest constructor with wrong conversation_id."""
        with pytest.raises(ValueError, match="Improper conversation ID 'xyzzy'"):
            _ = QueryRequest(query="Tell me about Kubernetes", conversation_id="xyzzy")

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

    def test_get_documents_no_attachments(self) -> None:
        """Test the get_documents method."""
        attachments = []
        qr = QueryRequest(
            query="Tell me about Kubernetes",
            attachments=attachments,
        )
        documents = qr.get_documents()
        assert len(documents) == 0

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

        # Media type is now fully supported, no warning expected
        mock_logger.warning.assert_not_called()
