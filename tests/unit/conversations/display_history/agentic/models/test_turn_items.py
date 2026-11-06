"""Tests for conversations.display_history.agentic.models.turn_items."""

import pytest
from pydantic import ValidationError

from conversations.display_history.agentic.models import AgentTurn
from conversations.display_history.agentic.models.turn_items import (
    ApprovalRequestTurnItem,
    ApprovalResultTurnItem,
    MessageTurnItem,
    SourceChunk,
    SourcesTurnItem,
    ToolCallTurnItem,
    ToolResultTurnItem,
    ToolsetInfo,
)
from tests.unit.conversations.display_history.agentic.models.helpers import (
    assistant_message,
    user_message,
)


class TestSourcesTurnItem:
    """Retrieval evidence."""

    def test_sources_turn_item(self) -> None:
        """Sources item with chunk content round-trips through model_dump and validate."""
        item = SourcesTurnItem(
            id="src_1",
            origin="auto",
            chunks=[
                SourceChunk(content="chunk body", source="docs-index"),
            ],
        )
        parsed = SourcesTurnItem.model_validate(item.model_dump())
        assert isinstance(parsed, SourcesTurnItem)
        assert parsed.chunks[0].source == "docs-index"


class TestDeferredHitlFlow:
    """Deferred tools and approvals span turns."""

    def test_awaiting_input_then_resume_in_new_turn(self) -> None:
        """Pause ends with awaiting_input; resume supplies tool result and approval."""
        paused = AgentTurn(
            id="resp_pause",
            status="awaiting_input",
            provider="openai",
            model="gpt-4",
            started_at="2024-01-01T00:02:00Z",
            completed_at="2024-01-01T00:02:10Z",
            context_status="full",
            input=[user_message("u1", "Run the tool")],
            output=[
                ToolCallTurnItem(
                    id="tc1",
                    call_id="call_abc",
                    name="client_tool",
                    arguments={"path": "/tmp"},
                    toolset=ToolsetInfo(type="mcp", label="filesystem"),
                ),
                ApprovalRequestTurnItem(
                    id="ap1",
                    call_id="call_abc",
                    name="client_tool",
                    arguments={"path": "/tmp"},
                    toolset=ToolsetInfo(type="mcp", label="filesystem"),
                ),
            ],
        )
        resumed = AgentTurn(
            id="resp_resume",
            status="completed",
            provider="openai",
            model="gpt-4",
            started_at="2024-01-01T00:03:00Z",
            completed_at="2024-01-01T00:03:05Z",
            context_status="full",
            input=[
                ToolResultTurnItem(
                    id="tr1",
                    call_id="call_abc",
                    status="success",
                    content={"ok": True},
                    toolset=ToolsetInfo(type="mcp", label="filesystem"),
                ),
                ApprovalResultTurnItem(
                    id="ar1",
                    call_id="call_abc",
                    approved=True,
                ),
            ],
            output=[assistant_message("a1", "Done.")],
        )
        assert paused.status == "awaiting_input"
        assert resumed.input[0].kind == "tool_result"
        assert resumed.input[1].kind == "approval_result"

    def test_tool_result_status_and_content(self) -> None:
        """Tool result status is enumerated; content may be str or JSON-like."""
        with pytest.raises(ValidationError):
            ToolResultTurnItem(
                id="tr1",
                call_id="c1",
                status="maybe",  # type: ignore[arg-type]
                content={},
                toolset=ToolsetInfo(type="function"),
            )

        dict_item = ToolResultTurnItem(
            id="tr2",
            call_id="c2",
            status="success",
            content={"rows": [1, 2]},
            toolset=ToolsetInfo(type="function"),
        )
        assert dict_item.content == {"rows": [1, 2]}


class TestTurnItemPayloads:
    """dict/JSON-shaped payloads validate as concrete turn item models."""

    def test_turn_items_validate_from_dict_payloads(self) -> None:
        """Message and tool_call items parse from plain dict payloads."""
        message_payload = {
            "id": "m1",
            "kind": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello"}],
        }
        msg = MessageTurnItem.model_validate(message_payload)
        assert isinstance(msg, MessageTurnItem)

        tool_payload = {
            "id": "tc1",
            "kind": "tool_call",
            "call_id": "call_1",
            "name": "search",
            "arguments": {"q": "openshift"},
            "toolset": {"type": "mcp", "label": "wiki"},
        }
        tool = ToolCallTurnItem.model_validate(tool_payload)
        assert isinstance(tool, ToolCallTurnItem)
        assert tool.toolset.type == "mcp"
