"""Tests for mapping stored conversation rows onto the v3 envelope."""

from conversations.display_history.agentic.models.turn_items import MessageTurnItem
from conversations.display_history.persistence.mapping.conversation import (
    map_conversation,
    map_conversation_metadata,
)
from conversations.display_history.persistence.models import UserAgenticTurn
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_CONVERSATION,
    TEST_CONVERSATION_ID,
    TEST_INSTANT,
    TEST_RESPONSE_ID,
    TEST_TURN_NUMBER,
    new_conversation,
    new_turn,
)


def test_map_conversation_metadata_renames_envelope_fields() -> None:
    """Stored column names become the public conversation envelope."""
    row = new_conversation()
    row.created_at = TEST_INSTANT
    row.last_message_at = TEST_INSTANT
    row.message_count = 3
    mapped = map_conversation_metadata(row)
    assert mapped.conversation_id == TEST_CONVERSATION_ID
    assert mapped.created_at == TEST_INSTANT
    assert mapped.last_turn_at == TEST_INSTANT
    assert mapped.turn_count == 3
    assert mapped.last_used_model == SAMPLE_CONVERSATION["last_used_model"]
    assert mapped.last_used_provider == SAMPLE_CONVERSATION["last_used_provider"]
    assert mapped.topic_summary == SAMPLE_CONVERSATION["topic_summary"]


def test_map_conversation_metadata_blank_topic_is_none() -> None:
    """An empty stored topic summary is omitted on the public envelope."""
    row = new_conversation()
    row.created_at = TEST_INSTANT
    row.last_message_at = TEST_INSTANT
    row.topic_summary = ""
    assert map_conversation_metadata(row).topic_summary is None


def test_map_conversation_includes_chat_history() -> None:
    """GET mapping attaches ordered agent turns to conversation metadata."""
    row = new_conversation()
    row.created_at = TEST_INSTANT
    row.last_message_at = TEST_INSTANT
    agentic = UserAgenticTurn(
        conversation_id=TEST_CONVERSATION_ID,
        turn_number=TEST_TURN_NUMBER,
        status="completed",
        context_status="full",
        input_tokens=0,
        output_tokens=0,
        referenced_documents=[],
        input_items=[
            MessageTurnItem(id="u1", role="user", content=[]).model_dump(mode="json")
        ],
        output_items=[
            MessageTurnItem(id="a1", role="assistant", content=[]).model_dump(
                mode="json"
            )
        ],
    )
    conversation = map_conversation(row, [new_turn()], [agentic])
    assert conversation.conversation_id == TEST_CONVERSATION_ID
    assert len(conversation.chat_history) == 1
    assert conversation.chat_history[0].id == TEST_RESPONSE_ID
    assert conversation.chat_history[0].input[0].id == "u1"
