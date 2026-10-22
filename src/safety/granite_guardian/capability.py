"""``GraniteGuardianRisk`` and ``GraniteGuardian``: Granite-Guardian risk checks and their shield.

A ``granite_guardian`` shield can list several independent risks (e.g. jailbreak, harm,
groundedness). Rather than one capability that loops over all of them internally, each risk is
its own :class:`GraniteGuardianRisk`, and :class:`GraniteGuardian` combines one per risk via
:class:`~pydantic_ai.capabilities.CombinedCapability`, so each risk is its own guard in the
agent's capability chain -- screened, ordered, and reasoned about independently -- while still
sharing the one Granite Guardian `model`.

Neither class depends on :mod:`lightspeed.app.models.config`: `GraniteGuardian` takes plain
`Risk` values rather than a config object, so this module stays usable (and testable)
independent of the YAML config schema. `GraniteGuardianConfig.risks` is `Risk` directly (the
dependency runs the other way -- config on capability, not capability on config), so
:mod:`~lightspeed.core.agent.safety.factory` passes it through unchanged, resolving only
`GraniteGuardianConfig.model` to a pydantic-ai `Model` via `ProviderRegistry`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

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
class GraniteGuardianRisk(AbstractSafetyCapability[AgentDepsT]):
    """Screens a prompt or response for one risk, via a direct request to Granite Guardian.

    Attach the same way any other safety capability is attached -- see
    :class:`~lightspeed.core.agent.safety.base.AbstractSafetyCapability` -- or call
    :meth:`evaluate` directly for a standalone check. Typically constructed via
    :class:`GraniteGuardian` rather than directly, so sibling risks in the same shield share
    the same `model`.
    """

    risk: Risk = field(kw_only=True)
    """The risk to screen for -- its judging criteria, violation message, threshold, etc.
    `type` (see `AbstractSafetyCapability.type`) is copied from `risk.type` in
    `__post_init__`, so this is the only risk-specific input the constructor needs."""

    model: Model = field(kw_only=True)
    """The Granite Guardian model to send the risk check to. Required -- typically set via
    :class:`GraniteGuardian`, which shares one `model` across all of its risks."""

    type: Sequence[Literal["input", "output", "tool"]] = field(
        default_factory=list, init=False
    )
    """Which guardrail points this risk applies to; derived from `risk.type` in `__post_init__`.
    See `AbstractSafetyCapability.type`."""

    def __post_init__(self) -> None:
        """Copy ``risk.type`` onto this capability instance.

        Lets ``AbstractSafetyCapability`` hooks screen the guardrail points configured on
        ``risk`` without passing ``type`` separately.
        """
        self.type = self.risk.type

    async def evaluate(self, prompt: str) -> GuardrailResult:
        """Score `prompt` against `risk.criteria` and return the verdict.

        Calls `model.request` directly (via `pydantic_ai.direct.model_request`) instead of
        running an `Agent`: the check needs no tools, output schema, or agent-graph
        machinery, just the one request/response pair scored by its logprobs.

        Raises:
            UnexpectedModelBehavior: If the response is missing the `provider_details` or
                `logprobs` Granite Guardian's verdict is scored from.

        """
        request = ModelRequest.user_text_prompt(
            prompt,
            instructions=build_guardian_block(
                self.risk.criteria, think=self.risk.enable_thinking
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

        if is_safe(self.risk.threshold, logprobs):
            return GuardrailResult.allow()
        return GuardrailResult.block(message=self.risk.violation_message)


@dataclass
class GraniteGuardian(CombinedCapability[AgentDepsT]):
    """A ``granite_guardian`` shield: one :class:`GraniteGuardianRisk` per risk in `risks`.

    `capabilities` is derived from `risks` and `model` in `__post_init__`, rather than passed
    directly -- construct with `risks=`/`model=` instead of `capabilities=`.
    """

    risks: Sequence[Risk] = field(default_factory=list)
    """Risks to screen for. Each becomes its own `GraniteGuardianRisk` in `capabilities`."""

    model: Model = field(kw_only=True)
    """The Granite Guardian model shared by every risk in `capabilities`. Required; passed
    through unchanged to each risk's `GraniteGuardianRisk.model`."""

    check_tokens: int = field(kw_only=True, default=50)
    """Passed through to each risk's `GraniteGuardianRisk.check_tokens`."""

    capabilities: Sequence[AbstractCapability[AgentDepsT]] = field(
        default_factory=list, init=False
    )
    """Populated in `__post_init__` from `risks`; not meant to be passed directly."""

    def __post_init__(self) -> None:
        """Build one ``GraniteGuardianRisk`` per configured risk.

        Delegates to ``CombinedCapability`` normalization after populating ``capabilities``.
        """
        prefix = f"{self.id}." if self.id is not None else ""
        self.capabilities = [
            GraniteGuardianRisk(  # pylint: disable=unexpected-keyword-arg
                id=f"{prefix}{risk.name}",
                risk=risk,
                model=self.model,
                check_tokens=self.check_tokens,
            )
            for risk in self.risks
        ]
        super().__post_init__()
