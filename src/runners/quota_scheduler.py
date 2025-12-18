"""User and cluster quota scheduler runner."""

from typing import Any, Optional
from threading import Thread
from time import sleep


import constants
from log import get_logger
from models.config import (
    Configuration,
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
)

from quota.connect_pg import connect_pg
from quota.connect_sqlite import connect_sqlite

from quota.sql import (
    CREATE_QUOTA_TABLE_PG,
    CREATE_QUOTA_TABLE_SQLITE,
    INCREASE_QUOTA_STATEMENT_PG,
    INCREASE_QUOTA_STATEMENT_SQLITE,
    RESET_QUOTA_STATEMENT_PG,
    RESET_QUOTA_STATEMENT_SQLITE,
)

logger = get_logger(__name__)


# pylint: disable=R0912
def quota_scheduler(config: QuotaHandlersConfiguration) -> bool:
    """
    Run the quota scheduler loop that applies configured quota limiters periodically.

    Parameters:
        config (QuotaHandlersConfiguration): Configuration containing storage
        settings (sqlite or postgres), a list of limiter configurations, and
        scheduler.period in seconds. If configuration is invalid or no
        storage/limiters are configured, the scheduler will not start.

    Returns:
        bool: `True` if the scheduler started (unreachable in normal execution
        because the function enters an infinite loop), `False` if validation
        failed or a database connection could not be established.
    """
    if config is None:
        logger.warning("Quota limiters are not configured, skipping")
        return False

    if config.sqlite is None and config.postgres is None:
        logger.warning("Storage for quota limiter is not set, skipping")
        return False

    if len(config.limiters) == 0:
        logger.warning("No limiters are setup, skipping")
        return False

    for _ in range(config.scheduler.database_reconnection_count):
        try:
            # try to connect to database
            connection = connect(config)
            # if connection is established, we are ok
            if connection is not None:
                break
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Can not connect to database, will try later: %s", e)
        sleep(config.scheduler.database_reconnection_delay)
    else:
        # if the connection cannot be established after specified count
        # attempts, give up
        logger.warning("Can not connect to database, skipping")
        return False

    create_quota_table: Optional[str] = None
    if config.postgres is not None:
        create_quota_table = CREATE_QUOTA_TABLE_PG
    elif config.sqlite is not None:
        create_quota_table = CREATE_QUOTA_TABLE_SQLITE

    if create_quota_table is not None:
        init_tables(connection, create_quota_table)

    period = config.scheduler.period

    increase_quota_statement = get_increase_quota_statement(config)
    reset_quota_statement = get_reset_quota_statement(config)

    logger.info(
        "Quota scheduler started in separated thread with period set to %d seconds",
        period,
    )

    while True:
        logger.info("Quota scheduler sync started")
        for limiter in config.limiters:
            try:
                if not connected(connection):
                    # the old connection might be closed to avoid resource leaks
                    try:
                        connection.close()
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass  # Connection already dead
                    connection = connect(config)
                    if connection is None:
                        logger.warning("Can not connect to database, skipping")
                        continue
                quota_revocation(
                    connection, limiter, increase_quota_statement, reset_quota_statement
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Quota revoke error: %s", e)
        logger.info("Quota scheduler sync finished")
        sleep(period)
    # unreachable code
    connection.close()
    return True


def connected(connection: Any) -> bool:
    """Check if DB is still connected.

    Parameters:
        connection: Database connection object to verify.

    Returns:
        bool: True if connection is active, False otherwise.
    """
    if connection is None:
        logger.warning("Not connected, need to reconnect later")
        return False
    try:
        # for compatibility with SQLite it is not possible to use context manager there
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        logger.info("Connection to storage is ok")
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Disconnected from storage: %s", e)
        return False


def get_increase_quota_statement(config: QuotaHandlersConfiguration) -> str:
    """
    Select the SQL statement used to increase stored quota according to the database backend.

    Parameters:
        config (QuotaHandlersConfiguration): Configuration that indicates which
        storage backend (SQLite or PostgreSQL) is in use.

    Returns:
        str: SQL statement to perform a quota increase appropriate for the configured backend.
    """
    if config.sqlite is not None:
        return INCREASE_QUOTA_STATEMENT_SQLITE
    return INCREASE_QUOTA_STATEMENT_PG


def get_reset_quota_statement(config: QuotaHandlersConfiguration) -> str:
    """
    Return the SQL statement used to reset quota records for the configured database backend.

    Returns:
        str: The SQLite reset SQL statement when `config.sqlite` is set,
        otherwise the PostgreSQL reset SQL statement.
    """
    if config.sqlite is not None:
        return RESET_QUOTA_STATEMENT_SQLITE
    return RESET_QUOTA_STATEMENT_PG


def quota_revocation(
    connection: Any,
    quota_limiter: QuotaLimiterConfiguration,
    increase_quota_statement: str,
    reset_quota_statement: str,
) -> None:
    """
    Apply configured quota updates for a quota limiter using the provided database connection.

    Processes the given limiter: increases quota when `quota_increase` is set
    and resets initial quota when `initial_quota` is greater than zero, using
    the supplied SQL statements.

    Parameters:
        quota_limiter (QuotaLimiterConfiguration): Limiter configuration to process.
        increase_quota_statement (str): SQL statement used to increment quota values.
        reset_quota_statement (str): SQL statement used to reset quota values.

    Raises:
        ValueError: If the limiter's `type` or `period` is not set.
    """
    logger.info(
        "Quota revocation mechanism for limiter '%s' of type '%s'",
        quota_limiter.name,
        quota_limiter.type,
    )

    if quota_limiter.type is None:
        raise ValueError("Limiter type not set, skipping revocation")

    if quota_limiter.period is None:
        raise ValueError("Limiter period not set, skipping revocation")

    subject_id = get_subject_id(quota_limiter.type)

    if quota_limiter.quota_increase is not None:
        increase_quota(
            connection,
            increase_quota_statement,
            subject_id,
            quota_limiter.quota_increase,
            quota_limiter.period,
        )

    if quota_limiter.initial_quota is not None and quota_limiter.initial_quota > 0:
        reset_quota(
            connection,
            reset_quota_statement,
            subject_id,
            quota_limiter.initial_quota,
            quota_limiter.period,
        )


def increase_quota(
    connection: Any,
    update_statement: str,
    subject_id: str,
    increase_by: int,
    period: str,
) -> None:
    """
    Increase the stored quota for a subject by a specified amount for a given period.

    Executes the provided SQL update statement on the given database connection
    to increment the quota value for the specified subject and period.

    Parameters:
        connection (Any): Database connection object (Postgres or SQLite) to
                          execute the statement on.
        update_statement (str): SQL update statement that accepts parameters
                                (increase_by, subject_id, period).
        subject_id (str): Identifier for the subject whose quota is modified
                          (e.g., "u" for user, "c" for cluster).
        increase_by (int): Amount to add to the subject's quota.
        period (str): Quota period identifier used to scope the update.
    """
    logger.info(
        "Increasing quota for subject '%s' by %d when period %s is reached",
        subject_id,
        increase_by,
        period,
    )

    # for compatibility with SQLite it is not possible to use context manager
    # there
    cursor = connection.cursor()
    cursor.execute(
        update_statement,
        (
            increase_by,
            subject_id,
            period,
        ),
    )
    cursor.close()
    connection.commit()
    logger.info("Changed %d rows in database", cursor.rowcount)


def reset_quota(
    connection: Any,
    update_statement: str,
    subject_id: str,
    reset_to: int,
    period: str,
) -> None:
    """
    Set the stored quota for a subject to a specific value for the given period.

    Parameters:
        connection (Any): Database connection object used to execute the update.
        update_statement (str): SQL statement that sets the quota value
                                (expects parameters: new_value, subject_id, period).
        subject_id (str): Identifier for the quota subject (e.g., "u" for user, "c" for cluster).
        reset_to (int): Value to set the subject's quota to.
        period (str): Period identifier for which the quota is being set.
    """
    logger.info(
        "Resetting quota for subject '%s' to %d when period %s is reached",
        subject_id,
        reset_to,
        period,
    )

    # for compatibility with SQLite it is not possible to use context manager
    # there
    cursor = connection.cursor()
    cursor.execute(
        update_statement,
        (
            reset_to,
            subject_id,
            period,
        ),
    )
    cursor.close()
    connection.commit()
    logger.info("Changed %d rows in database", cursor.rowcount)


def get_subject_id(limiter_type: str) -> str:
    """
    Map a quota limiter type to its subject identifier.

    Parameters:
        limiter_type (str): Quota limiter type constant (e.g., user or cluster).

    Returns:
        str: `"u"` for a user limiter, `"c"` for a cluster limiter, or `"?"` if the type
             is not recognized.
    """
    match limiter_type:
        case constants.USER_QUOTA_LIMITER:
            return "u"
        case constants.CLUSTER_QUOTA_LIMITER:
            return "c"
        case _:
            return "?"


def connect(config: QuotaHandlersConfiguration) -> Any:
    """
    Create and return a database connection for quota handlers based on the configured backend.

    Parameters:
        config (QuotaHandlersConfiguration): Configuration containing
        `postgres` or `sqlite` connection settings.

    Returns:
        A database connection suitable for quota operations, or `None` if
        neither Postgres nor SQLite is configured.
    """
    logger.info("Initializing connection to quota limiter database")
    if config.postgres is not None:
        return connect_pg(config.postgres)
    if config.sqlite is not None:
        return connect_sqlite(config.sqlite)
    return None


def init_tables(connection: Any, create_quota_table: str) -> None:
    """
    Create the quota table required by the quota limiter on the provided database connection.

    Parameters:
        connection (Any): A DB-API compatible connection on which the quota
                          table(s) will be created; changes are committed before returning.
        create_quota_table (str): Command used to create table with quota.
    """
    logger.info("Initializing tables for quota limiter")
    cursor = connection.cursor()
    cursor.execute(create_quota_table)
    cursor.close()
    connection.commit()


def start_quota_scheduler(configuration: Configuration) -> None:
    """
    Start the quota scheduler in a daemon thread using the provided configuration.

    Parameters:
        configuration (Configuration): Global configuration whose `quota_handlers`
                                       attribute is passed to the scheduler thread.
    """
    logger.info("Starting quota scheduler")
    thread = Thread(
        target=quota_scheduler,
        daemon=True,
        args=(configuration.quota_handlers,),
    )
    thread.start()
