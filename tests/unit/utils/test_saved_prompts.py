"""Unit tests for saved prompt validation helpers and data access."""

import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.database.base import Base
from models.database.saved_prompts import SavedPrompt
from utils import saved_prompts as saved_prompts_utils
from utils.saved_prompts import (
    SavedPromptAccessDeniedError,
    SavedPromptConflictError,
    SavedPromptLimitExceededError,
    SavedPromptNotFoundError,
    SavedPromptValidationError,
    create_saved_prompt,
    delete_saved_prompt_by_id_and_user,
    list_saved_prompts_by_user,
    update_saved_prompt_by_id_and_user,
    validate_saved_prompt_content,
    validate_saved_prompt_name,
    validate_saved_prompt_quota,
)
from utils.suid import get_suid


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
        """Create a Session bound to the in-memory test engine.

        Returns:
            Session: A new SQLAlchemy session for patched DAL calls.

        """
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
            match=(r"Saved prompt limit exceeded: 50 existing prompts, maximum is 50"),
        ):
            validate_saved_prompt_quota(50, 50)

    def test_rejects_count_above_max(self) -> None:
        """Test create is rejected when current count is above the max."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(r"Saved prompt limit exceeded: 51 existing prompts, maximum is 50"),
        ):
            validate_saved_prompt_quota(51, 50)

    def test_rejects_when_max_is_zero(self) -> None:
        """Test max_prompts_per_user of 0 rejects even a zero current count."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(r"Saved prompt limit exceeded: 0 existing prompts, maximum is 0"),
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


@pytest.mark.usefixtures("patch_saved_prompts_get_session")
class TestCreateSavedPrompt:
    """Test cases for create_saved_prompt."""

    def test_create_persists_and_returns_entity(self, sqlite_engine: Engine) -> None:
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
        self,
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

    def test_create_at_limit_raises(self) -> None:
        """Test create raises when the user already has max_prompts_per_user prompts."""
        create_saved_prompt("user-1", "one", "c1", max_prompts_per_user=1)

        with pytest.raises(SavedPromptLimitExceededError):
            create_saved_prompt("user-1", "two", "c2", max_prompts_per_user=1)

    def test_create_duplicate_name_raises_conflict(self) -> None:
        """Test duplicate (user_id, name) raises SavedPromptConflictError."""
        create_saved_prompt("user-1", "same", "first", max_prompts_per_user=50)

        with pytest.raises(SavedPromptConflictError) as exc_info:
            create_saved_prompt("user-1", "same", "second", max_prompts_per_user=50)

        assert str(exc_info.value) == "Saved prompt name already exists"

    def test_create_allows_same_name_for_different_users(self) -> None:
        """Test the same name may exist for different users."""
        first = create_saved_prompt("user-a", "shared", "a", max_prompts_per_user=50)
        second = create_saved_prompt("user-b", "shared", "b", max_prompts_per_user=50)
        assert first.id != second.id


