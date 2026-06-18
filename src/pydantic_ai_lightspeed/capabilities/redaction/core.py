"""Core redaction logic for PII detection and replacement."""

from re import Pattern

from models.config import RedactionResult

CompiledPatterns = list[tuple[Pattern[str], str]]


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
