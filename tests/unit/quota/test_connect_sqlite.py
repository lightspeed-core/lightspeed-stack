"""Unit tests for SQLite connection handler."""

import pytest

from sqlite3 import OperationalError

from quota.connect_sqlite import connect_sqlite
from models.config import SQLiteDatabaseConfiguration


def test_connect_sqlite_when_connection_established():
    """Test the connection to SQLite database residing in memory."""
    configuration = SQLiteDatabaseConfiguration(db_path=":memory:")

    # connection should be established
    connection = connect_sqlite(configuration)
    assert connection is not None


def test_connect_sqlite_when_connection_error():
    """Test the connection to SQLite database."""
    configuration = SQLiteDatabaseConfiguration(db_path="/")

    # connection should not be established
    with pytest.raises(OperationalError, match="unable to open database file"):
        _ = connect_sqlite(configuration)