@pytest.mark.usefixtures("patch_saved_prompts_get_session")
class TestCreateSavedPromptPosition:
    """Test cases for per-user position assignment on create."""

    def test_create_assigns_position_1_for_first_prompt(self) -> None:
        """Test the first prompt created for a user gets position 1."""
        created = create_saved_prompt("user-1", "first", "c", max_prompts_per_user=50)

        assert created.position == 1

    def test_create_assigns_incrementing_positions(self) -> None:
        """Test subsequent creates append with max-plus-one positions."""
        first = create_saved_prompt("user-1", "one", "c1", max_prompts_per_user=50)
        second = create_saved_prompt("user-1", "two", "c2", max_prompts_per_user=50)
        third = create_saved_prompt("user-1", "three", "c3", max_prompts_per_user=50)

        assert (first.position, second.position, third.position) == (1, 2, 3)

    def test_create_assigns_max_plus_one_after_delete(self) -> None:
        """Test positions are not gap-filled after a deletion."""
        first = create_saved_prompt("user-1", "one", "c1", max_prompts_per_user=50)
        create_saved_prompt("user-1", "two", "c2", max_prompts_per_user=50)

        delete_saved_prompt_by_id_and_user(first.id, "user-1")
        third = create_saved_prompt("user-1", "three", "c3", max_prompts_per_user=50)

        assert third.position == 3

    def test_create_positions_independent_per_user(self) -> None:
        """Test each user's position sequence is independent."""
        user_a = create_saved_prompt("user-a", "a", "c", max_prompts_per_user=50)
        user_b = create_saved_prompt("user-b", "b", "c", max_prompts_per_user=50)

        assert user_a.position == 1
        assert user_b.position == 1

    def test_create_retries_once_on_position_conflict(
        self, sqlite_engine: Engine, mocker: MockerFixture
    ) -> None:
        """Test a position IntegrityError is retried once with a fresh max."""
        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=sqlite_engine
        )
        with session_factory() as session:
            session.add(
                SavedPrompt(
                    id="seed",
                    user_id="user-1",
                    name="seed",
                    content="c",
                    position=1,
                )
            )
            session.commit()

        real_next_position = (
            saved_prompts_utils._next_position  # pylint: disable=protected-access
        )
        calls: list[int] = []

        def fake_next_position(session: Session, user_id: str) -> int:
            """Simulate a concurrent create taking the computed position.

            Parameters:
                session: DAL session.
                user_id: Owner of the prompt.

            Returns:
                A colliding position on the first call, the real value after.

            """
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                return 1  # collides with the seeded row
            return real_next_position(session, user_id)

        mocker.patch(
            "utils.saved_prompts._next_position", side_effect=fake_next_position
        )

        created = create_saved_prompt("user-1", "new", "c", max_prompts_per_user=50)

        assert created.position == 2
        assert len(calls) == 2


