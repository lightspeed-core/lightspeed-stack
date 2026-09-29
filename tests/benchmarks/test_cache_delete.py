"""Benchmarks for deleting data from cache."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.noop_cache import NoopCache

from .cache_data import (
    CONVERSATION_ID_1,
    USER_ID,
    USER_PROVIDED_USER_ID,
    cache_entry_1,
)


def test_noop_cache_existing_conversation(
    noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    noop_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(noop_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_noop_cache_nonexistent_conversation(
    noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting a conversation that doesn't exist."""
    benchmark(noop_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_noop_cache_skip_user_id_check(
    noop_cache_fixture: NoopCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    skip_user_id_check = True
    noop_cache_fixture.insert_or_append(
        USER_PROVIDED_USER_ID, CONVERSATION_ID_1, cache_entry_1, skip_user_id_check
    )

    benchmark(
        noop_cache_fixture.delete,
        USER_PROVIDED_USER_ID,
        CONVERSATION_ID_1,
        skip_user_id_check,
    )
