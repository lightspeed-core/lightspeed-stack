"""Tests for transcript anonymization functionality."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from models.requests import QueryRequest, Attachment
from utils.transcripts import store_transcript, construct_transcripts_path
from utils.types import TurnSummary


# Set up test environment variable before importing the module
@pytest.fixture(autouse=True)
def setup_test_pepper():
    """Set up test pepper environment variable for all tests."""
    test_pepper = "test-pepper-for-transcript-tests"
    with patch.dict(os.environ, {"USER_ANON_PEPPER": test_pepper}):
        yield


class TestTranscriptAnonymization:
    """Test transcript storage with user anonymization."""

    @patch("utils.transcripts.get_anonymous_user_id")
    @patch("utils.transcripts.get_suid")
    @patch("utils.transcripts.configuration")
    def test_store_transcript_anonymizes_user_id(
        self, mock_config, mock_get_suid, mock_get_anonymous
    ):
        """Test that store_transcript uses anonymous user ID."""
        # Setup mocks
        mock_get_anonymous.return_value = "anon-uuid-123"
        mock_get_suid.return_value = "transcript-uuid"

        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config.user_data_collection_configuration.transcripts_storage = (
                temp_dir
            )

            # Create test data
            query_request = QueryRequest(
                query="Test query", model="test-model", provider="test-provider"
            )

            summary = TurnSummary(llm_response="Test response", tool_calls=[])

            # Call store_transcript
            store_transcript(
                user_id="original_user@example.com",
                conversation_id="conv-123",
                model_id="test-model",
                provider_id="test-provider",
                query_is_valid=True,
                query="Test query",
                query_request=query_request,
                summary=summary,
                rag_chunks=[],
                truncated=False,
                attachments=[],
            )

            # Verify anonymous user ID was used
            mock_get_anonymous.assert_called_once_with("original_user@example.com")

            # Verify file was created with anonymous path
            expected_path = (
                Path(temp_dir) / "anon-uuid-123" / "conv-123" / "transcript-uuid.json"
            )
            assert expected_path.exists()

            # Verify file content contains anonymous ID, not original
            with open(expected_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            assert data["metadata"]["anonymous_user_id"] == "anon-uuid-123"
            assert "user_id" not in data["metadata"]
            assert data["metadata"]["conversation_id"] == "conv-123"

    def test_construct_transcripts_path_with_anonymous_id(self):
        """Test that transcript path construction uses anonymous ID."""
        # This test verifies the path construction function directly
        result = construct_transcripts_path("anon-uuid-456", "conv-789")

        # Path should contain the anonymous ID, not original user ID
        assert "anon-uuid-456" in str(result)
        assert "conv-789" in str(result)

    @patch("utils.transcripts.get_anonymous_user_id")
    @patch("utils.transcripts.get_suid")
    @patch("utils.transcripts.configuration")
    def test_store_transcript_preserves_other_metadata(
        self, mock_config, mock_get_suid, mock_get_anonymous
    ):
        """Test that anonymization preserves all other metadata."""
        mock_get_anonymous.return_value = "anon-preserved-test"
        mock_get_suid.return_value = "metadata-test-uuid"

        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config.user_data_collection_configuration.transcripts_storage = (
                temp_dir
            )

            query_request = QueryRequest(
                query="Metadata test",
                model="metadata-model",
                provider="metadata-provider",
            )

            summary = TurnSummary(llm_response="Metadata response", tool_calls=[])

            # Store transcript with rich metadata
            store_transcript(
                user_id="metadata_user@example.com",
                conversation_id="metadata-conv",
                model_id="actual-model",
                provider_id="actual-provider",
                query_is_valid=True,
                query="Metadata test query",
                query_request=query_request,
                summary=summary,
                rag_chunks=["chunk1", "chunk2"],
                truncated=True,
                attachments=[],
            )

            # Read and verify all metadata is preserved
            transcript_file = (
                Path(temp_dir)
                / "anon-preserved-test"
                / "metadata-conv"
                / "metadata-test-uuid.json"
            )
            with open(transcript_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            metadata = data["metadata"]
            assert metadata["provider"] == "actual-provider"
            assert metadata["model"] == "actual-model"
            assert metadata["query_provider"] == "metadata-provider"
            assert metadata["query_model"] == "metadata-model"
            assert metadata["conversation_id"] == "metadata-conv"
            assert "timestamp" in metadata

            # Verify other data preserved
            assert data["redacted_query"] == "Metadata test query"
            assert data["query_is_valid"] is True
            assert data["llm_response"] == "Metadata response"
            assert data["rag_chunks"] == ["chunk1", "chunk2"]
            assert data["truncated"] is True

    @patch("utils.transcripts.get_anonymous_user_id")
    @patch("utils.transcripts.get_suid")
    @patch("utils.transcripts.configuration")
    def test_store_transcript_with_attachments(
        self, mock_config, mock_get_suid, mock_get_anonymous
    ):
        """Test transcript storage with attachments preserves anonymization."""
        mock_get_anonymous.return_value = "anon-attachments-test"
        mock_get_suid.return_value = "attachments-uuid"

        with tempfile.TemporaryDirectory() as temp_dir:
            mock_config.user_data_collection_configuration.transcripts_storage = (
                temp_dir
            )

            # Create attachment
            attachment = Attachment(
                attachment_type="text",
                content_type="text/plain",
                content="Test attachment content",
            )

            query_request = QueryRequest(
                query="Query with attachment",
                model="attachment-model",
                provider="attachment-provider",
            )

            summary = TurnSummary(
                llm_response="Response with attachment", tool_calls=[]
            )

            store_transcript(
                user_id="attachment_user@example.com",
                conversation_id="attachment-conv",
                model_id="attachment-actual-model",
                provider_id="attachment-actual-provider",
                query_is_valid=True,
                query="Query with attachment",
                query_request=query_request,
                summary=summary,
                rag_chunks=[],
                truncated=False,
                attachments=[attachment],
            )

            # Verify attachment data preserved with anonymization
            transcript_file = (
                Path(temp_dir)
                / "anon-attachments-test"
                / "attachment-conv"
                / "attachments-uuid.json"
            )
            with open(transcript_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            assert data["metadata"]["anonymous_user_id"] == "anon-attachments-test"
            assert len(data["attachments"]) == 1
            assert data["attachments"][0]["attachment_type"] == "text"
            assert data["attachments"][0]["content"] == "Test attachment content"

    @patch("utils.transcripts.configuration")
    def test_path_sanitization_with_anonymous_ids(self, mock_config):
        """Test that path sanitization works correctly with anonymous UUIDs."""
        # Setup mock configuration
        mock_config.user_data_collection_configuration.transcripts_storage = (
            "/tmp/transcripts"
        )

        # Test with various UUID formats and potential path injection
        test_cases = [
            ("anon-uuid-123", "conv-456"),
            ("../anon-malicious", "conv-normal"),  # Path traversal attempt
            ("anon/with/slashes", "conv-789"),  # Embedded slashes
            ("anon-normal", "../conv-malicious"),  # Conversation ID traversal attempt
        ]

        for anon_id, conv_id in test_cases:
            result = construct_transcripts_path(anon_id, conv_id)
            result_str = str(result)

            # Should not contain path traversal sequences
            assert "../" not in result_str
            # Paths should be absolute (start with /) since we use /tmp/transcripts as base
            assert result_str.startswith("/tmp/transcripts/")

    @patch("utils.transcripts.get_anonymous_user_id")
    def test_logging_shows_anonymization(self, mock_get_anonymous, caplog):
        """Test that logging shows anonymization is happening."""
        import logging  # pylint: disable=import-outside-toplevel

        mock_get_anonymous.return_value = "anon-logging-test"

        with caplog.at_level(logging.DEBUG):
            # Create minimal test setup
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch("utils.transcripts.configuration") as mock_config:
                    mock_config.user_data_collection_configuration.transcripts_storage = (
                        temp_dir
                    )

                    with patch(
                        "utils.transcripts.get_suid", return_value="log-test-uuid"
                    ):
                        query_request = QueryRequest(
                            query="Log test", model="log-model", provider="log-provider"
                        )

                        summary = TurnSummary(
                            llm_response="Log response", tool_calls=[]
                        )

                        store_transcript(
                            user_id="log_test_user@example.com",
                            conversation_id="log-conv",
                            model_id="log-model",
                            provider_id="log-provider",
                            query_is_valid=True,
                            query="Log test query",
                            query_request=query_request,
                            summary=summary,
                            rag_chunks=[],
                            truncated=False,
                            attachments=[],
                        )

        # Check that transcript storage is logged
        log_messages = [record.message for record in caplog.records]
        storage_logs = [
            msg
            for msg in log_messages
            if "Storing transcript for anonymous user" in msg
        ]
        assert len(storage_logs) > 0

        # Verify the log shows only anonymous user ID (no original user ID)
        storage_log = storage_logs[0]
        assert "anon-logging-test" in storage_log
        # Should NOT contain any reference to original user ID
        assert "log_test_user" not in storage_log
        assert "log_test..." not in storage_log
