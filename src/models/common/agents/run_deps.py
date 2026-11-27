"""Per-run fields collected during an agent run for projection."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from models.common.turn_summary import ContextStatus, ReferencedDocument

type AgentRunContextStatus = Literal["full", "compacted"]
"""Whether agent history for this run was compacted."""


class AgentRunDeps(BaseModel):
    """Mutable collector capabilities fill during one agent run.

    The caller passes one instance into the run. Capabilities update it in
    place; projection reads the same object afterward.

    Attributes:
        context_status: Whether agent history was full or compacted.
        referenced_documents: Citations from automatic inline RAG.

    """

    model_config = ConfigDict(extra="forbid")

    context_status: AgentRunContextStatus = Field(
        default="full",
        description="Whether agent history for this run was full or compacted",
    )
    referenced_documents: list[ReferencedDocument] = Field(
        default_factory=list,
        description=(
            "Citations from automatic inline RAG when retrieval runs in auto mode"
        ),
    )


def public_context_status(
    pre_agent: ContextStatus, run: AgentRunContextStatus
) -> ContextStatus:
    """Combine the pre-agent and the agent-run compaction outcomes for the API.

    While both compaction paths exist, a turn is ``"summarized"`` when the
    pre-agent compaction served it in compacted mode or when the agent run's
    compaction changed the history (LCORE-4694); otherwise ``"full"``.

    Parameters:
        pre_agent: The status the pre-agent compaction reported for the turn.
        run: The status the agent run's deps hold after the run.

    Returns:
        The value of the public ``context_status`` field.

    """
    if pre_agent == "summarized" or run == "compacted":
        return "summarized"
    return "full"
