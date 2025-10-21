"""Abstract class that is parent for all quota limiter implementations."""

from abc import ABC, abstractmethod

from typing import Optional

import psycopg2

from log import get_logger
from models.config import SQLiteDatabaseConfiguration, PostgreSQLDatabaseConfiguration
from quota.connect_pg import connect_pg
from quota.connect_sqlite import connect_sqlite


logger = get_logger(__name__)


class QuotaLimiter(ABC):
    """Abstract class that is parent for all quota limiter implementations."""

    @abstractmethod
    def available_quota(self, subject_id: str) -> int:
        """Retrieve available quota for given user."""

    @abstractmethod
    def revoke_quota(self) -> None:
        """Revoke quota for given user."""

    @abstractmethod
    def increase_quota(self) -> None:
        """Increase quota for given user."""

    @abstractmethod
    def ensure_available_quota(self, subject_id: str = "") -> None:
        """Ensure that there's available quota left."""

    @abstractmethod
    def consume_tokens(
        self, input_tokens: int, output_tokens: int, subject_id: str = ""
    ) -> None:
        """Consume tokens by given user."""

    @abstractmethod
    def __init__(self) -> None:
        """Initialize connection configuration(s)."""
        self.sqlite_connection_config: Optional[SQLiteDatabaseConfiguration] = None
        self.postgres_connection_config: Optional[PostgreSQLDatabaseConfiguration] = (
            None
        )

    @abstractmethod
    def _initialize_tables(self) -> None:
        """Initialize tables and indexes."""

    # pylint: disable=W0201
    def connect(self) -> None:
        """Initialize connection to database."""
        logger.info("Initializing connection to quota limiter database")
        if self.postgres_connection_config is not None:
            self.connection = connect_pg(self.postgres_connection_config)
        if self.sqlite_connection_config is not None:
            self.connection = connect_sqlite(self.sqlite_connection_config)

        try:
            self._initialize_tables()
        except Exception as e:
            self.connection.close()
            logger.exception("Error initializing Postgres database:\n%s", e)
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
        except psycopg2.OperationalError as e:
            logger.error("Disconnected from storage: %s", e)
            return False
