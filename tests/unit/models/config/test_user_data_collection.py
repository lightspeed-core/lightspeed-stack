"""Unit tests for UserDataCollection model."""

import pytest

from models.config import UserDataCollection
from utils.checks import InvalidConfigurationError


def test_user_data_collection_feedback_enabled() -> None:
    """Test the UserDataCollection constructor for feedback."""
    # correct configuration
    cfg = UserDataCollection(feedback_enabled=False, feedback_storage=None)
    assert cfg is not None
    assert cfg.feedback_enabled is False
    assert cfg.feedback_storage is None


def test_user_data_collection_feedback_disabled() -> None:
    """Test the UserDataCollection constructor for feedback."""
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="feedback_storage is required when feedback is enabled",
    ):
        UserDataCollection(feedback_enabled=True, feedback_storage=None)


def test_user_data_collection_transcripts_enabled() -> None:
    """Test the UserDataCollection constructor for transcripts."""
    # correct configuration
    cfg = UserDataCollection(transcripts_enabled=False, transcripts_storage=None)
    assert cfg is not None


def test_user_data_collection_transcripts_disabled() -> None:
    """Test the UserDataCollection constructor for transcripts."""
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="transcripts_storage is required when transcripts is enabled",
    ):
        UserDataCollection(transcripts_enabled=True, transcripts_storage=None)


def test_user_data_collection_wrong_directory_path() -> None:
    """Test the UserDataCollection constructor for wrong directory path."""
    with pytest.raises(
        InvalidConfigurationError,
        match="Check directory to store feedback '/root' is not writable",
    ):
        _ = UserDataCollection(feedback_enabled=True, feedback_storage="/root")

    with pytest.raises(
        InvalidConfigurationError,
        match="Check directory to store transcripts '/root' is not writable",
    ):
        _ = UserDataCollection(transcripts_enabled=True, transcripts_storage="/root")
