"""Unit tests for safety.granite_guardian.types."""

from dataclasses import FrozenInstanceError

import pytest

from safety.granite_guardian.types import DEFAULT_VIOLATION_MESSAGE, Risk


class TestRisk:
    """Tests for the Granite Guardian risk description."""

    def test_defaults(self) -> None:
        """Test that an unspecified risk uses the generic guard settings."""
        risk = Risk(name="harm", criteria="harmful content")

        assert risk.violation_message == DEFAULT_VIOLATION_MESSAGE
        assert risk.threshold == 0.5
        assert risk.enable_thinking is False
        assert risk.type == []

    def test_type_lists_are_not_shared(self) -> None:
        """Test that each risk gets its own guard-point list."""
        first = Risk(name="harm", criteria="harmful content")
        second = Risk(name="jailbreak", criteria="injection")

        first.type.append("input")

        assert first.type == ["input"]
        assert second.type == []

    def test_custom_values_and_equality(self) -> None:
        """Test that equal field values compare equal."""
        risk = Risk(
            name="harm",
            criteria="harmful content",
            violation_message="No.",
            threshold=0.2,
            enable_thinking=True,
            type=["input", "output"],
        )
        same = Risk(
            name="harm",
            criteria="harmful content",
            violation_message="No.",
            threshold=0.2,
            enable_thinking=True,
            type=["input", "output"],
        )

        assert risk == same
        assert risk != Risk(name="other", criteria="harmful content")

    def test_frozen(self) -> None:
        """Test that risk fields cannot be reassigned."""
        risk = Risk(name="harm", criteria="harmful content")

        with pytest.raises(FrozenInstanceError):
            risk.name = "renamed"  # type: ignore[misc]
