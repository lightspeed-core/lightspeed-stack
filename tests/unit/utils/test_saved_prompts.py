"""Unit tests for saved prompt validation helpers and data access."""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.database.base import Base
from models.database.saved_prompts import SavedPrompt
from utils.saved_prompts import (
    SavedPromptConflictError,
    SavedPromptLimitExceededError,
    SavedPromptValidationError,
    create_saved_prompt,
    validate_saved_prompt_content,
    validate_saved_prompt_name,
    validate_saved_prompt_quota,
)


@pytest.fixture(name="sqlite_engine")
def sqlite_engine_fixture() -> Generator[Engine, None, None]:
    """Provide a function-scoped in-memory SQLite engine with tables created.

    Yields:
        Engine: SQLAlchemy engine bound to an in-memory SQLite database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="patch_saved_prompts_get_session")
def patch_saved_prompts_get_session_fixture(
    mocker: MockerFixture, sqlite_engine: Engine
) -> None:
    """Patch utils.saved_prompts.get_session to use the in-memory engine.

    Parameters:
        mocker: pytest-mock fixture.
        sqlite_engine: Function-scoped in-memory engine.
    """
    session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=sqlite_engine
    )

    def _get_session() -> Session:
        return session_factory()

    mocker.patch("utils.saved_prompts.get_session", side_effect=_get_session)


class TestValidateSavedPromptQuota:
    """Test cases for validate_saved_prompt_quota."""

    def test_allows_count_below_max(self) -> None:
        """Test create is allowed when current count is below the inclusive max."""
        validate_saved_prompt_quota(49, 50)

    def test_rejects_count_equal_to_max(self) -> None:
        """Test create is rejected when current count equals the inclusive max."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(
                r"Saved prompt limit exceeded: 50 existing prompts, " r"maximum is 50"
            ),
        ):
            validate_saved_prompt_quota(50, 50)

    def test_rejects_count_above_max(self) -> None:
        """Test create is rejected when current count is above the max."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(
                r"Saved prompt limit exceeded: 51 existing prompts, " r"maximum is 50"
            ),
        ):
            validate_saved_prompt_quota(51, 50)

    def test_rejects_when_max_is_zero(self) -> None:
        """Test max_prompts_per_user of 0 rejects even a zero current count."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(
                r"Saved prompt limit exceeded: 0 existing prompts, " r"maximum is 0"
            ),
        ):
            validate_saved_prompt_quota(0, 0)


