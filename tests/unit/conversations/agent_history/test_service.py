"""Unit tests for AgentHistoryService."""

from pathlib import Path

import pytest
from pydantic_ai_harness.step_persistence import (
    SqliteStepStore,
    StepPersistence,
)

from conversations.agent_history.service import AgentHistoryService
from models.config import (
    AgentStepPersistenceNoopConfiguration,
    AgentStepPersistenceSqliteConfiguration,
    SQLiteDatabaseConfiguration,
)


@pytest.fixture(autouse=True)
def _fresh_service() -> None:
    """Isolate service store state between tests."""
    AgentHistoryService().clear_store()


def test_initialize_noop_disables_store() -> None:
    """Noop persistence config leaves store and capability unset."""
    service = AgentHistoryService()
    service.initialize(AgentStepPersistenceNoopConfiguration())
    assert service.store is None
    assert service.step_persistence is None


def test_initialize_sqlite_uses_configured_path(tmp_path: Path) -> None:
    """SQLite persistence opens the configured database file."""
    db_path = tmp_path / "steps.db"
    service = AgentHistoryService()
    service.initialize(
        AgentStepPersistenceSqliteConfiguration(
            sqlite=SQLiteDatabaseConfiguration(db_path=str(db_path)),
        )
    )
    store = service.store
    assert isinstance(store, SqliteStepStore)
    assert store._database == db_path.resolve()
    assert service.step_persistence is not None
    assert isinstance(service.step_persistence, StepPersistence)
    assert service.step_persistence.store is store
