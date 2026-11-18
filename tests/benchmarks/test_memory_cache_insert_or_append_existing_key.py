"""Benchmarks for cache method insert__or_append."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.in_memory_cache import InMemoryCache

from .cache_data import (
    CONVERSATION_ID_1,
    CONVERSATION_ID_2,
    USER_ID,
    cache_entry_1,
    cache_entry_2,
)


def test_memory_cache(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for insert_or_append method for existing item."""
    memory_cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
    benchmark(
        memory_cache_fixture.insert_or_append,
        USER_ID,
        CONVERSATION_ID_2,
        cache_entry_2,
    )
