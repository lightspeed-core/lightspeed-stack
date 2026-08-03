# List of source files stored in `src/a2a_storage` directory

## [__init__.py](__init__.py)
A2A protocol persistent storage components.

## [context_store.py](context_store.py)
Abstract base class for A2A context-to-conversation mapping storage.

## [in_memory_context_store.py](in_memory_context_store.py)
In-memory implementation of A2A context store.

## [postgres_context_store.py](postgres_context_store.py)
PostgreSQL implementation of A2A context store.

## [sqlite_context_store.py](sqlite_context_store.py)
SQLite implementation of A2A context store.

## [storage_factory.py](storage_factory.py)
Factory for creating A2A storage backends.

