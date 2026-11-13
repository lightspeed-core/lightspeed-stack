"""Unit tests for startup schema migrations."""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.schema_migrations import run_startup_migrations
from models.database.base import Base
from utils.saved_prompts import list_saved_prompts_by_user

# The RHDH 2.1 schema of saved_prompt, before the position column existed.
_OLD_TABLE_SQL = """
CREATE TABLE saved_prompt (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR,
    name VARCHAR(255),
    content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""


@pytest.fixture(name="old_schema_engine")
def old_schema_engine_fixture() -> Generator[Engine, None, None]:
    """Provide an in-memory SQLite engine with the pre-position saved_prompt table.

    Yields:
        Engine: Engine whose saved_prompt table matches the RHDH 2.1 schema
        (no position column, name uniqueness enforced via unique index).

    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(text(_OLD_TABLE_SQL))
        connection.execute(
            text("CREATE INDEX ix_saved_prompt_user_id ON saved_prompt (user_id)")
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_saved_prompt_user_name "
                "ON saved_prompt (user_id, name)"
            )
        )
    yield engine
    engine.dispose()


@pytest.fixture(name="modern_schema_engine")
def modern_schema_engine_fixture() -> Generator[Engine, None, None]:
    """Provide an in-memory SQLite engine created by Base.metadata.create_all.

    Yields:
        Engine: Engine with the current model schema (position column present).

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


def _insert_old_row(
    engine: Engine,
    prompt_id: str,
    user_id: str,
    name: str,
    created_at: str,
) -> None:
    """Insert a row into a pre-position saved_prompt table.

    Parameters:
        engine: Engine owning the old-schema table.
        prompt_id: Primary key of the row.
        user_id: Owner of the row.
        name: Display name of the prompt.
        created_at: Explicit creation timestamp (ISO-like string).

    """
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO saved_prompt (id, user_id, name, content, "
                "created_at, updated_at) "
                "VALUES (:id, :user_id, :name, :content, :created_at, :created_at)"
            ),
            {
                "id": prompt_id,
                "user_id": user_id,
                "name": name,
                "content": f"content of {name}",
                "created_at": created_at,
            },
        )


def _positions_by_id(engine: Engine) -> dict[str, int]:
    """Map every saved_prompt row id to its current position value.

    Parameters:
        engine: Engine owning the saved_prompt table.

    Returns:
        Dict keyed by row id with the stored position values.

    """
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, position FROM saved_prompt")
        ).fetchall()
    return dict(rows)


def _has_position_column(engine: Engine) -> bool:
    """Check whether the saved_prompt table has a position column.

    Parameters:
        engine: Engine owning the saved_prompt table.

    Returns:
        True if the position column exists.

    """
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("saved_prompt")}
    return "position" in columns


def test_migration_adds_position_column_to_old_table(
    old_schema_engine: Engine,
) -> None:
    """Old-table migration adds position and leaves no NULL values."""
    _insert_old_row(old_schema_engine, "p1", "user-123", "First", "2026-01-01 10:00:00")
    _insert_old_row(
        old_schema_engine, "p2", "user-123", "Second", "2026-01-02 10:00:00"
    )

    run_startup_migrations(old_schema_engine)

    assert _has_position_column(old_schema_engine)
    positions = _positions_by_id(old_schema_engine)
    assert all(position is not None for position in positions.values())


def test_backfill_assigns_positions_newest_first_per_user(
    old_schema_engine: Engine,
) -> None:
    """Backfill gives each user 1..N ordered by created_at descending."""
    _insert_old_row(old_schema_engine, "oldest", "user-123", "A", "2026-01-01 10:00:00")
    _insert_old_row(old_schema_engine, "middle", "user-123", "B", "2026-01-02 10:00:00")
    _insert_old_row(old_schema_engine, "newest", "user-123", "C", "2026-01-03 10:00:00")
    _insert_old_row(
        old_schema_engine, "other-old", "user-456", "D", "2026-01-01 09:00:00"
    )
    _insert_old_row(
        old_schema_engine, "other-new", "user-456", "E", "2026-01-05 09:00:00"
    )

    run_startup_migrations(old_schema_engine)

    positions = _positions_by_id(old_schema_engine)
    assert positions["newest"] == 1
    assert positions["middle"] == 2
    assert positions["oldest"] == 3
    assert positions["other-new"] == 1
    assert positions["other-old"] == 2


def test_backfill_breaks_created_at_ties_by_id(
    old_schema_engine: Engine,
) -> None:
    """Rows with equal created_at are ordered by id ascending."""
    _insert_old_row(old_schema_engine, "id-z", "user-123", "A", "2026-01-01 10:00:00")
    _insert_old_row(old_schema_engine, "id-a", "user-123", "B", "2026-01-01 10:00:00")

    run_startup_migrations(old_schema_engine)

    positions = _positions_by_id(old_schema_engine)
    assert positions["id-a"] == 1
    assert positions["id-z"] == 2


def test_migration_is_idempotent(old_schema_engine: Engine) -> None:
    """A second migration run changes nothing and does not error."""
    _insert_old_row(old_schema_engine, "p1", "user-123", "A", "2026-01-01 10:00:00")
    _insert_old_row(old_schema_engine, "p2", "user-123", "B", "2026-01-02 10:00:00")

    run_startup_migrations(old_schema_engine)
    after_first = _positions_by_id(old_schema_engine)

    run_startup_migrations(old_schema_engine)

    assert _positions_by_id(old_schema_engine) == after_first


def test_noop_when_table_missing() -> None:
    """A database without the saved_prompt table is left untouched."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        run_startup_migrations(engine)
        assert "saved_prompt" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_noop_when_column_already_present(
    modern_schema_engine: Engine,
) -> None:
    """A table that already has position is left unchanged."""
    with modern_schema_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO saved_prompt (id, user_id, name, content, position) "
                "VALUES ('p1', 'user-123', 'A', 'content', 7)"
            )
        )

    run_startup_migrations(modern_schema_engine)

    assert _positions_by_id(modern_schema_engine) == {"p1": 7}


