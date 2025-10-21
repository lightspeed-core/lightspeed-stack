"""Simple quota limiter where quota can be revoked."""

from datetime import datetime

from models.config import QuotaHandlersConfiguration
from log import get_logger
from utils.connection_decorator import connection
from quota.quota_exceed_error import QuotaExceedError
from quota.quota_limiter import QuotaLimiter
from quota.sql import (
    CREATE_QUOTA_TABLE,
    UPDATE_AVAILABLE_QUOTA_PG,
    SELECT_QUOTA_PG,
    SET_AVAILABLE_QUOTA_PG,
    INIT_QUOTA_PG,
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
        """Initialize quota limiter."""
        self.subject_type = subject_type
        self.initial_quota = initial_quota
        self.increase_by = increase_by
        self.sqlite_connection_config = configuration.sqlite
        self.postgres_connection_config = configuration.postgres

    @connection
    def available_quota(self, subject_id: str = "") -> int:
        """Retrieve available quota for given subject."""
        if self.subject_type == "c":
            subject_id = ""
        with self.connection.cursor() as cursor:
            cursor.execute(
                SELECT_QUOTA_PG,
                (subject_id, self.subject_type),
            )
            value = cursor.fetchone()
            if value is None:
                self._init_quota(subject_id)
                return self.initial_quota
            return value[0]

    @connection
    def revoke_quota(self, subject_id: str = "") -> None:
        """Revoke quota for given subject."""
        if self.subject_type == "c":
            subject_id = ""
        # timestamp to be used
        revoked_at = datetime.now()

        with self.connection.cursor() as cursor:
            cursor.execute(
                SET_AVAILABLE_QUOTA_PG,
                (self.initial_quota, revoked_at, subject_id, self.subject_type),
            )
            self.connection.commit()

    @connection
    def increase_quota(self, subject_id: str = "") -> None:
        """Increase quota for given subject."""
        if self.subject_type == "c":
            subject_id = ""
        # timestamp to be used
        updated_at = datetime.now()

        with self.connection.cursor() as cursor:
            cursor.execute(
                UPDATE_AVAILABLE_QUOTA_PG,
                (self.increase_by, updated_at, subject_id, self.subject_type),
            )
            self.connection.commit()

    def ensure_available_quota(self, subject_id: str = "") -> None:
        """Ensure that there's avaiable quota left."""
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
        """Consume tokens by given subject."""
        if self.subject_type == "c":
            subject_id = ""
        logger.info(
            "Consuming %d input and %d output tokens for subject %s",
            input_tokens,
            output_tokens,
            subject_id,
        )
        to_be_consumed = input_tokens + output_tokens

        with self.connection.cursor() as cursor:
            # timestamp to be used
            updated_at = datetime.now()

            cursor.execute(
                UPDATE_AVAILABLE_QUOTA_PG,
                (-to_be_consumed, updated_at, subject_id, self.subject_type),
            )
            self.connection.commit()

    def _initialize_tables(self) -> None:
        """Initialize tables used by quota limiter."""
        logger.info("Initializing tables for quota limiter")
        cursor = self.connection.cursor()
        cursor.execute(CREATE_QUOTA_TABLE)
        cursor.close()
        self.connection.commit()

    def _init_quota(self, subject_id: str = "") -> None:
        """Initialize quota for given ID."""
        # timestamp to be used
        revoked_at = datetime.now()

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
