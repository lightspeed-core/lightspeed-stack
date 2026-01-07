"""Class with implementation of storage for token usage history.

One table named `token_usage` is used to store statistic about token usage
history. Input and output token count are stored for each triple (user_id,
provider, model). This triple is also used as a primary key to this table.
"""

import sqlite3
from datetime import datetime
from typing import Any

import psycopg2

from log import get_logger

from quota.connect_pg import connect_pg
from quota.connect_sqlite import connect_sqlite
from quota.sql import (
    CREATE_TOKEN_USAGE_TABLE,
    CONSUME_TOKENS_FOR_USER_PG,
    CONSUME_TOKENS_FOR_USER_SQLITE,
)

from models.config import (
    QuotaHandlersConfiguration,
    SQLiteDatabaseConfiguration,
    PostgreSQLDatabaseConfiguration,
)
from utils.connection_decorator import connection

logger = get_logger(__name__)


class TokenUsageHistory:
    """Class with implementation of storage for token usage history."""

    def __init__(self, configuration: QuotaHandlersConfiguration) -> None:
        """Initialize token usage history storage.

        Initialize TokenUsageHistory with the provided configuration and
        establish a database connection.

        Stores SQLite and PostgreSQL connection settings for later reconnection
        attempts, initializes the internal connection state, and opens the
        database connection.

        Parameters:
            configuration (QuotaHandlersConfiguration): Configuration
            containing `sqlite` and `postgres` connection settings.
        """
        # store the configuration, it will be used
        # by reconnection logic later, if needed
        self.sqlite_connection_config: SQLiteDatabaseConfiguration | None = (
            configuration.sqlite
        )
        self.postgres_connection_config: PostgreSQLDatabaseConfiguration | None = (
            configuration.postgres
        )
        self.connection: Any | None = None

        # initialize connection to DB
        self.connect()

    # pylint: disable=W0201
    def connect(self) -> None:
        """Initialize connection to database.

        Establish a database connection for token usage history and ensure required tables exist.

        Selects PostgreSQL if its configuration is present, otherwise uses
        SQLite; initializes the token_usage table, enables autocommit on the
        connection, and ensures the connection is closed and the exception is
        re-raised if table initialization fails.

        Raises:
            ValueError: If neither PostgreSQL nor SQLite configuration is provided.
        """
        logger.info("Initializing connection to quota usage history database")
        if self.postgres_connection_config is not None:
            self.connection = connect_pg(self.postgres_connection_config)
        if self.sqlite_connection_config is not None:
            self.connection = connect_sqlite(self.sqlite_connection_config)
        if self.connection is None:
            return

        try:
            self._initialize_tables()
        except Exception as e:
            self.connection.close()
            logger.exception("Error initializing quota usage history database:\n%s", e)
            raise

        self.connection.autocommit = True

    @connection
    def consume_tokens(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        user_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Consume tokens by given user.

        Record token usage for a specific user/provider/model triple in persistent storage.

        Parameters:
            user_id (str): Identifier of the user whose token usage will be updated.
            provider (str): Provider name associated with the usage (e.g., "openai").
            model (str): Model name associated with the usage (e.g., "gpt-4").
            input_tokens (int): Number of input tokens to add to the stored usage.
            output_tokens (int): Number of output tokens to add to the stored usage.

        Raises:
            ValueError: If no database backend configuration (Postgres or SQLite) is available.
        """
        logger.info(
            "Token usage for user %s, provider %s and model %s changed by %d, %d tokens",
            user_id,
            provider,
            model,
            input_tokens,
            output_tokens,
        )
        query_statement: str = ""
        if self.postgres_connection_config is not None:
            query_statement = CONSUME_TOKENS_FOR_USER_PG
        if self.sqlite_connection_config is not None:
            query_statement = CONSUME_TOKENS_FOR_USER_SQLITE

        # check if the connection was established
        if self.connection is None:
            logger.warning("Not connected, need to reconnect later")
            return

        # timestamp to be used
        updated_at = datetime.now()

        # it is not possible to use context manager there, because SQLite does
        # not support it
        cursor = self.connection.cursor()
        cursor.execute(
            query_statement,
            {
                "user_id": user_id,
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "updated_at": updated_at,
            },
        )
        cursor.close()

    def connected(self) -> bool:
        """Check if connection to quota usage history database is alive.

        Verify that the storage connection for token usage history is alive.

        Returns:
            `true` if the database connection is present and responds to a
            simple query, `false` otherwise.
        """
        if self.connection is None:
            logger.warning("Not connected, need to reconnect later")
            return False
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            logger.info("Connection to storage is ok")
            return True
        except (psycopg2.OperationalError, sqlite3.Error) as e:
            logger.error("Disconnected from storage: %s", e)
            return False
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.warning("Unable to close cursor")

    def _initialize_tables(self) -> None:
        """Initialize tables used by quota limiter.

        Ensure the token_usage table exists in the configured database.

        Creates the table required to store per-user token usage history (input/output tokens per
        user_id, provider, model) and commits the change to the database.
        """
        # check if the connection was established
        if self.connection is None:
            logger.warning("Not connected, need to reconnect later")
            return

        logger.info("Initializing tables for token usage history")
        cursor = self.connection.cursor()
        cursor.execute(CREATE_TOKEN_USAGE_TABLE)
        cursor.close()
        self.connection.commit()
