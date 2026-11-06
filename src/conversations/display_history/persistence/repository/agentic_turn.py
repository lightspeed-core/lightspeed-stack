"""Load, create, and delete agentic turn display records."""

from typing import Any, Optional

from conversations.display_history.persistence.models import UserAgenticTurn
from conversations.display_history.persistence.session import display_history_session


def get_agentic_turn(
    conversation_id: str,
    turn_number: int,
) -> Optional[UserAgenticTurn]:
    """Load agentic display data for a turn, or None if missing."""
    with display_history_session("load agentic turn") as session:
        return session.get(UserAgenticTurn, (conversation_id, turn_number))


def list_agentic_turns_for_conversation(conversation_id: str) -> list[UserAgenticTurn]:
    """List agentic display records for a conversation in turn-number order."""
    with display_history_session("list agentic turns") as session:
        return (
            session.query(UserAgenticTurn)
            .filter_by(conversation_id=conversation_id)
            .order_by(UserAgenticTurn.turn_number)
            .all()
        )


def insert_agentic_turn(  # pylint: disable=too-many-arguments
    conversation_id: str,
    turn_number: int,
    *,
    referenced_documents: list[dict[str, Any]],
    input_items: list[dict[str, Any]],
    output_items: list[dict[str, Any]],
    status: str = "completed",
    agent: Optional[str] = None,
    context_status: str = "full",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> UserAgenticTurn:
    """Create an agentic display record and return the saved row."""
    with display_history_session("insert agentic turn") as session:
        row = UserAgenticTurn(
            conversation_id=conversation_id,
            turn_number=turn_number,
            status=status,
            agent=agent,
            context_status=context_status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            referenced_documents=referenced_documents,
            input_items=input_items,
            output_items=output_items,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def delete_agentic_turn(conversation_id: str, turn_number: int) -> bool:
    """Delete agentic display data for a turn. Returns True if one was removed."""
    with display_history_session("delete agentic turn") as session:
        row = session.get(UserAgenticTurn, (conversation_id, turn_number))
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
