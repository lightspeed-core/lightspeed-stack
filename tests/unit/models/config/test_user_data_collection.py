"""Unit tests for UserDataCollection model."""

from pathlib import Path

import pytest

from lightspeed_stack.models.config import UserDataCollection
from lightspeed_stack.utils.checks import InvalidConfigurationError


def test_user_data_collection_feedback_enabled() -> None:
    """Test the UserDataCollection constructor for feedback."""
    # correct configuration
    cfg = UserDataCollection(
        feedback_enabled=False, feedback_storage=None
    )  # pyright: ignore[reportCallIssue]
    assert cfg is not None
    assert cfg.feedback_enabled is False
    assert cfg.feedback_storage is None


def test_user_data_collection_feedback_disabled() -> None:
    """Test the UserDataCollection constructor for feedback.

    Verify the constructor raises a ValueError when feedback is enabled but no
    storage is provided.

    This test constructs UserDataCollection with feedback_enabled=True and
    feedback_storage=None and asserts that a ValueError is raised with the
    message "feedback_storage is required when feedback is enabled".

    Raises:
        ValueError: if feedback is enabled while feedback_storage is None.
    """
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="feedback_storage is required when feedback is enabled",
    ):
        UserDataCollection(
            feedback_enabled=True, feedback_storage=None
        )  # pyright: ignore[reportCallIssue]


def test_user_data_collection_transcripts_enabled() -> None:
    """Test the UserDataCollection constructor for transcripts."""
    # correct configuration
    cfg = UserDataCollection(
        transcripts_enabled=False, transcripts_storage=None
    )  # pyright: ignore[reportCallIssue]
    assert cfg is not None
    assert cfg.transcripts_enabled is False
    assert cfg.transcripts_storage is None


def test_user_data_collection_transcripts_disabled() -> None:
    """Test the UserDataCollection constructor for transcripts.

    Verify the UserDataCollection constructor raises when transcripts are
    enabled but no storage is provided.

    Asserts that constructing with transcripts_enabled=True and
    transcripts_storage=None raises a ValueError with the message
    "transcripts_storage is required when transcripts is enabled".
    """
    # incorrect configuration
    with pytest.raises(
        ValueError,
        match="transcripts_storage is required when transcripts is enabled",
    ):
        UserDataCollection(
            transcripts_enabled=True, transcripts_storage=None
        )  # pyright: ignore[reportCallIssue]


def test_user_data_collection_wrong_directory_path(tmp_path: Path) -> None:
    """Test the UserDataCollection constructor for non-writable directory paths.

    Creates a temporary directory with no write permission and verifies that
    UserDataCollection raises InvalidConfigurationError for both feedback and
    transcript storage paths.
    """
    non_writable = tmp_path / "no_write"
    non_writable.mkdir()
    non_writable.chmod(0o444)

    with pytest.raises(
        InvalidConfigurationError,
        match=f"Check directory to store feedback '{non_writable}' is not writable",
    ):
        _ = UserDataCollection(
            feedback_enabled=True, feedback_storage=str(non_writable)
        )  # pyright: ignore[reportCallIssue]

    with pytest.raises(
        InvalidConfigurationError,
        match=f"Check directory to store transcripts '{non_writable}' is not writable",
    ):
        _ = UserDataCollection(
            transcripts_enabled=True, transcripts_storage=str(non_writable)
        )  # pyright: ignore[reportCallIssue]
