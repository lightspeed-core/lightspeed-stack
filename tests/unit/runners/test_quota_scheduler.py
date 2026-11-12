"""Unit tests for the quota scheduler runner.

These tests cover the parts of the scheduler that need no database: the
statement selection per backend, the subject mapping, the early returns of
``quota_scheduler`` and the shape of the PostgreSQL statements. The renewal
itself, on a real SQLite database, is covered by
``tests/integration/test_quota_scheduler.py``.
"""

import sqlite3
from typing import Any

import pytest
from pydantic import SecretStr
from pytest_mock import MockerFixture

import constants
from models.config import (
    PostgreSQLDatabaseConfiguration,
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    QuotaSchedulerConfiguration,
    SQLiteDatabaseConfiguration,
)
from quota.sql import (
    CREATE_QUOTA_TABLE_PG,
    INCREASE_QUOTA_STATEMENT_PG,
    INCREASE_QUOTA_STATEMENT_SQLITE,
    INIT_QUOTA_PG,
    INIT_QUOTA_SQLITE,
    RESET_QUOTA_STATEMENT_PG,
    RESET_QUOTA_STATEMENT_SQLITE,
    SELECT_QUOTA_PG,
    SELECT_QUOTA_SQLITE,
    SET_AVAILABLE_QUOTA_PG,
    SET_AVAILABLE_QUOTA_SQLITE,
    UPDATE_AVAILABLE_QUOTA_PG,
    UPDATE_AVAILABLE_QUOTA_SQLITE,
)
from runners import quota_scheduler
from runners.quota_scheduler import (
    connect,
    connected,
    get_increase_quota_statement,
    get_reset_quota_statement,
    get_subject_id,
    increase_quota,
    init_tables,
    quota_revocation,
    reset_quota,
)

SCHEDULER_MODULE = "runners.quota_scheduler"

POSTGRES = PostgreSQLDatabaseConfiguration(  # pyright: ignore[reportCallIssue]
    db="quota",
    user="quota",
    password=SecretStr("secret"),
    host="localhost",
    port=5432,
)
SQLITE = SQLiteDatabaseConfiguration(db_path=":memory:")


def user_limiter(
    initial_quota: int = 100, quota_increase: int = 10, period: str = "1 day"
) -> QuotaLimiterConfiguration:
    """Build the configuration of one user limiter."""
    return QuotaLimiterConfiguration(
        type="user_limiter",
        name="user quota",
        initial_quota=initial_quota,
        quota_increase=quota_increase,
        period=period,
    )


# ==========================================
# Pure helpers
# ==========================================


@pytest.mark.parametrize(
    ("limiter_type", "expected"),
    [
        (constants.USER_QUOTA_LIMITER, "u"),
        (constants.CLUSTER_QUOTA_LIMITER, "c"),
        ("something_else", "?"),
    ],
)
def test_get_subject_id(limiter_type: str, expected: str) -> None:
    """A limiter type maps to the subject column of the quota table."""
    assert get_subject_id(limiter_type) == expected


@pytest.mark.parametrize(
    ("config", "expected_increase", "expected_reset"),
    [
        pytest.param(
            QuotaHandlersConfiguration(
                sqlite=SQLITE
            ),  # pyright: ignore[reportCallIssue]
            INCREASE_QUOTA_STATEMENT_SQLITE,
            RESET_QUOTA_STATEMENT_SQLITE,
            id="sqlite",
        ),
        pytest.param(
            QuotaHandlersConfiguration(
                postgres=POSTGRES
            ),  # pyright: ignore[reportCallIssue]
            INCREASE_QUOTA_STATEMENT_PG,
            RESET_QUOTA_STATEMENT_PG,
            id="postgres",
        ),
        pytest.param(
            QuotaHandlersConfiguration(
                sqlite=SQLITE, postgres=POSTGRES
            ),  # pyright: ignore[reportCallIssue]
            INCREASE_QUOTA_STATEMENT_SQLITE,
            RESET_QUOTA_STATEMENT_SQLITE,
            id="both_prefers_sqlite",
        ),
    ],
)
def test_statement_selection(
    config: QuotaHandlersConfiguration, expected_increase: str, expected_reset: str
) -> None:
    """The scheduler picks the statements of the configured backend."""
    assert get_increase_quota_statement(config) == expected_increase
    assert get_reset_quota_statement(config) == expected_reset


def test_connected_on_live_closed_and_missing_connection() -> None:
    """``connected`` answers for a live, a closed and a missing connection."""
    connection = sqlite3.connect(":memory:")
    assert connected(connection) is True
    connection.close()
    assert connected(connection) is False
    assert connected(None) is False


# ==========================================
# quota_scheduler early returns
# ==========================================


@pytest.mark.parametrize(
    "config",
    [
        pytest.param(
            QuotaHandlersConfiguration(),  # pyright: ignore[reportCallIssue]
            id="no_storage",
        ),
        pytest.param(
            QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
                limiters=[user_limiter()]
            ),
            id="limiters_without_storage",
        ),
        pytest.param(
            QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
                sqlite=SQLITE
            ),
            id="no_limiters",
        ),
    ],
)
def test_quota_scheduler_does_not_start_without_storage_or_limiters(
    config: QuotaHandlersConfiguration, mocker: MockerFixture
) -> None:
    """Without storage or limiters the scheduler returns without connecting."""
    connect_mock = mocker.patch(f"{SCHEDULER_MODULE}.connect")

    assert quota_scheduler.quota_scheduler(config) is False

    connect_mock.assert_not_called()


