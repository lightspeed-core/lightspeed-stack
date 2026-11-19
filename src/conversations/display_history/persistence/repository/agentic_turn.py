"""Load, create, and delete agentic turn display records."""

from typing import Optional

from conversations.display_history.agentic.models.agent_turn_summary import (
    AgentTurnSummary,
)
from conversations.display_history.persistence.models import UserAgenticTurn
from conversations.display_history.persistence.session import display_history_session


def get_agentic_turn(
    conversation_id: str,
    turn_number: int,
) -> Optional[UserAgenticTurn]:
    """Load agentic display data for one turn.

    Returns:
        Stored row, or None when missing.

    """
    with display_history_session("load agentic turn") as session:
        return session.get(UserAgenticTurn, (conversation_id, turn_number))


def list_agentic_turns_for_conversation(conversation_id: str) -> list[UserAgenticTurn]:
    """List agentic turns for a conversation in turn order."""
    with display_history_session("list agentic turns") as session:
        return (
            session.query(UserAgenticTurn)
            .filter_by(conversation_id=conversation_id)
            .order_by(UserAgenticTurn.turn_number)
            .all()
        )


def insert_agentic_turn(
    conversation_id: str,
    turn_number: int,
    summary: AgentTurnSummary,
) -> UserAgenticTurn:
    """Create an agentic turn row from a projection summary.

    Returns:
        The persisted row.

    """
    with display_history_session("insert agentic turn") as session:
        row = UserAgenticTurn(
            conversation_id=conversation_id,
            turn_number=turn_number,
            status=summary.status,
            agent=summary.agent,
            context_status=summary.context_status,
            input_tokens=summary.input_tokens,
            output_tokens=summary.output_tokens,
            referenced_documents=[
                doc.model_dump(mode="json") for doc in summary.referenced_documents
            ],
            input_items=[item.model_dump(mode="json") for item in summary.input],
            output_items=[item.model_dump(mode="json") for item in summary.output],
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def delete_agentic_turn(conversation_id: str, turn_number: int) -> bool:
    """Delete agentic display data for one turn.

    Returns:
        True when a row was removed.

    """
    with display_history_session("delete agentic turn") as session:
        row = session.get(UserAgenticTurn, (conversation_id, turn_number))
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
