"""A2A protocol persistent storage components.

This module provides storage backends for A2A protocol state, including:
- Task storage (using A2A SDK's TaskStore interface)
- Context-to-conversation mapping storage

For multi-worker deployments, use SQLite or PostgreSQL backends to ensure
state is shared across all workers.
"""

from a2a_storage.context_store import A2AContextStore
from a2a_storage.in_memory_context_store import InMemoryA2AContextStore
from a2a_storage.sqlite_context_store import SQLiteA2AContextStore
from a2a_storage.postgres_context_store import PostgresA2AContextStore
from a2a_storage.storage_factory import A2AStorageFactory

__all__ = [
    "A2AContextStore",
    "InMemoryA2AContextStore",
    "SQLiteA2AContextStore",
    "PostgresA2AContextStore",
    "A2AStorageFactory",
]