@pytest.mark.usefixtures("patch_saved_prompts_get_session")
class TestListSavedPromptsByUser:
    """Test cases for list_saved_prompts_by_user."""

    def test_list_empty_returns_empty_list(self) -> None:
        """Test listing for a user with no prompts returns []."""
        assert list_saved_prompts_by_user("nobody") == []

    def test_list_returns_only_that_users_prompts_ordered_by_position(
        self, sqlite_engine: Engine
    ) -> None:
        """Test list is user-scoped and ordered by position ascending."""
        first = create_saved_prompt("user-1", "first", "c1", max_prompts_per_user=50)
        second = create_saved_prompt("user-1", "second", "c2", max_prompts_per_user=50)
        third = create_saved_prompt("user-1", "third", "c3", max_prompts_per_user=50)
        create_saved_prompt("user-11", "other", "c4", max_prompts_per_user=50)

        # Concurrent inserts can share the same created_at; force a clear
        # tiebreaker order for the duplicate-position test below.
        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=sqlite_engine
        )
        with session_factory() as session:
            first_row = session.get(SavedPrompt, first.id)
            second_row = session.get(SavedPrompt, second.id)
            third_row = session.get(SavedPrompt, third.id)
            assert first_row is not None
            assert second_row is not None
            assert third_row is not None
            first_row.created_at = third_row.created_at - timedelta(seconds=2)
            second_row.created_at = third_row.created_at - timedelta(seconds=1)
            session.commit()

        results = list_saved_prompts_by_user("user-1")

        assert [p.id for p in results] == [first.id, second.id, third.id]
        assert all(p.user_id == "user-1" for p in results)

    def test_list_order_deterministic_with_duplicate_positions(
        self, mocker: MockerFixture
    ) -> None:
        """Test duplicate positions fall back to created_at desc, then id.

        Upgraded deployments may lack the (user_id, position) unique
        constraint, so the listing must stay deterministic when duplicates
        exist. The table here mirrors a migrated one: position column
        present, no position unique constraint.
        """
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE saved_prompt ("
                        "id VARCHAR PRIMARY KEY, "
                        "user_id VARCHAR, "
                        "name VARCHAR(255), "
                        "content TEXT, "
                        "position INTEGER, "
                        "created_at DATETIME, "
                        "updated_at DATETIME)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE UNIQUE INDEX uq_saved_prompt_user_name "
                        "ON saved_prompt (user_id, name)"
                    )
                )
                base = datetime.now(UTC)
                for prompt_id, offset in (("older-id", 0), ("newer-id", 1)):
                    connection.execute(
                        text(
                            "INSERT INTO saved_prompt "
                            "(id, user_id, name, content, position, "
                            "created_at, updated_at) "
                            "VALUES (:id, 'user-1', :name, 'c', 2, :ts, :ts)"
                        ),
                        {
                            "id": prompt_id,
                            "name": prompt_id,
                            "ts": base + timedelta(seconds=offset),
                        },
                    )
            session_factory = sessionmaker(
                autocommit=False, autoflush=False, bind=engine
            )
            mocker.patch(
                "utils.saved_prompts.get_session",
                side_effect=session_factory,
            )

            first_pass = list_saved_prompts_by_user("user-1")
            second_pass = list_saved_prompts_by_user("user-1")

            assert [p.id for p in first_pass] == ["newer-id", "older-id"]
            assert [p.id for p in second_pass] == [p.id for p in first_pass]
        finally:
            engine.dispose()

    def test_list_excludes_near_collision_user_ids(self) -> None:
        """Test list does not match nearby user_id strings (prefix/substring)."""
        owned = create_saved_prompt(
            "user-1", "deploy", "owned-body", max_prompts_per_user=50
        )
        create_saved_prompt(
            "user-11", "deploy-1", "other-11-body", max_prompts_per_user=50
        )
        create_saved_prompt(
            "user-1a", "deploy", "other-1a-body", max_prompts_per_user=50
        )

        results = list_saved_prompts_by_user("user-1")

        assert len(results) == 1
        assert results[0].id == owned.id
        assert results[0].user_id == "user-1"
        assert results[0].content == "owned-body"

    def test_list_caps_at_configured_upper_bound(
        self, mocker: MockerFixture, sqlite_engine: Engine
    ) -> None:
        """Test list applies SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND as a hard cap."""
        mocker.patch(
            "utils.saved_prompts.constants.SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND",
            2,
        )
        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=sqlite_engine
        )
        with session_factory() as session:
            for index in range(3):
                session.add(
                    SavedPrompt(
                        id=get_suid(),
                        user_id="user-1",
                        name=f"prompt-{index}",
                        content=f"content-{index}",
                    )
                )
            session.commit()

        results = list_saved_prompts_by_user("user-1")
        assert len(results) == 2

    def test_list_heals_null_positions(self, sqlite_engine: Engine) -> None:
        """Test rows written without a position get one when listed.

        During a rolling update, old-code pods insert rows with a NULL
        position after the new pod has already migrated. Listing must heal
        those rows (append after the user's maximum) rather than fail
        response validation.
        """
        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=sqlite_engine
        )
        base = datetime.now(UTC)
        with session_factory() as session:
            session.add(
                SavedPrompt(
                    id="p1",
                    user_id="user-1",
                    name="p1",
                    content="c",
                    position=1,
                    created_at=base,
                    updated_at=base,
                )
            )
            session.add(
                SavedPrompt(
                    id="p2",
                    user_id="user-1",
                    name="p2",
                    content="c",
                    position=2,
                    created_at=base,
                    updated_at=base,
                )
            )
            session.add(
                SavedPrompt(
                    id="p3-null",
                    user_id="user-1",
                    name="p3-null",
                    content="c",
                    created_at=base + timedelta(seconds=1),
                    updated_at=base + timedelta(seconds=1),
                )
            )
            session.commit()

        results = list_saved_prompts_by_user("user-1")

        assert [row.id for row in results] == ["p1", "p2", "p3-null"]
        assert [row.position for row in results] == [1, 2, 3]


