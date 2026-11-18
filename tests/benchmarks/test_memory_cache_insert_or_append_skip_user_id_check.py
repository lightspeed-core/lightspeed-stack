"""Benchmarks for cache method insert__or_append."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.in_memory_cache import InMemoryCache

from .cache_data import (
    CONVERSATION_ID_1,
    USER_PROVIDED_USER_ID,
    cache_entry_1,
)


def test_memory_cache(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the insert_or_append method.

    Verify that insert_or_append accepts a non-UUID user identifier when
    skip_user_id_check is True.

    This test calls insert_or_append with a user-provided (non-UUID) user id, a
    conversation id, and a cache entry while passing skip_user_id_check=True;
    the operation is expected to complete without raising an exception.
    """
    skip_user_id_check = True
    benchmark(
        memory_cache_fixture.insert_or_append,
        USER_PROVIDED_USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
        skip_user_id_check,
    )
