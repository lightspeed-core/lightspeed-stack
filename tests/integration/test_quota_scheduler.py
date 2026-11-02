"""Integration tests for the periodic quota renewal (LCORE-4610).

The quota scheduler renews the balances the limiters keep in the quota
database: once a limiter's period has elapsed for a row, the row is reset to
``initial_quota`` and/or increased by ``quota_increase``, and its
``revoked_at`` stamp moves so that the next renewal waits for a whole period
again (LCORE-4606).

Everything here runs on a real SQLite file: the rows are created and consumed
through the real limiters, and the renewal runs the scheduler's own
statements over the scheduler's own connection. Time is not waited for; the
``revoked_at`` stamp of a row is moved into the past instead, in both formats
found in a real database (the limiter writes an ISO ``T`` timestamp, the
scheduler rewrites it with SQLite's ``datetime('now')``). The stamp the
limiter really writes is checked once, as SQLite reads it.
"""

import sqlite3
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from models.config import QuotaHandlersConfiguration, QuotaLimiterConfiguration
from quota.cluster_quota_limiter import ClusterQuotaLimiter
from quota.quota_limiter import QuotaLimiter
from quota.sql import CREATE_QUOTA_TABLE_SQLITE
from quota.user_quota_limiter import UserQuotaLimiter
from runners import quota_scheduler
from runners.quota_scheduler import connect
from tests.integration._quota_helpers import (
    CLUSTER,
    CLUSTER_SUBJECT,
    USER_SUBJECT,
    back_date,
    handlers,
    limiter_config,
    read_available,
    read_revoked_at,
    read_row_age_seconds,
    renew,
    spend,
    table_exists,
)

ALICE, BOB = "alice", "bob"

ELAPSED = "2 seconds"
NOT_ELAPSED = "10 seconds"
PAST_NOT_ELAPSED = 11
"""Back-dating by this much puts a row past a ``NOT_ELAPSED`` period."""


class StopLoop(Exception):
    """Raised from the patched ``sleep`` to leave the scheduler's endless loop."""


@pytest.fixture(name="quota_db")
def quota_db_fixture(tmp_path: Path) -> Path:
    """Path of the SQLite quota database of the test."""
    return tmp_path / "quota.db"


@pytest.fixture(name="make_limiter")
def make_limiter_fixture() -> Generator[Callable[..., QuotaLimiter], None, None]:
    """Create real limiters on a configuration and close them after the test."""
    created: list[QuotaLimiter] = []

    def _make(
        config: QuotaHandlersConfiguration, limiter: QuotaLimiterConfiguration
    ) -> QuotaLimiter:
        """Create the limiter object a configuration entry describes."""
        cls = (
            UserQuotaLimiter if limiter.type == "user_limiter" else ClusterQuotaLimiter
        )
        instance = cls(config, limiter.initial_quota, limiter.quota_increase)
        created.append(instance)
        return instance

    yield _make
    for instance in created:
        instance.connection.close()


@pytest.fixture(name="scheduler_connection")
def scheduler_connection_fixture() -> Generator[Callable[..., Any], None, None]:
    """Open the scheduler's own connection to a configuration's database."""
    connections: list[Any] = []

    def _open(config: QuotaHandlersConfiguration) -> Any:
        """Connect the way the scheduler does."""
        connection = connect(config)
        connections.append(connection)
        return connection

    yield _open
    for connection in connections:
        connection.close()


# ==========================================
# Renewal statements
# ==========================================

RESET = limiter_config(
    "user_limiter", initial_quota=100, quota_increase=0, period=ELAPSED
)
INCREASE = limiter_config(
    "user_limiter", initial_quota=0, quota_increase=50, period=ELAPSED
)
CLUSTER_RESET = limiter_config(
    "cluster_limiter", initial_quota=1000, quota_increase=0, period=ELAPSED
)


def with_period(
    limiter: QuotaLimiterConfiguration, period: str
) -> QuotaLimiterConfiguration:
    """Return the same limiter with another period."""
    return limiter.model_copy(update={"period": period})


