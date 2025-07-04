"""
Shields module for query and attachment redaction.

Provides Llama Stack compatible shield implementations.
"""

from .redaction_shield import (
    RedactionShield,
    get_redaction_shield,
    redact_query,
    redact_attachments,
)

__all__ = [
    "RedactionShield",
    "get_redaction_shield",
    "redact_query",
    "redact_attachments",
]
