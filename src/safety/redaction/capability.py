"""``RedactionCapability``: pattern-based text redaction for prompts and model output.

A minimal, standalone
:class:`~lightspeed.core.agent.safety.base.AbstractSafetyCapability`: unlike
:class:`~lightspeed.core.agent.safety.question_validity.capability.QuestionValidityCapability`,
it never blocks a request -- it only ever rewrites the spans its patterns match, via
`GuardrailResult.replace`, so it composes safely alongside guards that do block without
competing with them over the same verdict.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic_ai.tools import AgentDepsT

from safety.base import AbstractSafetyCapability, GuardrailResult

DEFAULT_REPLACEMENT = "[REDACTED]"


@dataclass
class RedactionCapability(AbstractSafetyCapability[AgentDepsT]):
    """Rewrites text matching configured regex patterns to a placeholder.

    Attach the same way any other safety capability is attached -- see
    :class:`~lightspeed.core.agent.safety.base.AbstractSafetyCapability` -- or call
    :meth:`evaluate` directly for a standalone check. Guards both `'input'` and `'output'`
    by default, so PII typed by the user and PII a model happens to generate are both caught.
    """

    type: Sequence[Literal["input", "output", "tool"]] = field(
        default_factory=lambda: ["input"]
    )
    """Defaults to guarding both the user's prompt and the model's streamed output."""

    patterns: Optional[Mapping[str, str]] = None
    """Named regex patterns to redact, keyed by a label used only for readability.

    `None` (the default) is normalized to an empty mapping in :meth:`__post_init__` (no
    redaction). Patterns are compiled once there -- replacing this after construction
    (rather than passing it to `__init__`) won't take effect; build a new instance instead.
    """

    replacement: Optional[str] = None
    """Text substituted in place of each match. `None` (the default) falls back to
    :data:`DEFAULT_REPLACEMENT` in `__post_init__`."""

    def __post_init__(self) -> None:
        """Fill unset fields from their module-level defaults, then compile `patterns`.

        Defaults filled in here rather than as plain dataclass field defaults so callers --
        e.g. `SafetyCapabilityFactory`, forwarding a config field that's `None` when unset --
        can pass `None` through and still get the default, instead of having to omit the
        keyword argument entirely to avoid overriding it.
        """
        if self.patterns is None:
            self.patterns = {}
        if self.replacement is None:
            self.replacement = DEFAULT_REPLACEMENT
        self._compiled: tuple[re.Pattern[str], ...] = tuple(
            re.compile(pattern) for pattern in self.patterns.values()
        )

    async def evaluate(self, prompt: str) -> GuardrailResult:
        """Redact every configured pattern's matches in `prompt`.

        Returns `GuardrailResult.allow()` unchanged when nothing matches, so a redaction
        guard with no hits never triggers `replace_latest_message`'s multimodal-prompt
        check on a request it had no reason to touch.
        """
        replacement = self.replacement or DEFAULT_REPLACEMENT
        redacted = prompt
        for pattern in self._compiled:
            redacted = pattern.sub(replacement, redacted)
        if redacted == prompt:
            return GuardrailResult.allow()
        return GuardrailResult.replace(redacted)
