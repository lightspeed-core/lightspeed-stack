"""Benchmarks for cache method insert__or_append."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.sqlite_cache import SQLiteCache

from .cache_data import (
    CONVERSATION_ID_1,
    USER_ID,
    cache_entry_1,
)


def test_sqlite_cache(
    sqlite_cache_fixture: SQLiteCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the insert_or_append method."""
    benchmark(
        sqlite_cache_fixture.insert_or_append,
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
