"""Unit tests for the TokenUsageHistory class."""

import sqlite3

import pytest

from models.config import QuotaHandlersConfiguration, SQLiteDatabaseConfiguration
from quota.token_usage_history import TokenUsageHistory

USER = "user-1"
OTHER_USER = "user-2"
PROVIDER = "test-provider"
MODEL = "test-model"


@pytest.fixture(name="history")
def history_fixture() -> TokenUsageHistory:
    """Create a token usage history on an in-memory SQLite database."""
    configuration = QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
        sqlite=SQLiteDatabaseConfiguration(db_path=":memory:"),
        enable_token_history=True,
    )
    return TokenUsageHistory(configuration)


def usage_rows(history: TokenUsageHistory) -> dict[tuple[str, str, str], tuple]:
    """Read every token_usage row of the history, keyed by its primary key."""
    assert history.connection is not None
    cursor = history.connection.cursor()
    cursor.execute(
        "SELECT user_id, provider, model, input_tokens, output_tokens FROM token_usage"
    )
    rows = cursor.fetchall()
    cursor.close()
    return {(row[0], row[1], row[2]): (row[3], row[4]) for row in rows}


def test_connected_with_storage(history: TokenUsageHistory) -> None:
    """A history created on a storage is connected and has its table."""
    assert history.connected()
    assert not usage_rows(history)


def test_usage_accumulates_per_user_provider_and_model(
    history: TokenUsageHistory,
) -> None:
    """Every (user, provider, model) triple keeps its own running totals."""
    history.consume_tokens(USER, PROVIDER, MODEL, 100, 50)
    history.consume_tokens(USER, PROVIDER, MODEL, 20, 5)
    history.consume_tokens(USER, PROVIDER, "other-model", 1, 1)
    history.consume_tokens(OTHER_USER, PROVIDER, MODEL, 7, 3)

    assert usage_rows(history) == {
        (USER, PROVIDER, MODEL): (120, 55),
        (USER, PROVIDER, "other-model"): (1, 1),
        (OTHER_USER, PROVIDER, MODEL): (7, 3),
    }


def test_reconnects_after_the_connection_was_closed(
    history: TokenUsageHistory,
) -> None:
    """A dead connection is reopened before the next write."""
    assert history.connection is not None
    history.connection.close()
    assert not history.connected()

    history.consume_tokens(USER, PROVIDER, MODEL, 1, 2)

    assert history.connected()
    # :memory: databases do not survive their connection, so the reopened
    # history starts empty and holds only the write made after the reconnect
    assert usage_rows(history) == {(USER, PROVIDER, MODEL): (1, 2)}


def test_without_storage_nothing_is_connected_and_writes_are_ignored() -> None:
    """Without a storage the history has no connection and consuming is a no-op."""
    history = TokenUsageHistory(
        QuotaHandlersConfiguration(  # pyright: ignore[reportCallIssue]
            enable_token_history=True
        )
    )

    assert history.connection is None
    assert not history.connected()
    history.consume_tokens(USER, PROVIDER, MODEL, 1, 1)
    assert history.connection is None


def test_write_fails_loudly_when_the_table_is_gone(
    history: TokenUsageHistory,
) -> None:
    """A storage error is not swallowed; the caller maps it to an HTTP 500."""
    assert history.connection is not None
    history.connection.execute("DROP TABLE token_usage")

    with pytest.raises(sqlite3.OperationalError):
        history.consume_tokens(USER, PROVIDER, MODEL, 1, 1)
