"""SQLite implementation of A2A context store."""

from typing import Optional

from sqlalchemy import Column, String, Table, MetaData, select, delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from a2a_storage.context_store import A2AContextStore
from log import get_logger

logger = get_logger(__name__)

# Define the table metadata
metadata = MetaData()

a2a_context_table = Table(
    "a2a_contexts",
    metadata,
    Column("context_id", String, primary_key=True),
    Column("conversation_id", String, nullable=False),
)


class SQLiteA2AContextStore(A2AContextStore):
    """SQLite implementation of A2A context-to-conversation store.

    Stores context mappings in a SQLite database for persistence across
    restarts and sharing across workers (when using a shared database file).

    The store creates a table 'a2a_contexts' with the following schema:
        context_id (TEXT, PRIMARY KEY): The A2A context ID
        conversation_id (TEXT, NOT NULL): The Llama Stack conversation ID
    """

    def __init__(
        self,
        engine: AsyncEngine,
        create_table: bool = True,
    ) -> None:
        """Initialize the SQLite context store.

        Args:
            engine: SQLAlchemy async engine connected to the SQLite database.
            create_table: If True, create the table on initialization.
        """
        logger.debug("Initializing SQLiteA2AContextStore")
        self._engine = engine
        self._session_maker = async_sessionmaker(engine, expire_on_commit=False)
        self._create_table = create_table
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the store and create tables if needed."""
        if self._initialized:
            return

        logger.debug("Initializing SQLite A2A context store schema")
        if self._create_table:
            async with self._engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
        self._initialized = True
        logger.info("SQLiteA2AContextStore initialized successfully")

    async def _ensure_initialized(self) -> None:
        """Ensure the store is initialized before use."""
        if not self._initialized:
            await self.initialize()

    async def get(self, context_id: str) -> Optional[str]:
        """Retrieve the conversation ID for an A2A context.

        Args:
            context_id: The A2A context ID.

        Returns:
            The Llama Stack conversation ID, or None if not found.
        """
        await self._ensure_initialized()

        async with self._session_maker() as session:
            stmt = select(a2a_context_table.c.conversation_id).where(
                a2a_context_table.c.context_id == context_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if row:
                logger.debug("Context %s maps to conversation %s", context_id, row)
                return row
            logger.debug("Context %s not found in store", context_id)
            return None

    async def set(self, context_id: str, conversation_id: str) -> None:
        """Store a context-to-conversation mapping.

        Uses delete-then-insert to handle both new and existing mappings.

        Args:
            context_id: The A2A context ID.
            conversation_id: The Llama Stack conversation ID.
        """
        await self._ensure_initialized()

        async with self._session_maker.begin() as session:
            # Upsert by deleting existing row and inserting new values
            await session.execute(
                a2a_context_table.delete().where(
                    a2a_context_table.c.context_id == context_id
                )
            )
            await session.execute(
                a2a_context_table.insert().values(
                    context_id=context_id,
                    conversation_id=conversation_id,
                )
            )
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
        await self._ensure_initialized()

        async with self._session_maker.begin() as session:
            stmt = delete(a2a_context_table).where(
                a2a_context_table.c.context_id == context_id
            )
            await session.execute(stmt)
            logger.debug("Deleted context mapping for %s", context_id)

    def ready(self) -> bool:
        """Check if the store is ready for use.

        Returns:
            True if the store is initialized, False otherwise.
        """
        return self._initialized
