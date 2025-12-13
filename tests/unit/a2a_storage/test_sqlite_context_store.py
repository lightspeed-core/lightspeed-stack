"""Unit tests for SQLiteA2AContextStore."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from a2a_storage.sqlite_context_store import SQLiteA2AContextStore


class TestSQLiteA2AContextStore:
    """Tests for SQLiteA2AContextStore."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> SQLiteA2AContextStore:
        """Create a fresh SQLite context store for each test."""
        db_path = tmp_path / "test_a2a_context.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
        )
        context_store = SQLiteA2AContextStore(engine, create_table=True)
        await context_store.initialize()
        return context_store

    @pytest.mark.asyncio
    async def test_initialization(self, store: SQLiteA2AContextStore) -> None:
        """Test store initialization."""
        assert store.ready() is True

    @pytest.mark.asyncio
    async def test_not_ready_before_initialize(self, tmp_path: Path) -> None:
        """Test store is not ready before initialization."""
        db_path = tmp_path / "test_a2a_context_uninit.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
        )
        context_store = SQLiteA2AContextStore(engine, create_table=True)
        assert context_store.ready() is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, store: SQLiteA2AContextStore) -> None:
        """Test getting a key that doesn't exist returns None."""
        result = await store.get("nonexistent-context-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, store: SQLiteA2AContextStore) -> None:
        """Test setting and getting a context mapping."""
        context_id = "ctx-123"
        conversation_id = "conv-456"

        await store.set(context_id, conversation_id)
        result = await store.get(context_id)

        assert result == conversation_id

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(self, store: SQLiteA2AContextStore) -> None:
        """Test that set overwrites an existing mapping."""
        context_id = "ctx-123"
        conversation_id_1 = "conv-456"
        conversation_id_2 = "conv-789"

        await store.set(context_id, conversation_id_1)
        await store.set(context_id, conversation_id_2)
        result = await store.get(context_id)

        assert result == conversation_id_2

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, store: SQLiteA2AContextStore) -> None:
        """Test deleting an existing key."""
        context_id = "ctx-123"
        conversation_id = "conv-456"

        await store.set(context_id, conversation_id)
        await store.delete(context_id)
        result = await store.get(context_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, store: SQLiteA2AContextStore) -> None:
        """Test deleting a key that doesn't exist (should not raise)."""
        # Should not raise any exception
        await store.delete("nonexistent-context-id")

    @pytest.mark.asyncio
    async def test_multiple_contexts(self, store: SQLiteA2AContextStore) -> None:
        """Test storing multiple context mappings."""
        mappings = {
            "ctx-1": "conv-1",
            "ctx-2": "conv-2",
            "ctx-3": "conv-3",
        }

        for ctx_id, conv_id in mappings.items():
            await store.set(ctx_id, conv_id)

        for ctx_id, expected_conv_id in mappings.items():
            result = await store.get(ctx_id)
            assert result == expected_conv_id

    @pytest.mark.asyncio
    async def test_persistence_across_operations(
        self, store: SQLiteA2AContextStore
    ) -> None:
        """Test that data persists after multiple operations."""
        # Set multiple values
        await store.set("ctx-1", "conv-1")
        await store.set("ctx-2", "conv-2")

        # Delete one
        await store.delete("ctx-1")

        # Update one
        await store.set("ctx-2", "conv-2-updated")

        # Add one more
        await store.set("ctx-3", "conv-3")

        # Verify state
        assert await store.get("ctx-1") is None
        assert await store.get("ctx-2") == "conv-2-updated"
        assert await store.get("ctx-3") == "conv-3"

    @pytest.mark.asyncio
    async def test_auto_initialize_on_operations(self, tmp_path: Path) -> None:
        """Test that store auto-initializes on first operation."""
        db_path = tmp_path / "test_auto_init.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
        )
        store = SQLiteA2AContextStore(engine, create_table=True)

        # Don't call initialize(), just use the store
        assert store.ready() is False

        # This should auto-initialize
        await store.set("ctx-1", "conv-1")
        assert store.ready() is True

        result = await store.get("ctx-1")
        assert result == "conv-1"
