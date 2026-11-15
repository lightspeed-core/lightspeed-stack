"""Unit tests for SQLite connection handler."""

from sqlite3 import OperationalError

import pytest

from models.config import SQLiteDatabaseConfiguration
from quota.connect_sqlite import connect_sqlite


def test_connect_sqlite_when_connection_established() -> None:
    """Open an in-memory SQLite database for quota storage."""
    configuration = SQLiteDatabaseConfiguration(db_path=":memory:")

    # connection should be established
    connection = connect_sqlite(configuration)
    assert connection is not None


def test_connect_sqlite_when_connection_error() -> None:
    """Surface SQLite connection failures from invalid database paths."""
    configuration = SQLiteDatabaseConfiguration(db_path="/")

    # connection should not be established
    with pytest.raises(OperationalError, match="unable to open database file"):
        _ = connect_sqlite(configuration)