@pytest.mark.parametrize(
    ("limiter", "renewed_balance"),
    [
        pytest.param(RESET, 100, id="reset_to_initial_quota"),
        pytest.param(INCREASE, -30 + 50, id="increase_by_quota_increase"),
    ],
)
@pytest.mark.parametrize(
    ("period", "elapsed"),
    [
        pytest.param(ELAPSED, True, id="period_elapsed"),
        pytest.param(NOT_ELAPSED, False, id="period_not_elapsed"),
    ],
)
def test_renewal_applies_only_once_the_period_elapsed(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    limiter: QuotaLimiterConfiguration,
    renewed_balance: int,
    period: str,
    elapsed: bool,
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    scheduler_connection: Callable[..., Any],
) -> None:
    """A consumed balance is renewed when, and only when, its period has elapsed."""
    config = handlers(quota_db, with_period(limiter, period))
    spend(make_limiter(config, config.limiters[0]), 30, ALICE)
    consumed_balance = read_available(quota_db, ALICE, USER_SUBJECT)
    assert consumed_balance == limiter.initial_quota - 30
    back_date(quota_db)

    renew(scheduler_connection(config), config)

    expected = renewed_balance if elapsed else consumed_balance
    assert read_available(quota_db, ALICE, USER_SUBJECT) == expected


@pytest.mark.parametrize(
    ("limiter", "renewed", "spent", "renewed_again"),
    [
        pytest.param(RESET, 100, 90, 100, id="reset"),
        pytest.param(INCREASE, 20, 10, 60, id="increase"),
    ],
)
def test_renewal_happens_once_per_period(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    limiter: QuotaLimiterConfiguration,
    renewed: int,
    spent: int,
    renewed_again: int,
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    scheduler_connection: Callable[..., Any],
) -> None:
    """A renewal moves the stamp, so the next sync waits for a whole period again.

    Both statements must move it. Before LCORE-4606 a row written by the
    scheduler itself was renewed on every tick, which turned any
    ``quota_increase`` into an unlimited quota. The last renewal works on the
    stamp the scheduler wrote, in SQLite's own ``datetime('now')`` text. The
    period is ten seconds so that a slow runner can not let it elapse between
    the first and the second renewal.
    """
    config = handlers(quota_db, with_period(limiter, NOT_ELAPSED))
    alice = make_limiter(config, config.limiters[0])
    connection = scheduler_connection(config)
    spend(alice, 30, ALICE)
    back_date(quota_db, seconds=PAST_NOT_ELAPSED)

    renew(connection, config)
    assert read_available(quota_db, ALICE, USER_SUBJECT) == renewed
    stamped_at = read_revoked_at(quota_db, ALICE, USER_SUBJECT)

    spend(alice, 10, ALICE)
    renew(connection, config)
    assert (
        read_available(quota_db, ALICE, USER_SUBJECT) == spent
    ), "must not renew twice in one period"
    assert read_revoked_at(quota_db, ALICE, USER_SUBJECT) == stamped_at

    back_date(quota_db, seconds=PAST_NOT_ELAPSED, style="scheduler")
    renew(connection, config)
    assert read_available(quota_db, ALICE, USER_SUBJECT) == renewed_again


@pytest.mark.parametrize(
    ("limiter", "row_id", "subject"),
    [
        pytest.param(RESET, ALICE, USER_SUBJECT, id="user"),
        pytest.param(CLUSTER_RESET, CLUSTER, CLUSTER_SUBJECT, id="cluster"),
    ],
)
def test_the_limiter_stamps_a_new_row_with_the_current_time_as_sqlite_reads_it(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    limiter: QuotaLimiterConfiguration,
    row_id: str,
    subject: str,
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    scheduler_connection: Callable[..., Any],
) -> None:
    """A row's period starts when the limiter creates it, in a format SQLite parses.

    This is the limiter's half of LCORE-4606: the renewal statements read
    ``revoked_at`` through ``datetime()``, which yields NULL (and never
    matches) for a missing stamp or one in a text it does not understand.
    The stamp is checked as SQLite computes it, not as Python would.
    """
    config = handlers(quota_db, with_period(limiter, NOT_ELAPSED))
    spend(make_limiter(config, config.limiters[0]), 30, row_id)
    consumed_balance = limiter.initial_quota - 30
    connection = scheduler_connection(config)

    age = read_row_age_seconds(quota_db, row_id, subject)
    assert age is not None, "SQLite can not read the stamp the limiter wrote"
    assert 0 <= age < 5, f"the row should have been stamped just now, not {age}s ago"

    renew(connection, config)
    assert read_available(quota_db, row_id, subject) == consumed_balance

    back_date(quota_db, seconds=PAST_NOT_ELAPSED)
    renew(connection, config)
    assert read_available(quota_db, row_id, subject) == limiter.initial_quota


