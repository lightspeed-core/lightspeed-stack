"""PostgreSQL cache implementation."""

import json
import psycopg2
from psycopg2.extensions import AsIs

from cache.cache import Cache
from cache.cache_error import CacheError
from models.cache_entry import CacheEntry
from models.config import PostgreSQLDatabaseConfiguration
from models.requests import Attachment
from models.responses import ConversationData, ReferencedDocument
from utils.connection_decorator import connection
from utils.types import ToolCallSummary, ToolResultSummary
from log import get_logger

logger = get_logger("cache.postgres_cache")


class PostgresCache(Cache):
    """Cache that uses PostgreSQL to store cached values.

    The cache itself lives stored in following table:

    ```
         Column            |              Type              | Nullable |
    -----------------------+--------------------------------+----------+
     user_id               | text                           | not null |
     conversation_id       | text                           | not null |
     created_at            | timestamp without time zone    | not null |
     started_at            | text                           |          |
     completed_at          | text                           |          |
     query                 | text                           |          |
     response              | text                           |          |
     provider              | text                           |          |
     model                 | text                           |          |
     referenced_documents  | jsonb                          |          |
     tool_calls            | jsonb                          |          |
     tool_results          | jsonb                          |          |
     attachments           | jsonb                          |          |
    Indexes:
        "cache_pkey" PRIMARY KEY, btree (user_id, conversation_id, created_at)
        "timestamps" btree (created_at)
    ```
    """

    CREATE_SCHEMA = """
       CREATE SCHEMA IF NOT EXISTS %s;
       """

    CREATE_CACHE_TABLE = """
        CREATE TABLE IF NOT EXISTS cache (
            user_id              text NOT NULL,
            conversation_id      text NOT NULL,
            created_at           timestamp NOT NULL,
            started_at           text,
            completed_at         text,
            query                text,
            response             text,
            provider             text,
            model                text,
            referenced_documents jsonb,
            tool_calls           jsonb,
            tool_results         jsonb,
            attachments          jsonb,
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
        SELECT query, response, provider, model, started_at, completed_at,
               referenced_documents, tool_calls, tool_results, attachments
          FROM cache
         WHERE user_id=%s AND conversation_id=%s
         ORDER BY created_at
        """

    INSERT_CONVERSATION_HISTORY_STATEMENT = """
        INSERT INTO cache(user_id, conversation_id, created_at, started_at, completed_at,
                          query, response, provider, model, referenced_documents,
                          tool_calls, tool_results, attachments)
        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        """Create a new instance of PostgreSQL cache.

        Initialize a Postgres-backed cache using the provided database configuration.

        Stores the configuration on the instance and establishes the PostgreSQL
        connection, initializing the cache schema.

        Parameters:
            config (PostgreSQLDatabaseConfiguration): Configuration used to
            connect to the PostgreSQL server and configure the cache.
        """
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
        namespace = "public"
        if config.namespace is not None:
            namespace = config.namespace
            # LCORE-1158 need to be implemented too!
            # validate namespace contains only valid PostgreSQL identifier characters
            if not namespace.replace("_", "").replace("$", "").isalnum():
                raise ValueError(f"Invalid namespace: {namespace}")
            if len(namespace) > 63:
                raise ValueError(
                    f"Invalid namespace: {namespace}. "
                    "Maximum length is 63 characters."
                )
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
                options=f"-c search_path={namespace}",
            )
            self.initialize_cache(namespace)
        except Exception as e:
            if self.connection is not None:
                self.connection.close()
            logger.exception("Error initializing Postgres cache:\n%s", e)
            raise
        self.connection.autocommit = True

    def connected(self) -> bool:
        """Check if connection to cache is alive.

        Determine whether the PostgreSQL connection is alive and responsive.

        Returns:
            bool: `True` if the connection exists and a simple probe query
            succeeds, `False` otherwise.
        """
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

    def initialize_cache(self, namespace: str) -> None:
        """Initialize cache and create schema if needed.

        Parameters:
            namespace: PostgreSQL schema namespace to use for cache tables.
                      If not "public", the schema will be created if it doesn't exist.

        Raises:
            CacheError: If the cache is disconnected.
        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("Initialize_cache: cache is disconnected")

        # cursor as context manager is not used there on purpose
        # any CREATE statement can raise it's own exception
        # and it should not interfere with other statements
        cursor = self.connection.cursor()

        logger.info("Initializing schema")
        if namespace != "public":
            cursor.execute(PostgresCache.CREATE_SCHEMA, (AsIs(namespace),))

        logger.info("Initializing table for cache")
        cursor.execute(PostgresCache.CREATE_CACHE_TABLE)

        logger.info("Initializing table for conversations")
        cursor.execute(PostgresCache.CREATE_CONVERSATIONS_TABLE)

        logger.info("Initializing index for cache")
        cursor.execute(PostgresCache.CREATE_INDEX)

        cursor.close()
        self.connection.commit()

    @connection
    def get(  # pylint: disable=R0914
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> list[CacheEntry]:
        """Get the value associated with the given key.

        Parameters:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            The value associated with the key, or None if not found.

        Raises:
            CacheError: If the cache connection is not available.
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
                # Parse referenced_documents back into ReferencedDocument objects
                docs_data = conversation_entry[6]
                docs_obj = None
                if docs_data:
                    try:
                        docs_obj = [
                            ReferencedDocument.model_validate(doc) for doc in docs_data
                        ]
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Failed to deserialize referenced_documents for "
                            "conversation %s: %s",
                            conversation_id,
                            e,
                        )

                # Parse tool_calls back into ToolCallSummary objects
                tool_calls_data = conversation_entry[7]
                tool_calls_obj = None
                if tool_calls_data:
                    try:
                        tool_calls_obj = [
                            ToolCallSummary.model_validate(tc) for tc in tool_calls_data
                        ]
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Failed to deserialize tool_calls for "
                            "conversation %s: %s",
                            conversation_id,
                            e,
                        )

                # Parse tool_results back into ToolResultSummary objects
                tool_results_data = conversation_entry[8]
                tool_results_obj = None
                if tool_results_data:
                    try:
                        tool_results_obj = [
                            ToolResultSummary.model_validate(tr)
                            for tr in tool_results_data
                        ]
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Failed to deserialize tool_results for "
                            "conversation %s: %s",
                            conversation_id,
                            e,
                        )

                # Parse attachments back into Attachment objects
                attachments_data = conversation_entry[9]
                attachments_obj = None
                if attachments_data:
                    try:
                        attachments_obj = [
                            Attachment.model_validate(att) for att in attachments_data
                        ]
                    except (ValueError, TypeError) as e:
                        logger.warning(
                            "Failed to deserialize attachments for "
                            "conversation %s: %s",
                            conversation_id,
                            e,
                        )

                cache_entry = CacheEntry(
                    query=conversation_entry[0],
                    response=conversation_entry[1],
                    provider=conversation_entry[2],
                    model=conversation_entry[3],
                    started_at=conversation_entry[4],
                    completed_at=conversation_entry[5],
                    referenced_documents=docs_obj,
                    tool_calls=tool_calls_obj,
                    tool_results=tool_results_obj,
                    attachments=attachments_obj,
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

        Parameters:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            cache_entry: The `CacheEntry` object to store.
            skip_user_id_check: Skip user_id suid check.

        Raises:
            CacheError: If the cache is disconnected or a database error occurs
            while persisting the entry.
        """
        if self.connection is None:
            logger.error("Cache is disconnected")
            raise CacheError("insert_or_append: cache is disconnected")

        try:
            referenced_documents_json = None
            if cache_entry.referenced_documents:
                try:
                    docs_as_dicts = [
                        doc.model_dump(mode="json")
                        for doc in cache_entry.referenced_documents
                    ]
                    referenced_documents_json = json.dumps(docs_as_dicts)
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "Failed to serialize referenced_documents for "
                        "conversation %s: %s",
                        conversation_id,
                        e,
                    )

            tool_calls_json = None
            if cache_entry.tool_calls:
                try:
                    tool_calls_as_dicts = [
                        tc.model_dump(mode="json") for tc in cache_entry.tool_calls
                    ]
                    tool_calls_json = json.dumps(tool_calls_as_dicts)
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "Failed to serialize tool_calls for conversation %s: %s",
                        conversation_id,
                        e,
                    )

            tool_results_json = None
            if cache_entry.tool_results:
                try:
                    tool_results_as_dicts = [
                        tr.model_dump(mode="json") for tr in cache_entry.tool_results
                    ]
                    tool_results_json = json.dumps(tool_results_as_dicts)
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "Failed to serialize tool_results for conversation %s: %s",
                        conversation_id,
                        e,
                    )

            attachments_json = None
            if cache_entry.attachments:
                try:
                    attachments_as_dicts = [
                        att.model_dump(mode="json") for att in cache_entry.attachments
                    ]
                    attachments_json = json.dumps(attachments_as_dicts)
                except (TypeError, ValueError) as e:
                    logger.warning(
                        "Failed to serialize attachments for conversation %s: %s",
                        conversation_id,
                        e,
                    )

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
                        referenced_documents_json,
                        tool_calls_json,
                        tool_results_json,
                        attachments_json,
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

        Parameters:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            bool: True if the conversation was deleted, False if not found.

        Raises:
            CacheError: If the cache is disconnected or a database error occurs.
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

        Parameters:
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

        Parameters:
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
