"""Project an agent run into a display-history turn summary."""

from __future__ import annotations

from typing import Any, Final, Optional

from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelResponse
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import DeferredToolRequests

from conversations.display_history.agentic.models.agent_turn_summary import (
    AgentTurnSummary,
)
from conversations.display_history.agentic.models.types import AgentTurnStatus
from conversations.display_history.agentic.projection.items import (
    turn_items_from_messages,
)
from models.common.agents import AgentRunDeps
from utils.referenced_documents import deduplicate_referenced_documents

type AgentRunOutcome = AgentRunResult[Any] | RunCancelled
"""Completed agent run or a cancelled run that still has message history."""

_FINISH_REASON_STATUS: Final[dict[str, AgentTurnStatus]] = {
    "stop": "completed",
    "content_filter": "completed",
    "length": "failed",
    "error": "failed",
    "tool_call": "completed",
}
_DEFAULT_FINISH_REASON_STATUS: Final[AgentTurnStatus] = "completed"


def project_agent_turn_summary(
    run: AgentRunOutcome,
    deps: AgentRunDeps,
) -> Optional[AgentTurnSummary]:
    """Build persistence fields for one agentic turn row.

    Status, token usage, and turn items come from the run. Compaction status
    and inline citations come from the per-run collector. Agent name stays
    unset until a future source supplies it.

    Args:
        run: Completed agent run or a cancelled run with message history.
        deps: Per-run collector updated by capabilities during the run.

    Returns:
        Turn summary for storage, or None when the run has no run id.

    """
    if not run.run_id:
        return None
    input_items, output_items, run_documents = turn_items_from_messages(
        run.new_messages()
    )
    return AgentTurnSummary(
        status=_status_from_run(run),
        agent=None,
        context_status=deps.context_status,
        input_tokens=run.usage.input_tokens,
        output_tokens=run.usage.output_tokens,
        referenced_documents=deduplicate_referenced_documents(
            [*deps.referenced_documents, *run_documents]
        ),
        input=input_items,
        output=output_items,
    )


def _status_from_run(run: AgentRunOutcome) -> AgentTurnStatus:
    """Map run completion or cancellation onto a stored turn status."""
    if isinstance(run, RunCancelled):
        return "interrupted"
    if isinstance(run.output, DeferredToolRequests):
        return "awaiting_input"
    try:
        response = run.response
    except ValueError:
        return "failed"
    return _status_from_response(response)


def _status_from_response(response: ModelResponse) -> AgentTurnStatus:
    """Map a model response finish reason onto a stored turn status."""
    details = response.provider_details or {}
    if details.get("finish_reason") == "cancelled":
        return "interrupted"
    reason = response.finish_reason
    if reason is None:
        return _DEFAULT_FINISH_REASON_STATUS
    return _FINISH_REASON_STATUS.get(reason, _DEFAULT_FINISH_REASON_STATUS)
