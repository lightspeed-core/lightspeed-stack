"""Load and create turn records for display history."""

from datetime import datetime
from typing import Optional

from sqlalchemy import func

from conversations.display_history.persistence.session import display_history_session
from models.database.conversations import UserTurn


def get_turn(conversation_id: str, turn_number: int) -> Optional[UserTurn]:
    """Load a turn by conversation id and turn number, or None if missing."""
    with display_history_session("load turn") as session:
        return session.get(UserTurn, (conversation_id, turn_number))


def get_turn_by_response_id(response_id: str) -> Optional[UserTurn]:
    """Load a turn by response id, or None if missing."""
    with display_history_session("load turn by response") as session:
        return session.query(UserTurn).filter_by(response_id=response_id).first()


def turn_exists_for_response_id(response_id: str) -> bool:
    """Return whether a turn exists for the given response id."""
    with display_history_session("check turn exists") as session:
        return (
            session.query(UserTurn).filter_by(response_id=response_id).first()
            is not None
        )


def list_turns_for_conversation(conversation_id: str) -> list[UserTurn]:
    """List turns for a conversation in turn-number order."""
    with display_history_session("list turns") as session:
        return (
            session.query(UserTurn)
            .filter_by(conversation_id=conversation_id)
            .order_by(UserTurn.turn_number)
            .all()
        )


def max_turn_number_for_conversation(conversation_id: str) -> int:
    """Return the highest turn number in the conversation, or 0 if there are none."""
    with display_history_session("resolve max turn number") as session:
        value = (
            session.query(func.max(UserTurn.turn_number))
            .filter_by(conversation_id=conversation_id)
            .scalar()
        )
        return int(value or 0)


def insert_turn(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    conversation_id: str,
    turn_number: int,
    started_at: datetime,
    completed_at: datetime,
    provider: str,
    model: str,
    response_id: Optional[str],
) -> UserTurn:
    """Create a turn and return the saved record."""
    with display_history_session("insert turn") as session:
        turn = UserTurn(
            conversation_id=conversation_id,
            turn_number=turn_number,
            started_at=started_at,
            completed_at=completed_at,
            provider=provider,
            model=model,
            response_id=response_id,
        )
        session.add(turn)
        session.commit()
        session.refresh(turn)
        return turn
