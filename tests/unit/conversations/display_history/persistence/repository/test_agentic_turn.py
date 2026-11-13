"""Agentic turn repository tests."""

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.display_history.persistence.repository.agentic_turn import (
    delete_agentic_turn,
    get_agentic_turn,
    insert_agentic_turn,
    list_agentic_turns_for_conversation,
)
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_AGENTIC_INPUT_ITEMS,
    TEST_CONVERSATION_ID,
    TEST_TURN_NUMBER,
    seed_sample_conversation_and_turn,
)


@pytest.mark.usefixtures("patch_display_history_session")
def test_agentic_turn_repository_round_trip(memory_engine: Engine) -> None:
    """Covers insert, get, list, and delete."""
    with Session(memory_engine) as session:
        conversation_id, turn_number = seed_sample_conversation_and_turn(session)

    inserted = insert_agentic_turn(
        conversation_id,
        turn_number,
        referenced_documents=[],
        input_items=SAMPLE_AGENTIC_INPUT_ITEMS,
        output_items=[],
        status="completed",
    )
    assert inserted.status == "completed"

    loaded = get_agentic_turn(conversation_id, turn_number)
    assert loaded is not None
    assert loaded.input_items[0]["id"] == "u1"

    listed = list_agentic_turns_for_conversation(conversation_id)
    assert len(listed) == 1

    assert delete_agentic_turn(conversation_id, turn_number) is True
    assert get_agentic_turn(conversation_id, turn_number) is None
    assert delete_agentic_turn(conversation_id, turn_number) is False
    assert get_agentic_turn(TEST_CONVERSATION_ID, TEST_TURN_NUMBER) is None
