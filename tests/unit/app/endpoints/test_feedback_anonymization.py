"""Tests for feedback endpoint anonymization functionality."""

import os
from unittest.mock import patch, MagicMock

import pytest

from app.endpoints.feedback import store_feedback


# Set up test environment variable before importing the module
@pytest.fixture(autouse=True)
def setup_test_pepper():
    """Set up test pepper environment variable for all tests."""
    test_pepper = "test-pepper-for-feedback-tests"
    with patch.dict(os.environ, {"USER_ANON_PEPPER": test_pepper}):
        yield


class TestFeedbackAnonymization:
    """Test feedback storage with user anonymization."""

    @patch("app.endpoints.feedback.get_anonymous_user_id")
    @patch("app.endpoints.feedback.get_suid")
    @patch("app.endpoints.feedback.json")
    @patch("app.endpoints.feedback.Path")
    def test_store_feedback_anonymizes_user_id(
        self, mock_path, mock_json, mock_get_suid, mock_get_anonymous
    ):
        """Test that store_feedback uses anonymous user ID."""
        # Setup mocks
        mock_get_anonymous.return_value = "anon-feedback-123"
        mock_get_suid.return_value = "feedback-uuid"
        mock_path.return_value = MagicMock()

        # Mock configuration
        with (
            patch("app.endpoints.feedback.configuration") as mock_config,
            patch("builtins.open"),
        ):
            mock_config.user_data_collection_configuration.feedback_storage = (
                "/tmp/feedback"
            )

            # Call store_feedback
            store_feedback(
                user_id="original_user@example.com",
                feedback={
                    "feedback": "This is test feedback",
                    "sentiment": 1,
                    "categories": ["helpful"],
                },
            )

            # Verify anonymous user ID was used
            mock_get_anonymous.assert_called_once_with("original_user@example.com")

            # Verify stored data uses anonymous ID
            stored_data = mock_json.dump.call_args[0][0]
            assert stored_data["anonymous_user_id"] == "anon-feedback-123"
            assert "user_id" not in stored_data
            assert stored_data["feedback"] == "This is test feedback"
            assert stored_data["sentiment"] == 1
            assert stored_data["categories"] == ["helpful"]

    @patch("app.endpoints.feedback.get_anonymous_user_id")
    def test_store_feedback_different_users_get_different_anonymous_ids(
        self, mock_get_anonymous
    ):
        """Test that different users get different anonymous IDs for feedback."""

        def mock_anonymous_side_effect(user_id):
            if user_id == "user1@example.com":
                return "anon-feedback-user1"
            if user_id == "user2@example.com":
                return "anon-feedback-user2"
            return "anon-unknown"

        mock_get_anonymous.side_effect = mock_anonymous_side_effect

        with (
            patch("app.endpoints.feedback.json") as mock_json,
            patch("app.endpoints.feedback.Path") as mock_path,
            patch("builtins.open"),
            patch("app.endpoints.feedback.get_suid", return_value="uuid"),
            patch("app.endpoints.feedback.configuration") as mock_config,
        ):

            mock_config.user_data_collection_configuration.feedback_storage = (
                "/tmp/feedback"
            )
            mock_path.return_value = MagicMock()

            # Store feedback for user 1
            store_feedback("user1@example.com", {"feedback": "Test 1"})
            first_call_data = mock_json.dump.call_args[0][0]

            # Reset mock for second call
            mock_json.reset_mock()

            # Store feedback for user 2
            store_feedback("user2@example.com", {"feedback": "Test 2"})
            second_call_data = mock_json.dump.call_args[0][0]

            # Verify different anonymous IDs were used
            assert first_call_data["anonymous_user_id"] == "anon-feedback-user1"
            assert second_call_data["anonymous_user_id"] == "anon-feedback-user2"
            assert (
                first_call_data["anonymous_user_id"]
                != second_call_data["anonymous_user_id"]
            )

    @patch("app.endpoints.feedback.get_anonymous_user_id")
    @patch("app.endpoints.feedback.logger")
    def test_feedback_logging_uses_anonymous_id(self, mock_logger, mock_get_anonymous):
        """Test that feedback logging uses anonymous user ID."""
        mock_get_anonymous.return_value = "anon-feedback-logging"

        with (
            patch("app.endpoints.feedback.json"),
            patch("app.endpoints.feedback.Path") as mock_path,
            patch("builtins.open"),
            patch("app.endpoints.feedback.get_suid", return_value="uuid"),
            patch("app.endpoints.feedback.configuration") as mock_config,
        ):

            mock_config.user_data_collection_configuration.feedback_storage = (
                "/tmp/feedback"
            )
            mock_path.return_value = MagicMock()

            # Store feedback
            store_feedback("user@example.com", {"feedback": "Test feedback"})

            # Verify logging uses anonymous ID
            mock_logger.debug.assert_called_once_with(
                "Storing feedback for anonymous user %s", "anon-feedback-logging"
            )
