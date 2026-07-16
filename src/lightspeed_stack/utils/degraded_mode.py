"""Degraded mode state tracking.

This module provides a singleton to track whether Lightspeed Core Stack is
running in degraded mode (i.e., without Llama Stack connectivity).
"""

from typing import Optional

from metrics import recording
from utils.types import Singleton


class DegradedModeTracker(metaclass=Singleton):
    """Track degraded mode state for Lightspeed Core Stack.

    When LCORE cannot connect to Llama Stack during startup and
    allow_degraded_mode is enabled, the service enters degraded mode.
    This tracker maintains that state for health reporting.
    """

    def __init__(self) -> None:
        """Initialize the degraded mode tracker."""
        self._is_degraded: bool = False
        self._degraded_reason: Optional[str] = None

    def set_degraded(self, reason: str) -> None:
        """Mark the service as running in degraded mode.

        Parameters:
            reason: Description of why degraded mode was entered.
        """
        self._is_degraded = True
        self._degraded_reason = reason

        # Record startup state metric
        recording.set_started_in_degraded_mode(True)

    def set_healthy(self) -> None:
        """Mark the service as running in healthy mode."""
        self._is_degraded = False
        self._degraded_reason = None

        # Record startup state metric
        recording.set_started_in_degraded_mode(False)

    def is_degraded(self) -> bool:
        """Check if the service is running in degraded mode.

        Returns:
            True if service is in degraded mode, False otherwise.
        """
        return self._is_degraded

    def get_degraded_reason(self) -> Optional[str]:
        """Get the reason for degraded mode.

        Returns:
            Description of why degraded mode was entered, or None if healthy.
        """
        return self._degraded_reason
