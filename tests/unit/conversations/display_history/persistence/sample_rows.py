"""Fixed conversation and turn records for persistence tests."""

from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy.orm import Session

from conversations.display_history.persistence.models import UserConversation, UserTurn

TEST_INSTANT: Final[datetime] = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)

TEST_CONVERSATION_ID: Final[str] = "conv-1"
TEST_USER_ID: Final[str] = "user-1"
TEST_OTHER_USER_ID: Final[str] = "user-2"
TEST_TURN_NUMBER: Final[int] = 1
TEST_RESPONSE_ID: Final[str] = "resp-1"

SAMPLE_CONVERSATION: Final[dict[str, Any]] = {
    "id": TEST_CONVERSATION_ID,
    "user_id": TEST_USER_ID,
    "last_used_model": "gpt-4",
    "last_used_provider": "openai",
    "topic_summary": "Initial topic",
    "message_count": 0,
    "last_response_id": None,
}

SAMPLE_TURN: Final[dict[str, Any]] = {
    "conversation_id": TEST_CONVERSATION_ID,
    "turn_number": TEST_TURN_NUMBER,
    "started_at": TEST_INSTANT,
    "completed_at": TEST_INSTANT,
    "provider": "openai",
    "model": "gpt-4",
    "response_id": TEST_RESPONSE_ID,
}

SAMPLE_AGENTIC_INPUT_ITEMS: Final[list[dict[str, Any]]] = [
    {"id": "u1", "kind": "message", "role": "user", "content": []},
]


def new_conversation() -> UserConversation:
    """Return a fresh UserConversation from SAMPLE_CONVERSATION."""
    return UserConversation(**SAMPLE_CONVERSATION)


def new_turn() -> UserTurn:
    """Return a fresh UserTurn from SAMPLE_TURN."""
    return UserTurn(**SAMPLE_TURN)


def seed_sample_conversation_and_turn(session: Session) -> tuple[str, int]:
    """Insert the sample conversation and turn using an open SQLAlchemy session.

    Use this when a test needs parent rows (foreign keys) before exercising turn
    or agentic persistence. Repository tests call this on the in-memory engine;
    they do not run automatically.

    Returns:
        The sample conversation id and turn number.

    """
    session.add(new_conversation())
    session.add(new_turn())
    session.commit()
    return TEST_CONVERSATION_ID, TEST_TURN_NUMBER