@pytest.mark.parametrize(
    ("limiter", "expected_calls"),
    [
        pytest.param(RESET, {"reset_quota"}, id="zero_increase_skips_increase"),
        pytest.param(INCREASE, {"increase_quota"}, id="zero_initial_skips_reset"),
    ],
)
def test_the_statement_of_a_zero_value_is_not_executed(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    limiter: QuotaLimiterConfiguration,
    expected_calls: set[str],
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    scheduler_connection: Callable[..., Any],
    mocker: MockerFixture,
) -> None:
    """A zero increase or a zero initial quota runs no statement at all (LCORE-4606).

    Running the statement anyway stamped ``revoked_at`` without changing the
    balance, which kept the other statement from ever matching the row. The
    balance shows that for a zero increase (the reset after it then applies,
    see ``test_renewal_applies_only_once_the_period_elapsed``) but not for a
    zero initial quota, since the reset runs second; hence the spies.
    """
    config = handlers(quota_db, limiter)
    spend(make_limiter(config, limiter), 30, ALICE)
    back_date(quota_db)
    spies = {
        name: mocker.spy(quota_scheduler, name)
        for name in ("increase_quota", "reset_quota")
    }

    renew(scheduler_connection(config), config)

    assert {name for name, spy in spies.items() if spy.called} == expected_calls


@pytest.mark.xfail(
    strict=True,
    reason=(
        "the increase runs first and stamps revoked_at, so the reset of the "
        "same tick no longer matches: the balance becomes 70 + 50 = 120 "
        "instead of the 100 + 50 the quota_limiter module documents; "
        "reported with LCORE-4610, to be fixed under its own ticket"
    ),
)
def test_initial_quota_and_increase_together_reset_to_their_sum(
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    scheduler_connection: Callable[..., Any],
) -> None:
    """With both values set, an elapsed period resets to ``initial_quota + quota_increase``."""
    both = limiter_config(
        "user_limiter", initial_quota=100, quota_increase=50, period=ELAPSED
    )
    config = handlers(quota_db, both)
    spend(make_limiter(config, both), 30, ALICE)
    back_date(quota_db)

    renew(scheduler_connection(config), config)

    assert read_available(quota_db, ALICE, USER_SUBJECT) == 100 + 50


def test_renewal_touches_only_the_rows_of_its_own_subject(
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    scheduler_connection: Callable[..., Any],
) -> None:
    """A cluster renewal leaves user rows alone and vice versa; all rows of a subject renew."""
    config = handlers(quota_db, RESET, CLUSTER_RESET)
    users = make_limiter(config, RESET)
    spend(users, 30, ALICE)
    spend(users, 40, BOB)
    spend(make_limiter(config, CLUSTER_RESET), 500)
    back_date(quota_db)
    connection = scheduler_connection(config)

    renew(connection, handlers(quota_db, CLUSTER_RESET))
    assert read_available(quota_db, CLUSTER, CLUSTER_SUBJECT) == 1000
    assert read_available(quota_db, ALICE, USER_SUBJECT) == 70
    assert read_available(quota_db, BOB, USER_SUBJECT) == 60

    renew(connection, handlers(quota_db, RESET))
    assert read_available(quota_db, ALICE, USER_SUBJECT) == 100
    assert read_available(quota_db, BOB, USER_SUBJECT) == 100
    assert read_available(quota_db, CLUSTER, CLUSTER_SUBJECT) == 1000


# ==========================================
# The scheduler loop
# ==========================================


