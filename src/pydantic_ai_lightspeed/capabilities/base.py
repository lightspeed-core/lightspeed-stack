from abc import abstractmethod

from pydantic_ai.capabilities import AbstractCapability
from typing_extensions import TypeVar

from models.common.moderation import ShieldModerationResult

T = TypeVar("T", default=object)


class AbstractSafetyCapability(AbstractCapability[T]):
    """Interface for safety/moderation that can be called directly."""

    @abstractmethod
    async def run(self, input_text: str) -> ShieldModerationResult:
        """Run moderation on input text."""
        ...
