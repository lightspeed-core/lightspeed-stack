"""Tests for query endpoint anonymization functionality."""

import logging
from unittest.mock import patch, MagicMock

from sqlalchemy import inspect

from app.endpoints.query import persist_user_conversation_details
from models.database.conversations import UserConversation


class TestQueryAnonymization:
    """Test query endpoint user anonymization."""

    @patch("app.endpoints.query.get_anonymous_user_id")
    @patch("app.endpoints.query.get_session")
    def test_persist_user_conversation_details_new_conversation(
        self, mock_get_session, mock_get_anonymous
    ):
        """Test persisting new conversation uses anonymous user ID."""
        # Setup mocks
        mock_get_anonymous.return_value = "anon-new-conv-123"
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        # Call function
        persist_user_conversation_details(
            user_id="new_user@example.com",
            conversation_id="new-conv-456",
            model="test-model",
            provider_id="test-provider",
        )

        # Verify anonymous user ID was obtained
        mock_get_anonymous.assert_called_once_with("new_user@example.com")

        # Verify database query used anonymous ID
        mock_session.query.assert_called_once_with(UserConversation)
        filter_call = mock_session.query.return_value.filter_by.call_args
        assert filter_call[1]["id"] == "new-conv-456"
        assert filter_call[1]["anonymous_user_id"] == "anon-new-conv-123"

        # Verify new conversation was created with anonymous ID
        mock_session.add.assert_called_once()
        added_conversation = mock_session.add.call_args[0][0]
        assert isinstance(added_conversation, UserConversation)
        assert added_conversation.id == "new-conv-456"
        assert added_conversation.anonymous_user_id == "anon-new-conv-123"
        assert added_conversation.last_used_model == "test-model"
        assert added_conversation.last_used_provider == "test-provider"
        assert added_conversation.message_count == 1

        mock_session.commit.assert_called_once()

    @patch("app.endpoints.query.get_anonymous_user_id")
    @patch("app.endpoints.query.get_session")
    def test_persist_user_conversation_details_existing_conversation(
        self, mock_get_session, mock_get_anonymous
    ):
        """Test updating existing conversation uses anonymous user ID."""
        # Setup existing conversation
        existing_conv = MagicMock(spec=UserConversation)
        existing_conv.last_used_model = "old-model"
        existing_conv.last_used_provider = "old-provider"
        existing_conv.message_count = 5

        mock_get_anonymous.return_value = "anon-existing-789"
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            existing_conv
        )

        # Call function
        persist_user_conversation_details(
            user_id="existing_user@example.com",
            conversation_id="existing-conv-123",
            model="new-model",
            provider_id="new-provider",
        )

        # Verify anonymous user ID was used for lookup
        mock_get_anonymous.assert_called_once_with("existing_user@example.com")
        filter_call = mock_session.query.return_value.filter_by.call_args
        assert filter_call[1]["anonymous_user_id"] == "anon-existing-789"

        # Verify existing conversation was updated
        assert existing_conv.last_used_model == "new-model"
        assert existing_conv.last_used_provider == "new-provider"
        assert existing_conv.message_count == 6  # Incremented

        # Verify no new conversation was added
        mock_session.add.assert_not_called()
        mock_session.commit.assert_called_once()

    @patch("app.endpoints.query.get_anonymous_user_id")
    def test_persist_user_conversation_logs_anonymization(
        self, mock_get_anonymous, caplog
    ):
        """Test that conversation persistence logs anonymization."""

        mock_get_anonymous.return_value = "anon-logging-456"

        with caplog.at_level(logging.DEBUG):
            with patch("app.endpoints.query.get_session") as mock_get_session:
                mock_session = MagicMock()
                mock_get_session.return_value.__enter__.return_value = mock_session
                mock_session.query.return_value.filter_by.return_value.first.return_value = (
                    None
                )

                persist_user_conversation_details(
                    user_id="logging_test_user@example.com",
                    conversation_id="logging-conv-789",
                    model="logging-model",
                    provider_id="logging-provider",
                )

        # Check that anonymization is logged
        log_messages = [record.message for record in caplog.records]
        anonymization_logs = [
            msg
            for msg in log_messages
            if "Associated conversation" in msg and "anonymous user" in msg
        ]
        assert len(anonymization_logs) > 0

        # Verify log contains both anonymous and truncated original user
        log_msg = anonymization_logs[0]
        assert "anon-logging-456" in log_msg
        assert "logging-conv-789" in log_msg
        assert "logging_..." in log_msg  # Truncated original user ID

    def test_conversation_model_uses_anonymous_field(self):
        """Test that UserConversation model uses anonymous_user_id field."""
        # Verify the model has the correct field
        conversation = UserConversation()
        assert hasattr(conversation, "anonymous_user_id")

        # Verify we can set the anonymous user ID
        conversation.anonymous_user_id = "test-anon-uuid"
        assert conversation.anonymous_user_id == "test-anon-uuid"

        # Verify the field is mapped correctly (this tests the database column)
        mapper = inspect(UserConversation)
        assert "anonymous_user_id" in mapper.columns

    @patch("app.endpoints.query.get_anonymous_user_id")
    @patch("app.endpoints.query.get_session")
    def test_persist_user_conversation_different_users_same_conversation_id(
        self, mock_get_session, mock_get_anonymous
    ):
        """Test that different users can't access each other's conversations."""

        # Simulate two different users with same conversation ID (edge case)
        def mock_anonymous_side_effect(user_id):
            if user_id == "user1@example.com":
                return "anon-user1-123"
            if user_id == "user2@example.com":
                return "anon-user2-456"
            return "anon-unknown"

        mock_get_anonymous.side_effect = mock_anonymous_side_effect

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        # User 1 creates conversation
        persist_user_conversation_details(
            user_id="user1@example.com",
            conversation_id="shared-conv-id",
            model="model1",
            provider_id="provider1",
        )

        # Verify first user's anonymous ID was used
        first_call = mock_session.query.return_value.filter_by.call_args_list[0]
        assert first_call[1]["anonymous_user_id"] == "anon-user1-123"

        # Reset mock for second call
        mock_session.reset_mock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        # User 2 tries to create conversation with same ID
        persist_user_conversation_details(
            user_id="user2@example.com",
            conversation_id="shared-conv-id",  # Same conversation ID
            model="model2",
            provider_id="provider2",
        )

        # Verify second user's anonymous ID was used (different from first)
        second_call = mock_session.query.return_value.filter_by.call_args_list[0]
        assert second_call[1]["anonymous_user_id"] == "anon-user2-456"
        assert second_call[1]["anonymous_user_id"] != "anon-user1-123"
