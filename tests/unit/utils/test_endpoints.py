"""Unit tests for endpoints utility functions."""

# pylint: disable=too-many-lines

import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import AnyUrl
from pytest_mock import MockerFixture
from sqlalchemy.exc import SQLAlchemyError

from models.database.conversations import UserConversation
from utils import endpoints
from utils.types import ReferencedDocument


@pytest.fixture(name="input_file")
def input_file_fixture(tmp_path: Path) -> str:
    """Create file manually using the tmp_path fixture."""
    filename = os.path.join(tmp_path, "prompt.txt")
    with open(filename, "wt", encoding="utf-8") as fout:
        fout.write("this is prompt!")
    return filename


# Tests for unified create_referenced_documents function
class TestCreateReferencedDocuments:
    """Test cases for the unified create_referenced_documents function."""

    def test_create_referenced_documents_empty_chunks(self) -> None:
        """Test that empty chunks list returns empty result."""
        result = endpoints.create_referenced_documents([])
        assert not result

    def test_create_referenced_documents_http_urls_referenced_document_format(
        self,
    ) -> None:
        """Test HTTP URLs with ReferencedDocument format."""

        mock_chunk1 = type("MockChunk", (), {"source": "https://example.com/doc1"})()
        mock_chunk2 = type("MockChunk", (), {"source": "https://example.com/doc2"})()

        result = endpoints.create_referenced_documents([mock_chunk1, mock_chunk2])

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "doc1"
        assert result[1].doc_url == AnyUrl("https://example.com/doc2")
        assert result[1].doc_title == "doc2"

    def test_create_referenced_documents_document_ids_with_metadata(self) -> None:
        """Test document IDs with metadata enrichment."""

        mock_chunk1 = type("MockChunk", (), {"source": "doc_id_1"})()
        mock_chunk2 = type("MockChunk", (), {"source": "doc_id_2"})()

        metadata_map = {
            "doc_id_1": {"docs_url": "https://example.com/doc1", "title": "Document 1"},
            "doc_id_2": {"docs_url": "https://example.com/doc2", "title": "Document 2"},
        }

        result = endpoints.create_referenced_documents(
            [mock_chunk1, mock_chunk2], metadata_map
        )

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "Document 1"
        assert result[1].doc_url == AnyUrl("https://example.com/doc2")
        assert result[1].doc_title == "Document 2"

    def test_create_referenced_documents_skips_tool_names(self) -> None:
        """Test that tool names like 'knowledge_search' are skipped."""

        mock_chunk1 = type("MockChunk", (), {"source": "knowledge_search"})()
        mock_chunk2 = type("MockChunk", (), {"source": "https://example.com/doc1"})()

        result = endpoints.create_referenced_documents([mock_chunk1, mock_chunk2])

        # one referenced document is expected
        assert len(result) == 1
        # result must exist
        assert result[0] is not None
        # result must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "doc1"

    def test_create_referenced_documents_skips_empty_sources(self) -> None:
        """Test that chunks with empty or None sources are skipped."""

        mock_chunk1 = type("MockChunk", (), {"source": None})()
        mock_chunk2 = type("MockChunk", (), {"source": ""})()
        mock_chunk3 = type("MockChunk", (), {"source": "https://example.com/doc1"})()

        result = endpoints.create_referenced_documents(
            [mock_chunk1, mock_chunk2, mock_chunk3]
        )

        # one referenced document is expected
        assert len(result) == 1
        # result must exist
        assert result[0] is not None
        # result must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[0].doc_title == "doc1"

    def test_create_referenced_documents_deduplication(self) -> None:
        """Test that duplicate sources are deduplicated."""

        mock_chunk1 = type("MockChunk", (), {"source": "https://example.com/doc1"})()
        mock_chunk2 = type(
            "MockChunk", (), {"source": "https://example.com/doc1"}
        )()  # Duplicate
        mock_chunk3 = type("MockChunk", (), {"source": "doc_id_1"})()
        mock_chunk4 = type("MockChunk", (), {"source": "doc_id_1"})()  # Duplicate

        result = endpoints.create_referenced_documents(
            [mock_chunk1, mock_chunk2, mock_chunk3, mock_chunk4]
        )

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        assert result[0].doc_url == AnyUrl("https://example.com/doc1")
        assert result[1].doc_title == "doc_id_1"

    def test_create_referenced_documents_invalid_urls(self) -> None:
        """Test handling of invalid URLs."""

        mock_chunk1 = type("MockChunk", (), {"source": "not-a-valid-url"})()
        mock_chunk2 = type("MockChunk", (), {"source": "https://example.com/doc1"})()

        result = endpoints.create_referenced_documents([mock_chunk1, mock_chunk2])

        # two referenced documents are expected
        assert len(result) == 2
        # results must exist
        assert result[0] is not None
        assert result[1] is not None
        # results must be of the right type
        assert isinstance(result[0], ReferencedDocument)
        assert isinstance(result[1], ReferencedDocument)
        assert result[0].doc_url is None
        assert result[0].doc_title == "not-a-valid-url"
        assert result[1].doc_url == AnyUrl("https://example.com/doc1")
        assert result[1].doc_title == "doc1"


