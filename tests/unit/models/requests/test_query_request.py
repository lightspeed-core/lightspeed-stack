"""Unit tests for QueryRequest model."""

from logging import Logger

import pytest
from pytest_mock import MockerFixture

from models.requests import Attachment, QueryRequest


class TestQueryRequest:
    """Test cases for the QueryRequest model."""

    def test_constructor(self) -> None:
        """Test the QueryRequest constructor."""
        qr = QueryRequest(
            query="Tell me about Kubernetes"
        )  # pyright: ignore[reportCallIssue]

        assert qr.query == "Tell me about Kubernetes"
        assert qr.conversation_id is None
        assert qr.provider is None
        assert qr.model is None
        assert qr.system_prompt is None
        assert qr.attachments is None

    def test_constructor_wrong_conversation_id(self) -> None:
        """Test the QueryRequest constructor with wrong conversation_id."""
        with pytest.raises(ValueError, match="Improper conversation ID 'xyzzy'"):
            _ = QueryRequest(
                query="Tell me about Kubernetes", conversation_id="xyzzy"
            )  # pyright: ignore[reportCallIssue]

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
        )  # pyright: ignore[reportCallIssue]
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
        )  # pyright: ignore[reportCallIssue]
        assert qr.query == "Tell me about Kubernetes"
        assert qr.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert qr.provider == "OpenAI"
        assert qr.model == "gpt-3.5-turbo"
        assert qr.system_prompt == "You are a helpful assistant"
        assert qr.attachments is None

    def test_validate_media_type(self, mocker: MockerFixture) -> None:
        """Test the validate_media_type method.

        Verify that setting a supported media type does not emit a warning.

        Patches the module logger, constructs a QueryRequest with provider,
        model, and media_type "text/plain", and asserts the logger's warning
        method was not called.
        """
        # Mock the logger
        mock_logger = mocker.Mock(spec=Logger)
        mocker.patch("models.requests.logger", mock_logger)

        qr = QueryRequest(
            query="Tell me about Kubernetes",
            provider="OpenAI",
            model="gpt-3.5-turbo",
            media_type="text/plain",
        )  # pyright: ignore[reportCallIssue]
        assert qr is not None
        assert qr.provider == "OpenAI"
        assert qr.model == "gpt-3.5-turbo"
        assert qr.media_type == "text/plain"

        # Media type is now fully supported, no warning expected
        mock_logger.warning.assert_not_called()

    def test_generate_topic_summary_explicit_false(self) -> None:
        """Test that generate_topic_summary can be explicitly set to False."""
        qr = QueryRequest(
            query="Tell me about Kubernetes", generate_topic_summary=False
        )  # pyright: ignore[reportCallIssue]
        assert qr.generate_topic_summary is False

    def test_generate_topic_summary_explicit_true(self) -> None:
        """Test that generate_topic_summary can be explicitly set to True."""
        qr = QueryRequest(
            query="Tell me about Kubernetes", generate_topic_summary=True
        )  # pyright: ignore[reportCallIssue]
        assert qr.generate_topic_summary is True