class TestValidateSavedPromptName:
    """Test cases for validate_saved_prompt_name."""

    def test_valid_name_returns_stripped_value(self) -> None:
        """Test valid name is accepted and returned stripped."""
        assert (
            validate_saved_prompt_name("  my prompt  ", max_display_name_length=10)
            == "my prompt"
        )

    def test_empty_name_rejected(self) -> None:
        """Test empty name raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name must not be empty",
        ):
            validate_saved_prompt_name("", max_display_name_length=10)

    def test_spaces_only_name_rejected(self) -> None:
        """Test spaces-only name raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name must not be empty",
        ):
            validate_saved_prompt_name("   ", max_display_name_length=10)

    def test_mixed_whitespace_only_name_rejected(self) -> None:
        """Test name of only spaces/newlines/tabs is rejected."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name must not be empty",
        ):
            validate_saved_prompt_name("   \n\t  ", max_display_name_length=10)

    def test_name_at_exact_max_length_accepted(self) -> None:
        """Test name of exactly max_display_name_length is accepted."""
        assert (
            validate_saved_prompt_name("abcdefghij", max_display_name_length=10)
            == "abcdefghij"
        )

    def test_name_longer_than_max_rejected(self) -> None:
        """Test name exceeding max_display_name_length is rejected."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name length 11 exceeds maximum 10",
        ):
            validate_saved_prompt_name("abcdefghijk", max_display_name_length=10)

    def test_name_rejected_when_max_length_is_zero(self) -> None:
        """Test max_display_name_length of 0 rejects any non-empty name."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name length 1 exceeds maximum 0",
        ):
            validate_saved_prompt_name("a", max_display_name_length=0)

    def test_unicode_emoji_name_within_length_accepted(self) -> None:
        """Test unicode/emoji name within length is accepted."""
        assert (
            validate_saved_prompt_name("🔥 tip", max_display_name_length=10) == "🔥 tip"
        )


class TestValidateSavedPromptContent:
    """Test cases for validate_saved_prompt_content."""

    def test_valid_content_accepted(self) -> None:
        """Test non-empty content within the max length is accepted."""
        validate_saved_prompt_content(
            "do something useful",
            max_content_length=50,
        )

    def test_empty_content_rejected(self) -> None:
        """Test empty content raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content must not be empty",
        ):
            validate_saved_prompt_content("", max_content_length=50)

    def test_spaces_only_content_rejected(self) -> None:
        """Test spaces-only content raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content must not be empty",
        ):
            validate_saved_prompt_content("   ", max_content_length=50)

    def test_mixed_whitespace_only_content_rejected(self) -> None:
        """Test content of only spaces/newlines/tabs is rejected."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content must not be empty",
        ):
            validate_saved_prompt_content("   \n\t  ", max_content_length=50)

    def test_non_blank_content_with_whitespace_accepted(self) -> None:
        """Test content with leading/trailing whitespace is accepted when non-blank."""
        validate_saved_prompt_content(
            "  keep my spaces  ",
            max_content_length=50,
        )

    def test_content_at_exact_max_length_accepted(self) -> None:
        """Test content of exactly max_content_length is accepted."""
        validate_saved_prompt_content("123456789012", max_content_length=12)

    def test_content_longer_than_max_rejected(self) -> None:
        """Test content exceeding max_content_length is rejected on original length."""
        # Leading spaces count toward length; strip would be under max but original is not.
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content length 14 exceeds maximum 12",
        ):
            validate_saved_prompt_content(
                "  1234567890  ",
                max_content_length=12,
            )

    def test_content_rejected_when_max_length_is_zero(self) -> None:
        """Test max_content_length of 0 rejects any non-empty content."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content length 1 exceeds maximum 0",
        ):
            validate_saved_prompt_content("a", max_content_length=0)


class TestCreateSavedPrompt:
    """Test cases for create_saved_prompt."""

    def test_create_persists_and_returns_entity(
        self, patch_saved_prompts_get_session: None, sqlite_engine: Engine
    ) -> None:
        """Test create returns a persisted SavedPrompt with id and fields."""
        created = create_saved_prompt(
            user_id="user-1",
            name="My Prompt",
            content="Hello",
            max_prompts_per_user=50,
        )

        assert created.id
        assert created.user_id == "user-1"
        assert created.name == "My Prompt"
        assert created.content == "Hello"

        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=sqlite_engine
        )
        with session_factory() as session:
            stored = session.get(SavedPrompt, created.id)
            assert stored is not None
            assert stored.name == "My Prompt"
            assert stored.content == "Hello"

    def test_create_return_value_has_usable_timestamps_after_session_close(
        self, patch_saved_prompts_get_session: None
    ) -> None:
        """Test timestamps are readable on the returned object after DAL returns."""
        created = create_saved_prompt(
            user_id="user-1",
            name="Timed",
            content="Body",
            max_prompts_per_user=50,
        )

        assert created.created_at is not None
        assert created.updated_at is not None

    def test_create_at_limit_raises(
        self, patch_saved_prompts_get_session: None
    ) -> None:
        """Test create raises when the user already has max_prompts_per_user prompts."""
        create_saved_prompt("user-1", "one", "c1", max_prompts_per_user=1)

        with pytest.raises(SavedPromptLimitExceededError):
            create_saved_prompt("user-1", "two", "c2", max_prompts_per_user=1)

    def test_create_duplicate_name_raises_conflict(
        self, patch_saved_prompts_get_session: None
    ) -> None:
        """Test duplicate (user_id, name) raises SavedPromptConflictError."""
        create_saved_prompt("user-1", "same", "first", max_prompts_per_user=50)

        with pytest.raises(SavedPromptConflictError) as exc_info:
            create_saved_prompt("user-1", "same", "second", max_prompts_per_user=50)

        assert str(exc_info.value) == "Saved prompt name already exists"

    def test_create_allows_same_name_for_different_users(
        self, patch_saved_prompts_get_session: None
    ) -> None:
        """Test the same name may exist for different users."""
        first = create_saved_prompt("user-a", "shared", "a", max_prompts_per_user=50)
        second = create_saved_prompt("user-b", "shared", "b", max_prompts_per_user=50)
        assert first.id != second.id