def test_migration_heals_null_positions_on_modern_table(
    modern_schema_engine: Engine,
) -> None:
    """Rows written without a position during a rolling update heal on boot.

    Old-code pods serving during a rolling update insert rows with no
    position (their ORM predates the column). Every boot re-runs the
    backfill so such rows get positions appended after the user's current
    maximum instead of breaking the list endpoint.
    """
    _seed_rows_with_null_positions(modern_schema_engine)

    run_startup_migrations(modern_schema_engine)

    # Existing positions are preserved; NULL rows are appended after the
    # user's maximum, newest first, deterministically.
    assert _positions_by_id(modern_schema_engine) == {
        "p1": 1,
        "p2": 2,
        "p4-null": 3,
        "p3-null": 4,
    }


def test_empty_old_table_gets_column(
    old_schema_engine: Engine,
) -> None:
    """An empty old table gets the column without any row changes."""
    run_startup_migrations(old_schema_engine)

    assert _has_position_column(old_schema_engine)
    assert not _positions_by_id(old_schema_engine)


def test_lazy_heal_matches_startup_backfill_ordering(
    modern_schema_engine: Engine,
    mocker: MockerFixture,
) -> None:
    """The lazy heal and the startup backfill assign identical positions.

    The stray-NULL heal rule exists twice — in SQL (startup backfill) and in
    Python (lazy heal on read) — so this test pins both implementations to
    the same outcome for identical input; drift between them would make a
    user's list order change across a reboot.
    """
    _seed_rows_with_null_positions(modern_schema_engine)
    backfill_engine = modern_schema_engine

    lazy_engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(lazy_engine)
    try:
        _seed_rows_with_null_positions(lazy_engine)
        session_factory = sessionmaker(
            autocommit=False, autoflush=False, bind=lazy_engine
        )
        mocker.patch(
            "utils.saved_prompts.get_session",
            side_effect=session_factory,
        )

        run_startup_migrations(backfill_engine)
        list_saved_prompts_by_user("user-123")

        assert _positions_by_id(backfill_engine) == _positions_by_id(lazy_engine)
    finally:
        lazy_engine.dispose()


def _seed_rows_with_null_positions(engine: Engine) -> None:
    """Seed a modern-schema table with positioned rows and NULL strays.

    Parameters:
        engine: Engine owning a modern saved_prompt table.

    """
    with engine.begin() as connection:
        for prompt_id, position, created_at in (
            ("p1", 1, "2026-01-01 10:00:00"),
            ("p2", 2, "2026-01-02 10:00:00"),
            ("p3-null", None, "2026-01-05 10:00:00"),
            ("p4-null", None, "2026-01-06 10:00:00"),
        ):
            connection.execute(
                text(
                    "INSERT INTO saved_prompt "
                    "(id, user_id, name, content, position, created_at, updated_at) "
                    "VALUES (:id, 'user-123', :name, 'c', :position, :ts, :ts)"
                ),
                {
                    "id": prompt_id,
                    "name": prompt_id,
                    "position": position,
                    "ts": created_at,
                },
            )
