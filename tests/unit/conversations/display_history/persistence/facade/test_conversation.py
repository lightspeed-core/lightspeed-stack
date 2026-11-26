"""Tests for the conversation persistence facade."""

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.display_history.agentic.models.agent_turn_summary import (
    AgentTurnSummary,
)
from conversations.display_history.agentic.models.turn_items import MessageTurnItem
from conversations.display_history.errors import (
    ConversationAccessDeniedError,
    ConversationNotFoundError,
)
from conversations.display_history.persistence.facade.conversation import (
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation_topic,
)
from conversations.display_history.persistence.repository.agentic_turn import (
    insert_agentic_turn,
)
from conversations.display_history.persistence.repository.conversation import (
    get_conversation_by_id,
    insert_conversation,
)
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_CONVERSATION,
    TEST_CONVERSATION_ID,
    TEST_OTHER_USER_ID,
    TEST_TURN_NUMBER,
    TEST_USER_ID,
    seed_sample_conversation_and_turn,
)


def _seed_agentic_turn() -> None:
    """Attach display items to the sample turn envelope."""
    insert_agentic_turn(
        TEST_CONVERSATION_ID,
        TEST_TURN_NUMBER,
        AgentTurnSummary(
            status="completed",
            input=[
                MessageTurnItem(id="u1", role="user", content=[]),
            ],
            output=[
                MessageTurnItem(id="a1", role="assistant", content=[]),
            ],
        ),
    )


@pytest.mark.usefixtures("patch_display_history_session")
def test_list_conversations_for_owner(memory_engine: Engine) -> None:
    """Owners see only their conversations when others are not allowed."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    insert_conversation(
        "conv-2",
        TEST_OTHER_USER_ID,
        "gpt-4",
        "openai",
        "Other topic",
        0,
        None,
    )

    listed = list_conversations(TEST_USER_ID, False)
    assert len(listed) == 1
    assert listed[0].conversation_id == TEST_CONVERSATION_ID
    assert listed[0].topic_summary == SAMPLE_CONVERSATION["topic_summary"]
    assert listed[0].last_used_model == "gpt-4"


@pytest.mark.usefixtures("patch_display_history_session")
def test_list_conversations_includes_others_when_allowed(
    memory_engine: Engine,
) -> None:
    """Privileged callers receive every stored conversation."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    insert_conversation(
        "conv-2",
        TEST_OTHER_USER_ID,
        "gpt-4",
        "openai",
        "Other topic",
        0,
        None,
    )

    listed = list_conversations(TEST_USER_ID, True)
    assert {row.conversation_id for row in listed} == {
        TEST_CONVERSATION_ID,
        "conv-2",
    }


@pytest.mark.usefixtures("patch_display_history_session")
def test_get_conversation_assembles_agent_turns(memory_engine: Engine) -> None:
    """GET joins the turn envelope with persisted agentic items."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    _seed_agentic_turn()

    conversation = get_conversation(TEST_CONVERSATION_ID, TEST_USER_ID, False)
    assert conversation.conversation_id == TEST_CONVERSATION_ID
    assert len(conversation.chat_history) == 1
    turn = conversation.chat_history[0]
    assert turn.id == "resp-1"
    assert turn.status == "completed"
    assert turn.provider == "openai"
    assert turn.model == "gpt-4"
    assert turn.input[0].id == "u1"
    assert turn.output[0].id == "a1"


@pytest.mark.usefixtures("patch_display_history_session")
def test_get_conversation_skips_turns_without_agentic_data(
    memory_engine: Engine,
) -> None:
    """Envelope-only turns are omitted from the v3 timeline."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)

    conversation = get_conversation(TEST_CONVERSATION_ID, TEST_USER_ID, False)
    assert conversation.chat_history == []


@pytest.mark.usefixtures("patch_display_history_session")
def test_get_conversation_forbidden(memory_engine: Engine) -> None:
    """Non-owners cannot read another user's conversation."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    with pytest.raises(ConversationAccessDeniedError):
        get_conversation(TEST_CONVERSATION_ID, TEST_OTHER_USER_ID, False)


@pytest.mark.usefixtures("patch_display_history_session")
def test_get_conversation_not_found() -> None:
    """Missing conversations raise ConversationNotFoundError."""
    with pytest.raises(ConversationNotFoundError):
        get_conversation("missing-conv", TEST_USER_ID, True)


@pytest.mark.usefixtures("patch_display_history_session")
def test_delete_conversation_owner(memory_engine: Engine) -> None:
    """Owners can delete their conversation."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    assert delete_conversation(TEST_CONVERSATION_ID, TEST_USER_ID, False) is True
    assert get_conversation_by_id(TEST_CONVERSATION_ID) is None


@pytest.mark.usefixtures("patch_display_history_session")
def test_delete_conversation_missing_is_not_found() -> None:
    """Deleting a missing conversation returns False rather than 404 at this layer."""
    assert delete_conversation("missing-conv", TEST_USER_ID, False) is False


@pytest.mark.usefixtures("patch_display_history_session")
def test_delete_conversation_forbidden(memory_engine: Engine) -> None:
    """Non-owners cannot delete another user's conversation."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    with pytest.raises(ConversationAccessDeniedError):
        delete_conversation(TEST_CONVERSATION_ID, TEST_OTHER_USER_ID, False)
    assert get_conversation_by_id(TEST_CONVERSATION_ID) is not None


@pytest.mark.usefixtures("patch_display_history_session")
def test_update_conversation_topic(memory_engine: Engine) -> None:
    """Owners can replace the topic summary."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    assert (
        update_conversation_topic(
            TEST_CONVERSATION_ID,
            TEST_USER_ID,
            False,
            "Updated topic",
        )
        is True
    )
    loaded = get_conversation_by_id(TEST_CONVERSATION_ID)
    assert loaded is not None
    assert loaded.topic_summary == "Updated topic"


@pytest.mark.usefixtures("patch_display_history_session")
def test_update_conversation_topic_not_found() -> None:
    """Updating a missing conversation raises ConversationNotFoundError."""
    with pytest.raises(ConversationNotFoundError):
        update_conversation_topic("missing-conv", TEST_USER_ID, True, "x")
