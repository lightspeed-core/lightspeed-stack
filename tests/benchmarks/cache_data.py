"""Data used by cache benchmarks."""

from cache.cache_entry import CacheEntry
from utils import suid

USER_ID = suid.get_suid()
CONVERSATION_ID_1 = suid.get_suid()
CONVERSATION_ID_2 = suid.get_suid()
USER_PROVIDED_USER_ID = "test-user1"
cache_entry_1 = CacheEntry(
    query="user message1",
    response="AI message1",
    provider="foo",
    model="bar",
    started_at="2025-10-03T09:31:25Z",
    completed_at="2025-10-03T09:31:29Z",
)
cache_entry_2 = CacheEntry(
    query="user message2",
    response="AI message2",
    provider="foo",
    model="bar",
    started_at="2025-10-03T09:31:25Z",
    completed_at="2025-10-03T09:31:29Z",
)
