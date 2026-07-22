"""Unit tests for InMemoryCache class — conversation compaction summaries (LCORE-1571).

The in-memory cache is a non-persisting implementation (its ``get`` returns an
empty list and ``insert_or_append`` is a no-op). The summary operations follow
the same contract: ``store_summary`` validates the key but does not persist, and
``get_summaries`` always returns an empty list.
"""

import pytest

from lightspeed_stack.cache.in_memory_cache import InMemoryCache
from lightspeed_stack.models.compaction import ConversationSummary
from lightspeed_stack.models.config import InMemoryCacheConfig
from lightspeed_stack.utils import suid

USER_ID = suid.get_suid()
CONVERSATION_ID = suid.get_suid()

summary_1 = ConversationSummary(
    summary_text="Summary chunk for the in-memory cache test.",
    summarized_through_turn=8,
    token_count=9,
    created_at="2025-10-03T09:31:29Z",
    model_used="openai/gpt-4o-mini",
)


@pytest.fixture(name="cache_fixture")
def cache() -> InMemoryCache:
    """Construct an initialized in-memory cache for tests."""
    c = InMemoryCache(InMemoryCacheConfig(max_entries=100))
    c.initialize_cache()
    return c


def test_store_summary_is_noop(cache_fixture: InMemoryCache) -> None:
    """store_summary accepts a summary without persisting (in-memory cache)."""
    cache_fixture.store_summary(USER_ID, CONVERSATION_ID, summary_1)


def test_get_summaries_returns_empty(cache_fixture: InMemoryCache) -> None:
    """get_summaries always returns an empty list for the in-memory cache."""
    cache_fixture.store_summary(USER_ID, CONVERSATION_ID, summary_1)
    assert cache_fixture.get_summaries(USER_ID, CONVERSATION_ID) == []


def test_store_summary_validates_conversation_id(cache_fixture: InMemoryCache) -> None:
    """store_summary validates the conversation ID like the other operations."""
    with pytest.raises(ValueError, match="Invalid conversation ID"):
        cache_fixture.store_summary(USER_ID, "not-a-valid-uuid", summary_1)


def test_get_summaries_validates_conversation_id(cache_fixture: InMemoryCache) -> None:
    """get_summaries validates the conversation ID like the other operations."""
    with pytest.raises(ValueError, match="Invalid conversation ID"):
        cache_fixture.get_summaries(USER_ID, "not-a-valid-uuid")


def test_replace_summaries_is_noop(cache_fixture: InMemoryCache) -> None:
    """replace_summaries accepts a fold without persisting (in-memory cache)."""
    cache_fixture.replace_summaries(USER_ID, CONVERSATION_ID, summary_1)
    assert cache_fixture.get_summaries(USER_ID, CONVERSATION_ID) == []


def test_replace_summaries_validates_conversation_id(
    cache_fixture: InMemoryCache,
) -> None:
    """replace_summaries validates the conversation ID like the other operations."""
    with pytest.raises(ValueError, match="Invalid conversation ID"):
        cache_fixture.replace_summaries(USER_ID, "not-a-valid-uuid", summary_1)
