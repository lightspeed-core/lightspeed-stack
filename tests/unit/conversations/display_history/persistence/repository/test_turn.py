"""Turn repository tests."""

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.display_history.persistence.repository.turn import (
    get_turn,
    get_turn_by_response_id,
    insert_turn,
    list_turns_for_conversation,
    max_turn_number_for_conversation,
    turn_exists_for_response_id,
)
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_TURN,
    TEST_CONVERSATION_ID,
    TEST_INSTANT,
    TEST_RESPONSE_ID,
    TEST_TURN_NUMBER,
    seed_sample_conversation_and_turn,
)


@pytest.mark.usefixtures("patch_display_history_session")
def test_turn_repository_round_trip(memory_engine: Engine) -> None:
    """Covers turn queries and insert."""
    assert max_turn_number_for_conversation("missing-conv") == 0

    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)

    loaded = get_turn(TEST_CONVERSATION_ID, TEST_TURN_NUMBER)
    assert loaded is not None
    assert loaded.response_id == TEST_RESPONSE_ID
    assert get_turn(TEST_CONVERSATION_ID, 99) is None

    assert get_turn_by_response_id(TEST_RESPONSE_ID) is not None
    assert get_turn_by_response_id("unknown") is None

    assert turn_exists_for_response_id(TEST_RESPONSE_ID) is True
    assert turn_exists_for_response_id("unknown") is False

    second = insert_turn(
        TEST_CONVERSATION_ID,
        2,
        TEST_INSTANT,
        TEST_INSTANT,
        "openai",
        "gpt-4",
        "resp-2",
    )
    assert second.turn_number == 2

    listed = list_turns_for_conversation(TEST_CONVERSATION_ID)
    assert [t.turn_number for t in listed] == [1, 2]
    assert list_turns_for_conversation("missing") == []

    assert max_turn_number_for_conversation(TEST_CONVERSATION_ID) == 2

    assert SAMPLE_TURN["model"] == loaded.model
