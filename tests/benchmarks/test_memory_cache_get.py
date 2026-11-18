"""Benchmarks for retrieving data from cache."""

from pytest_benchmark.fixture import BenchmarkFixture

from cache.in_memory_cache import InMemoryCache

from .cache_data import (
    CONVERSATION_ID_1,
    CONVERSATION_ID_2,
    EXTRA_LONG_CONVERSATION_ENTRIES,
    LONG_CONVERSATION_ENTRIES,
    MEDIUM_CONVERSATION_ENTRIES,
    SHORT_CONVERSATION_ENTRIES,
    USER_ID,
    cache_entry_1,
    cache_entry_2,
)
from .cache_utils import fill_in_conversations


def test_memory_cache_empty_cache(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving existing items."""
    # this UUID is different from DEFAULT_USER_UID
    benchmark(
        memory_cache_fixture.get,
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        CONVERSATION_ID_1,
    )


def test_memory_cache_existing_user(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving existing items."""
    # this UUID is different from DEFAULT_USER_UID
    memory_cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID_1,
        cache_entry_1,
    )
    memory_cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID_2,
        cache_entry_2,
    )
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_short_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, SHORT_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_medium_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, MEDIUM_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_long_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_extra_long_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 10, EXTRA_LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_short_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, SHORT_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_medium_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, MEDIUM_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_long_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_extra_long_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 100, EXTRA_LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_short_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, SHORT_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_medium_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, MEDIUM_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_long_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_extra_long_conversations_key_at_end(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    fill_in_conversations(memory_cache_fixture, 1000, EXTRA_LONG_CONVERSATION_ENTRIES)
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_short_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 10, SHORT_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_medium_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 10, MEDIUM_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_long_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 10, LONG_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_10_extra_long_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 10, EXTRA_LONG_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_short_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 100, SHORT_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_medium_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 100, MEDIUM_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_long_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 100, LONG_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_100_extra_long_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 100, EXTRA_LONG_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_short_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 1000, SHORT_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_medium_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 1000, MEDIUM_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_long_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 1000, LONG_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )


def test_memory_cache_1000_extra_long_conversations_key_at_beginning(
    memory_cache_fixture: InMemoryCache, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for deleting an existing conversation."""
    memory_cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID_1, cache_entry_1)
    fill_in_conversations(memory_cache_fixture, 1000, EXTRA_LONG_CONVERSATION_ENTRIES)
    benchmark(
        memory_cache_fixture.get,
        USER_ID,
        CONVERSATION_ID_1,
    )
