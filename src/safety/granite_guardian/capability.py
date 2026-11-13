"""``GraniteGuardianType`` and ``GraniteGuardian``: Granite-Guardian risk checks and their shield.

A ``granite_guardian`` shield can list several independent risks (e.g. jailbreak, harm,
groundedness). :class:`GraniteGuardian` groups those risks by guard point and builds one
:class:`GraniteGuardianType` each for input, output, and tool results. A group scores every
risk that applies to its point, in parallel, and combines the verdicts. The groups share one
Granite Guardian `model` and sit in the agent's capability chain as separate guards via
:class:`~pydantic_ai.capabilities.CombinedCapability`.

Neither class depends on :mod:`lightspeed.app.models.config`: `GraniteGuardian` takes plain
`Risk` values rather than a config object, so this module stays usable (and testable)
independent of the YAML config schema. `GraniteGuardianConfig.risks` is `Risk` directly (the
dependency runs the other way -- config on capability, not capability on config), so
:mod:`~lightspeed.core.agent.safety.factory` passes it through unchanged, resolving only
`GraniteGuardianConfig.model` to a pydantic-ai `Model` via `ProviderRegistry`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic_ai.capabilities import AbstractCapability, CombinedCapability
from pydantic_ai.direct import model_request
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.tools import AgentDepsT

from safety.base import AbstractSafetyCapability, GuardrailResult
from safety.granite_guardian.types import Risk
from safety.granite_guardian.utils import build_guardian_block, is_safe


@dataclass
class GraniteGuardianType(AbstractSafetyCapability[AgentDepsT]):
    """Screens one guard point for every risk that applies to it.

    Attach the same way any other safety capability is attached -- see
    :class:`~lightspeed.core.agent.safety.base.AbstractSafetyCapability` -- or call
    :meth:`evaluate` directly for a standalone check. Typically constructed via
    :class:`GraniteGuardian` rather than directly, so sibling groups in the same shield share
    the same `model`. `evaluate` sends one Granite Guardian request per risk and combines the
    verdicts: any block wins, and block messages are joined in risk order.
    """

    risks: Sequence[Risk] = field(kw_only=True)
    """Risks screened together at this guard point.

    Each risk contributes its criteria, threshold, and violation message. An empty sequence
    allows without calling the model. `type` is the single guard point this group screens;
    :class:`GraniteGuardian` sets it when it groups risks."""

    model: Model = field(kw_only=True)
    """The Granite Guardian model to send each risk check to. Required -- typically set via
    :class:`GraniteGuardian`, which shares one `model` across every guard point."""

    async def evaluate(self, prompt: str) -> GuardrailResult:
        """Score `prompt` against every risk and return one combined verdict.

        Calls `model.request` directly (via `pydantic_ai.direct.model_request`) instead of
        running an `Agent`: each check needs no tools, output schema, or agent-graph
        machinery, just the one request/response pair scored by its logprobs. The requests
        run together. An empty `risks` sequence allows without a model call.

        Raises:
            UnexpectedModelBehavior: If a response is missing the `provider_details` or
                `logprobs` Granite Guardian's verdict is scored from.

        """

        async def evaluate_risk(risk: Risk) -> GuardrailResult:
            """Score `prompt` against one risk's criteria."""
            request = ModelRequest.user_text_prompt(
                prompt,
                instructions=build_guardian_block(
                    risk.criteria, think=risk.enable_thinking
                ),
            )
            response = await model_request(
                model=self.model,
                messages=[request],
                model_settings=OpenAIChatModelSettings(
                    openai_logprobs=True, openai_top_logprobs=20
                ),
            )
            if not response.provider_details:
                raise UnexpectedModelBehavior(
                    "No provider_details in Granite Guardian's response"
                )

            logprobs = response.provider_details.get("logprobs")
            if not logprobs:
                raise UnexpectedModelBehavior(
                    "No logprobs field in Granite Guardian's provider_details"
                )

            if is_safe(risk.threshold, logprobs):
                return GuardrailResult.allow()
            return GuardrailResult.block(message=risk.violation_message)

        results = await asyncio.gather(*[evaluate_risk(risk) for risk in self.risks])

        return GuardrailResult.combine(results)


@dataclass
class GraniteGuardian(CombinedCapability[AgentDepsT]):
    """A ``granite_guardian`` shield: one :class:`GraniteGuardianType` per guard point.

    `capabilities` is derived from `risks` and `model` in `__post_init__`, rather than passed
    directly -- construct with `risks=`/`model=` instead of `capabilities=`.
    """

    risks: Sequence[Risk] = field(default_factory=list)
    """Risks to screen for. Each is placed on the guard points listed in `Risk.type`."""

    model: Model = field(kw_only=True)
    """The Granite Guardian model shared by every group in `capabilities`. Required; passed
    through unchanged to each group's `GraniteGuardianType.model`."""

    check_tokens: int = field(kw_only=True, default=50)
    """Passed through to each group's `GraniteGuardianType.check_tokens`."""

    capabilities: Sequence[AbstractCapability[AgentDepsT]] = field(init=False)
    """Assigned in `__post_init__` from `risks`; not meant to be passed directly."""

    def __post_init__(self) -> None:
        """Build one ``GraniteGuardianType`` per guard point.

        A point with no matching risks still gets a child, and that child allows without
        calling the model. Delegates to ``CombinedCapability`` normalization after
        assigning ``capabilities``.
        """
        prefix = f"{self.id}." if self.id is not None else ""
        children: list[GraniteGuardianType[AgentDepsT]] = []
        for guard_type in ("input", "output", "tool"):
            child = GraniteGuardianType(
                type=[guard_type],
                risks=[risk for risk in self.risks if guard_type in risk.type],
                model=self.model,
                check_tokens=self.check_tokens,
            )
            child.id = f"{prefix}{guard_type}"
            children.append(child)
        self.capabilities = children
        super().__post_init__()
