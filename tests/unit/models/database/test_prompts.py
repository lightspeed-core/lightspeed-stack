"""Unit tests for Prompt and PromptVersion database models."""

from collections.abc import Generator

import pytest
from sqlalchemy import String, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.database.base import Base
from models.database.prompts import Prompt, PromptVersion
from prompts.exceptions import PromptValidationError


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
        sqlite_engine: In-memory SQLite engine fixture.

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


@pytest.fixture(name="sample_prompt")
def sample_prompt_fixture(db_session: Session) -> Prompt:
    """Insert and return a sample Prompt row.

    Parameters:
        db_session: Active database session.

    Returns:
        Prompt: The persisted prompt instance.

    """
    prompt = Prompt(id="pmpt_001", name="greeting", default_version=1)
    db_session.add(prompt)
    db_session.commit()
    return prompt


class TestPromptModelDefinition:
    """Test cases for Prompt model schema definition."""

    def test_tablename(self) -> None:
        """Test Prompt uses the expected table name."""
        assert Prompt.__tablename__ == "prompt"

    def test_expected_columns_exist(self) -> None:
        """Test Prompt defines all expected columns."""
        column_names = {col.name for col in Prompt.__table__.columns}
        expected = {"id", "name", "default_version", "created_at", "updated_at"}
        assert column_names == expected

    def test_name_column_max_length(self) -> None:
        """Test name column has max length 255."""
        name_column = Prompt.__table__.c.name
        assert isinstance(name_column.type, String)
        assert name_column.type.length == 255

    def test_id_is_primary_key(self) -> None:
        """Test id column is the primary key."""
        assert Prompt.__table__.c.id.primary_key


class TestPromptVersionModelDefinition:
    """Test cases for PromptVersion model schema definition."""

    def test_tablename(self) -> None:
        """Test PromptVersion uses the expected table name."""
        assert PromptVersion.__tablename__ == "prompt_version"

    def test_expected_columns_exist(self) -> None:
        """Test PromptVersion defines all expected columns."""
        column_names = {col.name for col in PromptVersion.__table__.columns}
        expected = {"prompt_id", "version", "template", "variables", "created_at"}
        assert column_names == expected

    def test_composite_primary_key(self) -> None:
        """Test primary key is (prompt_id, version)."""
        pk_columns = {col.name for col in PromptVersion.__table__.primary_key.columns}
        assert pk_columns == {"prompt_id", "version"}

    def test_prompt_id_has_foreign_key(self) -> None:
        """Test prompt_id references prompt.id."""
        fk_targets = {
            fk.target_fullname
            for fk in PromptVersion.__table__.c.prompt_id.foreign_keys
        }
        assert "prompt.id" in fk_targets


