"""Core redaction logic for PII detection and replacement."""

from pydantic import BaseModel, ConfigDict

from lightspeed_stack.utils.types import CompiledPatterns


class RedactionResult(BaseModel):
    """Result of applying PII redaction rules to text.

    Attributes:
        content: The text after all redaction rules have been applied.
        redacted: True if at least one rule matched and changed the text.
        redaction_count: Total number of substitutions made across all rules.
    """

    model_config = ConfigDict(frozen=True)

    content: str
    redacted: bool
    redaction_count: int


def redact_text(
    content: str,
    compiled_patterns: CompiledPatterns,
) -> RedactionResult:
    """Apply PII redaction rules to the given text.

    Rules are applied sequentially in the order provided. Earlier rules
    may affect later rule matches.

    Args:
        content: The text to redact. Not mutated.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A RedactionResult with the redacted content, a flag indicating
        whether any substitution occurred, and the total substitution
        count.
    """
    result = content
    total_count = 0

    for pattern, replacement in compiled_patterns:
        result, count = pattern.subn(replacement, result)
        total_count += count

    return RedactionResult(
        content=result,
        redacted=total_count > 0,
        redaction_count=total_count,
    )
