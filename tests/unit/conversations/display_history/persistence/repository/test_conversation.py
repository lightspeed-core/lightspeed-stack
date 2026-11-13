"""Conversation repository tests."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.display_history.persistence.repository.conversation import (
    delete_conversation,
    get_conversation_by_id,
    get_conversation_owner_user_id,
    insert_conversation,
    list_conversations,
    list_conversations_for_user,
    update_conversation_metadata,
    update_conversation_topic_summary,
)
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_CONVERSATION,
    TEST_CONVERSATION_ID,
    TEST_OTHER_USER_ID,
    TEST_USER_ID,
    seed_sample_conversation_and_turn,
)


@pytest.mark.usefixtures("patch_display_history_session")
def test_conversation_repository_round_trip(memory_engine: Engine) -> None:
    """Covers create, read, update, and delete paths."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)

    other = insert_conversation(
        "conv-2",
        TEST_OTHER_USER_ID,
        "gpt-4",
        "openai",
        "",
        0,
        None,
    )
    assert other.user_id == TEST_OTHER_USER_ID

    loaded = get_conversation_by_id(TEST_CONVERSATION_ID)
    assert loaded is not None
    assert loaded.topic_summary == SAMPLE_CONVERSATION["topic_summary"]
    assert get_conversation_by_id("missing") is None

    assert get_conversation_owner_user_id(TEST_CONVERSATION_ID) == TEST_USER_ID
    assert get_conversation_owner_user_id("missing") is None

    by_user = list_conversations_for_user(TEST_USER_ID)
    assert len(by_user) == 1
    other_user_rows = list_conversations_for_user(TEST_OTHER_USER_ID)
    assert len(other_user_rows) == 1
    assert other_user_rows[0].id == "conv-2"

    all_conversations = list_conversations()
    assert len(all_conversations) == 2

    assert update_conversation_topic_summary(TEST_CONVERSATION_ID, "Updated summary")
    reloaded = get_conversation_by_id(TEST_CONVERSATION_ID)
    assert reloaded is not None
    assert reloaded.topic_summary == "Updated summary"
    assert update_conversation_topic_summary("missing", "x") is False

    at = datetime(2025, 7, 1, tzinfo=UTC)
    assert (
        update_conversation_metadata(
            TEST_CONVERSATION_ID,
            last_used_model="gpt-4o",
            last_used_provider="openai",
            last_message_at=at,
            last_response_id="resp-2",
        )
        is True
    )
    meta_updated = get_conversation_by_id(TEST_CONVERSATION_ID)
    assert meta_updated is not None
    assert meta_updated.last_used_model == "gpt-4o"
    assert meta_updated.message_count == 1
    assert meta_updated.last_response_id == "resp-2"

    assert (
        update_conversation_metadata(
            TEST_CONVERSATION_ID,
            last_used_model="gpt-4o",
            last_used_provider="openai",
            last_message_at=at,
            last_response_id=None,
        )
        is True
    )
    skipped_pointer = get_conversation_by_id(TEST_CONVERSATION_ID)
    assert skipped_pointer is not None
    assert skipped_pointer.last_response_id == "resp-2"
    assert skipped_pointer.message_count == 2
    assert (
        update_conversation_metadata(
            "missing",
            last_used_model="m",
            last_used_provider="p",
            last_message_at=at,
            last_response_id=None,
        )
        is False
    )

    assert delete_conversation("conv-2") is True
    assert get_conversation_by_id("conv-2") is None
    assert delete_conversation("missing") is False

    assert delete_conversation(TEST_CONVERSATION_ID) is True
    assert get_conversation_by_id(TEST_CONVERSATION_ID) is None
