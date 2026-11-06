"""UserAgenticTurn ORM tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from conversations.display_history.persistence.models import UserAgenticTurn, UserTurn
from models.database.base import Base
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_TURN,
    TEST_CONVERSATION_ID,
    seed_sample_conversation_and_turn,
)


def test_user_agentic_turn_persists_with_shared_envelope() -> None:
    """Saves agentic fields and enforces the user_turn foreign key."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_sample_conversation_and_turn(session)
        session.add(
            UserAgenticTurn(
                conversation_id=TEST_CONVERSATION_ID,
                turn_number=1,
                status="awaiting_input",
                context_status="full",
                input_tokens=10,
                output_tokens=5,
                referenced_documents=[
                    {"doc_title": "Docs", "doc_url": "https://example.com/"}
                ],
                input_items=[
                    {
                        "id": "u1",
                        "kind": "message",
                        "role": "user",
                        "content": [{"type": "text", "text": "Hi"}],
                    }
                ],
                output_items=[],
            )
        )
        session.commit()

        loaded = session.get(UserAgenticTurn, ("conv-1", 1))
        assert loaded is not None
        assert loaded.status == "awaiting_input"
        assert loaded.input_tokens == 10
        assert loaded.input_items[0]["kind"] == "message"
        assert loaded.referenced_documents[0]["doc_title"] == "Docs"

        loaded_turn = session.get(UserTurn, ("conv-1", 1))
        assert loaded_turn is not None
        assert loaded_turn.response_id == SAMPLE_TURN["response_id"]
