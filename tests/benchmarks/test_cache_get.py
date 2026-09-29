"""Benchmarks for retrieving data from cache."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.noop_cache import NoopCache

from .cache_data import (
    CONVERSATION_ID_1,
    CONVERSATION_ID_2,
    USER_ID,
    cache_entry_1,
    cache_entry_2,
)


def test_noop_cache_empty_cache(
    noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving existing items."""
    # this UUID is different from DEFAULT_USER_UID
    benchmark(
        noop_cache_fixture.get,
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        CONVERSATION_ID_1,
    )


def test_noop_cache_existing_user(
    noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving existing items."""
    # this UUID is different from DEFAULT_USER_UID
    noop_cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
    noop_cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID_2,
        cache_entry_2,
    )
    benchmark(
        noop_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )
