"""Mutable per-turn state for agent response processing."""

from dataclasses import dataclass, field
from typing import Final, Optional

from pydantic_ai import AgentRunResult

from lightspeed_stack.models.common.turn_summary import TurnSummary


@dataclass(slots=True)
class AgentTurnAccumulator:  # pylint: disable=too-many-instance-attributes
    """Information accumulator for a single interaction turn.

    Attributes:
        vector_store_ids: Vector store IDs used to resolve RAG source labels.
        rag_id_mapping: Maps vector store IDs to user-facing source names.
        turn_summary: Aggregated turn output (text, tools, RAG, token usage).
        run_result: Agent run result (streaming only).
        chunk_id: Monotonic SSE chunk index (streaming only).
        text_parts: Buffered text deltas before turn_complete (streaming only).
        tool_round: Current tool-call round for summary labeling.
        round_increment_pending: Whether to bump tool_round on the next step.
        emitted_tool_call_ids: Tool call IDs already sent or recorded.
        emitted_tool_result_ids: Tool result IDs already sent or recorded.
        seen_docs: Referenced-document keys already added (deduplication).
    """

    vector_store_ids: Final[list[str]]
    rag_id_mapping: Final[dict[str, str]]
    turn_summary: TurnSummary
    run_result: Optional[AgentRunResult[str]] = None
    chunk_id: int = 0
    text_parts: list[str] = field(default_factory=list)
    tool_round: int = 1
    round_increment_pending: bool = False
    emitted_tool_call_ids: set[str] = field(default_factory=set)
    emitted_tool_result_ids: set[str] = field(default_factory=set)
    seen_docs: set[tuple[str, str]] = field(default_factory=set)

    def increment_round_if_pending(self) -> None:
        """Increment tool_round if round_increment_pending is True."""
        if not self.round_increment_pending:
            return
        self.tool_round += 1
        self.round_increment_pending = False
