"""Benchmarks for cache method insert__or_append."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.in_memory_cache import InMemoryCache

from .cache_data import (
    CONVERSATION_ID_1,
    USER_ID,
    cache_entry_1,
)


def test_memory_cache(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the insert_or_append method."""
    benchmark(
        memory_cache_fixture.insert_or_append,
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
