"""Factory for building step persistence capabilities."""

from typing import Optional

from pydantic_ai_harness.step_persistence import StepPersistence

from conversations.agent_history import AgentHistoryService


class StepPersistenceFactory:  # pylint: disable=too-few-public-methods
    """Factory for building step persistence capabilities."""

    @staticmethod
    def build_capability() -> Optional[StepPersistence]:
        """Build a step persistence capability from step persistence settings."""
        return AgentHistoryService().step_persistence
