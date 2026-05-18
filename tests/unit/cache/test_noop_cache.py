"""Unit tests for NoopCache class."""

from typing import Optional

import pytest

from cache.cache_entry import CacheEntry
from cache.noop_cache import NoopCache
from utils import suid

USER_ID = suid.get_suid()
CONVERSATION_ID = suid.get_suid()
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


@pytest.fixture(name="cache_fixture")
def cache() -> NoopCache:
    """Fixture with constructed and initialized in memory cache object.

    Create and initialize an in-memory NoopCache for use as a test fixture.

    Returns:
        NoopCache: An initialized NoopCache instance ready for tests.
    """
    c = NoopCache()
    c.initialize_cache()
    return c


def test_connect(cache_fixture: NoopCache) -> None:
    """Test the behavior of connect method."""
    cache_fixture.connect()


def test_insert_or_append(cache_fixture: NoopCache) -> None:
    """Test the behavior of insert_or_append method.

    Verify that inserting a CacheEntry for a user and conversation via
    `insert_or_append` completes without raising an exception.

    This confirms the cache accepts the provided `cache_entry_1` for `USER_ID`
    and `CONVERSATION_ID`.
    """
    cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID,
        cache_entry_1,
    )


def test_insert_or_append_skip_user_id_check(cache_fixture: NoopCache) -> None:
    """Test the behavior of insert_or_append method.

    Verify that insert_or_append accepts a non-UUID user identifier when
    skip_user_id_check is True.

    This test calls insert_or_append with a user-provided (non-UUID) user id, a
    conversation id, and a cache entry while passing skip_user_id_check=True;
    the operation is expected to complete without raising an exception.
    """
    skip_user_id_check = True
    cache_fixture.insert_or_append(
        USER_PROVIDED_USER_ID, CONVERSATION_ID, cache_entry_1, skip_user_id_check
    )


def test_insert_or_append_existing_key(cache_fixture: NoopCache) -> None:
    """Test the behavior of insert_or_append method for existing item."""
    cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID,
        cache_entry_1,
    )
    cache_fixture.insert_or_append(
        USER_ID,
        CONVERSATION_ID,
        cache_entry_2,
    )


def test_get_nonexistent_user(cache_fixture: NoopCache) -> None:
    """Test how non-existent items are handled by the cache."""
    # this UUID is different from DEFAULT_USER_UID
    assert (
        cache_fixture.get("ffffffff-ffff-ffff-ffff-ffffffffffff", CONVERSATION_ID) == []
    )


def test_delete_existing_conversation(cache_fixture: NoopCache) -> None:
    """Test deleting an existing conversation."""
    cache_fixture.insert_or_append(USER_ID, CONVERSATION_ID, cache_entry_1)

    result = cache_fixture.delete(USER_ID, CONVERSATION_ID)

    assert result is True


def test_delete_nonexistent_conversation(cache_fixture: NoopCache) -> None:
    """Test deleting a conversation that doesn't exist."""
    result = cache_fixture.delete(USER_ID, CONVERSATION_ID)
    assert result is True


def test_delete_improper_conversation_id(cache_fixture: NoopCache) -> None:
    """Test delete with invalid conversation ID.

    Verify that deleting with an invalid conversation ID raises a ValueError.

    Raises:
        ValueError: If the conversation ID is not a valid UUID (message
        contains "Invalid conversation ID").
    """
    with pytest.raises(ValueError, match="Invalid conversation ID"):
        cache_fixture.delete(USER_ID, "invalid-id")


def test_delete_skip_user_id_check(cache_fixture: NoopCache) -> None:
    """Test deleting an existing conversation.

    Verify that deleting a conversation created with skip_user_id_check=True succeeds.

    Inserts a cache entry for a non-UUID user ID using skip_user_id_check,
    deletes it with the same flag, and asserts the deletion returns True.
    """
    skip_user_id_check = True
    cache_fixture.insert_or_append(
        USER_PROVIDED_USER_ID, CONVERSATION_ID, cache_entry_1, skip_user_id_check
    )

    result = cache_fixture.delete(
        USER_PROVIDED_USER_ID, CONVERSATION_ID, skip_user_id_check
    )

    assert result is True


