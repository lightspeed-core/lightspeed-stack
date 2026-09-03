"""Unit tests for the degraded mode tracker."""

from utils.degraded_mode import DegradedModeTracker


class TestDegradedModeTracker:
    """Test cases for DegradedModeTracker."""

    def test_initial_state_is_healthy(self) -> None:
        """Test tracker starts in healthy state."""
        tracker = DegradedModeTracker()
        assert tracker.is_degraded() is False
        assert tracker.get_degraded_reason() is None

    def test_set_degraded(self) -> None:
        """Test setting degraded mode."""
        tracker = DegradedModeTracker()
        reason = "Failed to connect to Llama Stack"

        tracker.set_degraded(reason)

        assert tracker.is_degraded() is True
        assert tracker.get_degraded_reason() == reason

    def test_set_healthy(self) -> None:
        """Test setting healthy mode."""
        tracker = DegradedModeTracker()

        tracker.set_healthy()

        assert tracker.is_degraded() is False
        assert tracker.get_degraded_reason() is None

    def test_transition_from_degraded_to_healthy(self) -> None:
        """Test transitioning from degraded to healthy state."""
        tracker = DegradedModeTracker()

        # Set degraded
        tracker.set_degraded("Connection error")
        assert tracker.is_degraded() is True

        # Transition to healthy
        tracker.set_healthy()
        assert tracker.is_degraded() is False
        assert tracker.get_degraded_reason() is None

    def test_singleton_pattern(self) -> None:
        """Test that DegradedModeTracker is a singleton."""
        tracker1 = DegradedModeTracker()
        tracker2 = DegradedModeTracker()

        assert tracker1 is tracker2

        # Set state on one instance
        tracker1.set_degraded("Test reason")

        # Verify state is shared across instances
        assert tracker2.is_degraded() is True
        assert tracker2.get_degraded_reason() == "Test reason"
