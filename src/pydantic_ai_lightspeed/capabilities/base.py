from abc import abstractmethod

from pydantic_ai.capabilities import AbstractCapability
from typing_extensions import TypeVar

from models.common.moderation import ShieldModerationResultV2

T = TypeVar("T", default=None)


class AbstractSafetyCapability(AbstractCapability[T]):
    """Interface for safety/moderation that can be called directly."""

    @abstractmethod
    async def run(self, input_text: str) -> ShieldModerationResultV2:
        """Run moderation on input text."""
        ...
