"""Unit tests for A2AStorageFactory."""

# pylint: disable=protected-access

from pathlib import Path
from typing import Generator
from unittest.mock import PropertyMock

import pytest
from pytest_mock import MockerFixture

from a2a.server.tasks import InMemoryTaskStore, DatabaseTaskStore

from a2a_storage import A2AStorageFactory
from a2a_storage.in_memory_context_store import InMemoryA2AContextStore
from a2a_storage.sqlite_context_store import SQLiteA2AContextStore
from models.config import A2AStateConfiguration, SQLiteDatabaseConfiguration


class TestA2AStorageFactory:
    """Tests for A2AStorageFactory."""

    @pytest.fixture(autouse=True)
    def reset_factory(self) -> Generator[None, None, None]:
        """Reset factory state before each test."""
        A2AStorageFactory.reset()
        yield
        A2AStorageFactory.reset()

    @pytest.mark.asyncio
    async def test_create_memory_task_store(self) -> None:
        """Test creating an in-memory task store (default, no config)."""
        config = A2AStateConfiguration()

        store = await A2AStorageFactory.create_task_store(config)

        assert isinstance(store, InMemoryTaskStore)

    @pytest.mark.asyncio
    async def test_create_memory_context_store(self) -> None:
        """Test creating an in-memory context store (default, no config)."""
        config = A2AStateConfiguration()

        store = await A2AStorageFactory.create_context_store(config)

        assert isinstance(store, InMemoryA2AContextStore)
        assert store.ready() is True

    @pytest.mark.asyncio
    async def test_create_sqlite_task_store(self, tmp_path: Path) -> None:
        """Test creating a SQLite task store."""
        db_path = tmp_path / "test_task_store.db"
        sqlite_config = SQLiteDatabaseConfiguration(db_path=str(db_path))
        config = A2AStateConfiguration(sqlite=sqlite_config)

        store = await A2AStorageFactory.create_task_store(config)

        assert isinstance(store, DatabaseTaskStore)

    @pytest.mark.asyncio
    async def test_create_sqlite_context_store(self, tmp_path: Path) -> None:
        """Test creating a SQLite context store."""
        db_path = tmp_path / "test_context_store.db"
        sqlite_config = SQLiteDatabaseConfiguration(db_path=str(db_path))
        config = A2AStateConfiguration(sqlite=sqlite_config)

        store = await A2AStorageFactory.create_context_store(config)

        assert isinstance(store, SQLiteA2AContextStore)
        assert store.ready() is True

    @pytest.mark.asyncio
    async def test_factory_reuses_task_store(self) -> None:
        """Test that factory reuses the same task store instance."""
        config = A2AStateConfiguration()

        store1 = await A2AStorageFactory.create_task_store(config)
        store2 = await A2AStorageFactory.create_task_store(config)

        assert store1 is store2

    @pytest.mark.asyncio
    async def test_factory_reuses_context_store(self) -> None:
        """Test that factory reuses the same context store instance."""
        config = A2AStateConfiguration()

        store1 = await A2AStorageFactory.create_context_store(config)
        store2 = await A2AStorageFactory.create_context_store(config)

        assert store1 is store2

    @pytest.mark.asyncio
    async def test_cleanup_disposes_state(self) -> None:
        """Test that cleanup disposes the stores."""
        config = A2AStateConfiguration()

        await A2AStorageFactory.create_task_store(config)
        await A2AStorageFactory.create_context_store(config)

        assert A2AStorageFactory._task_store is not None
        assert A2AStorageFactory._context_store is not None

        await A2AStorageFactory.cleanup()

        assert A2AStorageFactory._engine is None
        assert A2AStorageFactory._task_store is None
        assert A2AStorageFactory._context_store is None

    @pytest.mark.asyncio
    async def test_reset_clears_state(self) -> None:
        """Test that reset clears all factory state."""
        config = A2AStateConfiguration()

        await A2AStorageFactory.create_task_store(config)
        await A2AStorageFactory.create_context_store(config)

        A2AStorageFactory.reset()

        assert A2AStorageFactory._engine is None
        assert A2AStorageFactory._task_store is None
        assert A2AStorageFactory._context_store is None

    @pytest.mark.asyncio
    async def test_invalid_storage_type_raises_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test that an invalid storage type raises ValueError."""
        config = A2AStateConfiguration()

        # Mock the storage_type property to return an invalid value
        mocker.patch.object(
            A2AStateConfiguration,
            "storage_type",
            new_callable=PropertyMock,
            return_value="invalid",
        )
        with pytest.raises(ValueError, match="Unknown A2A state type"):
            await A2AStorageFactory.create_task_store(config)

    @pytest.mark.asyncio
    async def test_sqlite_storage_type_without_config_raises_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test that SQLite storage type without config raises ValueError."""
        config = A2AStateConfiguration()

        # Mock to simulate misconfiguration
        mocker.patch.object(
            A2AStateConfiguration,
            "storage_type",
            new_callable=PropertyMock,
            return_value="sqlite",
        )
        with pytest.raises(ValueError, match="SQLite configuration required"):
            await A2AStorageFactory.create_task_store(config)

    @pytest.mark.asyncio
    async def test_postgres_storage_type_without_config_raises_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test that PostgreSQL storage type without config raises ValueError."""
        config = A2AStateConfiguration()

        # Mock to simulate misconfiguration
        mocker.patch.object(
            A2AStateConfiguration,
            "storage_type",
            new_callable=PropertyMock,
            return_value="postgres",
        )
        with pytest.raises(ValueError, match="PostgreSQL configuration required"):
            await A2AStorageFactory.create_task_store(config)
