"""Unit tests for InMemoryA2AContextStore."""

import pytest

from a2a_storage.in_memory_context_store import InMemoryA2AContextStore


class TestInMemoryA2AContextStore:
    """Tests for InMemoryA2AContextStore."""

    @pytest.fixture
    def store(self) -> InMemoryA2AContextStore:
        """Create a fresh in-memory context store for each test."""
        return InMemoryA2AContextStore()

    @pytest.mark.asyncio
    async def test_initialization(self, store: InMemoryA2AContextStore) -> None:
        """Test store initialization."""
        assert store.ready() is True

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, store: InMemoryA2AContextStore) -> None:
        """Test getting a key that doesn't exist returns None."""
        result = await store.get("nonexistent-context-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, store: InMemoryA2AContextStore) -> None:
        """Test setting and getting a context mapping."""
        context_id = "ctx-123"
        conversation_id = "conv-456"

        await store.set(context_id, conversation_id)
        result = await store.get(context_id)

        assert result == conversation_id

    @pytest.mark.asyncio
    async def test_set_overwrites_existing(
        self, store: InMemoryA2AContextStore
    ) -> None:
        """Test that set overwrites an existing mapping."""
        context_id = "ctx-123"
        conversation_id_1 = "conv-456"
        conversation_id_2 = "conv-789"

        await store.set(context_id, conversation_id_1)
        await store.set(context_id, conversation_id_2)
        result = await store.get(context_id)

        assert result == conversation_id_2

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, store: InMemoryA2AContextStore) -> None:
        """Test deleting an existing key."""
        context_id = "ctx-123"
        conversation_id = "conv-456"

        await store.set(context_id, conversation_id)
        await store.delete(context_id)
        result = await store.get(context_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, store: InMemoryA2AContextStore) -> None:
        """Test deleting a key that doesn't exist (should not raise)."""
        # Should not raise any exception
        await store.delete("nonexistent-context-id")

    @pytest.mark.asyncio
    async def test_multiple_contexts(self, store: InMemoryA2AContextStore) -> None:
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
    async def test_initialize_is_noop(self, store: InMemoryA2AContextStore) -> None:
        """Test that initialize is a no-op for in-memory store."""
        # Store should already be ready
        assert store.ready() is True

        # Initialize should not change anything
        await store.initialize()
        assert store.ready() is True
