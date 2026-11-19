"""Tests for mapping stored turn rows onto AgentTurn."""

from conversations.display_history.agentic.models.turn_items import MessageTurnItem
from conversations.display_history.persistence.mapping.agent_turn import (
    map_agent_turn,
    map_chat_history,
)
from conversations.display_history.persistence.models import UserAgenticTurn, UserTurn
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_TURN,
    TEST_CONVERSATION_ID,
    TEST_RESPONSE_ID,
    TEST_TURN_NUMBER,
    new_turn,
)


def _agentic_row(
    *,
    turn_number: int = TEST_TURN_NUMBER,
    input_tokens: int = 4,
    output_tokens: int = 6,
) -> UserAgenticTurn:
    user_item = MessageTurnItem(id="u1", role="user", content=[])
    assistant_item = MessageTurnItem(id="a1", role="assistant", content=[])
    return UserAgenticTurn(
        conversation_id=TEST_CONVERSATION_ID,
        turn_number=turn_number,
        status="completed",
        agent=None,
        context_status="compacted",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        referenced_documents=[{"doc_title": "OpenShift Docs", "doc_url": None}],
        input_items=[user_item.model_dump(mode="json")],
        output_items=[assistant_item.model_dump(mode="json")],
    )


def test_map_agent_turn_joins_envelope_and_row() -> None:
    """Public AgentTurn merges envelope fields with agentic JSON columns."""
    turn = new_turn()
    mapped = map_agent_turn(turn, _agentic_row())
    assert mapped.id == TEST_RESPONSE_ID
    assert mapped.provider == turn.provider
    assert mapped.model == turn.model
    assert mapped.started_at == turn.started_at
    assert mapped.completed_at == turn.completed_at
    assert mapped.status == "completed"
    assert mapped.context_status == "compacted"
    assert mapped.usage.input_tokens == 4
    assert mapped.usage.output_tokens == 6
    assert mapped.input[0].id == "u1"
    assert mapped.output[0].id == "a1"
    assert mapped.referenced_documents[0].doc_title == "OpenShift Docs"


def _turn(*, turn_number: int, response_id: str | None) -> UserTurn:
    """Build a turn envelope, including the legacy no-response-id case."""
    return UserTurn(
        **{
            **SAMPLE_TURN,
            "turn_number": turn_number,
            "response_id": response_id,
        }
    )


def test_map_chat_history_skips_incomplete_turns() -> None:
    """Turns without agentic data or a response id are omitted."""
    history = map_chat_history(
        [
            new_turn(),
            _turn(turn_number=2, response_id=TEST_RESPONSE_ID),
            _turn(turn_number=3, response_id=None),
        ],
        [_agentic_row(turn_number=1), _agentic_row(turn_number=3)],
    )
    assert len(history) == 1
    assert history[0].id == TEST_RESPONSE_ID
