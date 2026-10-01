"""Benchmarks for cache method insert__or_append."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.noop_cache import NoopCache

from .cache_data import (
    CONVERSATION_ID_1,
    CONVERSATION_ID_2,
    USER_ID,
    cache_entry_1,
    cache_entry_2,
)


def test_noop_cache(noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture) -> None:
    """Benchmark for insert_or_append method for existing item."""
    noop_cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
    benchmark(
        noop_cache_fixture.insert_or_append,
        USER_ID,
        CONVERSATION_ID_2,
        cache_entry_2,
    )