def test_scheduler_loop_renews_and_then_sleeps_for_its_period(
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    mocker: MockerFixture,
) -> None:
    """One pass of ``quota_scheduler``: connect, create the table, renew, sleep."""
    config = handlers(quota_db, RESET, scheduler_period=5)
    spend(make_limiter(config, RESET), 30, ALICE)
    back_date(quota_db)
    sleep = mocker.patch("runners.quota_scheduler.sleep", side_effect=StopLoop)

    with pytest.raises(StopLoop):
        quota_scheduler.quota_scheduler(config)

    assert read_available(quota_db, ALICE, USER_SUBJECT) == 100
    sleep.assert_called_once_with(5)


def test_scheduler_loop_creates_the_quota_table_on_an_empty_database(
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    mocker: MockerFixture,
) -> None:
    """On a database no limiter has opened yet, the scheduler creates the table itself.

    In the deployed service the scheduler thread starts before the first
    request builds the limiters, so on a fresh deployment it is the one that
    must create ``quota_limits``; its first ticks would otherwise fail on a
    missing table, silently, forever.
    """
    config = handlers(quota_db, RESET)
    init_tables = mocker.spy(quota_scheduler, "init_tables")
    mocker.patch("runners.quota_scheduler.sleep", side_effect=StopLoop)
    assert not quota_db.exists()

    with pytest.raises(StopLoop):
        quota_scheduler.quota_scheduler(config)

    assert table_exists(quota_db, "quota_limits")
    init_tables.assert_called_once_with(mocker.ANY, CREATE_QUOTA_TABLE_SQLITE)
    spend(make_limiter(config, RESET), 30, ALICE)
    assert read_available(quota_db, ALICE, USER_SUBJECT) == 70


def test_scheduler_loop_survives_a_failing_limiter_and_renews_the_next(
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    mocker: MockerFixture,
) -> None:
    """A database error on one limiter is logged; the others are still renewed.

    This is what keeps the scheduler thread alive after a transient error,
    such as SQLite's ``database is locked``.
    """
    config = handlers(quota_db, RESET, CLUSTER_RESET)
    spend(make_limiter(config, RESET), 30, ALICE)
    spend(make_limiter(config, CLUSTER_RESET), 500)
    back_date(quota_db)
    real_revocation = quota_scheduler.quota_revocation
    revocation = mocker.patch("runners.quota_scheduler.quota_revocation")

    def failing_once(*args: Any, **kwargs: Any) -> None:
        """Fail the first limiter of the tick, renew the others for real."""
        if revocation.call_count == 1:
            raise sqlite3.OperationalError("database is locked")
        real_revocation(*args, **kwargs)

    revocation.side_effect = failing_once
    sleep = mocker.patch("runners.quota_scheduler.sleep", side_effect=StopLoop)

    with pytest.raises(StopLoop):
        quota_scheduler.quota_scheduler(config)

    assert revocation.call_count == len(config.limiters)
    assert read_available(quota_db, ALICE, USER_SUBJECT) == 70, "the failed one"
    assert read_available(quota_db, CLUSTER, CLUSTER_SUBJECT) == 1000
    sleep.assert_called_once_with(config.scheduler.period)


def test_scheduler_loop_reconnects_when_its_connection_died(
    quota_db: Path,
    make_limiter: Callable[..., QuotaLimiter],
    mocker: MockerFixture,
) -> None:
    """A connection lost between two ticks is replaced and the renewal goes on."""
    config = handlers(quota_db, RESET)
    alice = make_limiter(config, RESET)
    spend(alice, 30, ALICE)
    back_date(quota_db)
    connect_spy = mocker.spy(quota_scheduler, "connect")

    def between_ticks(_period: int) -> None:
        """Kill the scheduler's connection after the first tick, stop after the second."""
        if connect_spy.call_count == 1:
            assert read_available(quota_db, ALICE, USER_SUBJECT) == 100
            connect_spy.spy_return.close()
            spend(alice, 10, ALICE)
            back_date(quota_db)
            return
        raise StopLoop

    mocker.patch("runners.quota_scheduler.sleep", side_effect=between_ticks)

    with pytest.raises(StopLoop):
        quota_scheduler.quota_scheduler(config)

    assert connect_spy.call_count == 2
    assert read_available(quota_db, ALICE, USER_SUBJECT) == 100