def test_quota_scheduler_gives_up_after_the_configured_reconnection_attempts(
    mocker: MockerFixture,
) -> None:
    """An unreachable database is retried the configured number of times, then skipped."""
    config = QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
        sqlite=SQLiteDatabaseConfiguration(db_path="/nonexistent/dir/quota.db"),
        limiters=[user_limiter()],
        scheduler=QuotaSchedulerConfiguration(
            period=1, database_reconnection_count=3, database_reconnection_delay=7
        ),
    )
    connect_sqlite = mocker.patch(
        f"{SCHEDULER_MODULE}.connect_sqlite",
        side_effect=sqlite3.OperationalError("unable to open database file"),
    )
    sleep = mocker.patch(f"{SCHEDULER_MODULE}.sleep")

    assert quota_scheduler.quota_scheduler(config) is False

    assert connect_sqlite.call_count == 3
    assert sleep.call_args_list == [mocker.call(7)] * 3


# ==========================================
# PostgreSQL: statement shape, with a mocked connection
# ==========================================

# No PostgreSQL service exists in CI or locally, so the PostgreSQL path is
# checked for shape only: the statements take the same parameters in the same
# order as the SQLite ones that the integration tests execute for real.


@pytest.mark.parametrize(
    ("pg_statement", "sqlite_statement"),
    [
        pytest.param(INCREASE_QUOTA_STATEMENT_PG, INCREASE_QUOTA_STATEMENT_SQLITE),
        pytest.param(RESET_QUOTA_STATEMENT_PG, RESET_QUOTA_STATEMENT_SQLITE),
        pytest.param(INIT_QUOTA_PG, INIT_QUOTA_SQLITE),
        pytest.param(SELECT_QUOTA_PG, SELECT_QUOTA_SQLITE),
        pytest.param(SET_AVAILABLE_QUOTA_PG, SET_AVAILABLE_QUOTA_SQLITE),
        pytest.param(UPDATE_AVAILABLE_QUOTA_PG, UPDATE_AVAILABLE_QUOTA_SQLITE),
    ],
    ids=["increase", "reset", "init", "select", "set_available", "update_available"],
)
def test_pg_and_sqlite_statements_take_the_same_parameters(
    pg_statement: str, sqlite_statement: str
) -> None:
    """Both backends are driven by one parameter tuple, so the counts must match."""
    assert pg_statement.count("%s") == sqlite_statement.count("?")


def _pg_connection(mocker: MockerFixture) -> Any:
    """Build a DB-API connection double that records what is executed on it."""
    connection = mocker.Mock()
    connection.cursor.return_value.rowcount = 1
    return connection


def test_increase_and_reset_execute_pg_statements_with_value_subject_period(
    mocker: MockerFixture,
) -> None:
    """The PostgreSQL statements get (value, subject, period), then a commit."""
    connection = _pg_connection(mocker)

    increase_quota(connection, INCREASE_QUOTA_STATEMENT_PG, "u", 10, "1 day")
    reset_quota(connection, RESET_QUOTA_STATEMENT_PG, "c", 100, "1 month")

    cursor = connection.cursor.return_value
    assert cursor.execute.call_args_list == [
        mocker.call(INCREASE_QUOTA_STATEMENT_PG, (10, "u", "1 day")),
        mocker.call(RESET_QUOTA_STATEMENT_PG, (100, "c", "1 month")),
    ]
    assert connection.commit.call_count == 2


def test_quota_revocation_runs_both_pg_statements_for_the_limiter_subject(
    mocker: MockerFixture,
) -> None:
    """With PostgreSQL configured, revocation issues the PG increase and reset.

    Which of the two runs first is not pinned: the order decides what a row
    with both values set ends up with (see the integration tests) and is
    being reported, not asserted.
    """
    config = QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
        postgres=POSTGRES,
        limiters=[user_limiter(initial_quota=100, quota_increase=10, period="1 day")],
    )
    connection = _pg_connection(mocker)

    quota_revocation(
        connection,
        config.limiters[0],
        get_increase_quota_statement(config),
        get_reset_quota_statement(config),
    )

    cursor = connection.cursor.return_value
    assert cursor.execute.call_count == 2
    cursor.execute.assert_any_call(INCREASE_QUOTA_STATEMENT_PG, (10, "u", "1 day"))
    cursor.execute.assert_any_call(RESET_QUOTA_STATEMENT_PG, (100, "u", "1 day"))


def test_init_tables_executes_the_create_statement_and_commits(
    mocker: MockerFixture,
) -> None:
    """Table creation runs the given statement once and commits."""
    connection = _pg_connection(mocker)

    init_tables(connection, CREATE_QUOTA_TABLE_PG)

    connection.cursor.return_value.execute.assert_called_once_with(
        CREATE_QUOTA_TABLE_PG
    )
    connection.commit.assert_called_once()


def test_connect_prefers_postgres_and_falls_back_to_sqlite(
    mocker: MockerFixture,
) -> None:
    """``connect`` opens PostgreSQL when configured, SQLite otherwise, nothing without both."""
    connect_pg = mocker.patch(f"{SCHEDULER_MODULE}.connect_pg")
    connect_sqlite = mocker.patch(f"{SCHEDULER_MODULE}.connect_sqlite")

    both = QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
        postgres=POSTGRES, sqlite=SQLITE
    )
    sqlite_only = QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
        sqlite=SQLITE
    )
    neither = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]

    assert connect(both) is connect_pg.return_value
    connect_pg.assert_called_once_with(POSTGRES)
    connect_sqlite.assert_not_called()

    assert connect(sqlite_only) is connect_sqlite.return_value
    connect_sqlite.assert_called_once_with(SQLITE)

    assert connect(neither) is None
