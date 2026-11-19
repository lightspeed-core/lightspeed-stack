"""Benchmarks for cache method insert__or_append."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.sqlite_cache import SQLiteCache

from .cache_data import (
    CONVERSATION_ID_1,
    CONVERSATION_ID_2,
    USER_ID,
    cache_entry_1,
    cache_entry_2,
)


def test_sqlite_cache(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for insert_or_append method for existing item."""
    sqlite_cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
    benchmark(
        sqlite_cache_fixture.insert_or_append,
        USER_ID,
        CONVERSATION_ID_2,
        cache_entry_2,
    )
