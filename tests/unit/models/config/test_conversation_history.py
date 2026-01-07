"""Unit tests for ConversationHistoryConfiguration model."""

from pathlib import Path

import pytest
from pytest_subtests import SubTests

from pydantic import ValidationError

import constants
from models.config import (
    ConversationHistoryConfiguration,
    InMemoryCacheConfig,
    SQLiteDatabaseConfiguration,
    PostgreSQLDatabaseConfiguration,
)


def test_conversation_cache_no_type_specified() -> None:
    """Check the test for type as optional attribute.

    Verify that a ConversationHistoryConfiguration created with no arguments
    has its type set to None.
    """
    c = ConversationHistoryConfiguration()
    assert c.type is None


def test_conversation_cache_unknown_type() -> None:
    """Check the test for cache type.

    Verify that providing an invalid conversation cache type raises a
    ValidationError with the expected message.

    The test constructs a ConversationHistoryConfiguration with an unsupported
    type value and asserts that validation fails with the message: "Input
    should be 'noop', 'memory', 'sqlite' or 'postgres'".
    """
    with pytest.raises(
        ValidationError,
        match="Input should be 'noop', 'memory', 'sqlite' or 'postgres'",
    ):
        _ = ConversationHistoryConfiguration(type="foo")


def test_conversation_cache_correct_type_but_not_configured(subtests: SubTests) -> None:
    """Check the test for cache type.

    Verify that specifying a cache type without providing its corresponding
    backend configuration raises a ValidationError with the expected message.

    Parameters:
        subtests (SubTests): pytest_subtests SubTests object used to create
        subtests for memory, sqlite, and postgres cases.
    """
    with subtests.test(msg="Memory cache"):
        with pytest.raises(
            ValidationError, match="Memory cache is selected, but not configured"
        ):
            _ = ConversationHistoryConfiguration(type=constants.CACHE_TYPE_MEMORY)

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(
            ValidationError, match="SQLite cache is selected, but not configured"
        ):
            _ = ConversationHistoryConfiguration(type=constants.CACHE_TYPE_SQLITE)

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(
            ValidationError, match="PostgreSQL cache is selected, but not configured"
        ):
            _ = ConversationHistoryConfiguration(type=constants.CACHE_TYPE_POSTGRES)


def test_conversation_cache_no_type_but_configured(subtests: SubTests) -> None:
    """Check the test for cache type.

    Verify that providing a backend configuration without specifying a
    conversation cache type raises a ValidationError.

    This test asserts that constructing ConversationHistoryConfiguration with a
    memory, sqlite, or postgres backend (but without setting the `type` field)
    fails with a ValidationError whose message is "Conversation cache type must
    be set when backend configuration is provided".
    """
    m = "Conversation cache type must be set when backend configuration is provided"

    with subtests.test(msg="Memory cache"):
        with pytest.raises(ValidationError, match=m):
            _ = ConversationHistoryConfiguration(
                memory=InMemoryCacheConfig(max_entries=100)
            )

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(ValidationError, match=m):
            _ = ConversationHistoryConfiguration(
                sqlite=SQLiteDatabaseConfiguration(db_path="path")
            )

    with subtests.test(msg="PostgreSQL cache"):
        d = PostgreSQLDatabaseConfiguration(
            db="db",
            user="user",
            password="password",
            port=1234,
            ca_cert_path=Path("tests/configuration/server.crt"),
        )
        with pytest.raises(ValidationError, match=m):
            _ = ConversationHistoryConfiguration(postgres=d)


def test_conversation_cache_multiple_configurations(subtests: SubTests) -> None:
    """Test how multiple configurations are handled."""
    d = PostgreSQLDatabaseConfiguration(
        db="db",
        user="user",
        password="password",
        port=1234,
        ca_cert_path=Path("tests/configuration/server.crt"),
    )

    with subtests.test(msg="Memory cache"):
        with pytest.raises(
            ValidationError, match="Only memory cache config must be provided"
        ):
            _ = ConversationHistoryConfiguration(
                type=constants.CACHE_TYPE_MEMORY,
                memory=InMemoryCacheConfig(max_entries=100),
                sqlite=SQLiteDatabaseConfiguration(db_path="path"),
                postgres=d,
            )

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(
            ValidationError, match="Only SQLite cache config must be provided"
        ):
            _ = ConversationHistoryConfiguration(
                type=constants.CACHE_TYPE_SQLITE,
                memory=InMemoryCacheConfig(max_entries=100),
                sqlite=SQLiteDatabaseConfiguration(db_path="path"),
                postgres=d,
            )

    with subtests.test(msg="PostgreSQL cache"):
        with pytest.raises(
            ValidationError, match="Only PostgreSQL cache config must be provided"
        ):
            _ = ConversationHistoryConfiguration(
                type=constants.CACHE_TYPE_POSTGRES,
                memory=InMemoryCacheConfig(max_entries=100),
                sqlite=SQLiteDatabaseConfiguration(db_path="path"),
                postgres=d,
            )


