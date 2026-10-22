"""Verdicts and the streamed-output buffer used by safety capabilities."""

from dataclasses import dataclass, field
from typing import Literal, Optional, Self

from pydantic_ai import (
    AgentStreamEvent,
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
)


@dataclass
class OutputState:
    """Per-run buffer of model-response stream events awaiting an `evaluate` check.

    `AbstractSafetyCapability` gives each run its own instance (via `for_run`), so concurrent
    runs sharing a capability instance don't share a buffer.
    """

    events: list[AgentStreamEvent] = field(default_factory=list)
    """Stream events accumulated since the last check."""

    def append(self, event: AgentStreamEvent) -> None:
        """Buffer a stream event."""
        self.events.append(event)

    def ready(self, interval: int) -> bool:
        """Whether enough events have accumulated to run the next check.

        Also ready as soon as a part finishes, so a completed part is checked promptly instead of
        waiting on the next part's events to cross `interval`.
        """
        if self.events and isinstance(self.events[-1], PartEndEvent):
            return True
        return len(self.events) >= interval

    def text(self) -> str:
        """Return the buffered text."""
        chunks: list[str] = []
        for event in self.events:
            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                chunks.append(event.part.content)
            elif isinstance(event, PartDeltaEvent) and isinstance(
                event.delta, TextPartDelta
            ):
                chunks.append(event.delta.content_delta)
        return "".join(chunks)

    def flush(self) -> tuple[str, list[AgentStreamEvent]]:
        """Return the buffered text and events, then clear the buffer."""
        text, events = self.text(), self.events[:]
        self.events.clear()
        return text, events


@dataclass
class GuardrailResult:
    """The verdict a safety guard returns for a prompt or a response."""

    action: Literal["allow", "block", "replace"]
    message: Optional[str] = None
    replacement: Optional[object] = None

    @classmethod
    def allow(cls) -> Self:
        """Return an allow verdict."""
        return cls(action="allow")

    @classmethod
    def block(cls, message: str | None = None) -> Self:
        """Return a block verdict with an optional caller-facing message."""
        return cls(action="block", message=message)

    @classmethod
    def replace(cls, value: object) -> Self:
        """Return a replace verdict with the given replacement value."""
        return cls(action="replace", replacement=value)
