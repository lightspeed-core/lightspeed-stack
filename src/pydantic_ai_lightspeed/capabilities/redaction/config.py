"""Configuration models for PII redaction rules."""

import re
from typing import Self

from pydantic import Field, PrivateAttr, model_validator

from models.config import ConfigurationBase
from pydantic_ai_lightspeed.capabilities.redaction.core import (
    CompiledPatterns,
)


class RedactionRule(ConfigurationBase):
    """A single regex-based redaction rule.

    Attributes:
        pattern: Raw regex pattern string to match sensitive data.
        replacement: Text to substitute for each match.
        case_sensitive: Per-rule override for case sensitivity.
            When None, the global ``RedactionConfig.case_sensitive``
            flag applies.
    """

    pattern: str = Field(
        ...,
        title="Pattern",
        description="Regex pattern to match sensitive data",
    )
    replacement: str = Field(
        ...,
        title="Replacement",
        description="Replacement string for matched text",
    )
    case_sensitive: bool | None = Field(
        None,
        title="Case sensitive",
        description=(
            "Per-rule case sensitivity override. "
            "When None, the global config flag applies."
        ),
    )


class RedactionConfig(ConfigurationBase):
    """Configuration for PII redaction with regex-based rules.

    Rules are validated and compiled at construction time. Invalid
    regex patterns raise a ``ValueError`` immediately.

    Attributes:
        rules: Ordered list of redaction rules applied sequentially.
        case_sensitive: When False, patterns are compiled with
            ``re.IGNORECASE``. Defaults to False.
    """

    rules: list[RedactionRule] = Field(
        default_factory=list,
        title="Redaction rules",
        description="Ordered list of PII redaction rules",
    )
    case_sensitive: bool = Field(
        False,
        title="Case sensitive",
        description=("When False, patterns are compiled with re.IGNORECASE"),
    )

    _compiled_patterns: CompiledPatterns = PrivateAttr(
        default_factory=list,
    )

    @model_validator(mode="after")
    def compile_patterns(self) -> Self:
        """Compile regex patterns and reject invalid ones.

        Per-rule ``case_sensitive`` overrides the global flag when set.

        Raises:
            ValueError: If any rule contains an invalid regex pattern.

        Returns:
            The validated configuration instance.
        """
        global_case_sensitive = self.case_sensitive
        compiled: CompiledPatterns = []
        for rule in self.rules:
            effective = (
                rule.case_sensitive
                if rule.case_sensitive is not None
                else global_case_sensitive
            )
            flags = 0 if effective else re.IGNORECASE
            try:
                pattern = re.compile(rule.pattern, flags)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {rule.pattern}: {e}") from e
            compiled.append((pattern, rule.replacement))
        self._compiled_patterns = compiled
        return self

    @property
    def compiled_patterns(self) -> CompiledPatterns:
        """Pre-compiled (regex, replacement) pairs.

        Returns a shallow copy to prevent mutation of internal state.
        """
        return list(self._compiled_patterns)