@pytest.mark.usefixtures("patch_saved_prompts_get_session")
class TestDeleteSavedPromptByIdAndUser:
    """Test cases for delete_saved_prompt_by_id_and_user."""

    def test_delete_owned_prompt(self, sqlite_engine: Engine) -> None:
        """Test deleting an owned prompt removes the row."""
        created = create_saved_prompt(
            "user-1", "to-delete", "body", max_prompts_per_user=50
        )

        delete_saved_prompt_by_id_and_user(created.id, "user-1")

        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=sqlite_engine
        )
        with session_factory() as session:
            assert session.get(SavedPrompt, created.id) is None

    def test_delete_missing_raises_not_found(self) -> None:
        """Test deleting an unknown id raises SavedPromptNotFoundError."""
        with pytest.raises(SavedPromptNotFoundError) as exc_info:
            delete_saved_prompt_by_id_and_user("missing-id", "user-1")

        assert str(exc_info.value) == "Saved prompt not found"

    def test_delete_other_users_prompt_raises_access_denied(
        self, sqlite_engine: Engine
    ) -> None:
        """Test delete by non-owner raises access denied and leaves the row."""
        created = create_saved_prompt(
            "owner", "private", "body", max_prompts_per_user=50
        )

        with pytest.raises(SavedPromptAccessDeniedError) as exc_info:
            delete_saved_prompt_by_id_and_user(created.id, "intruder")

        assert str(exc_info.value) == "Saved prompt access denied"

        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=sqlite_engine
        )
        with session_factory() as session:
            assert session.get(SavedPrompt, created.id) is not None


