"""PostgreSQL cache implementation."""

import psycopg2

from cache.cache import Cache
from cache.cache_error import CacheError
from models.cache_entry import CacheEntry
from models.config import PostgreSQLDatabaseConfiguration
from log import get_logger
from utils.connection_decorator import connection

logger = get_logger("cache.postgres_cache")


class PostgresCache(Cache):
    """Cache that uses PostgreSQL to store cached values.

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
        "cache_pkey" PRIMARY KEY, btree (user_id, conversation_id)
        "cache_key_key" UNIQUE CONSTRAINT, btree (key)
        "timestamps" btree (updated_at)
    Access method: heap
    ```
    """

    CREATE_CACHE_TABLE = """
        CREATE TABLE IF NOT EXISTS cache (
            user_id         text NOT NULL,
            conversation_id text NOT NULL,
            created_at      timestamp NOT NULL,
            query           text,
            response        text,
            provider        text,
            model           text,
            PRIMARY KEY(user_id, conversation_id, created_at)
        );
        """

    CREATE_INDEX = """
        CREATE INDEX IF NOT EXISTS timestamps
            ON cache (created_at)
        """

    SELECT_CONVERSATION_HISTORY_STATEMENT = """
        SELECT query, response, provider, model
          FROM cache
         WHERE user_id=%s AND conversation_id=%s
         ORDER BY created_at
        """

    INSERT_CONVERSATION_HISTORY_STATEMENT = """
        INSERT INTO cache(user_id, conversation_id, created_at, query, response, provider, model)
        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s)
        """

    QUERY_CACHE_SIZE = """
        SELECT count(*) FROM cache;
        """

    DELETE_SINGLE_CONVERSATION_STATEMENT = """
        DELETE FROM cache
         WHERE user_id=%s AND conversation_id=%s
        """

    LIST_CONVERSATIONS_STATEMENT = """
        SELECT conversation_id, max(created_at) AS created_at
          FROM cache
         WHERE user_id=%s
         GROUP BY conversation_id
         ORDER BY created_at DESC
    """

    def __init__(self, config: PostgreSQLDatabaseConfiguration) -> None:
        """Create a new instance of PostgreSQL cache."""
        self.postgres_config = config

        # initialize connection to DB
        self.connect()
        # self.capacity = config.max_entries

    # pylint: disable=W0201
    def connect(self) -> None:
        """Initialize connection to database."""
        logger.info("Connecting to storage")
        # make sure the connection will have known state
        # even if PostgreSQL is not alive
        self.connection = None
        config = self.postgres_config
        try:
            self.connection = psycopg2.connect(
                host=config.host,
                port=config.port,
                user=config.user,
                password=config.password.get_secret_value(),
                dbname=config.db,
                sslmode=config.ssl_mode,
                sslrootcert=config.ca_cert_path,
                gssencmode=config.gss_encmode,
            )
            self.initialize_cache()
        except Exception as e:
            if self.connection is not None:
                self.connection.close()
            logger.exception("Error initializing Postgres cache:\n%s", e)
            raise
        self.connection.autocommit = True

    def connected(self) -> bool:
        """Check if connection to cache is alive."""
        if self.connection is None:
            logger.warning("Not connected, need to reconnect later")
            return False
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            logger.info("Connection to storage is ok")
            return True
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            logger.error("Disconnected from storage: %s", e)
            return False

    def initialize_cache(self) -> None:
        """Initialize cache - clean it up etc."""
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("Initialize_cache: cache is disconnected")

        # cursor as context manager is not used there on purpose
        # any CREATE statement can raise it's own exception
        # and it should not interfere with other statements
        cursor = self.connection.cursor()

        logger.info("Initializing table for cache")
        cursor.execute(PostgresCache.CREATE_CACHE_TABLE)

        logger.info("Initializing index for cache")
        cursor.execute(PostgresCache.CREATE_INDEX)

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

        with self.connection.cursor() as cursor:
            cursor.execute(
                self.SELECT_CONVERSATION_HISTORY_STATEMENT, (user_id, conversation_id)
            )
            conversation_entries = cursor.fetchall()

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

        try:
            # the whole operation is run in one transaction
            with self.connection.cursor() as cursor:
                cursor.execute(
                    PostgresCache.INSERT_CONVERSATION_HISTORY_STATEMENT,
                    (
                        user_id,
                        conversation_id,
                        cache_entry.query,
                        cache_entry.response,
                        cache_entry.provider,
                        cache_entry.model,
                    ),
                )
                # commit is implicit at this point
        except psycopg2.DatabaseError as e:
            logger.error("PostgresCache.insert_or_append: %s", e)
            raise CacheError("PostgresCache.insert_or_append", e) from e

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

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    PostgresCache.DELETE_SINGLE_CONVERSATION_STATEMENT,
                    (user_id, conversation_id),
                )
                deleted = cursor.rowcount
                return deleted > 0
        except psycopg2.DatabaseError as e:
            logger.error("PostgresCache.delete: %s", e)
            raise CacheError("PostgresCache.delete", e) from e

    @connection
    def list(self, user_id: str, skip_user_id_check: bool = False) -> list[str]:
        """List all conversations for a given user_id.

        Args:
            user_id: User identification.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            A list of conversation ids from the cache

        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("list: cache is disconnected")

        with self.connection.cursor() as cursor:
            cursor.execute(self.LIST_CONVERSATIONS_STATEMENT, (user_id,))
            conversations = cursor.fetchall()

        return [conversation[0] for conversation in conversations]

    def ready(self) -> bool:
        """Check if the cache is ready.

        Returns:
            True if the cache is ready, False otherwise.
        """
        return True
