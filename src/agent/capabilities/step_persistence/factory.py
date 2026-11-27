"""Factory for building step persistence capabilities."""

from typing import Optional

from pydantic_ai_harness.step_persistence import StepPersistence

from agent.types.settings import StepPersistenceSettings
from conversations.agent_history import AgentHistoryService


class StepPersistenceFactory:  # pylint: disable=too-few-public-methods
    """Factory for building step persistence capabilities."""

    @staticmethod
    def build_capability(
        settings: StepPersistenceSettings,
    ) -> Optional[StepPersistence]:
        """Build a step persistence capability from step persistence settings.

        Disabled settings produce no capability. Enabled settings return the
        capability owned by the agent history service, which is ``None`` when
        persistence is configured as a no-op.

        Parameters:
            settings: Step persistence settings, including whether persistence
                is enabled for this agent.

        Returns:
            The history service capability, or ``None`` when persistence is
            disabled or no store is configured.

        """
        if not settings.enabled:
            return None
        return AgentHistoryService().step_persistence