@pytest.mark.usefixtures("patch_saved_prompts_get_session")
class TestUpdateSavedPromptByIdAndUser:
    """Test cases for update_saved_prompt_by_id_and_user."""

    def test_update_changes_name_and_content_in_place(self) -> None:
        """Test update edits fields without delete + recreate."""
        created = create_saved_prompt("user-1", "old name", "old body", 50)

        updated = update_saved_prompt_by_id_and_user(
            created.id, "user-1", "new name", "new body", 1
        )

        assert updated.id == created.id
        assert updated.name == "new name"
        assert updated.content == "new body"
        assert updated.position == 1
        assert updated.created_at == created.created_at

    def test_update_advances_updated_at(self) -> None:
        """Test a field update advances the updated_at timestamp."""
        created = create_saved_prompt("user-1", "name", "body", 50)
        time.sleep(1.1)  # SQLite CURRENT_TIMESTAMP has second resolution

        updated = update_saved_prompt_by_id_and_user(
            created.id, "user-1", "name", "new body", 1
        )

        assert updated.updated_at > created.updated_at

    def test_reorder_to_front_renumbers_siblings(self) -> None:
        """Test moving position 3 to 1 shifts siblings to 2, 3, 4."""
        prompts = [
            create_saved_prompt("user-1", f"p{i}", f"c{i}", 50) for i in range(4)
        ]
        target = prompts[2]  # position 3

        updated = update_saved_prompt_by_id_and_user(
            target.id, "user-1", target.name, target.content, 1
        )

        assert updated.position == 1
        results = list_saved_prompts_by_user("user-1")
        assert [p.id for p in results] == [
            prompts[2].id,
            prompts[0].id,
            prompts[1].id,
            prompts[3].id,
        ]
        assert [p.position for p in results] == [1, 2, 3, 4]

    def test_update_succeeds_when_positions_have_gaps(self) -> None:
        """Test PUT keeps working after interior deletes leave position gaps.

        Deletes never renumber, so a user's positions are routinely sparse
        (e.g. {1, 4} after deleting the middle two of four). The renumber
        must not collide with still-present old positions.
        """
        prompts = [
            create_saved_prompt("user-1", f"p{i}", f"c{i}", 50) for i in range(4)
        ]
        # Delete the middle two, leaving positions {1, 4}.
        delete_saved_prompt_by_id_and_user(prompts[1].id, "user-1")
        delete_saved_prompt_by_id_and_user(prompts[2].id, "user-1")
        target = prompts[3]  # position 4

        updated = update_saved_prompt_by_id_and_user(
            target.id, "user-1", target.name, target.content, 4
        )

        assert updated.position == 2
        results = list_saved_prompts_by_user("user-1")
        assert [p.id for p in results] == [prompts[0].id, prompts[3].id]
        assert [p.position for p in results] == [1, 2]

    def test_update_succeeds_with_wide_gap_from_multiple_deletes(
        self,
    ) -> None:
        """Test PUT keeps working when deletes leave a wide position gap.

        Six prompts with the middle three deleted leave positions {1, 5, 6};
        a naive offset based on row count collides with the row still
        holding position 5.
        """
        prompts = [
            create_saved_prompt("user-1", f"p{i}", f"c{i}", 50) for i in range(6)
        ]
        for deleted in prompts[1:4]:  # positions 2, 3, 4
            delete_saved_prompt_by_id_and_user(deleted.id, "user-1")
        target = prompts[5]  # position 6

        updated = update_saved_prompt_by_id_and_user(
            target.id, "user-1", target.name, target.content, 6
        )

        assert updated.position == 3
        results = list_saved_prompts_by_user("user-1")
        assert [p.id for p in results] == [
            prompts[0].id,
            prompts[4].id,
            prompts[5].id,
        ]
        assert [p.position for p in results] == [1, 2, 3]

    def test_position_beyond_count_clamps_to_end(self) -> None:
        """Test a position above the prompt count moves the prompt to the end."""
        prompts = [
            create_saved_prompt("user-1", f"p{i}", f"c{i}", 50) for i in range(3)
        ]
        target = prompts[0]  # position 1

        updated = update_saved_prompt_by_id_and_user(
            target.id, "user-1", target.name, target.content, 99
        )

        assert updated.position == 3
        results = list_saved_prompts_by_user("user-1")
        assert [p.id for p in results] == [
            prompts[1].id,
            prompts[2].id,
            prompts[0].id,
        ]

    def test_update_missing_raises_not_found(self) -> None:
        """Test updating a nonexistent id raises not found."""
        with pytest.raises(SavedPromptNotFoundError):
            update_saved_prompt_by_id_and_user(
                "nonexistent", "user-1", "name", "body", 1
            )

    def test_update_other_users_prompt_raises_access_denied(self) -> None:
        """Test update by non-owner raises access denied and leaves the row."""
        created = create_saved_prompt("owner", "private", "body", 50)

        with pytest.raises(SavedPromptAccessDeniedError):
            update_saved_prompt_by_id_and_user(
                created.id, "intruder", "new name", "new body", 1
            )

        results = list_saved_prompts_by_user("owner")
        assert results[0].name == "private"

    def test_rename_to_existing_name_raises_conflict(self) -> None:
        """Test renaming to a name the user already has raises conflict."""
        first = create_saved_prompt("user-1", "first", "c1", 50)
        second = create_saved_prompt("user-1", "second", "c2", 50)

        with pytest.raises(SavedPromptConflictError):
            update_saved_prompt_by_id_and_user(first.id, "user-1", "second", "c1", 1)

        # The failed update leaves both rows unchanged.
        results = list_saved_prompts_by_user("user-1")
        assert [p.name for p in results] == ["first", "second"]
        assert [p.position for p in results] == [1, 2]
        assert second.name == "second"

    def test_update_leaves_other_users_positions_untouched(self) -> None:
        """Test a reorder does not renumber another user's prompts."""
        mine = create_saved_prompt("user-1", "mine", "c", 50)
        theirs = [create_saved_prompt("user-2", f"t{i}", f"c{i}", 50) for i in range(3)]

        update_saved_prompt_by_id_and_user(
            mine.id, "user-1", mine.name, mine.content, 1
        )

        their_results = list_saved_prompts_by_user("user-2")
        assert [p.id for p in their_results] == [t.id for t in theirs]
        assert [p.position for p in their_results] == [1, 2, 3]
