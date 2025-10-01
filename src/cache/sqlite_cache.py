"""Cache that uses SQLite to store cached values."""

from time import time

import sqlite3

from cache.cache import Cache
from cache.cache_error import CacheError
from models.cache_entry import CacheEntry, ConversationData
from models.config import SQLiteDatabaseConfiguration
from log import get_logger
from utils.connection_decorator import connection

logger = get_logger("cache.sqlite_cache")


class SQLiteCache(Cache):
    """Cache that uses SQLite to store cached values.

    The cache itself is stored in following table:

    ```
         Column      |            Type             | Nullable |
    -----------------+-----------------------------+----------+
     user_id         | text                        | not null |
     conversation_id | text                        | not null |
     created_at      | int                         | not null |
     query           | text                        |          |
     response        | text                        |          |
     provider        | text                        |          |
     model           | text                        |          |
    Indexes:
        "cache_pkey" PRIMARY KEY, btree (user_id, conversation_id, created_at)
        "cache_key_key" UNIQUE CONSTRAINT, btree (key)
        "timestamps" btree (updated_at)
    Access method: heap
    ```
    """

    CREATE_CACHE_TABLE = """
        CREATE TABLE IF NOT EXISTS cache (
            user_id         text NOT NULL,
            conversation_id text NOT NULL,
            created_at      int NOT NULL,
            query           text,
            response        text,
            provider        text,
            model           text,
            PRIMARY KEY(user_id, conversation_id, created_at)
        );
        """

    CREATE_CONVERSATIONS_TABLE = """
        CREATE TABLE IF NOT EXISTS conversations (
            user_id                text NOT NULL,
            conversation_id        text NOT NULL,
            topic_summary          text,
            last_message_timestamp int NOT NULL,
            PRIMARY KEY(user_id, conversation_id)
        );
        """

    CREATE_INDEX = """
        CREATE INDEX IF NOT EXISTS timestamps
            ON cache (created_at)
        """

    SELECT_CONVERSATION_HISTORY_STATEMENT = """
        SELECT query, response, provider, model
          FROM cache
         WHERE user_id=? AND conversation_id=?
         ORDER BY created_at
        """

    INSERT_CONVERSATION_HISTORY_STATEMENT = """
        INSERT INTO cache(user_id, conversation_id, created_at, query, response, provider, model)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

    QUERY_CACHE_SIZE = """
        SELECT count(*) FROM cache;
        """

    DELETE_SINGLE_CONVERSATION_STATEMENT = """
        DELETE FROM cache
         WHERE user_id=? AND conversation_id=?
        """

    LIST_CONVERSATIONS_STATEMENT = """
        SELECT conversation_id, topic_summary, last_message_timestamp
          FROM conversations
         WHERE user_id=?
         ORDER BY last_message_timestamp DESC
    """

    INSERT_OR_UPDATE_TOPIC_SUMMARY_STATEMENT = """
        INSERT OR REPLACE INTO conversations(user_id, conversation_id, topic_summary, last_message_timestamp)
        VALUES (?, ?, ?, ?)
        """

    DELETE_CONVERSATION_STATEMENT = """
        DELETE FROM conversations
         WHERE user_id=? AND conversation_id=?
        """

    UPSERT_CONVERSATION_STATEMENT = """
        INSERT INTO conversations(user_id, conversation_id, topic_summary, last_message_timestamp)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id, conversation_id)
        DO UPDATE SET last_message_timestamp = excluded.last_message_timestamp
        """

    def __init__(self, config: SQLiteDatabaseConfiguration) -> None:
        """Create a new instance of SQLite cache."""
        self.sqlite_config = config

        # initialize connection to DB
        self.connect()
        # self.capacity = config.max_entries

    # pylint: disable=W0201
    def connect(self) -> None:
        """Initialize connection to database."""
        logger.info("Connecting to storage")
        # make sure the connection will have known state
        # even if SQLite is not alive
        self.connection = None
        config = self.sqlite_config
        try:
            self.connection = sqlite3.connect(database=config.db_path)
            self.initialize_cache()
        except sqlite3.Error as e:
            if self.connection is not None:
                self.connection.close()
            logger.exception("Error initializing SQLite cache:\n%s", e)
            raise
        self.connection.autocommit = True

    def connected(self) -> bool:
        """Check if connection to cache is alive."""
        if self.connection is None:
            logger.warning("Not connected, need to reconnect later")
            return False
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            logger.info("Connection to storage is ok")
            return True
        except sqlite3.Error as e:
            logger.error("Disconnected from storage: %s", e)
            return False
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.warning("Unable to close cursor")

    def initialize_cache(self) -> None:
        """Initialize cache - clean it up etc."""
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("Initialize_cache: cache is disconnected")

        cursor = self.connection.cursor()

        logger.info("Initializing table for cache")
        cursor.execute(SQLiteCache.CREATE_CACHE_TABLE)

        logger.info("Initializing table for conversations")
        cursor.execute(SQLiteCache.CREATE_CONVERSATIONS_TABLE)

        logger.info("Initializing index for cache")
        cursor.execute(SQLiteCache.CREATE_INDEX)

        cursor.close()
        self.connection.commit()

    @connection
    def get(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> list[CacheEntry]:
        """Get the value associated with the given key.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            The value associated with the key, or None if not found.
        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("get: cache is disconnected")

        cursor = self.connection.cursor()
        cursor.execute(
            self.SELECT_CONVERSATION_HISTORY_STATEMENT, (user_id, conversation_id)
        )
        conversation_entries = cursor.fetchall()
        cursor.close()

        result = []
        for conversation_entry in conversation_entries:
            cache_entry = CacheEntry(
                query=conversation_entry[0],
                response=conversation_entry[1],
                provider=conversation_entry[2],
                model=conversation_entry[3],
            )
            result.append(cache_entry)

        return result

    @connection
    def insert_or_append(
        self,
        user_id: str,
        conversation_id: str,
        cache_entry: CacheEntry,
        skip_user_id_check: bool = False,
    ) -> None:
        """Set the value associated with the given key.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            cache_entry: The `CacheEntry` object to store.
            skip_user_id_check: Skip user_id suid check.

        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("insert_or_append: cache is disconnected")

        cursor = self.connection.cursor()
        current_time = time()
        cursor.execute(
            self.INSERT_CONVERSATION_HISTORY_STATEMENT,
            (
                user_id,
                conversation_id,
                current_time,
                cache_entry.query,
                cache_entry.response,
                cache_entry.provider,
                cache_entry.model,
            ),
        )

        # Update or insert conversation record with last_message_timestamp
        cursor.execute(
            self.UPSERT_CONVERSATION_STATEMENT,
            (user_id, conversation_id, None, current_time),
        )

        cursor.close()
        self.connection.commit()

    @connection
    def delete(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> bool:
        """Delete conversation history for a given user_id and conversation_id.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            bool: True if the conversation was deleted, False if not found.

        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("delete: cache is disconnected")

        cursor = self.connection.cursor()
        cursor.execute(
            self.DELETE_SINGLE_CONVERSATION_STATEMENT,
            (user_id, conversation_id),
        )
        deleted = cursor.rowcount > 0

        # Also delete conversation record for this conversation
        cursor.execute(
            self.DELETE_CONVERSATION_STATEMENT,
            (user_id, conversation_id),
        )

        cursor.close()
        self.connection.commit()
        return deleted

    @connection
    def list(
        self, user_id: str, skip_user_id_check: bool = False
    ) -> list[ConversationData]:
        """List all conversations for a given user_id.

        Args:
            user_id: User identification.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            A list of ConversationData objects containing conversation_id,
            topic_summary, and last_message_timestamp

        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("list: cache is disconnected")

        cursor = self.connection.cursor()
        cursor.execute(self.LIST_CONVERSATIONS_STATEMENT, (user_id,))
        conversations = cursor.fetchall()
        cursor.close()

        result = []
        for conversation in conversations:
            conversation_data = ConversationData(
                conversation_id=conversation[0],
                topic_summary=conversation[1],
                last_message_timestamp=conversation[2],
            )
            result.append(conversation_data)

        return result

    @connection
    def set_topic_summary(
        self,
        user_id: str,
        conversation_id: str,
        topic_summary: str,
        skip_user_id_check: bool = False,
    ) -> None:
        """Set the topic summary for the given conversation.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            topic_summary: The topic summary to store.
            skip_user_id_check: Skip user_id suid check.
        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("set_topic_summary: cache is disconnected")

        cursor = self.connection.cursor()
        cursor.execute(
            self.INSERT_OR_UPDATE_TOPIC_SUMMARY_STATEMENT,
            (user_id, conversation_id, topic_summary, time()),
        )
        cursor.close()
        self.connection.commit()

    def ready(self) -> bool:
        """Check if the cache is ready.

        Returns:
            True if the cache is ready, False otherwise.
        """
        return True
