"""Unit tests for ConversationCacheConfiguration model."""

from pathlib import Path

import pytest

from pydantic import ValidationError

import constants
from models.config import (
    ConversationCacheConfiguration,
    InMemoryCacheConfig,
    SQLiteDatabaseConfiguration,
    PostgreSQLDatabaseConfiguration,
)


def test_conversation_cache_no_type_specified() -> None:
    """Check the test for type as optional attribute."""
    c = ConversationCacheConfiguration()
    assert c.type is None


def test_conversation_cache_unknown_type() -> None:
    """Check the test for cache type."""
    with pytest.raises(
        ValidationError, match="Input should be 'memory', 'sqlite' or 'postgres'"
    ):
        _ = ConversationCacheConfiguration(type="foo")


def test_conversation_cache_correct_type_but_not_configured(subtests) -> None:
    """Check the test for cache type."""
    with subtests.test(msg="Memory cache"):
        with pytest.raises(
            ValidationError, match="Memory cache is selected, but not configured"
        ):
            _ = ConversationCacheConfiguration(type=constants.CACHE_TYPE_MEMORY)

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(
            ValidationError, match="SQLite cache is selected, but not configured"
        ):
            _ = ConversationCacheConfiguration(type=constants.CACHE_TYPE_SQLITE)

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(
            ValidationError, match="PostgreSQL cache is selected, but not configured"
        ):
            _ = ConversationCacheConfiguration(type=constants.CACHE_TYPE_POSTGRES)


def test_conversation_cache_no_type_but_configured(subtests) -> None:
    """Check the test for cache type."""
    m = "Conversation cache type must be set when backend configuration is provided"

    with subtests.test(msg="Memory cache"):
        with pytest.raises(ValidationError, match=m):
            _ = ConversationCacheConfiguration(
                memory=InMemoryCacheConfig(max_entries=100)
            )

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(ValidationError, match=m):
            _ = ConversationCacheConfiguration(
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
            _ = ConversationCacheConfiguration(postgres=d)


def test_conversation_cache_multiple_configurations(subtests) -> None:
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
            _ = ConversationCacheConfiguration(
                type=constants.CACHE_TYPE_MEMORY,
                memory=InMemoryCacheConfig(max_entries=100),
                sqlite=SQLiteDatabaseConfiguration(db_path="path"),
                postgres=d,
            )

    with subtests.test(msg="SQLite cache"):
        with pytest.raises(
            ValidationError, match="Only SQLite cache config must be provided"
        ):
            _ = ConversationCacheConfiguration(
                type=constants.CACHE_TYPE_SQLITE,
                memory=InMemoryCacheConfig(max_entries=100),
                sqlite=SQLiteDatabaseConfiguration(db_path="path"),
                postgres=d,
            )

    with subtests.test(msg="PostgreSQL cache"):
        with pytest.raises(
            ValidationError, match="Only PostgreSQL cache config must be provided"
        ):
            _ = ConversationCacheConfiguration(
                type=constants.CACHE_TYPE_POSTGRES,
                memory=InMemoryCacheConfig(max_entries=100),
                sqlite=SQLiteDatabaseConfiguration(db_path="path"),
                postgres=d,
            )


def test_conversation_type_memory() -> None:
    """Test the memory conversation cache configuration."""
    c = ConversationCacheConfiguration(
        type=constants.CACHE_TYPE_MEMORY, memory=InMemoryCacheConfig(max_entries=100)
    )
    assert c.type == constants.CACHE_TYPE_MEMORY
    assert c.memory is not None
    assert c.sqlite is None
    assert c.postgres is None
    assert c.memory.max_entries == 100


def test_conversation_type_memory_wrong_config() -> None:
    """Test the memory conversation cache configuration."""
    with pytest.raises(ValidationError, match="Field required"):
        _ = ConversationCacheConfiguration(
            type=constants.CACHE_TYPE_MEMORY,
            memory=InMemoryCacheConfig(),
        )

    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        _ = ConversationCacheConfiguration(
            type=constants.CACHE_TYPE_MEMORY,
            memory=InMemoryCacheConfig(max_entries=-100),
        )


def test_conversation_type_sqlite() -> None:
    """Test the SQLite conversation cache configuration."""
    c = ConversationCacheConfiguration(
        type=constants.CACHE_TYPE_SQLITE,
        sqlite=SQLiteDatabaseConfiguration(db_path="path"),
    )
    assert c.type == constants.CACHE_TYPE_SQLITE
    assert c.memory is None
    assert c.sqlite is not None
    assert c.postgres is None
    assert c.sqlite.db_path == "path"


def test_conversation_type_sqlite_wrong_config() -> None:
    """Test the SQLite conversation cache configuration."""
    with pytest.raises(ValidationError, match="Field required"):
        _ = ConversationCacheConfiguration(
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

    c = ConversationCacheConfiguration(
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
    """Test the SQLite conversation cache configuration."""
    with pytest.raises(ValidationError, match="Field required"):
        _ = ConversationCacheConfiguration(
            type=constants.CACHE_TYPE_POSTGRES,
            postgres=PostgreSQLDatabaseConfiguration(),
        )
