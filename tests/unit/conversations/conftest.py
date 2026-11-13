"""Shared fixtures for conversations unit tests."""

import pytest
from pytest_mock import MockerFixture
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from models.database.base import Base


@pytest.fixture(name="memory_engine")
def memory_engine_fixture() -> Engine:
    """Create an in-memory SQLite engine with conversation tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(name="patch_display_history_session")
def patch_display_history_session_fixture(
    mocker: MockerFixture, memory_engine: Engine
) -> None:
    """Point display_history_session at the in-memory engine."""
    mocker.patch(
        "conversations.display_history.persistence.session.get_session",
        side_effect=lambda: Session(memory_engine),
    )
