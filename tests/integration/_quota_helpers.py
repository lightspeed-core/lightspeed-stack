"""Shared helpers for the quota management integration tests (LCORE-4610).

The quota limiters and the quota scheduler share one SQLite table,
``quota_limits``, with one row per (subject id, subject type). The helpers
here build limiter configurations, read rows straight from the database and
move the ``revoked_at`` stamp of rows into the past, so that a renewal can be
observed without waiting for a period to elapse.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Optional

from models.config import (
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    QuotaSchedulerConfiguration,
    SQLiteDatabaseConfiguration,
)
from quota.quota_limiter import QuotaLimiter
from runners.quota_scheduler import (
    get_increase_quota_statement,
    get_reset_quota_statement,
    quota_revocation,
)

USER_SUBJECT = "u"
CLUSTER_SUBJECT = "c"
CLUSTER = ""
"""The cluster limiter keeps one row, under the empty id."""

ROW_AGE_SECONDS = 3
"""Rows are back-dated by this much: past a 2 second period, inside a 10 second one."""

TimestampStyle = Literal["limiter", "scheduler"]


def limiter_config(
    limiter_type: str,
    *,
    initial_quota: int,
    quota_increase: int,
    period: str,
) -> QuotaLimiterConfiguration:
    """Build the configuration of one limiter."""
    return QuotaLimiterConfiguration(
        type=limiter_type,  # type: ignore[arg-type]
        name=f"{limiter_type} test",
        initial_quota=initial_quota,
        quota_increase=quota_increase,
        period=period,
    )


def handlers(
    db_path: Path,
    *limiters: QuotaLimiterConfiguration,
    scheduler_period: int = 1,
    enable_token_history: bool = False,
) -> QuotaHandlersConfiguration:
    """Build a quota configuration on the given SQLite file."""
    return QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
        sqlite=SQLiteDatabaseConfiguration(db_path=str(db_path)),
        limiters=list(limiters),
        scheduler=QuotaSchedulerConfiguration(
            period=scheduler_period
        ),  # pyright: ignore[reportCallIssue]
        enable_token_history=enable_token_history,
    )


@contextmanager
def _connected(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection for one helper call, commit on success, close always.

    The ``sqlite3`` connection as a context manager only wraps a transaction;
    it never closes, and the endpoint tests call the helpers dozens of times
    on a file the limiters and the scheduler keep open.
    """
    connection = sqlite3.connect(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def read_available(db_path: Path, row_id: str, subject: str) -> Optional[int]:
    """Read the balance of one row straight from the database, None if no row."""
    with _connected(db_path) as connection:
        row = connection.execute(
            "SELECT available FROM quota_limits WHERE id=? AND subject=?",
            (row_id, subject),
        ).fetchone()
    return None if row is None else int(row[0])


def read_revoked_at(db_path: Path, row_id: str, subject: str) -> str:
    """Read the ``revoked_at`` stamp of one row as the text SQLite stores."""
    with _connected(db_path) as connection:
        (revoked_at,) = connection.execute(
            "SELECT revoked_at FROM quota_limits WHERE id=? AND subject=?",
            (row_id, subject),
        ).fetchone()
    return str(revoked_at)


def read_row_age_seconds(db_path: Path, row_id: str, subject: str) -> Optional[float]:
    """Read how long ago SQLite thinks one row was last renewed.

    The age is computed by SQLite itself from the ``revoked_at`` text, the way
    the renewal statements read it. It is None when the stamp is missing or
    is in a format ``datetime()`` can not parse, which is the case a renewal
    silently never matches.
    """
    with _connected(db_path) as connection:
        (age,) = connection.execute(
            "SELECT (julianday('now') - julianday(revoked_at)) * 86400"
            "  FROM quota_limits WHERE id=? AND subject=?",
            (row_id, subject),
        ).fetchone()
    return None if age is None else float(age)


def table_exists(db_path: Path, table: str) -> bool:
    """Tell whether the database file holds a table of the given name."""
    with _connected(db_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    return row is not None


def read_token_usage(db_path: Path) -> dict[tuple[str, str, str], tuple[int, int]]:
    """Read the token usage history, keyed by (user, provider, model)."""
    with _connected(db_path) as connection:
        rows = connection.execute(
            "SELECT user_id, provider, model, input_tokens, output_tokens"
            "  FROM token_usage"
        ).fetchall()
    return {(row[0], row[1], row[2]): (int(row[3]), int(row[4])) for row in rows}


def back_date(
    db_path: Path,
    seconds: int = ROW_AGE_SECONDS,
    style: TimestampStyle = "limiter",
    subject: Optional[str] = None,
) -> None:
    """Move the ``revoked_at`` stamp of the rows into the past.

    ``limiter`` writes the stamp as the limiter does, an ISO timestamp with a
    ``T`` separator; ``scheduler`` writes it as the renewal statements do, with
    SQLite's ``datetime()`` text. Without ``subject`` every row is moved.
    """
    where = "" if subject is None else " WHERE subject=?"
    params: tuple[Any, ...] = () if subject is None else (subject,)
    with _connected(db_path) as connection:
        if style == "limiter":
            stamp = datetime.now(tz=UTC) - timedelta(seconds=seconds)
            connection.execute(
                f"UPDATE quota_limits SET revoked_at=?{where}",
                (stamp.replace(tzinfo=None).isoformat(), *params),
            )
        else:
            connection.execute(
                f"UPDATE quota_limits SET revoked_at=datetime('now', ?){where}",
                (f"-{seconds} seconds", *params),
            )


def spend(limiter: QuotaLimiter, tokens: int, subject: str = CLUSTER) -> None:
    """Use a limiter the way a request does: read the balance first, then consume.

    The read creates the row of a subject the database has not seen yet, with
    ``initial_quota`` and the current time as its ``revoked_at`` stamp.
    """
    limiter.available_quota(subject)
    limiter.consume_tokens(tokens, 0, subject)


def renew(connection: Any, config: QuotaHandlersConfiguration) -> None:
    """Run one scheduler sync: the renewal of every configured limiter."""
    for limiter in config.limiters:
        quota_revocation(
            connection,
            limiter,
            get_increase_quota_statement(config),
            get_reset_quota_statement(config),
        )
