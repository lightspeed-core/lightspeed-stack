"""PostgreSQL cache implementation."""

import psycopg2

from cache.cache import Cache
from cache.cache_error import CacheError
from models.cache_entry import CacheEntry, AdditionalKwargs
from models.config import PostgreSQLDatabaseConfiguration
from models.responses import ConversationData
from log import get_logger
from utils.connection_decorator import connection

logger = get_logger("cache.postgres_cache")


class PostgresCache(Cache):
    """Cache that uses PostgreSQL to store cached values.

    The cache itself lives stored in following table:

    ```
         Column      |              Type              | Nullable |
    -----------------+--------------------------------+----------+
     user_id         | text                           | not null |
     conversation_id | text                           | not null |
     created_at      | timestamp without time zone    | not null |
     started_at      | text                           |          |
     completed_at    | text                           |          |
     query           | text                           |          |
     response        | text                           |          |
     provider        | text                           |          |
     model           | text                           |          |
    Indexes:
        "cache_pkey" PRIMARY KEY, btree (user_id, conversation_id, created_at)
        "timestamps" btree (created_at)
    ```
    """

    CREATE_CACHE_TABLE = """
        CREATE TABLE IF NOT EXISTS cache (
            user_id           text NOT NULL,
            conversation_id   text NOT NULL,
            created_at        timestamp NOT NULL,
            started_at        text,
            completed_at      text,
            query             text,
            response          text,
            provider          text,
            model             text,
            additional_kwargs jsonb,
            PRIMARY KEY(user_id, conversation_id, created_at)
        );
        """

    CREATE_CONVERSATIONS_TABLE = """
        CREATE TABLE IF NOT EXISTS conversations (
            user_id                text NOT NULL,
            conversation_id        text NOT NULL,
            topic_summary          text,
            last_message_timestamp timestamp NOT NULL,
            PRIMARY KEY(user_id, conversation_id)
        );
        """

    CREATE_INDEX = """
        CREATE INDEX IF NOT EXISTS timestamps
            ON cache (created_at)
        """

    SELECT_CONVERSATION_HISTORY_STATEMENT = """
        SELECT query, response, provider, model, started_at, completed_at, additional_kwargs
          FROM cache
         WHERE user_id=%s AND conversation_id=%s
         ORDER BY created_at
        """

    INSERT_CONVERSATION_HISTORY_STATEMENT = """
        INSERT INTO cache(user_id, conversation_id, created_at, started_at, completed_at,
                          query, response, provider, model, additional_kwargs)
        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s)
        """

    QUERY_CACHE_SIZE = """
        SELECT count(*) FROM cache;
        """

    DELETE_SINGLE_CONVERSATION_STATEMENT = """
        DELETE FROM cache
         WHERE user_id=%s AND conversation_id=%s
        """

    LIST_CONVERSATIONS_STATEMENT = """
        SELECT conversation_id, topic_summary, EXTRACT(EPOCH FROM last_message_timestamp) as last_message_timestamp
          FROM conversations
         WHERE user_id=%s
         ORDER BY last_message_timestamp DESC
    """

    INSERT_OR_UPDATE_TOPIC_SUMMARY_STATEMENT = """
        INSERT INTO conversations(user_id, conversation_id, topic_summary, last_message_timestamp)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, conversation_id)
        DO UPDATE SET topic_summary = EXCLUDED.topic_summary, last_message_timestamp = EXCLUDED.last_message_timestamp
        """

    DELETE_CONVERSATION_STATEMENT = """
        DELETE FROM conversations
         WHERE user_id=%s AND conversation_id=%s
        """

    UPSERT_CONVERSATION_STATEMENT = """
        INSERT INTO conversations(user_id, conversation_id, topic_summary, last_message_timestamp)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, conversation_id)
        DO UPDATE SET last_message_timestamp = EXCLUDED.last_message_timestamp
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

        logger.info("Initializing table for conversations")
        cursor.execute(PostgresCache.CREATE_CONVERSATIONS_TABLE)

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
                # Parse it back into an LLMResponse object
                additional_kwargs_data = conversation_entry[6]
                additional_kwargs_obj = None
                if additional_kwargs_data:
                    additional_kwargs_obj = AdditionalKwargs.model_validate(additional_kwargs_data)
                cache_entry = CacheEntry(
                    query=conversation_entry[0],
                    response=conversation_entry[1],
                    provider=conversation_entry[2],
                    model=conversation_entry[3],
                    started_at=conversation_entry[4],
                    completed_at=conversation_entry[5],
                    additional_kwargs=additional_kwargs_obj,
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
            additional_kwargs_json = None
            if cache_entry.additional_kwargs:
                # Use exclude_none=True to keep JSON clean
                additional_kwargs_json = cache_entry.additional_kwargs.model_dump_json(exclude_none=True)
            # the whole operation is run in one transaction
            with self.connection.cursor() as cursor:
                cursor.execute(
                    PostgresCache.INSERT_CONVERSATION_HISTORY_STATEMENT,
                    (
                        user_id,
                        conversation_id,
                        cache_entry.started_at,
                        cache_entry.completed_at,
                        cache_entry.query,
                        cache_entry.response,
                        cache_entry.provider,
                        cache_entry.model,
                        additional_kwargs_json,
                    ),
                )

                # Update or insert conversation record with last_message_timestamp
                cursor.execute(
                    PostgresCache.UPSERT_CONVERSATION_STATEMENT,
                    (user_id, conversation_id, None),
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

                # Also delete conversation record for this conversation
                cursor.execute(
                    PostgresCache.DELETE_CONVERSATION_STATEMENT,
                    (user_id, conversation_id),
                )

                return deleted > 0
        except psycopg2.DatabaseError as e:
            logger.error("PostgresCache.delete: %s", e)
            raise CacheError("PostgresCache.delete", e) from e

    @connection
    def list(
        self, user_id: str, skip_user_id_check: bool = False
    ) -> list[ConversationData]:
        """List all conversations for a given user_id.

        Args:
            user_id: User identification.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            A list of ConversationData objects containing conversation_id, topic_summary, and
            last_message_timestamp

        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("list: cache is disconnected")

        with self.connection.cursor() as cursor:
            cursor.execute(self.LIST_CONVERSATIONS_STATEMENT, (user_id,))
            conversations = cursor.fetchall()

        result = []
        for conversation in conversations:
            conversation_data = ConversationData(
                conversation_id=conversation[0],
                topic_summary=conversation[1],
                last_message_timestamp=float(conversation[2]),
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

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    self.INSERT_OR_UPDATE_TOPIC_SUMMARY_STATEMENT,
                    (user_id, conversation_id, topic_summary),
                )
        except psycopg2.DatabaseError as e:
            logger.error("PostgresCache.set_topic_summary: %s", e)
            raise CacheError("PostgresCache.set_topic_summary", e) from e

    def ready(self) -> bool:
        """Check if the cache is ready.

        Returns:
            True if the cache is ready, False otherwise.
        """
        return True
