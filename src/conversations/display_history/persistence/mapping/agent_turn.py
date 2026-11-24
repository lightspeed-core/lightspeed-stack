"""Map stored turn rows onto the public agent-turn contract."""

from __future__ import annotations

from conversations.display_history.agentic.models.agent_turn import AgentTurn
from conversations.display_history.persistence.models import UserAgenticTurn, UserTurn


def map_agent_turn(turn: UserTurn, agentic_turn: UserAgenticTurn) -> AgentTurn:
    """Join a turn envelope and agentic row into a public agent turn.

    Args:
        turn: Turn envelope (provider, model, timestamps, run id).
        agentic_turn: Agentic display row for the same turn number.

    Returns:
        Public agent turn for the conversation timeline.

    """
    return AgentTurn.model_validate(
        {
            "id": turn.response_id,
            "status": agentic_turn.status,
            "agent": agentic_turn.agent,
            "provider": turn.provider,
            "model": turn.model,
            "started_at": turn.started_at,
            "completed_at": turn.completed_at,
            "context_status": agentic_turn.context_status,
            "usage": {
                "input_tokens": agentic_turn.input_tokens,
                "output_tokens": agentic_turn.output_tokens,
            },
            "referenced_documents": agentic_turn.referenced_documents,
            "input": agentic_turn.input_items,
            "output": agentic_turn.output_items,
        }
    )


def map_chat_history(
    turns: list[UserTurn],
    agentic_turns: list[UserAgenticTurn],
) -> list[AgentTurn]:
    """Build ordered chat history by matching turn number.

    Args:
        turns: Turn envelopes for the conversation.
        agentic_turns: Agentic rows for the same conversation.

    Returns:
        Public agent turns in turn-number order.

    """
    agentic_by_number = {row.turn_number: row for row in agentic_turns}
    history: list[AgentTurn] = []
    for turn in turns:
        agentic = agentic_by_number.get(turn.turn_number)
        if agentic is None or not turn.response_id:
            continue
        history.append(map_agent_turn(turn, agentic))
    return history
