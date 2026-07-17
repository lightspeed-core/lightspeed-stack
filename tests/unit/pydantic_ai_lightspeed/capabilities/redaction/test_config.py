"""Unit tests for pydantic_ai_lightspeed.capabilities.redaction.config module."""

import re

import pytest
from pydantic import ValidationError

from lightspeed_stack.models.config import (
    RedactionConfig,
    RedactionRule,
)


class TestRedactionRule:
    """Tests for the RedactionRule model."""

    def test_construction(self) -> None:
        """Test that a RedactionRule can be constructed with valid fields."""
        rule = RedactionRule(pattern=r"\d+", replacement="[NUM]", case_sensitive=False)
        assert rule.pattern == r"\d+"
        assert rule.replacement == "[NUM]"
        assert rule.case_sensitive is False

    def test_case_sensitive_defaults_to_none(self) -> None:
        """Test that case_sensitive defaults to None when omitted."""
        rule = RedactionRule(pattern=r"\d+", replacement="[NUM]")
        assert rule.case_sensitive is None

    def test_case_sensitive_override(self) -> None:
        """Test that per-rule case_sensitive can be set."""
        rule = RedactionRule(
            pattern=r"secret", replacement="[REDACTED]", case_sensitive=True
        )
        assert rule.case_sensitive is True

    def test_rejects_extra_fields(self) -> None:
        """Test that extra fields are rejected by ConfigurationBase."""
        with pytest.raises(ValidationError):
            RedactionRule(pattern=r"\d+", replacement="[NUM]", unknown_field="bad")


class TestRedactionConfigCompilation:
    """Tests for RedactionConfig pattern compilation."""

    def test_empty_rules(self) -> None:
        """Test that empty rules produce no compiled patterns."""
        config = RedactionConfig(rules=[])
        assert not config.compiled_patterns

    def test_single_rule_compiles(self) -> None:
        """Test that a single rule is compiled into a pattern."""
        config = RedactionConfig(
            rules=[
                RedactionRule(
                    pattern=r"\d{3}-\d{4}",
                    replacement="[PHONE]",
                    case_sensitive=False,
                )
            ]
        )
        patterns = config.compiled_patterns
        assert len(patterns) == 1
        compiled_re, replacement = patterns[0]
        assert replacement == "[PHONE]"
        assert compiled_re.search("call 555-1234")

    def test_multiple_rules_compile(self) -> None:
        """Test that multiple rules produce multiple compiled patterns."""
        config = RedactionConfig(
            rules=[
                RedactionRule(pattern=r"foo", replacement="[A]", case_sensitive=False),
                RedactionRule(pattern=r"bar", replacement="[B]", case_sensitive=True),
            ]
        )
        assert len(config.compiled_patterns) == 2

    def test_invalid_regex_raises(self) -> None:
        """Test that an invalid regex pattern raises ValueError."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            RedactionConfig(
                rules=[
                    RedactionRule(
                        pattern=r"[invalid",
                        replacement="x",
                        case_sensitive=False,
                    )
                ]
            )


class TestRedactionConfigCaseSensitivity:
    """Tests for case sensitivity behavior in RedactionConfig."""

    def test_default_case_insensitive(self) -> None:
        """Test that patterns are case-insensitive by default."""
        config = RedactionConfig(
            rules=[
                RedactionRule(
                    pattern=r"secret",
                    replacement="[REDACTED]",
                    case_sensitive=None,
                )
            ]
        )
        compiled_re, _ = config.compiled_patterns[0]
        assert compiled_re.flags & re.IGNORECASE

    def test_global_case_sensitive(self) -> None:
        """Test that global case_sensitive=True disables IGNORECASE."""
        config = RedactionConfig(
            rules=[
                RedactionRule(
                    pattern=r"secret",
                    replacement="[REDACTED]",
                    case_sensitive=None,
                )
            ],
            case_sensitive=True,
        )
        compiled_re, _ = config.compiled_patterns[0]
        assert (compiled_re.flags & re.IGNORECASE) == 0

    def test_per_rule_override(self) -> None:
        """Test that per-rule case_sensitive overrides the global flag."""
        config = RedactionConfig(
            rules=[
                RedactionRule(
                    pattern=r"secret",
                    replacement="[REDACTED]",
                    case_sensitive=True,
                ),
            ],
            case_sensitive=False,
        )
        compiled_re, _ = config.compiled_patterns[0]
        assert (compiled_re.flags & re.IGNORECASE) == 0


class TestRedactionConfigCompiledPatternsProperty:
    """Tests for compiled_patterns property behavior."""

    def test_returns_list(self) -> None:
        """Test that compiled_patterns returns a list."""
        config = RedactionConfig(
            rules=[RedactionRule(pattern=r"x", replacement="y", case_sensitive=False)]
        )
        assert isinstance(config.compiled_patterns, list)

    def test_returns_copy(self) -> None:
        """Test that compiled_patterns returns a copy, not the internal list."""
        config = RedactionConfig(
            rules=[RedactionRule(pattern=r"x", replacement="y", case_sensitive=False)]
        )
        a = config.compiled_patterns
        b = config.compiled_patterns
        assert a == b
        assert a is not b
