"""Configuration models for PII redaction rules.

Canonical definitions live in models.config; this module re-exports them
for convenient access within the capabilities package.
"""

from models.config import (
    RedactionConfig,
    RedactionRule,
)

__all__ = ["RedactionConfig", "RedactionRule"]