class TestPromptDatabaseOperations:
    """Test cases for Prompt database operations."""

    def test_tables_created_by_metadata(self, sqlite_engine: Engine) -> None:
        """Test prompt and prompt_version tables are created via Base.metadata."""
        inspector = inspect(sqlite_engine)
        table_names = inspector.get_table_names()
        assert "prompt" in table_names
        assert "prompt_version" in table_names

    def test_insert_and_read_prompt(self, db_session: Session) -> None:
        """Test inserting and reading back a Prompt row."""
        prompt = Prompt(id="pmpt_001", name="greeting", default_version=1)
        db_session.add(prompt)
        db_session.commit()

        result = db_session.get(Prompt, "pmpt_001")
        assert result is not None
        assert result.id == "pmpt_001"
        assert result.name == "greeting"
        assert result.default_version == 1
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_duplicate_prompt_id_raises_integrity_error(
        self, db_session: Session
    ) -> None:
        """Test inserting duplicate prompt id raises IntegrityError."""
        db_session.add(Prompt(id="pmpt_001", name="first", default_version=1))
        db_session.commit()

        db_session.add(Prompt(id="pmpt_001", name="second", default_version=1))
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestPromptVersionDatabaseOperations:
    """Test cases for PromptVersion database operations."""

    def test_insert_and_read_version(
        self, db_session: Session, sample_prompt: Prompt
    ) -> None:
        """Test inserting and reading back a PromptVersion row."""
        version = PromptVersion(
            prompt_id=sample_prompt.id,
            version=1,
            template="Hello {{name}}",
            variables=["name"],
        )
        db_session.add(version)
        db_session.commit()

        result = db_session.get(PromptVersion, (sample_prompt.id, 1))
        assert result is not None
        assert result.prompt_id == sample_prompt.id
        assert result.version == 1
        assert result.template == "Hello {{name}}"
        assert result.variables == ["name"]
        assert result.created_at is not None

    def test_multiple_versions_for_same_prompt(
        self, db_session: Session, sample_prompt: Prompt
    ) -> None:
        """Test that a prompt can have multiple versions."""
        v1 = PromptVersion(
            prompt_id=sample_prompt.id,
            version=1,
            template="Hello {{name}}",
            variables=["name"],
        )
        v2 = PromptVersion(
            prompt_id=sample_prompt.id,
            version=2,
            template="Hi {{name}}, welcome to {{place}}",
            variables=["name", "place"],
        )
        db_session.add_all([v1, v2])
        db_session.commit()

        results = (
            db_session.query(PromptVersion)
            .filter_by(prompt_id=sample_prompt.id)
            .order_by(PromptVersion.version)
            .all()
        )
        assert len(results) == 2
        assert results[0].version == 1
        assert results[1].version == 2

    def test_duplicate_prompt_id_and_version_raises_integrity_error(
        self, db_session: Session, sample_prompt: Prompt
    ) -> None:
        """Test inserting duplicate (prompt_id, version) raises IntegrityError."""
        db_session.add(
            PromptVersion(
                prompt_id=sample_prompt.id,
                version=1,
                template="first",
                variables=[],
            )
        )
        db_session.commit()

        db_session.add(
            PromptVersion(
                prompt_id=sample_prompt.id,
                version=1,
                template="second",
                variables=[],
            )
        )
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_foreign_key_enforced(self, db_session: Session) -> None:
        """Test inserting a version for a non-existent prompt raises IntegrityError."""
        db_session.execute(text("PRAGMA foreign_keys = ON"))
        version = PromptVersion(
            prompt_id="nonexistent",
            version=1,
            template="Hello",
            variables=[],
        )
        db_session.add(version)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_empty_variables_defaults_to_list(
        self, db_session: Session, sample_prompt: Prompt
    ) -> None:
        """Test that variables defaults to an empty list."""
        version = PromptVersion(
            prompt_id=sample_prompt.id,
            version=1,
            template="No placeholders here",
        )
        db_session.add(version)
        db_session.commit()

        result = db_session.get(PromptVersion, (sample_prompt.id, 1))
        assert result is not None
        assert result.variables == []


class TestPromptVersionVariableValidation:
    """Test cases for PromptVersion variable uniqueness validation."""

    def test_unique_variables_accepted(self) -> None:
        """Test that a list of unique variable names is accepted."""
        version = PromptVersion(
            prompt_id="pmpt_001",
            version=1,
            template="{{a}} {{b}}",
            variables=["a", "b"],
        )
        assert version.variables == ["a", "b"]

    def test_duplicate_variables_raises_validation_error(self) -> None:
        """Test that duplicate variable names raise PromptValidationError."""
        with pytest.raises(PromptValidationError, match="duplicate names"):
            PromptVersion(
                prompt_id="pmpt_001",
                version=1,
                template="{{a}} {{a}}",
                variables=["a", "a"],
            )

    def test_empty_variables_accepted(self) -> None:
        """Test that an empty variable list is accepted."""
        version = PromptVersion(
            prompt_id="pmpt_001",
            version=1,
            template="No variables",
            variables=[],
        )
        assert version.variables == []

    def test_single_variable_accepted(self) -> None:
        """Test that a single variable is accepted."""
        version = PromptVersion(
            prompt_id="pmpt_001",
            version=1,
            template="{{name}}",
            variables=["name"],
        )
        assert version.variables == ["name"]