class TestValidateAndRetrieveConversation:
    """Tests for validate_and_retrieve_conversation function."""

    def test_successful_retrieval(self, mocker: MockerFixture) -> None:
        """Test successful conversation retrieval when user has access."""
        normalized_conv_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mock_conversation = mocker.Mock(spec=UserConversation)
        mock_conversation.id = normalized_conv_id
        mock_conversation.user_id = user_id

        mocker.patch("utils.endpoints.can_access_conversation", return_value=True)
        mocker.patch(
            "utils.endpoints.retrieve_conversation", return_value=mock_conversation
        )

        result = endpoints.validate_and_retrieve_conversation(
            normalized_conv_id=normalized_conv_id,
            user_id=user_id,
            others_allowed=False,
        )

        assert result == mock_conversation

    def test_forbidden_access(self, mocker: MockerFixture) -> None:
        """Test that 403 Forbidden is raised when user doesn't have access."""
        normalized_conv_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mocker.patch("utils.endpoints.can_access_conversation", return_value=False)
        mocker.patch("utils.endpoints.logger")

        with pytest.raises(HTTPException) as exc_info:
            endpoints.validate_and_retrieve_conversation(
                normalized_conv_id=normalized_conv_id,
                user_id=user_id,
                others_allowed=False,
            )

        assert exc_info.value.status_code == 403
        # Check that it's a forbidden response with proper error details
        assert isinstance(exc_info.value.detail, dict)
        assert "response" in exc_info.value.detail
        assert "cause" in exc_info.value.detail

    def test_conversation_not_found(self, mocker: MockerFixture) -> None:
        """Test that 404 Not Found is raised when conversation doesn't exist."""
        normalized_conv_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mocker.patch("utils.endpoints.can_access_conversation", return_value=True)
        mocker.patch("utils.endpoints.retrieve_conversation", return_value=None)
        mocker.patch("utils.endpoints.logger")

        with pytest.raises(HTTPException) as exc_info:
            endpoints.validate_and_retrieve_conversation(
                normalized_conv_id=normalized_conv_id,
                user_id=user_id,
                others_allowed=False,
            )

        assert exc_info.value.status_code == 404
        # Check that it's a not found response with proper error details
        assert isinstance(exc_info.value.detail, dict)
        assert "response" in exc_info.value.detail
        assert "cause" in exc_info.value.detail

    def test_database_error(self, mocker: MockerFixture) -> None:
        """Test that 500 Internal Server Error is raised on database error."""
        normalized_conv_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mocker.patch("utils.endpoints.can_access_conversation", return_value=True)
        mocker.patch(
            "utils.endpoints.retrieve_conversation",
            side_effect=SQLAlchemyError("Database connection error", None, None),
        )
        mocker.patch("utils.endpoints.logger")

        with pytest.raises(HTTPException) as exc_info:
            endpoints.validate_and_retrieve_conversation(
                normalized_conv_id=normalized_conv_id,
                user_id=user_id,
                others_allowed=False,
            )

        assert exc_info.value.status_code == 500
        # Check that it's an internal server error response with proper error details
        assert isinstance(exc_info.value.detail, dict)
        assert "response" in exc_info.value.detail
        assert "cause" in exc_info.value.detail

    def test_successful_retrieval_with_others_allowed(
        self, mocker: MockerFixture
    ) -> None:
        """Test successful retrieval when others_allowed is True."""
        normalized_conv_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mock_conversation = mocker.Mock(spec=UserConversation)
        mock_conversation.id = normalized_conv_id
        mock_conversation.user_id = "other-user"  # Different user

        mocker.patch("utils.endpoints.can_access_conversation", return_value=True)
        mocker.patch(
            "utils.endpoints.retrieve_conversation", return_value=mock_conversation
        )

        result = endpoints.validate_and_retrieve_conversation(
            normalized_conv_id=normalized_conv_id,
            user_id=user_id,
            others_allowed=True,  # Allow access to others' conversations
        )

        assert result == mock_conversation


