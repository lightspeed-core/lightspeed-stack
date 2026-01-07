"""Simple quota limiter where quota can be revoked."""

from datetime import datetime

from models.config import QuotaHandlersConfiguration
from log import get_logger
from utils.connection_decorator import connection
from quota.quota_exceed_error import QuotaExceedError
from quota.quota_limiter import QuotaLimiter
from quota.sql import (
    CREATE_QUOTA_TABLE_PG,
    CREATE_QUOTA_TABLE_SQLITE,
    UPDATE_AVAILABLE_QUOTA_PG,
    UPDATE_AVAILABLE_QUOTA_SQLITE,
    SELECT_QUOTA_PG,
    SELECT_QUOTA_SQLITE,
    SET_AVAILABLE_QUOTA_PG,
    SET_AVAILABLE_QUOTA_SQLITE,
    INIT_QUOTA_PG,
    INIT_QUOTA_SQLITE,
)

logger = get_logger(__name__)


class RevokableQuotaLimiter(QuotaLimiter):
    """Simple quota limiter where quota can be revoked."""

    def __init__(
        self,
        configuration: QuotaHandlersConfiguration,
        initial_quota: int,
        increase_by: int,
        subject_type: str,
    ) -> None:
        """Initialize quota limiter.

        Create a revokable quota limiter configured for a specific subject type.

        Parameters:
            configuration (QuotaHandlersConfiguration): Configuration object
            containing `sqlite` and `postgres` connection settings.
            initial_quota (int): The starting quota value assigned when a
            subject's quota is initialized or revoked.
            increase_by (int): Number of quota units to add when increasing a subject's quota.
            subject_type (str): Identifier for the kind of subject the limiter
            applies to (e.g., user, customer); when set to "c" the limiter
            treats subject IDs as empty strings.
        """
        self.subject_type = subject_type
        self.initial_quota = initial_quota
        self.increase_by = increase_by
        self.sqlite_connection_config = configuration.sqlite
        self.postgres_connection_config = configuration.postgres

    @connection
    def available_quota(self, subject_id: str = "") -> int:
        """Retrieve available quota for given subject.

        Get the available quota for a subject.

        Parameters:
            subject_id (str): Subject identifier. For limiters with
            subject_type "c", this value is ignored and treated as an empty
            string.

        Returns:
            int: The available quota for the subject. Returns 0 if no backend is configured.
        """
        if self.subject_type == "c":
            subject_id = ""
        if self.sqlite_connection_config is not None:
            return self._read_available_quota(SELECT_QUOTA_SQLITE, subject_id)
        if self.postgres_connection_config is not None:
            return self._read_available_quota(SELECT_QUOTA_PG, subject_id)
        # default value is used only if quota limiter database is not setup
        return 0

    def _read_available_quota(self, query_statement: str, subject_id: str) -> int:
        """Read available quota from selected database.

        Fetches the available quota for a subject from the database.

        If no quota record exists for the given subject, initializes the quota
        and returns the limiter's initial quota.

        Parameters:
            query_statement (str): SQL statement used to select the quota.
            subject_id (str): Identifier of the subject whose quota is requested.

        Returns:
            int: The available quota for the subject; `initial_quota` if a new
                 record was initialized.
        """
        # it is not possible to use context manager there, because SQLite does
        # not support it
        cursor = self.connection.cursor()
        cursor.execute(
            query_statement,
            (subject_id, self.subject_type),
        )
        value = cursor.fetchone()
        if value is None:
            self._init_quota(subject_id)
            return self.initial_quota
        cursor.close()
        return value[0]

    @connection
    def revoke_quota(self, subject_id: str = "") -> None:
        """Revoke quota for given subject.

        Revoke a subject's quota and record the revocation timestamp in the configured backend.

        Parameters:
                subject_id (str): Identifier of the subject whose quota will be
                revoked. If the limiter's `subject_type` is `"c"`, this value
                is ignored and treated as an empty string.
        """
        if self.subject_type == "c":
            subject_id = ""

        if self.postgres_connection_config is not None:
            self._revoke_quota(SET_AVAILABLE_QUOTA_PG, subject_id)
            return
        if self.sqlite_connection_config is not None:
            self._revoke_quota(SET_AVAILABLE_QUOTA_SQLITE, subject_id)
            return

    def _revoke_quota(self, set_statement: str, subject_id: str) -> None:
        """Revoke quota in given database.

        Set the subject's available quota back to the configured initial quota
        and record the revocation timestamp.

        Parameters:
            set_statement (str): SQL statement that updates the available quota
                                 and `revoked_at` for a subject.
            subject_id (str): Identifier of the subject whose quota will be
                              revoked.
        """
        # timestamp to be used
        revoked_at = datetime.now()

        cursor = self.connection.cursor()
        cursor.execute(
            set_statement,
            (self.initial_quota, revoked_at, subject_id, self.subject_type),
        )
        self.connection.commit()
        cursor.close()

    @connection
    def increase_quota(self, subject_id: str = "") -> None:
        """Increase quota for given subject.

        Increase the available quota for a subject by the limiter's configured increment.

        Parameters:
            subject_id (str): Identifier of the subject whose quota will be
            increased. When the limiter's `subject_type` is `"c"`, this value
            is normalized to the empty string and treated as a
            global/customer-level entry.
        """
        if self.subject_type == "c":
            subject_id = ""

        if self.postgres_connection_config is not None:
            self._increase_quota(UPDATE_AVAILABLE_QUOTA_PG, subject_id)
            return

        if self.sqlite_connection_config is not None:
            self._increase_quota(UPDATE_AVAILABLE_QUOTA_SQLITE, subject_id)
            return

    def _increase_quota(self, set_statement: str, subject_id: str) -> None:
        """Increase quota in given database.

        Increase the stored quota for a subject by the configured increment and
        record the update timestamp.

        Executes the provided SQL statement with parameters (increase amount,
        update timestamp, subject_id, subject_type) and commits the
        transaction.

        Parameters:
            set_statement (str): SQL statement that increments the available quota for a subject.
            subject_id (str): Identifier of the subject whose quota will be increased.
        """
        # timestamp to be used
        updated_at = datetime.now()

        cursor = self.connection.cursor()
        cursor.execute(
            set_statement,
            (self.increase_by, updated_at, subject_id, self.subject_type),
        )
        self.connection.commit()

    def ensure_available_quota(self, subject_id: str = "") -> None:
        """Ensure that there's available quota left.

        Ensure the subject has available quota; raises if quota is exhausted.

        Parameters:
                subject_id (str): Identifier of the subject to check. If this
                limiter's `subject_type` is `"c"`, the value is ignored and
                treated as an empty string.

        Raises:
                QuotaExceedError: If the available quota for the subject is
                less than or equal to zero.
        """
        if self.subject_type == "c":
            subject_id = ""
        available = self.available_quota(subject_id)
        logger.info("Available quota for subject %s is %d", subject_id, available)
        # check if ID still have available tokens to be consumed
        if available <= 0:
            e = QuotaExceedError(subject_id, self.subject_type, available)
            logger.exception("Quota exceed: %s", e)
            raise e

    @connection
    def consume_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        subject_id: str = "",
    ) -> None:
        """
        Consume tokens from a subject's available quota.

        Deducts the sum of `input_tokens` and `output_tokens` from the
        subject's stored quota and persists the update to the configured
        database backend. For subject type "c", the `subject_id` is normalized
        to an empty string before performing the operation.

        Parameters:
            input_tokens (int): Number of input tokens to consume.
            output_tokens (int): Number of output tokens to consume.
            subject_id (str): Identifier of the subject whose quota will be consumed.
        """
        if self.subject_type == "c":
            subject_id = ""
        logger.info(
            "Consuming %d input and %d output tokens for subject %s",
            input_tokens,
            output_tokens,
            subject_id,
        )

        if self.sqlite_connection_config is not None:
            self._consume_tokens(
                UPDATE_AVAILABLE_QUOTA_SQLITE, input_tokens, output_tokens, subject_id
            )
            return

        if self.postgres_connection_config is not None:
            self._consume_tokens(
                UPDATE_AVAILABLE_QUOTA_PG, input_tokens, output_tokens, subject_id
            )
            return

    def _consume_tokens(
        self,
        update_statement: str,
        input_tokens: int,
        output_tokens: int,
        subject_id: str,
    ) -> None:
        """Consume tokens from selected database.

        Deduct the sum of input and output tokens from the subject's available
        quota and persist the update.

        Parameters:
            update_statement (str): SQL statement used to apply the quota change.
            input_tokens (int): Number of input tokens to consume.
            output_tokens (int): Number of output tokens to consume.
            subject_id (str): Identifier of the subject whose quota will be updated.

        Notes:
            The function updates the quota by -(input_tokens + output_tokens)
            and stamps the record with the current datetime, then commits the
            change.
        """
        # timestamp to be used
        updated_at = datetime.now()

        to_be_consumed = input_tokens + output_tokens

        cursor = self.connection.cursor()
        cursor.execute(
            update_statement,
            (-to_be_consumed, updated_at, subject_id, self.subject_type),
        )
        self.connection.commit()
        cursor.close()

    def _initialize_tables(self) -> None:
        """Initialize tables used by quota limiter.

        Create quota-related tables in the configured database and commit the change.

        This ensures the database schema required by the quota limiter exists.
        """
        logger.info("Initializing tables for quota limiter")
        cursor = self.connection.cursor()
        if self.sqlite_connection_config is not None:
            cursor.execute(CREATE_QUOTA_TABLE_SQLITE)
        elif self.postgres_connection_config is not None:
            cursor.execute(CREATE_QUOTA_TABLE_PG)
        cursor.close()
        self.connection.commit()

    def _init_quota(self, subject_id: str = "") -> None:
        """Initialize quota for given ID.

        Create a quota record for the given subject and set its initial values.

        Inserts a quota row for `subject_id` with both available and total
        quota set to the limiter's configured initial value and stamps the
        revocation timestamp. The operation writes to whichever backend(s) are
        configured (SQLite and/or PostgreSQL) and commits the transaction.

        Parameters:
            subject_id (str): Identifier of the subject whose quota to
            initialize. Defaults to empty string.
        """
        # timestamp to be used
        revoked_at = datetime.now()

        if self.sqlite_connection_config is not None:
            cursor = self.connection.cursor()
            cursor.execute(
                INIT_QUOTA_SQLITE,
                (
                    subject_id,
                    self.subject_type,
                    self.initial_quota,
                    self.initial_quota,
                    revoked_at,
                ),
            )
            cursor.close()
            self.connection.commit()
        if self.postgres_connection_config is not None:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    INIT_QUOTA_PG,
                    (
                        subject_id,
                        self.subject_type,
                        self.initial_quota,
                        self.initial_quota,
                        revoked_at,
                    ),
                )
                self.connection.commit()
