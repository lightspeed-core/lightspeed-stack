"""Tests for agent turn summary fields stored on the turn row."""

from conversations.display_history.agentic.models import AgentTurnSummary


def test_summary_defaults_match_agentic_turn_row() -> None:
    """Summary holds agent-run display fields, not conversation envelope identity."""
    summary = AgentTurnSummary(status="completed")
    assert summary.context_status == "full"
    assert summary.input_tokens == 0
    assert summary.output_tokens == 0
    assert summary.input == []
    assert summary.output == []
    assert "provider" not in AgentTurnSummary.model_fields
    assert "model" not in AgentTurnSummary.model_fields
    assert "started_at" not in AgentTurnSummary.model_fields
    assert "id" not in AgentTurnSummary.model_fields
