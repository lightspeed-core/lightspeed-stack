"""Exceptions raised by safety capabilities to abort or recover an agent run."""

from typing import Optional


class OutputBlocked(BaseException):
    """The output was blocked by a safety guard."""

    def __init__(self, reason: Optional[str] = None) -> None:
        """Initialize with an optional human-readable block reason."""
        super().__init__(reason)
        self.reason = reason


class ToolBlocked(OutputBlocked):
    """A tool result was blocked by a safety guard.

    Subclass of `OutputBlocked` so `wrap_run_event_stream` can drain the in-flight
    stream (preserving provider usage) and `on_run_error` can recover the run the
    same way it does for a blocked model response.
    """
