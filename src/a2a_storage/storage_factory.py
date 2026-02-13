"""Factory for creating A2A storage backends."""

from urllib.parse import quote_plus
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from a2a.server.tasks import TaskStore, InMemoryTaskStore, DatabaseTaskStore

from a2a_storage.context_store import A2AContextStore
from a2a_storage.in_memory_context_store import InMemoryA2AContextStore
from a2a_storage.sqlite_context_store import SQLiteA2AContextStore
from a2a_storage.postgres_context_store import PostgresA2AContextStore
from models.config import A2AStateConfiguration
from log import get_logger

logger = get_logger(__name__)


class A2AStorageFactory:
    """Factory for creating A2A storage backends.

    Creates appropriate TaskStore and A2AContextStore implementations based
    on the A2A state configuration. For multi-worker deployments, this factory
    creates database-backed stores that share state across workers.
    """

    _engine: Optional[AsyncEngine] = None
    _task_store: Optional[TaskStore] = None
    _context_store: Optional[A2AContextStore] = None

    @classmethod
    async def create_task_store(cls, config: A2AStateConfiguration) -> TaskStore:
        """Create a TaskStore based on configuration.

        Args:
            config: A2A state configuration.

        Returns:
            TaskStore implementation (InMemoryTaskStore or DatabaseTaskStore).
        """
        if cls._task_store is not None:
            return cls._task_store

        match config.storage_type:
            case "memory":
                logger.info("Creating in-memory A2A task store")
                cls._task_store = InMemoryTaskStore()
            case "sqlite":
                if config.sqlite is None:
                    raise ValueError("SQLite configuration required")
                logger.info(
                    "Creating SQLite A2A task store at %s", config.sqlite.db_path
                )
                engine = await cls._get_or_create_engine(config)
                cls._task_store = DatabaseTaskStore(
                    engine, create_table=True, table_name="a2a_tasks"
                )
                await cls._task_store.initialize()
            case "postgres":
                if config.postgres is None:
                    raise ValueError("PostgreSQL configuration required")
                logger.info(
                    "Creating PostgreSQL A2A task store at %s:%s",
                    config.postgres.host,
                    config.postgres.port,
                )
                engine = await cls._get_or_create_engine(config)
                cls._task_store = DatabaseTaskStore(
                    engine, create_table=True, table_name="a2a_tasks"
                )
                await cls._task_store.initialize()
            case _:
                raise ValueError(f"Unknown A2A state type: {config.storage_type}")

        return cls._task_store

    @classmethod
    async def create_context_store(
        cls, config: A2AStateConfiguration
    ) -> A2AContextStore:
        """Create an A2AContextStore based on configuration.

        Args:
            config: A2A state configuration.

        Returns:
            A2AContextStore implementation.
        """
        if cls._context_store is not None:
            return cls._context_store

        match config.storage_type:
            case "memory":
                logger.info("Creating in-memory A2A context store")
                cls._context_store = InMemoryA2AContextStore()
            case "sqlite":
                if config.sqlite is None:
                    raise ValueError("SQLite configuration required")
                logger.info(
                    "Creating SQLite A2A context store at %s", config.sqlite.db_path
                )
                engine = await cls._get_or_create_engine(config)
                cls._context_store = SQLiteA2AContextStore(engine, create_table=True)
                await cls._context_store.initialize()
            case "postgres":
                if config.postgres is None:
                    raise ValueError("PostgreSQL configuration required")
                logger.info(
                    "Creating PostgreSQL A2A context store at %s:%s",
                    config.postgres.host,
                    config.postgres.port,
                )
                engine = await cls._get_or_create_engine(config)
                cls._context_store = PostgresA2AContextStore(engine, create_table=True)
                await cls._context_store.initialize()
            case _:
                raise ValueError(f"Unknown A2A state type: {config.storage_type}")

        return cls._context_store

    @classmethod
    async def _get_or_create_engine(cls, config: A2AStateConfiguration) -> AsyncEngine:
        """Get or create the SQLAlchemy async engine.

        The engine is reused for both task and context stores to share
        the connection pool.

        Args:
            config: A2A state configuration.

        Returns:
            SQLAlchemy AsyncEngine.
        """
        if cls._engine is not None:
            return cls._engine

        match config.storage_type:
            case "sqlite":
                if config.sqlite is None:
                    raise ValueError("SQLite configuration required")
                connection_string = f"sqlite+aiosqlite:///{config.sqlite.db_path}"
                cls._engine = create_async_engine(
                    connection_string,
                    echo=False,
                )
            case "postgres":
                if config.postgres is None:
                    raise ValueError("PostgreSQL configuration required")
                pg = config.postgres
                password = (
                    quote_plus(pg.password.get_secret_value()) if pg.password else ""
                )
                connection_string = (
                    f"postgresql+asyncpg://{pg.user}:{password}"
                    f"@{pg.host}:{pg.port}/{pg.db}"
                )
                cls._engine = create_async_engine(
                    connection_string,
                    echo=False,
                )
            case _:
                raise ValueError(
                    f"Cannot create engine for storage type: {config.storage_type}"
                )

        logger.info("Created async database engine for A2A storage")
        return cls._engine

    @classmethod
    async def cleanup(cls) -> None:
        """Clean up resources (close database connections)."""
        if cls._engine is not None:
            await cls._engine.dispose()
            cls._engine = None
            logger.info("Closed A2A storage database engine")
        cls._task_store = None
        cls._context_store = None

    @classmethod
    def reset(cls) -> None:
        """Reset factory state (for testing purposes)."""
        cls._engine = None
        cls._task_store = None
        cls._context_store = None
