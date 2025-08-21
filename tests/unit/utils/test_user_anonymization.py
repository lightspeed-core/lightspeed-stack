"""Tests for user anonymization utilities."""

import hashlib
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from utils.user_anonymization import (
    get_anonymous_user_id,
    get_user_count,
    find_anonymous_user_id,
    _hash_user_id,
)
from models.database.user_mapping import UserMapping


class TestUserAnonymization:
    """Test user anonymization functionality."""

    def test_hash_user_id_consistency(self):
        """Test that user ID hashing is consistent."""
        user_id = "test@example.com"
        hash1 = _hash_user_id(user_id)
        hash2 = _hash_user_id(user_id)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
        assert hash1 != user_id  # Should be different from original

    def test_hash_user_id_different_for_different_users(self):
        """Test that different user IDs produce different hashes."""
        user1_hash = _hash_user_id("user1@example.com")
        user2_hash = _hash_user_id("user2@example.com")

        assert user1_hash != user2_hash

    @patch("utils.user_anonymization.get_session")
    @patch("utils.user_anonymization.get_suid")
    def test_get_anonymous_user_id_new_user(self, mock_get_suid, mock_get_session):
        """Test creating new anonymous ID for first-time user."""
        # Setup mocks
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_get_suid.return_value = "anon-123-456"

        user_id = "new_user@example.com"
        result = get_anonymous_user_id(user_id)

        # Verify result
        assert result == "anon-123-456"

        # Verify database interactions
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the UserMapping was created correctly
        added_mapping = mock_session.add.call_args[0][0]
        assert isinstance(added_mapping, UserMapping)
        assert added_mapping.anonymous_id == "anon-123-456"
        assert added_mapping.user_id_hash == _hash_user_id(user_id)

    @patch("utils.user_anonymization.get_session")
    def test_get_anonymous_user_id_existing_user(self, mock_get_session):
        """Test retrieving existing anonymous ID for returning user."""
        # Setup existing mapping
        existing_mapping = UserMapping()
        existing_mapping.anonymous_id = "existing-anon-789"
        existing_mapping.user_id_hash = _hash_user_id("existing@example.com")

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            existing_mapping
        )

        result = get_anonymous_user_id("existing@example.com")

        # Verify result
        assert result == "existing-anon-789"

        # Verify no new mapping was created
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_called()

    @patch("utils.user_anonymization.get_session")
    @patch("utils.user_anonymization.get_suid")
    def test_get_anonymous_user_id_race_condition(
        self, mock_get_suid, mock_get_session
    ):
        """Test handling race condition when creating user mapping."""
        # Setup mocks for race condition scenario
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # First query returns None (no existing mapping)
        # Add raises IntegrityError (race condition)
        # Second query returns existing mapping (created by other thread)
        existing_mapping = UserMapping()
        existing_mapping.anonymous_id = "race-condition-uuid"

        mock_session.query.return_value.filter_by.return_value.first.side_effect = [
            None,  # First check - no existing mapping
            existing_mapping,  # Second check after race condition
        ]
        mock_session.add.side_effect = IntegrityError("Duplicate key", None, None)
        mock_get_suid.return_value = "new-uuid"

        result = get_anonymous_user_id("race_user@example.com")

        # Should return the mapping created by the other thread
        assert result == "race-condition-uuid"
        mock_session.rollback.assert_called_once()

    @patch("utils.user_anonymization.get_session")
    @patch("utils.user_anonymization.get_suid")
    def test_get_anonymous_user_id_race_condition_failure(
        self, mock_get_suid, mock_get_session
    ):
        """Test handling race condition where retrieval also fails."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # First query returns None, add fails, second query also returns None
        mock_session.query.return_value.filter_by.return_value.first.side_effect = [
            None,
            None,
        ]
        mock_session.add.side_effect = IntegrityError("Duplicate key", None, None)
        mock_get_suid.return_value = "new-uuid"

        with pytest.raises(
            RuntimeError, match="Unable to create or retrieve anonymous user ID"
        ):
            get_anonymous_user_id("problematic_user@example.com")

    @patch("utils.user_anonymization.get_session")
    def test_get_user_count(self, mock_get_session):
        """Test getting total user count."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.count.return_value = 42

        result = get_user_count()

        assert result == 42
        mock_session.query.assert_called_once_with(UserMapping)

    @patch("utils.user_anonymization.get_session")
    def test_find_anonymous_user_id_existing(self, mock_get_session):
        """Test finding existing anonymous ID without creating new one."""
        existing_mapping = UserMapping()
        existing_mapping.anonymous_id = "found-uuid"

        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = (
            existing_mapping
        )

        result = find_anonymous_user_id("existing@example.com")

        assert result == "found-uuid"

    @patch("utils.user_anonymization.get_session")
    def test_find_anonymous_user_id_not_found(self, mock_get_session):
        """Test finding non-existing anonymous ID returns None."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        result = find_anonymous_user_id("nonexistent@example.com")

        assert result is None

    def test_salt_prevents_rainbow_attacks(self):
        """Test that salt makes rainbow table attacks impractical."""
        # Common passwords/emails that might be in rainbow tables
        common_ids = ["admin", "test@test.com", "user123", "john.doe@company.com"]

        for user_id in common_ids:
            hash_result = _hash_user_id(user_id)
            # Hash should not match simple SHA-256 of just the user ID
            simple_hash = hashlib.sha256(user_id.encode()).hexdigest()
            assert hash_result != simple_hash

    def test_anonymization_preserves_uniqueness(self):
        """Test that different users get different anonymous IDs."""
        users = [
            "user1@example.com",
            "user2@example.com",
            "admin@company.com",
            "test.user@domain.org",
        ]

        hashes = [_hash_user_id(user) for user in users]

        # All hashes should be unique
        assert len(set(hashes)) == len(hashes)


class TestUserMappingModel:
    """Test the UserMapping database model."""

    def test_user_mapping_attributes(self):
        """Test UserMapping model has correct attributes."""
        mapping = UserMapping()

        # Check that required attributes exist
        assert hasattr(mapping, "anonymous_id")
        assert hasattr(mapping, "user_id_hash")
        assert hasattr(mapping, "created_at")

        # Check table name
        assert UserMapping.__tablename__ == "user_mapping"

    def test_user_mapping_creation(self):
        """Test creating UserMapping instance."""
        mapping = UserMapping(
            anonymous_id="test-uuid-123", user_id_hash="hashed_user_id"
        )

        assert mapping.anonymous_id == "test-uuid-123"
        assert mapping.user_id_hash == "hashed_user_id"
