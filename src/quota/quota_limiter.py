"""Abstract class that is the parent for all quota limiter implementations.

It is possible to limit quota usage per user or per service or services (that
typically run in one cluster). Each limit is configured as a separate _quota
limiter_. It can be of type `user_limiter` or `cluster_limiter` (which is name
that makes sense in OpenShift deployment). There are three configuration
options for each limiter:

1. `period` specified in a human-readable form, see
https://www.postgresql.org/docs/current/datatype-datetime.html#DATATYPE-INTERVAL-INPUT
for all possible options. When the end of the period is reached, quota is reset
or increased
1. `initial_quota` is set at beginning of the period
1. `quota_increase` this value (if specified) is used to increase quota when period is reached

There are two basic use cases:

1. When quota needs to be reset specific value periodically (for example on
weekly on monthly basis), specify `initial_quota` to the required value
1. When quota needs to be increased by specific value periodically (for example
on daily basis), specify `quota_increase`

Technically it is possible to specify both `initial_quota` and
`quota_increase`. It means that at the end of time period the quota will be
*reset* to `initial_quota + quota_increase`.

Please note that any number of quota limiters can be configured. For example,
two user quota limiters can be set to:
- increase quota by 100,000 tokens each day
- reset quota to 10,000,000 tokens each month
"""

from abc import ABC, abstractmethod

from typing import Optional

import datetime
import sqlite3
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
        """Retrieve available quota for given user.

        Get the remaining quota for the specified subject.

        Parameters:
            subject_id (str): Identifier of the subject (user or service) whose quota to retrieve.

        Returns:
            available_quota (int): Number of quota units currently available for the subject.
        """

    @abstractmethod
    def revoke_quota(self) -> None:
        """Revoke quota for given user.

        Revoke the quota for the limiter's target subject by setting its available quota to zero.

        This operation removes or disables any remaining allowance so
        subsequent checks will report no available quota.
        """

    @abstractmethod
    def increase_quota(self) -> None:
        """Increase quota for given user.

        Increase the available quota for the limiter's subject according to its
        configured increase policy.

        Updates persistent storage to add the configured quota increment to the
        subject's stored available quota.
        """

    @abstractmethod
    def ensure_available_quota(self, subject_id: str = "") -> None:
        """Ensure that there's available quota left."""

    @abstractmethod
    def consume_tokens(
        self, input_tokens: int, output_tokens: int, subject_id: str = ""
    ) -> None:
        """Consume tokens by given user.

        Consume the specified input and output tokens from a subject's available quota.

        Parameters:
            input_tokens (int): Number of input tokens to deduct from the subject's quota.
            output_tokens (int): Number of output tokens to deduct from the subject's quota.
            subject_id (str): Identifier of the subject (user or service) whose
            quota will be reduced. If omitted, applies to the default subject.
        """

    @abstractmethod
    def __init__(self) -> None:
        """Initialize connection configuration(s).

        Create a QuotaLimiter instance and initialize database connection configuration attributes.

        Attributes:
            sqlite_connection_config (Optional[SQLiteDatabaseConfiguration]):
            SQLite connection configuration or `None` when not configured.
            postgres_connection_config
            (Optional[PostgreSQLDatabaseConfiguration]): PostgreSQL connection
            configuration or `None` when not configured.
        """
        self.sqlite_connection_config: Optional[SQLiteDatabaseConfiguration] = None
        self.postgres_connection_config: Optional[PostgreSQLDatabaseConfiguration] = (
            None
        )

    @abstractmethod
    def _initialize_tables(self) -> None:
        """Initialize tables and indexes.

        Create any database tables and indexes required by the quota limiter implementation.

        Implementations must ensure the database schema and indexes needed for
        storing and querying quota state exist; calling this method when the
        schema already exists should be safe (idempotent). Raise an exception
        on irrecoverable initialization failures.
        """

    # pylint: disable=W0201
    def connect(self) -> None:
        """Initialize connection to database.

        Establish the configured database connection, initialize required
        tables, and enable autocommit.

        If a PostgreSQL or SQLite configuration is present, a connection to
        that backend will be created, then _initialize_tables() will be called
        to prepare storage. If table initialization fails, the connection is
        closed and the original exception is propagated.
        """
        logger.info("Initializing connection to quota limiter database")
        if self.postgres_connection_config is not None:
            self.connection = connect_pg(self.postgres_connection_config)
        if self.sqlite_connection_config is not None:
            self.connection = connect_sqlite(self.sqlite_connection_config)
            # the default adapters and converters are deprecated as of Python
            # 3.12. Instead, we use the Adapter and converter recipes and
            # tailor them to our needs.
            sqlite3.register_adapter(
                datetime.datetime, lambda val: val.replace(tzinfo=None).isoformat()
            )

        try:
            self._initialize_tables()
        except Exception as e:
            self.connection.close()
            logger.exception("Error initializing quota limiter database:\n%s", e)
            raise

        self.connection.autocommit = True

    def connected(self) -> bool:
        """Check if connection to quota limiter database is alive.

        Determine whether the storage connection is alive.

        Returns:
            `true` if the connection is alive, `false` otherwise.
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
