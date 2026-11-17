"""Tests for display_history.context_resolution."""

from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.agent_history.ids import with_conversation_prefix
from conversations.display_history.context_resolution import (
    is_conversation_tip,
    plan_conversation_continuation,
    plan_previous_response_continuation,
)
from conversations.display_history.errors import (
    ConversationAccessDeniedError,
    TurnNotFoundError,
)
from conversations.display_history.persistence.models import UserConversation
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_CONVERSATION,
    SAMPLE_TURN,
    TEST_CONVERSATION_ID,
    seed_sample_conversation_and_turn,
)


@pytest.mark.parametrize(
    ("last_response_id", "previous_response_id", "expected"),
    [
        (None, "resp-1", True),
        ("resp-1", "resp-1", True),
        ("resp-newer", "resp-1", False),
    ],
)
def test_is_conversation_tip(
    last_response_id: Optional[str],
    previous_response_id: str,
    expected: bool,
) -> None:
    """Tip detection compares the client response to the saved latest response."""
    assert is_conversation_tip(last_response_id, previous_response_id) is expected


@pytest.mark.usefixtures("patch_display_history_session")
def test_plan_conversation_continuation(memory_engine: Engine) -> None:
    """Access check and id normalization yield a continuation plan."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    plan = plan_conversation_continuation(
        with_conversation_prefix(TEST_CONVERSATION_ID),
        SAMPLE_CONVERSATION["user_id"],
        False,
    )
    assert plan.conversation_id == TEST_CONVERSATION_ID


@pytest.mark.usefixtures("patch_display_history_session")
def test_plan_previous_response_continuation_tip(memory_engine: Engine) -> None:
    """When the response is still the tip, continuation does not fork."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
        conversation = session.get(UserConversation, TEST_CONVERSATION_ID)
        assert conversation is not None
        conversation.last_response_id = SAMPLE_TURN["response_id"]
        session.commit()
    plan = plan_previous_response_continuation(
        SAMPLE_TURN["response_id"],
        SAMPLE_CONVERSATION["user_id"],
        False,
    )
    assert plan.conversation_id == SAMPLE_CONVERSATION["id"]
    assert plan.source_response_id == SAMPLE_TURN["response_id"]
    assert not plan.fork


@pytest.mark.usefixtures("patch_display_history_session")
def test_plan_previous_response_continuation_fork(memory_engine: Engine) -> None:
    """When the response is not the tip, continuation forks."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
        conversation = session.get(UserConversation, TEST_CONVERSATION_ID)
        assert conversation is not None
        conversation.last_response_id = "resp-newer"
        session.commit()
    plan = plan_previous_response_continuation(
        SAMPLE_TURN["response_id"],
        SAMPLE_CONVERSATION["user_id"],
        False,
    )
    assert plan.conversation_id == SAMPLE_CONVERSATION["id"]
    assert plan.source_response_id == SAMPLE_TURN["response_id"]
    assert plan.fork


@pytest.mark.usefixtures("patch_display_history_session")
def test_plan_previous_response_unknown_response() -> None:
    """Unknown response ids raise TurnNotFoundError."""
    with pytest.raises(TurnNotFoundError):
        plan_previous_response_continuation("resp-missing", "user-1", True)


@pytest.mark.usefixtures("patch_display_history_session")
def test_plan_previous_response_forbidden(memory_engine: Engine) -> None:
    """Non-owners cannot plan continuation when others are not allowed."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    with pytest.raises(ConversationAccessDeniedError):
        plan_previous_response_continuation(
            SAMPLE_TURN["response_id"],
            "other-user",
            False,
        )