def test_conversation_type_memory() -> None:
    """Test the memory conversation cache configuration."""
    c = ConversationHistoryConfiguration(
        type=constants.CACHE_TYPE_MEMORY, memory=InMemoryCacheConfig(max_entries=100)
    )
    assert c.type == constants.CACHE_TYPE_MEMORY
    assert c.memory is not None
    assert c.sqlite is None
    assert c.postgres is None
    assert c.memory.max_entries == 100


def test_conversation_type_memory_wrong_config() -> None:
    """Test the memory conversation cache configuration.

    Verify that selecting the memory conversation cache raises validation
    errors for missing or invalid memory configuration.

    Asserts:
    - A missing `max_entries` field in the memory configuration raises a
      ValidationError with "Field required".
    - A `max_entries` value less than or equal to zero raises a ValidationError
      with "Input should be greater than 0".
    """
    with pytest.raises(ValidationError, match="Field required"):
        _ = ConversationHistoryConfiguration(
            type=constants.CACHE_TYPE_MEMORY,
            memory=InMemoryCacheConfig(),
        )

    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        _ = ConversationHistoryConfiguration(
            type=constants.CACHE_TYPE_MEMORY,
            memory=InMemoryCacheConfig(max_entries=-100),
        )


def test_conversation_type_sqlite() -> None:
    """Test the SQLite conversation cache configuration."""
    c = ConversationHistoryConfiguration(
        type=constants.CACHE_TYPE_SQLITE,
        sqlite=SQLiteDatabaseConfiguration(db_path="path"),
    )
    assert c.type == constants.CACHE_TYPE_SQLITE
    assert c.memory is None
    assert c.sqlite is not None
    assert c.postgres is None
    assert c.sqlite.db_path == "path"


def test_conversation_type_sqlite_wrong_config() -> None:
    """Test the SQLite conversation cache configuration.

    Validate that selecting the SQLite conversation cache while supplying an
    incorrect backend configuration raises a validation error.

    This test asserts that when `type` is set to the SQLite cache but a
    `memory` configuration is provided instead of an `sqlite` configuration,
    model validation fails with a "Field required" error.
    """
    with pytest.raises(ValidationError, match="Field required"):
        _ = ConversationHistoryConfiguration(
            type=constants.CACHE_TYPE_SQLITE,
            memory=SQLiteDatabaseConfiguration(),
        )


def test_conversation_type_postgres() -> None:
    """Test the PostgreSQL conversation cache configuration."""
    d = PostgreSQLDatabaseConfiguration(
        db="db",
        user="user",
        password="password",
        port=1234,
        ca_cert_path=Path("tests/configuration/server.crt"),
    )

    c = ConversationHistoryConfiguration(
        type=constants.CACHE_TYPE_POSTGRES,
        postgres=d,
    )
    assert c.type == constants.CACHE_TYPE_POSTGRES
    assert c.memory is None
    assert c.sqlite is None
    assert c.postgres is not None
    assert c.postgres.host == "localhost"
    assert c.postgres.port == 1234
    assert c.postgres.db == "db"
    assert c.postgres.user == "user"


def test_conversation_type_postgres_wrong_config() -> None:
    """Test the PostgreSQL conversation cache configuration.

    Ensure a ValidationError is raised when PostgreSQL configuration is missing required fields.

    This test provides an empty PostgreSQLDatabaseConfiguration and expects
    validation to fail with a "Field required" message.
    """
    with pytest.raises(ValidationError, match="Field required"):
        _ = ConversationHistoryConfiguration(
            type=constants.CACHE_TYPE_POSTGRES,
            postgres=PostgreSQLDatabaseConfiguration(),
        )
