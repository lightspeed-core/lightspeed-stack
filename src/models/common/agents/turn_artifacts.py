"""Per-run PAI artifacts for agentic display persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from conversations.display_history.agentic.projection import AgentRunOutcome
    from models.common.agents.run_deps import AgentRunDeps


@dataclass
class AgentTurnArtifacts:
    """PAI run output carried alongside TurnSummary for agentic persistence.

    Call record after the agent finishes. The run and deps properties are for
    persistence only and raise if nothing was recorded yet.
    """

    _run: Optional[AgentRunOutcome] = field(default=None, repr=False)
    _deps: Optional[AgentRunDeps] = field(default=None, repr=False)

    def record(self, run: AgentRunOutcome, deps: AgentRunDeps) -> None:
        """Remember the run and deps from a finished agent invocation."""
        self._run = run
        self._deps = deps

    def is_recorded(self) -> bool:
        """Return True if record was called with both run and deps."""
        return self._run is not None and self._deps is not None

    @property
    def run(self) -> AgentRunOutcome:
        """Recorded agent run.

        Raises:
            RuntimeError: If record was not called.

        """
        if self._run is None:
            raise RuntimeError("Agent turn artifacts: run was not recorded")
        return self._run

    @property
    def deps(self) -> AgentRunDeps:
        """Recorded per-run deps.

        Raises:
            RuntimeError: If record was not called.

        """
        if self._deps is None:
            raise RuntimeError("Agent turn artifacts: deps were not recorded")
        return self._deps
