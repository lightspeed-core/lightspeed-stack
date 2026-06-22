"""Unit tests for pydantic_ai_lightspeed.capabilities.redaction.core module."""

import re

import pytest
from pydantic import ValidationError

from pydantic_ai_lightspeed.capabilities.redaction.core import (
    CompiledPatterns,
    RedactionResult,
    redact_text,
)

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PASSWORD_PATTERN = re.compile(r"(?i)(password|passwd)[\s:=]+[^\s]+")
SECRET_PATTERN = re.compile(r"(?i)(api_key|secret|token)[\s:=]+[a-zA-Z0-9\-_]{16,}")


class TestRedactionResult:
    """Tests for the RedactionResult model."""

    def test_construction(self) -> None:
        """Test that RedactionResult can be constructed with valid fields."""
        result = RedactionResult(content="redacted", redacted=True, redaction_count=1)
        assert result.content == "redacted"
        assert result.redacted is True
        assert result.redaction_count == 1

    def test_frozen(self) -> None:
        """Test that RedactionResult is immutable."""
        result = RedactionResult(content="text", redacted=False, redaction_count=0)
        with pytest.raises(ValidationError):
            result.content = "modified"


class TestRedactTextNoRules:
    """Tests for redact_text with no or non-matching rules."""

    def test_empty_rules(self) -> None:
        """Test that empty rules return original content unchanged."""
        result = redact_text("hello world", [])
        assert result.content == "hello world"
        assert result.redacted is False
        assert result.redaction_count == 0

    def test_no_match(self) -> None:
        """Test that non-matching rules return original content."""
        patterns: CompiledPatterns = [(EMAIL_PATTERN, "[REDACTED_EMAIL]")]
        result = redact_text("no emails here", patterns)
        assert result.content == "no emails here"
        assert result.redacted is False
        assert result.redaction_count == 0

    def test_empty_content(self) -> None:
        """Test that empty string input returns empty string."""
        patterns: CompiledPatterns = [(EMAIL_PATTERN, "[REDACTED_EMAIL]")]
        result = redact_text("", patterns)
        assert result.content == ""
        assert result.redacted is False
        assert result.redaction_count == 0

    def test_does_not_mutate_input(self) -> None:
        """Test that the original content string is not mutated."""
        original = "user@example.com"
        original_copy = original
        patterns: CompiledPatterns = [(EMAIL_PATTERN, "[REDACTED_EMAIL]")]
        redact_text(original, patterns)
        assert original == original_copy
        assert original == "user@example.com"


class TestRedactTextMatching:
    """Tests for redact_text with matching patterns."""

    def test_single_match(self) -> None:
        """Test that a single match is redacted."""
        patterns: CompiledPatterns = [(EMAIL_PATTERN, "[REDACTED_EMAIL]")]
        result = redact_text("contact user@example.com please", patterns)
        assert result.content == "contact [REDACTED_EMAIL] please"
        assert result.redacted is True
        assert result.redaction_count == 1

    def test_multiple_matches_same_pattern(self) -> None:
        """Test that multiple occurrences of the same pattern are all redacted."""
        patterns: CompiledPatterns = [(EMAIL_PATTERN, "[REDACTED_EMAIL]")]
        result = redact_text("from a@b.com to c@d.com", patterns)
        assert result.content == ("from [REDACTED_EMAIL] to [REDACTED_EMAIL]")
        assert result.redacted is True
        assert result.redaction_count == 2

    def test_sequential_rule_application(self) -> None:
        """Test that rules are applied sequentially; earlier rules affect later matches."""
        patterns: CompiledPatterns = [
            (re.compile(r"foo"), "bar"),
            (re.compile(r"bar"), "baz"),
        ]
        result = redact_text("foo", patterns)
        assert result.content == "baz"
        assert result.redacted is True
        assert result.redaction_count == 2

    def test_multiple_different_patterns(self) -> None:
        """Test redaction with multiple different pattern types."""
        patterns: CompiledPatterns = [
            (EMAIL_PATTERN, "[REDACTED_EMAIL]"),
            (PASSWORD_PATTERN, "[REDACTED_PASSWORD]"),
        ]
        result = redact_text(
            "email: user@test.com password: s3cret123",
            patterns,
        )
        assert "[REDACTED_EMAIL]" in result.content
        assert "[REDACTED_PASSWORD]" in result.content
        assert result.redacted is True
        assert result.redaction_count == 2

    def test_redaction_count_accumulates_across_rules(self) -> None:
        """Test that redaction_count sums substitutions from all rules."""
        patterns: CompiledPatterns = [
            (EMAIL_PATTERN, "[REDACTED_EMAIL]"),
            (PASSWORD_PATTERN, "[REDACTED_PASSWORD]"),
        ]
        text = "a@b.com c@d.com password: secret"
        result = redact_text(text, patterns)
        assert result.redaction_count == 3


class TestRedactTextCaseSensitivity:
    """Tests for case sensitivity behavior in redact_text."""

    def test_case_insensitive(self) -> None:
        """Test that case-insensitive patterns match mixed case."""
        patterns: CompiledPatterns = [
            (
                re.compile(r"password[\s:=]+[^\s]+", re.IGNORECASE),
                "[REDACTED_PASSWORD]",
            )
        ]
        result = redact_text("PASSWORD: secret123", patterns)
        assert result.content == "[REDACTED_PASSWORD]"
        assert result.redacted is True

    def test_case_sensitive(self) -> None:
        """Test that case-sensitive patterns only match exact case."""
        patterns: CompiledPatterns = [
            (
                re.compile(r"password[\s:=]+[^\s]+"),
                "[REDACTED_PASSWORD]",
            )
        ]
        result = redact_text("PASSWORD: secret123", patterns)
        assert result.content == "PASSWORD: secret123"
        assert result.redacted is False
