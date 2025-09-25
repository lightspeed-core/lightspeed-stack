"""Unit tests for CacheFactory class."""

import pytest

from constants import (
    CACHE_TYPE_NOOP,
    CACHE_TYPE_MEMORY,
    CACHE_TYPE_SQLITE,
    CACHE_TYPE_POSTGRES,
)

from models.config import (
    ConversationCacheConfiguration,
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
def noop_cache_config():
    """Fixture containing initialized instance of ConversationCacheConfiguration."""
    return ConversationCacheConfiguration(type=CACHE_TYPE_NOOP)


@pytest.fixture(scope="module", name="memory_cache_config_fixture")
def memory_cache_config():
    """Fixture containing initialized instance of InMemory cache."""
    return ConversationCacheConfiguration(
        type=CACHE_TYPE_MEMORY, memory=InMemoryCacheConfig(max_entries=10)
    )


@pytest.fixture(scope="module", name="postgres_cache_config_fixture")
def postgres_cache_config():
    """Fixture containing initialized instance of PostgreSQL cache."""
    return ConversationCacheConfiguration(
        type=CACHE_TYPE_POSTGRES,
        postgres=PostgreSQLDatabaseConfiguration(
            db="database", user="user", password="password"
        ),
    )


@pytest.fixture(name="sqlite_cache_config_fixture")
def sqlite_cache_config(tmpdir):
    """Fixture containing initialized instance of SQLite cache."""
    db_path = str(tmpdir / "test.sqlite")
    return ConversationCacheConfiguration(
        type=CACHE_TYPE_SQLITE, sqlite=SQLiteDatabaseConfiguration(db_path=db_path)
    )


@pytest.fixture(scope="module", name="invalid_cache_type_config_fixture")
def invalid_cache_type_config():
    """Fixture containing instance of ConversationCacheConfiguration with improper settings."""
    c = ConversationCacheConfiguration()
    c.type = "foo bar baz"
    return c


def test_conversation_cache_noop(noop_cache_config_fixture):
    """Check if NoopCache is returned by factory with proper configuration."""
    cache = CacheFactory.conversation_cache(noop_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, NoopCache)


def test_conversation_cache_in_memory(memory_cache_config_fixture):
    """Check if InMemoryCache is returned by factory with proper configuration."""
    cache = CacheFactory.conversation_cache(memory_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, InMemoryCache)


def test_conversation_cache_in_memory_improper_config():
    """Check if memory cache configuration is checked in cache factory."""
    cc = ConversationCacheConfiguration(
        type=CACHE_TYPE_MEMORY, memory=InMemoryCacheConfig(max_entries=10)
    )
    # simulate improper configuration (can not be done directly as model checks this)
    cc.memory = None
    with pytest.raises(ValueError, match="Expecting configuration for in-memory cache"):
        _ = CacheFactory.conversation_cache(cc)


def test_conversation_cache_sqlite(sqlite_cache_config_fixture):
    """Check if SQLiteCache is returned by factory with proper configuration."""
    cache = CacheFactory.conversation_cache(sqlite_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, SQLiteCache)


def test_conversation_cache_sqlite_improper_config(tmpdir):
    """Check if memory cache configuration is checked in cache factory."""
    db_path = str(tmpdir / "test.sqlite")
    cc = ConversationCacheConfiguration(
        type=CACHE_TYPE_SQLITE, sqlite=SQLiteDatabaseConfiguration(db_path=db_path)
    )
    # simulate improper configuration (can not be done directly as model checks this)
    cc.sqlite = None
    with pytest.raises(ValueError, match="Expecting configuration for SQLite cache"):
        _ = CacheFactory.conversation_cache(cc)


def test_conversation_cache_postgres(postgres_cache_config_fixture, mocker):
    """Check if PostgreSQL is returned by factory with proper configuration."""
    mocker.patch("psycopg2.connect")
    cache = CacheFactory.conversation_cache(postgres_cache_config_fixture)
    assert cache is not None
    # check if the object has the right type
    assert isinstance(cache, PostgresCache)


def test_conversation_cache_postgres_improper_config():
    """Check if PostgreSQL cache configuration is checked in cache factory."""
    cc = ConversationCacheConfiguration(
        type=CACHE_TYPE_POSTGRES,
        postgres=PostgreSQLDatabaseConfiguration(db="db", user="u", password="p"),
    )
    # simulate improper configuration (can not be done directly as model checks this)
    cc.postgres = None
    with pytest.raises(
        ValueError, match="Expecting configuration for PostgreSQL cache"
    ):
        _ = CacheFactory.conversation_cache(cc)


def test_conversation_cache_no_type():
    """Check if wrong cache configuration is detected properly."""
    cc = ConversationCacheConfiguration(type=CACHE_TYPE_NOOP)
    # simulate improper configuration (can not be done directly as model checks this)
    cc.type = None
    with pytest.raises(ValueError, match="Cache type must be set"):
        CacheFactory.conversation_cache(cc)


def test_conversation_cache_wrong_cache(invalid_cache_type_config_fixture):
    """Check if wrong cache configuration is detected properly."""
    with pytest.raises(ValueError, match="Invalid cache type"):
        CacheFactory.conversation_cache(invalid_cache_type_config_fixture)
