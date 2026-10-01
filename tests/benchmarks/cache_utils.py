"""Common utilities used by cache benchmarks."""

from datetime import UTC, datetime, timedelta

from cache.cache_entry import CacheEntry
from cache.noop_cache import NoopCache
from utils import suid


def fill_in_conversations(noop_cache: NoopCache, items: int, entries: int) -> None:
    """Fill-in cache by conversations."""
    for _ in range(items):
        user_id = suid.get_suid()
        conversation_id = suid.get_suid()
        for i in range(entries):
            # construct timestamps in string format
            now = datetime.now(tz=UTC)
            started = now - timedelta(minutes=5)
            started_str = started.strftime("%Y-%m-%d %H:%M:%S")
            completed = now
            completed_str = completed.strftime("%Y-%m-%d %H:%M:%S")

            # cache entry record
            cache_entry = CacheEntry(
                query=f"user message{i}",
                response=f"AI message{i}",
                provider="foo",
                model="bar",
                started_at=started_str,
                completed_at=completed_str,
            )

            # insert cache entry record into database
            noop_cache.insert_or_append(user_id, conversation_id, cache_entry)
