"""Process-local harness step store lifecycle for PAI agent history."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_ai_harness.step_persistence import (
    SqliteStepStore,
    StepPersistence,
    StepStore,
)

from log import get_logger
from models.config import (
    AgentStepPersistenceConfiguration,
    AgentStepPersistenceNoopConfiguration,
    AgentStepPersistenceSqliteConfiguration,
)
from utils.types import Singleton

logger = get_logger(__name__)


class AgentHistoryService(metaclass=Singleton):
    """Owns the shared harness step store for Pydantic AI StepPersistence."""

    def __init__(self) -> None:
        """Create an uninitialized service.

        Call initialize after application configuration is loaded.
        """
        self._store: Optional[StepStore] = None

    def initialize(self, config: AgentStepPersistenceConfiguration) -> None:
        """Build the step store from persistence configuration.

        Args:
            config: Agent step persistence settings (noop or sqlite).

        """
        match config:
            case AgentStepPersistenceNoopConfiguration():
                self._store = None
            case AgentStepPersistenceSqliteConfiguration() as sqlite:
                logger.info(
                    "Creating SQLite agent step store at %s", sqlite.sqlite.db_path
                )
                self._store = SqliteStepStore(database=Path(sqlite.sqlite.db_path))

    def clear_store(self) -> None:
        """Drop the active step store reference without reinitializing.

        Used on configuration reload or in tests before a fresh initialize call.
        """
        self._store = None

    @property
    def store(self) -> Optional[StepStore]:
        """Return the configured step store.

        Returns:
            The active store, or None when persistence is disabled (noop).

        """
        return self._store

    @property
    def step_persistence(self) -> Optional[StepPersistence[object]]:
        """Return the harness StepPersistence capability for Pydantic AI agents.

        Returns:
            StepPersistence wrapping the active store, or None when persistence
            is disabled.

        """
        if self._store is None:
            return None
        return StepPersistence(store=self._store)
