"""In-memory implementation of A2A context store."""

import asyncio
from typing import Optional

from a2a_storage.context_store import A2AContextStore
from log import get_logger

logger = get_logger(__name__)


class InMemoryA2AContextStore(A2AContextStore):
    """In-memory implementation of A2A context-to-conversation store.

    Stores context mappings in a dictionary in memory. Data is lost when the
    server process stops. This implementation is suitable for single-worker
    deployments or development/testing.

    For multi-worker deployments, use SQLiteA2AContextStore or
    PostgresA2AContextStore instead.
    """

    def __init__(self) -> None:
        """Initialize the in-memory context store."""
        logger.debug("Initializing InMemoryA2AContextStore")
        self._contexts: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._initialized = True

    async def get(self, context_id: str) -> Optional[str]:
        """Retrieve the conversation ID for an A2A context.

        Args:
            context_id: The A2A context ID.

        Returns:
            The Llama Stack conversation ID, or None if not found.
        """
        async with self._lock:
            conversation_id = self._contexts.get(context_id)
            if conversation_id:
                logger.debug(
                    "Context %s maps to conversation %s", context_id, conversation_id
                )
            else:
                logger.debug("Context %s not found in store", context_id)
            return conversation_id

    async def set(self, context_id: str, conversation_id: str) -> None:
        """Store a context-to-conversation mapping.

        Args:
            context_id: The A2A context ID.
            conversation_id: The Llama Stack conversation ID.
        """
        async with self._lock:
            self._contexts[context_id] = conversation_id
            logger.debug(
                "Stored mapping: context %s -> conversation %s",
                context_id,
                conversation_id,
            )

    async def delete(self, context_id: str) -> None:
        """Delete a context-to-conversation mapping.

        Args:
            context_id: The A2A context ID to delete.
        """
        async with self._lock:
            if context_id in self._contexts:
                del self._contexts[context_id]
                logger.debug("Deleted context mapping for %s", context_id)
            else:
                logger.debug(
                    "Attempted to delete non-existent context mapping: %s", context_id
                )

    async def initialize(self) -> None:
        """Initialize the store.

        For in-memory store, this is a no-op as initialization happens
        in __init__.
        """
        logger.debug("InMemoryA2AContextStore initialized")

    def ready(self) -> bool:
        """Check if the store is ready for use.

        Returns:
            True, as in-memory store is always ready after construction.
        """
        return self._initialized
