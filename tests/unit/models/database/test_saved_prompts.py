"""Unit tests for SavedPrompt database model."""

from collections.abc import Generator

import pytest
from sqlalchemy import String, UniqueConstraint, create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.database.base import Base
from models.database.saved_prompts import SavedPrompt


@pytest.fixture(name="sqlite_engine")
def sqlite_engine_fixture() -> Generator[Engine, None, None]:
    """Provide an in-memory SQLite engine with all tables created.

    Yields:
        Engine: A SQLAlchemy Engine bound to an in-memory SQLite database with
        tables created from Base.metadata.
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


@pytest.fixture(name="db_session")
def db_session_fixture(sqlite_engine: Engine) -> Generator[Session, None, None]:
    """Provide a database session for tests.

    Parameters:
        sqlite_engine (Engine): In-memory SQLite engine fixture.

    Yields:
        Session: A SQLAlchemy Session bound to the test engine.
    """
    session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=sqlite_engine
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


class TestSavedPromptModelDefinition:
    """Test cases for SavedPrompt model schema definition."""

    def test_tablename(self) -> None:
        """Test SavedPrompt uses the expected table name."""
        assert SavedPrompt.__tablename__ == "saved_prompt"

    def test_expected_columns_exist(self) -> None:
        """Test SavedPrompt defines all expected columns."""
        column_names = {col.name for col in SavedPrompt.__table__.columns}
        expected_columns = {
            "id",
            "user_id",
            "name",
            "content",
            "created_at",
            "updated_at",
        }
        assert column_names == expected_columns

    def test_name_column_max_length(self) -> None:
        """Test name column has max length 255."""
        name_column = SavedPrompt.__table__.c.name
        assert isinstance(name_column.type, String)
        assert name_column.type.length == 255

    def test_user_id_column_is_indexed(self) -> None:
        """Test user_id column is indexed."""
        user_id_column = SavedPrompt.__table__.c.user_id
        assert user_id_column.index is True

    def test_unique_constraint_on_user_id_and_name(self) -> None:
        """Test unique constraint exists on (user_id, name)."""
        table_args = SavedPrompt.__table_args__
        assert len(table_args) == 1
        constraint = table_args[0]
        assert isinstance(constraint, UniqueConstraint)
        assert constraint.name == "uq_saved_prompt_user_name"
        column_names = {col.name for col in constraint.columns}
        assert column_names == {"user_id", "name"}


class TestSavedPromptDatabaseOperations:
    """Test cases for SavedPrompt database operations."""

    def test_table_created_by_metadata(self, sqlite_engine: Engine) -> None:
        """Test saved_prompt table is created via Base.metadata.create_all."""
        inspector = inspect(sqlite_engine)
        assert "saved_prompt" in inspector.get_table_names()

    def test_insert_and_read_saved_prompt(self, db_session: Session) -> None:
        """Test inserting and reading back a SavedPrompt row."""
        saved_prompt = SavedPrompt(
            id="prompt-id-1",
            user_id="user-123",
            name="My Prompt",
            content="Hello, world!",
        )
        db_session.add(saved_prompt)
        db_session.commit()

        result = db_session.get(SavedPrompt, "prompt-id-1")
        assert result is not None
        assert result.id == "prompt-id-1"
        assert result.user_id == "user-123"
        assert result.name == "My Prompt"
        assert result.content == "Hello, world!"
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_duplicate_user_id_and_name_raises_integrity_error(
        self, db_session: Session
    ) -> None:
        """Test inserting duplicate (user_id, name) raises IntegrityError."""
        first_prompt = SavedPrompt(
            id="prompt-id-1",
            user_id="user-123",
            name="My Prompt",
            content="First content",
        )
        second_prompt = SavedPrompt(
            id="prompt-id-2",
            user_id="user-123",
            name="My Prompt",
            content="Second content",
        )
        db_session.add(first_prompt)
        db_session.commit()

        db_session.add(second_prompt)
        with pytest.raises(IntegrityError):
            db_session.commit()