def test_list_conversations(cache_fixture: NoopCache) -> None:
    """Test listing conversations for a user."""
    # Create multiple conversations
    conversation_id_1 = suid.get_suid()
    conversation_id_2 = suid.get_suid()

    cache_fixture.insert_or_append(USER_ID, conversation_id_1, cache_entry_1)
    cache_fixture.insert_or_append(USER_ID, conversation_id_2, cache_entry_2)

    conversations = cache_fixture.list(USER_ID)

    assert len(conversations) == 0


def test_list_conversations_skip_user_id_check(cache_fixture: NoopCache) -> None:
    """Test listing conversations for a user."""
    # Create multiple conversations
    conversation_id_1 = suid.get_suid()
    conversation_id_2 = suid.get_suid()
    skip_user_id_check = True

    cache_fixture.insert_or_append(
        USER_PROVIDED_USER_ID, conversation_id_1, cache_entry_1, skip_user_id_check
    )
    cache_fixture.insert_or_append(
        USER_PROVIDED_USER_ID, conversation_id_2, cache_entry_2, skip_user_id_check
    )

    conversations = cache_fixture.list(USER_PROVIDED_USER_ID, skip_user_id_check)

    assert len(conversations) == 0


def test_list_no_conversations(cache_fixture: NoopCache) -> None:
    """Test listing conversations for a user with no conversations."""
    conversations = cache_fixture.list(USER_ID)
    assert len(conversations) == 0


def test_ready(cache_fixture: NoopCache) -> None:
    """Test if in memory cache always report ready.

    Verify that the in-memory NoopCache reports readiness.

    Asserts that calling ready() on the provided cache_fixture returns True.
    """
    assert cache_fixture.ready()


improper_user_uuids = [
    None,
    "",
    " ",
    "\t",
    ":",
    "foo:bar",
    "ffffffff-ffff-ffff-ffff-fffffffffff",  # UUID-like string with missing chararacter
    "ffffffff-ffff-ffff-ffff-fffffffffffZ",  # UUID-like string, but with wrong character
    "ffffffff:ffff:ffff:ffff:ffffffffffff",
]


@pytest.mark.parametrize("uuid", improper_user_uuids)
def test_list_improper_user_id(cache_fixture: NoopCache, uuid: Optional[str]) -> None:
    """Test list with invalid user ID.

    Verify that listing conversations raises a ValueError for invalid user IDs.

    Parameters:
        - uuid (Optional[str]): The invalid user-id value to test; the test
          asserts a ValueError with message "Invalid user ID {uuid}".
    """
    with pytest.raises(ValueError, match=f"Invalid user ID {uuid}"):
        cache_fixture.list(uuid)


@pytest.mark.parametrize("uuid", improper_user_uuids)
def test_delete_improper_user_id(cache_fixture: NoopCache, uuid: Optional[str]) -> None:
    """Test delete with invalid user ID."""
    with pytest.raises(ValueError, match=f"Invalid user ID {uuid}"):
        cache_fixture.delete(uuid, CONVERSATION_ID)


@pytest.mark.parametrize("uuid", improper_user_uuids)
def test_get_improper_user_id(cache_fixture: NoopCache, uuid: Optional[str]) -> None:
    """Test how improper user ID is handled."""
    with pytest.raises(ValueError, match=f"Invalid user ID {uuid}"):
        cache_fixture.get(uuid, CONVERSATION_ID)


def test_get_improper_conversation_id(cache_fixture: NoopCache) -> None:
    """Test how improper conversation ID is handled.

    Validate that get() raises a ValueError when the conversation ID is not a valid UUID.

    Calls get() with an invalid conversation ID and expects a ValueError
    containing "Invalid conversation ID".
    """
    with pytest.raises(ValueError, match="Invalid conversation ID"):
        cache_fixture.get(USER_ID, "this-is-not-valid-uuid")
