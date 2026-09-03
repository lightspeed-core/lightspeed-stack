"""Abstract base class for A2A context-to-conversation mapping storage."""

from abc import ABC, abstractmethod
from typing import Optional


class A2AContextStore(ABC):
    """Abstract base class for storing A2A context-to-conversation mappings.

    This store maps A2A context IDs to Llama Stack conversation IDs to
    preserve multi-turn conversation history across requests.

    For multi-worker deployments, implementations should use persistent
    storage (SQLite or PostgreSQL) to share state across workers.
    """

    @abstractmethod
    async def get(self, context_id: str) -> Optional[str]:
        """Retrieve the conversation ID for an A2A context.

        Args:
            context_id: The A2A context ID.

        Returns:
            The Llama Stack conversation ID, or None if not found.
        """

    @abstractmethod
    async def set(self, context_id: str, conversation_id: str) -> None:
        """Store a context-to-conversation mapping.

        Args:
            context_id: The A2A context ID.
            conversation_id: The Llama Stack conversation ID.
        """

    @abstractmethod
    async def delete(self, context_id: str) -> None:
        """Delete a context-to-conversation mapping.

        Args:
            context_id: The A2A context ID to delete.
        """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the store (create tables, etc.).

        This method should be called before using the store.
        """

    @abstractmethod
    def ready(self) -> bool:
        """Check if the store is ready for use.

        Returns:
            True if the store is initialized and ready, False otherwise.
        """
