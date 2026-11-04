"""Unit tests for prompts store operations."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Literal, Optional, overload

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.database.base import Base
from models.database.prompts import Prompt, PromptVersion
from prompts.exceptions import PromptNotFoundError, PromptValidationError
from prompts.store import (
    create_prompt,
    delete_prompt,
    get_prompt,
    list_prompts,
    update_prompt,
)

DUMMY_CREATE_PROMPT_PARAMS = (
    "test-prompt",
    "Hello {{name}}! {{greeting}}!",
    ["name", "greeting"],
)
DUMMY_UPDATE_PROMPT_PARAMS = ("{{a}} {{b}}", ["a", "b"])
DUMMY_ID = "pmpt_testing"


@overload
def _setup_db(
    session: Session,
    with_v2: Literal[True],
) -> tuple[Prompt, PromptVersion, PromptVersion]: ...


@overload
def _setup_db(
    session: Session, with_v2: Literal[False] = False
) -> tuple[Prompt, PromptVersion, None]: ...


def _setup_db(
    session: Session, with_v2: bool = False
) -> tuple[Prompt, PromptVersion, Optional[PromptVersion]]:
    """Insert a Prompt with one or two versions for test setup.

    Parameters:
        session: Active database session.
        with_v2: If True, also insert a second version.

    Returns:
        A tuple of (Prompt, PromptVersion v1, PromptVersion v2 or None).

    """
    name, template_v1, variables_v1 = DUMMY_CREATE_PROMPT_PARAMS
    template_v2, variables_v2 = DUMMY_UPDATE_PROMPT_PARAMS
    version = 1

    prompt = Prompt(id=DUMMY_ID, name=name, default_version=version)
    prompt_version_v1 = PromptVersion(
        prompt_id=DUMMY_ID,
        version=version,
        template=template_v1,
        variables=variables_v1,
    )

    session.add(prompt)
    session.add(prompt_version_v1)
    session.commit()

    session.refresh(prompt)
    session.refresh(prompt_version_v1)

    if with_v2:
        prompt_version_v2 = PromptVersion(
            prompt_id=DUMMY_ID,
            version=version + 1,
            template=template_v2,
            variables=variables_v2,
        )
        session.add(prompt_version_v2)
        session.commit()
        session.refresh(prompt_version_v2)

        return (prompt, prompt_version_v1, prompt_version_v2)

    return (prompt, prompt_version_v1, None)


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
def db_session_fixture(mocker, sqlite_engine: Engine) -> Generator[Session, None, None]:
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

    @contextmanager
    def mock_get_session():
        yield session

    mocker.patch("prompts.store.get_session", mock_get_session)

    try:
        yield session
    finally:
        session.close()


class TestPromptStoreOperation:
    """Test cases for prompt store CRUD operations."""

    def test_create_prompt(self, db_session: Session) -> None:
        """Test creating a prompt inserts both Prompt and PromptVersion rows."""
        name, template, variables = DUMMY_CREATE_PROMPT_PARAMS

        prompt_version = create_prompt(*DUMMY_CREATE_PROMPT_PARAMS)

        # Prompt
        prompt_qy_result = (
            db_session.query(Prompt).filter_by(id=prompt_version.prompt_id).all()
        )
        assert len(prompt_qy_result) == 1
        prompt_in_db = prompt_qy_result[0]

        assert prompt_in_db.name == name
        assert prompt_in_db.default_version == 1

        # PromptVersion
        prompt_version_qy_result = (
            db_session.query(PromptVersion)
            .filter_by(prompt_id=prompt_version.prompt_id)
            .all()
        )
        assert len(prompt_version_qy_result) == 1
        prompt_version_in_db = prompt_version_qy_result[0]

        assert prompt_version_in_db.created_at == prompt_version.created_at
        assert prompt_version_in_db.template == template
        assert prompt_version_in_db.variables == variables
        assert prompt_version_in_db.version == 1

    def test_create_prompt_with_invalid_variables(self, db_session: Session) -> None:
        """Test creating a prompt with duplicate variables raises PromptValidationError."""
        _ = db_session
        name, template, _ = DUMMY_CREATE_PROMPT_PARAMS
        variables = ["name", "name"]
        with pytest.raises(PromptValidationError, match="duplicate names"):
            create_prompt(name, template, variables)

    def test_create_prompt_with_empty_template(self, db_session: Session) -> None:
        """Test creating a prompt with empty template raises PromptValidationError."""
        _ = db_session
        with pytest.raises(PromptValidationError, match="must not be empty"):
            create_prompt("test-prompt", "", ["name"])

    def test_get_prompt(self, db_session: Session) -> None:
        """Test retrieving a prompt by default version and by explicit version."""
        prompt, expected_pv_v1, expected_pv_v2 = _setup_db(db_session, True)

        # Version 1
        prompt_version_v1 = get_prompt(prompt.id)
        assert prompt_version_v1.version == expected_pv_v1.version
        assert prompt_version_v1.template == expected_pv_v1.template
        assert prompt_version_v1.variables == expected_pv_v1.variables
        assert prompt_version_v1.prompt_id == expected_pv_v1.prompt_id
        assert prompt_version_v1.created_at == expected_pv_v1.created_at

        # Version 2
        prompt_version_v2 = get_prompt(prompt.id, expected_pv_v2.version)
        assert prompt_version_v2.version == expected_pv_v2.version
        assert prompt_version_v2.template == expected_pv_v2.template
        assert prompt_version_v2.variables == expected_pv_v2.variables
        assert prompt_version_v2.prompt_id == expected_pv_v2.prompt_id

    def test_get_prompt_with_invalid_version(self, db_session: Session) -> None:
        """Test retrieving a nonexistent version raises PromptNotFoundError."""
        prompt, _, _ = _setup_db(db_session)

        with pytest.raises(
            PromptNotFoundError, match=r"Version \d+ of prompt id=\bpmpt_\w+ not found"
        ):
            get_prompt(prompt.id, 101)

    def test_get_prompt_with_nonexistent_id(self, db_session: Session) -> None:
        """Test retrieving a prompt with a nonexistent id raises PromptNotFoundError."""
        _setup_db(db_session)

        with pytest.raises(
            PromptNotFoundError, match=r"Prompt id=\bpmpt_\w+ not found"
        ):
            get_prompt("pmpt_nonexistent")

    def test_update_prompt(self, db_session: Session) -> None:
        """Test updating a prompt appends an immutable version and optionally sets default."""
        prompt, pv_1, _ = _setup_db(db_session)
        template_v2, variables_v2 = DUMMY_UPDATE_PROMPT_PARAMS

        # Since the session is not closed during the entire test, we need to save the values
        # before the operation for the comparison. Otherwise, we will always get the newest
        # values by the lazily reload.
        ori_default_version = prompt.default_version

        cur_pmpt_version_counts = (
            db_session.query(PromptVersion).filter_by(prompt_id=prompt.id).count()
        )
        # Only one PromptVersion exist before the update
        assert cur_pmpt_version_counts == 1

        pv_2 = update_prompt(prompt.id, *DUMMY_UPDATE_PROMPT_PARAMS)

        # Without default=True, the default_version should stay the same
        assert prompt.default_version == ori_default_version

        cur_pmpt_version_counts = (
            db_session.query(PromptVersion).filter_by(prompt_id=prompt.id).count()
        )
        # update_prompt creates a new PromptVersion in the database
        assert cur_pmpt_version_counts == 2

        assert pv_2.version == pv_1.version + 1
        assert pv_2.prompt_id == prompt.id
        assert pv_2.template == template_v2
        assert pv_2.variables == variables_v2

        template_v3, variables_v3 = ("{{c}} {{d}}", ["c", "d"])
        pv_3 = update_prompt(prompt.id, template_v3, variables_v3, default=True)
        # With default=True, the default version should be updated to the new version
        assert prompt.default_version == pv_3.version

        assert pv_3.template == template_v3
        assert pv_3.variables == variables_v3

    def test_update_prompt_with_no_prompt_version_exists(
        self, db_session: Session
    ) -> None:
        """Test updating a prompt with no existing versions raises PromptNotFoundError."""
        prompt, _, _ = _setup_db(db_session)

        db_session.query(PromptVersion).filter_by(prompt_id=prompt.id).delete()

        with pytest.raises(
            PromptNotFoundError,
            match=r"No available version found for prompt id=\bpmpt_\w+",
        ):
            update_prompt(prompt.id, "{{x}} {{y}}", ["x", "y"])

    def test_update_prompt_with_no_prompt_exists_when_default_is_set_to_true(
        self, db_session: Session
    ) -> None:
        """Test updating with default=True when prompt is deleted raises PromptNotFoundError."""
        prompt, _, _ = _setup_db(db_session)

        db_session.query(Prompt).filter_by(id=prompt.id).delete()

        with pytest.raises(
            PromptNotFoundError, match=r"Prompt id=\bpmpt_\w+ not found"
        ):
            update_prompt(prompt.id, "{{x}} {{y}}", ["x", "y"], default=True)

    def test_update_prompt_with_duplicate_variables(self, db_session: Session) -> None:
        """Test updating a prompt with duplicate variables raises PromptValidationError."""
        prompt, _, _ = _setup_db(db_session)

        with pytest.raises(PromptValidationError, match="duplicate names"):
            update_prompt(prompt.id, "{{x}} {{x}}", ["x", "x"])

    def test_update_prompt_with_empty_template(self, db_session: Session) -> None:
        """Test updating a prompt with empty template raises PromptValidationError."""
        prompt, _, _ = _setup_db(db_session)

        with pytest.raises(PromptValidationError, match="must not be empty"):
            update_prompt(prompt.id, "", ["x"])

    def test_list_prompts(self, db_session: Session) -> None:
        """Test listing prompts returns all prompt identities."""
        _setup_db(db_session, True)

        prompts = list_prompts()

        assert len(prompts) == 1

        second_prompt_id = "pmpt_testing2"
        second_prompt_name = "Second Prompt"
        new_prompt = Prompt(
            id=second_prompt_id, name=second_prompt_name, default_version=1
        )
        db_session.add(new_prompt)
        db_session.commit()

        prompts = list_prompts()

        assert len(prompts) == 2
        filtered_prompts = [pv for pv in prompts if pv.id == second_prompt_id]
        assert len(filtered_prompts) == 1
        second_prompt = filtered_prompts[0]
        assert second_prompt.name == second_prompt_name

    def test_list_prompts_empty(self, db_session: Session) -> None:
        """Test listing prompts returns an empty list when no prompts exist."""
        _ = db_session
        prompts = list_prompts()

        assert len(prompts) == 0

    def test_delete_prompt(self, db_session: Session) -> None:
        """Test deleting a prompt removes the prompt and all its versions."""
        prompt, _, _ = _setup_db(db_session, True)

        prompt_counts = db_session.query(Prompt).filter_by(id=prompt.id).count()
        prompt_version_counts = (
            db_session.query(PromptVersion).filter_by(prompt_id=prompt.id).count()
        )

        assert prompt_counts == 1
        assert prompt_version_counts == 2

        delete_prompt(prompt.id)

        prompt_counts = db_session.query(Prompt).filter_by(id=prompt.id).count()
        prompt_version_counts = (
            db_session.query(PromptVersion).filter_by(prompt_id=prompt.id).count()
        )

        assert prompt_counts == 0
        assert prompt_version_counts == 0

    def test_delete_prompt_with_nonexistent_prompt_id(
        self, db_session: Session
    ) -> None:
        """Test deleting a nonexistent prompt raises PromptNotFoundError."""
        _setup_db(db_session)

        with pytest.raises(
            PromptNotFoundError, match=r"Prompt id=\bpmpt_\w+ not found"
        ):
            delete_prompt("pmpt_nonexistent")
