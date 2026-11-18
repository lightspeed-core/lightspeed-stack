"""Benchmarks for deleting data from cache."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.in_memory_cache import InMemoryCache

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


def test_memory_cache_existing_conversation(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_10_short_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, SHORT_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_10_medium_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, MEDIUM_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_10_long_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_10_extra_long_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, EXTRA_LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_100_short_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, SHORT_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_100_medium_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, MEDIUM_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_100_long_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_100_extra_long_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, EXTRA_LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_1000_short_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, SHORT_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_1000_medium_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, MEDIUM_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_1000_long_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_1000_extra_long_conversations(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, EXTRA_LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_nonexistent_conversation(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting a conversation that doesn't exist."""
    benchmark(memory_cache_fixture.delete, USER_ID, CONVERSATION_ID_1)


def test_memory_cache_skip_user_id_check(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    skip_user_id_check = True
    memory_cache_fixture.insert_or_append(
        USER_PROVIDED_USER_ID, CONVERSATION_ID_1, cache_entry_1, skip_user_id_check
    )

    benchmark(
        memory_cache_fixture.delete,
        USER_PROVIDED_USER_ID,
        CONVERSATION_ID_1,
        skip_user_id_check,
    )
