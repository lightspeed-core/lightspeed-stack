"""Benchmarks for deleting data from cache."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.sqlite_cache import SQLiteCache

from .cache_data import (
    CONVERSATION_ID_1,
    EXTRA_LONG_CONVERSATION_ENTRIES,
    LONG_CONVERSATION_ENTRIES,
    MEDIUM_CONVERSATION_ENTRIES,
    SHORT_CONVERSATION_ENTRIES,
    USER_ID,
    USER_PROVIDED_USER_ID,
    cache_entry_1,
)
from .cache_utils import fill_in_conversations


def test_sqlite_cache_existing_conversation(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_10_short_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 10, SHORT_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_10_medium_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 10, MEDIUM_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_10_long_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 10, LONG_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_10_extra_long_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 10, EXTRA_LONG_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_100_short_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 100, SHORT_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_100_medium_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 100, MEDIUM_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_100_long_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 100, LONG_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_100_extra_long_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 100, EXTRA_LONG_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_1000_short_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 1000, SHORT_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_1000_medium_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 1000, MEDIUM_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_1000_long_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 1000, LONG_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_1000_extra_long_conversations(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(sqlite_cache_fixture, 1000, EXTRA_LONG_CONVERSATION_ENTRIES)
    sqlite_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_nonexistent_conversation(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting a conversation that doesn't exist."""
    benchmark(sqlite_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_sqlite_cache_skip_user_id_check(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    skip_user_id_check = True
    sqlite_cache_fixture.insert_or_append(
        USER_PROVIDED_USER_ID, CONVERSATION_ID_1, cache_entry_1, skip_user_id_check
    )

    benchmark(
        sqlite_cache_fixture.delete,
        USER_PROVIDED_USER_ID,
        CONVERSATION_ID_1,
        skip_user_id_check,
    )
