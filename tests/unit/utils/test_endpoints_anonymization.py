"""Tests for endpoint utilities anonymization functionality."""

from unittest.mock import patch, MagicMock
import pytest

from utils.endpoints import validate_conversation_ownership
from models.database.conversations import UserConversation


class TestEndpointsAnonymization:
    """Test endpoint utilities user anonymization."""

    @patch("utils.endpoints.get_anonymous_user_id")
    @patch("utils.endpoints.get_session")
    def test_validate_conversation_ownership_uses_anonymous_id(
        self, mock_get_session, mock_get_anonymous
    ):
        """Test that conversation ownership validation uses anonymous user ID."""
        # Setup mocks
        conversation = MagicMock(spec=UserConversation)
        conversation.id = "test-conv-123"
        conversation.anonymous_user_id = "anon-owner-456"

        mock_get_anonymous.return_value = "anon-owner-456"
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            conversation
        )

        # Call validation
        result = validate_conversation_ownership(
            user_id="owner@example.com", conversation_id="test-conv-123"
        )

        # Verify anonymous user ID was obtained
        mock_get_anonymous.assert_called_once_with("owner@example.com")

        # Verify database query used anonymous ID
        mock_session.query.assert_called_once_with(UserConversation)
        filter_call = mock_session.query.return_value.filter_by.call_args
        assert filter_call[1]["id"] == "test-conv-123"
        assert filter_call[1]["anonymous_user_id"] == "anon-owner-456"

        # Verify correct conversation returned
        assert result == conversation

    @patch("utils.endpoints.get_anonymous_user_id")
    @patch("utils.endpoints.get_session")
    def test_validate_conversation_ownership_not_owned(
        self, mock_get_session, mock_get_anonymous
    ):
        """Test validation fails when user doesn't own conversation."""
        mock_get_anonymous.return_value = "anon-not-owner-789"
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        # Call validation
        result = validate_conversation_ownership(
            user_id="notowner@example.com", conversation_id="not-owned-conv"
        )

        # Verify anonymous user ID was used for lookup
        mock_get_anonymous.assert_called_once_with("notowner@example.com")
        filter_call = mock_session.query.return_value.filter_by.call_args
        assert filter_call[1]["anonymous_user_id"] == "anon-not-owner-789"

        # Verify None returned for non-owned conversation
        assert result is None

    @patch("utils.endpoints.get_anonymous_user_id")
    @patch("utils.endpoints.get_session")
    def test_validate_conversation_ownership_different_users(
        self, mock_get_session, mock_get_anonymous
    ):
        """Test that different users get different anonymous IDs for validation."""

        def mock_anonymous_side_effect(user_id):
            if user_id == "user1@example.com":
                return "anon-user1-validation"
            if user_id == "user2@example.com":
                return "anon-user2-validation"
            return "anon-unknown"

        mock_get_anonymous.side_effect = mock_anonymous_side_effect

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        # Validate for user 1
        result1 = validate_conversation_ownership(
            user_id="user1@example.com", conversation_id="shared-conv-test"
        )

        first_call = mock_session.query.return_value.filter_by.call_args
        assert first_call[1]["anonymous_user_id"] == "anon-user1-validation"

        # Reset mock for second call
        mock_session.reset_mock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        # Validate for user 2
        result2 = validate_conversation_ownership(
            user_id="user2@example.com",
            conversation_id="shared-conv-test",  # Same conversation ID
        )

        second_call = mock_session.query.return_value.filter_by.call_args
        assert second_call[1]["anonymous_user_id"] == "anon-user2-validation"

        # Both should return None since neither owns the conversation
        assert result1 is None
        assert result2 is None

        # But they used different anonymous IDs (checking the calls, not constant comparison)
        assert first_call[1]["anonymous_user_id"] != second_call[1]["anonymous_user_id"]

    @patch("utils.endpoints.get_anonymous_user_id")
    @patch("utils.endpoints.get_session")
    def test_validate_conversation_ownership_preserves_conversation_data(
        self, mock_get_session, mock_get_anonymous
    ):
        """Test that validation preserves all conversation data."""
        # Create conversation with full data
        conversation = UserConversation()
        conversation.id = "full-data-conv"
        conversation.anonymous_user_id = "anon-full-data"
        conversation.last_used_model = "test-model"
        conversation.last_used_provider = "test-provider"
        conversation.message_count = 42

        mock_get_anonymous.return_value = "anon-full-data"
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            conversation
        )

        # Validate ownership
        result = validate_conversation_ownership(
            user_id="datauser@example.com", conversation_id="full-data-conv"
        )

        # Verify all conversation data is preserved
        assert result.id == "full-data-conv"
        assert result.anonymous_user_id == "anon-full-data"
        assert result.last_used_model == "test-model"
        assert result.last_used_provider == "test-provider"
        assert result.message_count == 42

    @patch("utils.endpoints.get_anonymous_user_id")
    def test_validate_conversation_ownership_error_handling(self, mock_get_anonymous):
        """Test that validation handles errors gracefully."""
        mock_get_anonymous.return_value = "anon-error-test"

        # Simulate database error
        with patch("utils.endpoints.get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_session.query.side_effect = Exception("Database error")

            # Should propagate the exception
            with pytest.raises(Exception, match="Database error"):
                validate_conversation_ownership(
                    user_id="erroruser@example.com", conversation_id="error-conv"
                )

            # Verify anonymous ID was still obtained before error
            mock_get_anonymous.assert_called_once_with("erroruser@example.com")
