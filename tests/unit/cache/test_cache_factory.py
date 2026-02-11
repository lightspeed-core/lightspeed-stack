"""Unit tests for CacheFactory class."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from pydantic import SecretStr

from constants import (
    CACHE_TYPE_NOOP,
    CACHE_TYPE_MEMORY,
    CACHE_TYPE_SQLITE,
    CACHE_TYPE_POSTGRES,
)

from models.config import (
    ConversationHistoryConfiguration,
    InMemoryCacheConfig,
    SQLiteDatabaseConfiguration,
    PostgreSQLDatabaseConfiguration,
)

from cache.cache_factory import CacheFactory
from cache.noop_cache import NoopCache
from cache.in_memory_cache import InMemoryCache
from cache.sqlite_cache import SQLiteCache
from cache.postgres_cache import PostgresCache


@pytest.fixture(scope="module", name="noop_cache_config_fixture")
def noop_cache_config() -> ConversationHistoryConfiguration:
    """Fixture containing initialized instance of ConversationHistoryConfiguration.

    Provide a ConversationHistoryConfiguration configured for the
    NOOP cache type.

    Returns:
        ConversationHistoryConfiguration: configuration instance with `type` set to CACHE_TYPE_NOOP
    """
    return ConversationHistoryConfiguration(
        type=CACHE_TYPE_NOOP
    )  # pyright: ignore[reportCallIssue]


@pytest.fixture(scope="module", name="memory_cache_config_fixture")
def memory_cache_config() -> ConversationHistoryConfiguration:
    """Fixture containing initialized instance of InMemory cache.

    Provide a ConversationHistoryConfiguration configured for an
    in-memory conversation cache.

    Returns:
        ConversationHistoryConfiguration: Configuration with type set to
        in-memory and an InMemoryCacheConfig(max_entries=10).
    """
    return ConversationHistoryConfiguration(
        type=CACHE_TYPE_MEMORY, memory=InMemoryCacheConfig(max_entries=10)
    )  # pyright: ignore[reportCallIssue]


@pytest.fixture(scope="module", name="postgres_cache_config_fixture")
def postgres_cache_config() -> ConversationHistoryConfiguration:
    """Fixture containing initialized instance of PostgreSQL cache.

    Create a ConversationHistoryConfiguration configured for a
    PostgreSQL cache.

    Returns:
        ConversationHistoryConfiguration: Configuration with type set to
        POSTGRES and `postgres` populated with db="database", user="user", and
        password=SecretStr("password").
    """
    return ConversationHistoryConfiguration(
        type=CACHE_TYPE_POSTGRES,
        postgres=PostgreSQLDatabaseConfiguration(
            db="database", user="user", password=SecretStr("password")
        ),  # pyright: ignore[reportCallIssue],
    )


@pytest.fixture(name="sqlite_cache_config_fixture")
def sqlite_cache_config(tmpdir: Path) -> ConversationHistoryConfiguration:
    """Fixture containing initialized instance of SQLite cache.

    Create a ConversationHistoryConfiguration for an SQLite cache
    using a temporary directory.

    Parameters:
        tmpdir (Path): Temporary directory path; the SQLite file will be
        created at `tmpdir / "test.sqlite"`.

    Returns:
        ConversationHistoryConfiguration: Configuration with `type` set to the
        SQLite cache constant and `sqlite` set to a SQLiteDatabaseConfiguration
        pointing to the test database path.
    """
    db_path = str(tmpdir / "test.sqlite")
    return ConversationHistoryConfiguration(
        type=CACHE_TYPE_SQLITE, sqlite=SQLiteDatabaseConfiguration(db_path=db_path)
    )  # pyright: ignore[reportCallIssue]


@pytest.fixture(scope="module", name="invalid_cache_type_config_fixture")
def invalid_cache_type_config() -> ConversationHistoryConfiguration:
    """Fixture containing instance of ConversationHistoryConfiguration with improper settings.

    Create a ConversationHistoryConfiguration whose type is set to
    an invalid string to test factory validation.

    Returns:
        ConversationHistoryConfiguration: configuration with `type` set to "foo bar baz".
    """
    c = ConversationHistoryConfiguration()  # pyright: ignore[reportCallIssue]
    # the conversation cache type name is incorrect in purpose
    c.type = "foo bar baz"  # pyright: ignore
    return c


def test_conversation_cache_noop(
    noop_cache_config_fixture: ConversationHistoryConfiguration,
) -> None:
    """Check if NoopCache is returned by factory with proper configuration."""
    cache = CacheFactory.conversation_cache(noop_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, NoopCache)


def test_conversation_cache_in_memory(
    memory_cache_config_fixture: ConversationHistoryConfiguration,
) -> None:
    """Check if InMemoryCache is returned by factory with proper configuration."""
    cache = CacheFactory.conversation_cache(memory_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, InMemoryCache)


def test_conversation_cache_in_memory_improper_config() -> None:
    """Check if memory cache configuration is checked in cache factory."""
    cc = ConversationHistoryConfiguration(
        type=CACHE_TYPE_MEMORY, memory=InMemoryCacheConfig(max_entries=10)
    )  # pyright: ignore[reportCallIssue]
    # simulate improper configuration (can not be done directly as model checks this)
    cc.memory = None
    with pytest.raises(ValueError, match="Expecting configuration for in-memory cache"):
        _ = CacheFactory.conversation_cache(cc)


def test_conversation_cache_sqlite(
    sqlite_cache_config_fixture: ConversationHistoryConfiguration,
) -> None:
    """Check if SQLiteCache is returned by factory with proper configuration."""
    cache = CacheFactory.conversation_cache(sqlite_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, SQLiteCache)


def test_conversation_cache_sqlite_improper_config(tmpdir: Path) -> None:
    """Check if memory cache configuration is checked in cache factory.

    Verifies that a nil SQLite configuration causes
    CacheFactory.conversation_cache to raise a ValueError.

    Expects a ValueError with message containing "Expecting configuration for
    SQLite cache" when the ConversationHistoryConfiguration has type SQLITE but
    its sqlite field is None.
    """
    db_path = str(tmpdir / "test.sqlite")
    cc = ConversationHistoryConfiguration(
        type=CACHE_TYPE_SQLITE, sqlite=SQLiteDatabaseConfiguration(db_path=db_path)
    )  # pyright: ignore[reportCallIssue]
    # simulate improper configuration (can not be done directly as model checks this)
    cc.sqlite = None
    with pytest.raises(ValueError, match="Expecting configuration for SQLite cache"):
        _ = CacheFactory.conversation_cache(cc)


def test_conversation_cache_postgres(
    postgres_cache_config_fixture: ConversationHistoryConfiguration,
    mocker: MockerFixture,
) -> None:
    """Check if PostgreSQL is returned by factory with proper configuration."""
    mocker.patch("psycopg2.connect")
    cache = CacheFactory.conversation_cache(postgres_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, PostgresCache)


def test_conversation_cache_postgres_improper_config() -> None:
    """Check if PostgreSQL cache configuration is checked in cache factory.

    Verify that the cache factory raises a ValueError when the PostgreSQL configuration is missing.

    This test simulates an absent `postgres` config on a
    ConversationHistoryConfiguration with type `POSTGRES` and asserts that
    CacheFactory.conversation_cache raises ValueError with message containing
    "Expecting configuration for PostgreSQL cache".
    """
    cc = ConversationHistoryConfiguration(
        type=CACHE_TYPE_POSTGRES,
        postgres=PostgreSQLDatabaseConfiguration(
            db="db", user="u", password=SecretStr("p")
        ),  # pyright: ignore[reportCallIssue]
    )
    # simulate improper configuration (can not be done directly as model checks this)
    cc.postgres = None
    with pytest.raises(
        ValueError, match="Expecting configuration for PostgreSQL cache"
    ):
        _ = CacheFactory.conversation_cache(cc)


def test_conversation_cache_no_type() -> None:
    """Check if wrong cache configuration is detected properly.

    Verify that a ConversationHistoryConfiguration with no type causes the factory to reject it.

    Asserts that calling CacheFactory.conversation_cache with a configuration
    whose `type` is None raises a ValueError with message "Cache type must be
    set".
    """
    cc = ConversationHistoryConfiguration(
        type=CACHE_TYPE_NOOP
    )  # pyright: ignore[reportCallIssue]
    # simulate improper configuration (can not be done directly as model checks this)
    cc.type = None
    with pytest.raises(ValueError, match="Cache type must be set"):
        CacheFactory.conversation_cache(cc)


def test_conversation_cache_wrong_cache(
    invalid_cache_type_config_fixture: ConversationHistoryConfiguration,
) -> None:
    """Check if wrong cache configuration is detected properly.

    Verify that an unsupported cache type in the configuration raises a ValueError.

    This test calls CacheFactory.conversation_cache with a configuration whose
    type is invalid and asserts a ValueError is raised with a message
    containing "Invalid cache type".
    """
    with pytest.raises(ValueError, match="Invalid cache type"):
        CacheFactory.conversation_cache(invalid_cache_type_config_fixture)
