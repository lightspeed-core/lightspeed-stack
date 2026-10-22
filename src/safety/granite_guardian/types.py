from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

DEFAULT_VIOLATION_MESSAGE = "I can't help with that."
"""Fallback `Risk.violation_message` / `GraniteGuardianRisk.violation_message` when a risk
doesn't set its own. Deliberately generic -- it says nothing about which risk was flagged --
since callers who want to tell the flagged risk apart in the response should set their own
per-risk message instead."""


@dataclass(frozen=True)
class Risk:
    """Plain description of one Granite Guardian risk.

    Used by :class:`GraniteGuardian` to build a :class:`GraniteGuardianRisk`. Not a pydantic
    model: keeping this a plain dataclass means constructing a `GraniteGuardian`
    doesn't require going through YAML config at all. `GraniteGuardianConfig.risks` uses this
    type directly (pydantic validates dicts onto stdlib dataclasses like any other field type),
    so there's no separate config/schema type duplicating these fields.
    """

    name: str
    """Unique name for this risk within its shield; combined with the shield's `id` for this
    risk's own `GraniteGuardianRisk.id`."""

    criteria: str
    """Natural-language description of what this risk flags, sent to Granite Guardian as the
    judging criteria."""

    violation_message: str = DEFAULT_VIOLATION_MESSAGE
    """Message returned to the caller in place of a prompt or response that violates this
    risk."""

    threshold: float = 0.5
    """Risk is flagged when Granite Guardian's normalized probability of a risky verdict
    meets or exceeds this value."""

    enable_thinking: bool = False
    """Whether to prompt Granite Guardian to reason before scoring (`<think>` block) rather
    than score immediately. Slower but can improve accuracy on subtler risks."""

    type: Sequence[Literal["input", "output", "tool"]] = field(default_factory=list)
    """Which guardrail points this risk applies to. See
    `AbstractSafetyCapability.type`."""
