"""Tests for conversations.display_history.agentic.models.agent_turn."""

from datetime import UTC, datetime

import pytest
from pydantic import AnyUrl, ValidationError

from conversations.display_history.agentic.models import AgentTurn, TurnItem
from conversations.display_history.agentic.models.content import TextContentPart
from conversations.display_history.agentic.models.turn_items import (
    MessageTurnItem,
    SourceChunk,
    SourcesTurnItem,
)
from models.common.turn_summary import ReferencedDocument


class TestAgentTurnStatus:
    """Public turn status must match AgentTurnStatus literals."""

    def test_blocked_status_rejected(self) -> None:
        """blocked is not a valid public status."""
        with pytest.raises(ValidationError):
            AgentTurn(
                id="resp_blocked",
                status="blocked",  # type: ignore[arg-type]
                provider="openai",
                model="gpt-4",
                started_at=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
                completed_at=datetime(2024, 1, 1, 0, 1, 5, tzinfo=UTC),
                context_status="full",
            )


class TestAgentTurnCitations:
    """Turn-level referenced documents."""

    def test_referenced_documents_on_turn(self) -> None:
        """Citations live on the turn alongside compacted context."""
        doc = ReferencedDocument(
            doc_title="OpenShift Docs",
            doc_url=AnyUrl("https://docs.openshift.com/"),
        )
        output: list[TurnItem] = [
            SourcesTurnItem(
                id="s1",
                origin="auto",
                chunks=[
                    SourceChunk(content="A Route exposes...", source="docs"),
                ],
            ),
            MessageTurnItem(
                id="a1",
                role="assistant",
                content=[TextContentPart(text="A Route is...")],
            ),
        ]
        turn = AgentTurn(
            id="resp_rag",
            status="completed",
            provider="openai",
            model="gpt-4",
            started_at=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            completed_at=datetime(2024, 1, 1, 0, 1, 5, tzinfo=UTC),
            context_status="compacted",
            referenced_documents=[doc],
            input=[
                MessageTurnItem(
                    id="u1",
                    role="user",
                    content=[TextContentPart(text="Explain routes")],
                )
            ],
            output=output,
        )
        assert turn.referenced_documents[0].doc_title == "OpenShift Docs"