class TestValidateConversationOwnership:
    """Tests for validate_conversation_ownership function."""

    def test_successful_retrieval_own_conversation(self, mocker: MockerFixture) -> None:
        """Test successful retrieval when conversation belongs to user."""
        conversation_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mock_conversation = mocker.Mock(spec=UserConversation)
        mock_conversation.id = conversation_id
        mock_conversation.user_id = user_id

        # Mock the database session and query chain
        mock_query = mocker.Mock()
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.first.return_value = mock_conversation
        mock_query.filter_by.return_value = mock_filtered_query

        mock_session = mocker.Mock()
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)

        mocker.patch("utils.endpoints.get_session", return_value=mock_session)

        result = endpoints.validate_conversation_ownership(
            user_id=user_id,
            conversation_id=conversation_id,
            others_allowed=False,
        )

        assert result == mock_conversation
        # Verify filter_by was called with both id and user_id
        mock_query.filter_by.assert_called_once_with(
            id=conversation_id, user_id=user_id
        )

    def test_returns_none_when_not_own_conversation(
        self, mocker: MockerFixture
    ) -> None:
        """Test returns None when conversation doesn't belong to user."""
        conversation_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        # Mock the database session and query chain - returns None
        mock_query = mocker.Mock()
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.first.return_value = None
        mock_query.filter_by.return_value = mock_filtered_query

        mock_session = mocker.Mock()
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)

        mocker.patch("utils.endpoints.get_session", return_value=mock_session)

        result = endpoints.validate_conversation_ownership(
            user_id=user_id,
            conversation_id=conversation_id,
            others_allowed=False,
        )

        assert result is None
        # Verify filter_by was called with both id and user_id
        mock_query.filter_by.assert_called_once_with(
            id=conversation_id, user_id=user_id
        )

    def test_successful_retrieval_others_allowed(self, mocker: MockerFixture) -> None:
        """Test successful retrieval when others_allowed=True (admin access)."""
        conversation_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mock_conversation = mocker.Mock(spec=UserConversation)
        mock_conversation.id = conversation_id
        mock_conversation.user_id = "other-user"  # Different user

        # Mock the database session and query chain
        mock_query = mocker.Mock()
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.first.return_value = mock_conversation
        mock_query.filter_by.return_value = mock_filtered_query

        mock_session = mocker.Mock()
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)

        mocker.patch("utils.endpoints.get_session", return_value=mock_session)

        result = endpoints.validate_conversation_ownership(
            user_id=user_id,
            conversation_id=conversation_id,
            others_allowed=True,
        )

        assert result == mock_conversation
        # Verify filter_by was called with only id (not user_id) when others_allowed=True
        mock_query.filter_by.assert_called_once_with(id=conversation_id)

    def test_returns_none_when_conversation_not_found_others_allowed(
        self, mocker: MockerFixture
    ) -> None:
        """Test returns None when conversation doesn't exist even with others_allowed=True."""
        conversation_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        # Mock the database session and query chain - returns None
        mock_query = mocker.Mock()
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.first.return_value = None
        mock_query.filter_by.return_value = mock_filtered_query

        mock_session = mocker.Mock()
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)

        mocker.patch("utils.endpoints.get_session", return_value=mock_session)

        result = endpoints.validate_conversation_ownership(
            user_id=user_id,
            conversation_id=conversation_id,
            others_allowed=True,
        )

        assert result is None
        # Verify filter_by was called with only id
        mock_query.filter_by.assert_called_once_with(id=conversation_id)

    def test_default_others_allowed_false(self, mocker: MockerFixture) -> None:
        """Test that others_allowed defaults to False."""
        conversation_id = "123e4567-e89b-12d3-a456-426614174000"
        user_id = "user-123"

        mock_conversation = mocker.Mock(spec=UserConversation)
        mock_conversation.id = conversation_id
        mock_conversation.user_id = user_id

        # Mock the database session and query chain
        mock_query = mocker.Mock()
        mock_filtered_query = mocker.Mock()
        mock_filtered_query.first.return_value = mock_conversation
        mock_query.filter_by.return_value = mock_filtered_query

        mock_session = mocker.Mock()
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = mocker.Mock(return_value=mock_session)
        mock_session.__exit__ = mocker.Mock(return_value=None)

        mocker.patch("utils.endpoints.get_session", return_value=mock_session)

        # Call without others_allowed parameter (should default to False)
        result = endpoints.validate_conversation_ownership(
            user_id=user_id,
            conversation_id=conversation_id,
        )

        assert result == mock_conversation
        # Verify filter_by was called with both id and user_id (default behavior)
        mock_query.filter_by.assert_called_once_with(
            id=conversation_id, user_id=user_id
        )
