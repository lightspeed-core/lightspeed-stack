"""Benchmarks for cache method insert__or_append."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.noop_cache import NoopCache

from .cache_data import (
    CONVERSATION_ID_1,
    USER_ID,
    cache_entry_1,
)


def test_noop_cache(noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture) -> None:
    """Benchmark for the insert_or_append method."""
    benchmark(
        noop_cache_fixture.insert_or_append,
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
