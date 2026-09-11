"""Granite Guardian safety capability for input/output guardrail moderation."""

import asyncio
from dataclasses import dataclass, field
from typing import ClassVar, Optional
from uuid import uuid4

import httpx
from openai import AsyncOpenAI
from pydantic import StrictBool
from pydantic_ai import AgentRunResult, RunContext
from pydantic_ai._agent_graph import GraphAgentState
from pydantic_ai.capabilities import WrapRunHandler
from pydantic_ai.direct import model_request
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage

from client.ogx import AsyncOgxClientHolder
from log import get_logger
from models.common.moderation import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)
from models.config import GraniteGuardianConfig, GuardrailPoint, RiskDefinition
from pydantic_ai_lightspeed.capabilities.base import AbstractSafetyCapability
from pydantic_ai_lightspeed.capabilities.granite_guardian.utils import (
    build_guardian_block,
    is_safe,
)
from pydantic_ai_lightspeed.capabilities.utils import (
    extract_conversation_id,
    message_to_str,
)
from utils.conversations import append_turn_to_conversation

type Guardrail = tuple[str, str, float, str]

logger = get_logger(__name__)


async def _package_risk_check_task(
    prompt: str, guardrail: Guardrail, model: Model
) -> tuple[ModelResponse, float, str]:
    """Run a single Guardian risk check and return its result.

    Parameters:
        prompt: The text to evaluate.
        guardrail: A guardrail tuple of (name, block, threshold, violation_message).
        model: The Granite Guardian model to use for evaluation.

    Returns:
        A tuple of (model_response, threshold, violation_message).
    """
    name, block, threshold, violation_message = guardrail
    start = asyncio.get_event_loop().time()
    result = await model_request(
        model=model,
        messages=[ModelRequest.user_text_prompt(prompt, instructions=block)],
        model_settings=OpenAIChatModelSettings(
            openai_logprobs=True, openai_top_logprobs=20
        ),
    )
    elapsed = asyncio.get_event_loop().time() - start
    logger.info("Guardian risk '%s' completed in %.3fs", name, elapsed)
    return result, threshold, violation_message


async def _run_risk_check(
    prompt: str,
    model: Model,
    guardrails: list[Guardrail],
    batch_size: int = 3,
) -> tuple[Optional[str], RequestUsage]:
    """Evaluate the prompt against guardrails in parallel batches.

    Guardrails are dispatched concurrently in batches. Within each batch,
    all checks run in parallel; if any violation is found the remaining
    batches are skipped. Per-rule latency is logged at INFO level.

    Parameters:
        prompt: The text to evaluate.
        model: The Granite Guardian model to use for evaluation.
        guardrails: Ordered list of guardrail tuples to check.
        batch_size: Number of risk checks to run in parallel per batch.

    Returns:
        A tuple of (violation_message, token_usage). violation_message is
        None when all checks pass.

    Raises:
        UnexpectedModelBehavior: When the model response is missing
            provider_details or logprobs.
    """
    token_usage = RequestUsage()

    for i in range(0, len(guardrails), batch_size):
        batch = [
            _package_risk_check_task(prompt, g, model)
            for g in guardrails[i : i + batch_size]
        ]

        results = await asyncio.gather(*batch)

        for result, _, _ in results:
            token_usage.incr(result.usage)

        for result, threshold, violation_message in results:
            if not result.provider_details:
                raise UnexpectedModelBehavior(
                    "No provider_details provided from granite guardian's response"
                )

            logprobs = result.provider_details.get("logprobs")
            if not logprobs:
                raise UnexpectedModelBehavior("No logprobs field in provider_details")

            if not is_safe(threshold, logprobs):
                return violation_message, token_usage

    return None, token_usage


def _filter_guardrails(
    risks: list[RiskDefinition], point: GuardrailPoint
) -> list[Guardrail]:
    """Filter risk definitions to guardrail tuples for a given guardrail point.

    Parameters:
        risks: All configured risk definitions.
        point: The guardrail point to filter by (INPUT, OUTPUT, or TOOL).

    Returns:
        A list of guardrail tuples for enabled risks matching the point.
    """
    return [
        (
            risk.name,
            build_guardian_block(risk.description, think=risk.enable_thinking),
            risk.threshold,
            risk.violation_message,
        )
        for risk in risks
        if risk.enabled and point in risk.points
    ]


def _get_batch_size(parallel: StrictBool | int, num_guardrail: int) -> int:
    """Resolve the parallel setting to a concrete batch size.

    Parameters:
        parallel: True for full parallelism, False for sequential, or an
            explicit batch size.
        num_guardrail: Total number of guardrails to run.

    Returns:
        The number of risk checks to run concurrently per batch.
    """
    if isinstance(parallel, bool):
        return max(1, num_guardrail) if parallel else 1

    return parallel


@dataclass
class GraniteGuardian(AbstractSafetyCapability):
    """Safety capability using Granite Guardian for risk-based moderation.

    Uses Granite Guardian's logprob-based scoring to evaluate user input
    against configured risk categories. When used as a pydantic-ai capability,
    ``wrap_run`` applies input guardrails. The ``run`` method provides a
    standalone shield interface for use outside the agent lifecycle.

    Attributes:
        config: Granite Guardian configuration with risks and connection details.
        run_moderation_guardrail_point: The guardrail point used by the
            standalone ``run`` method.
    """

    config: GraniteGuardianConfig
    run_moderation_guardrail_point: GuardrailPoint = "input"
    _model: Model = field(init=False)
    # Only one Granite Guardian shield should be configured; multiple entries are
    # unsupported. A dict is used defensively so that a misconfiguration with two
    # distinct configs does not cause one to silently overwrite the other's model.
    _model_cache: ClassVar[dict[int, Model]] = {}

    def __post_init__(self) -> None:
        """Initialize the Granite Guardian model with the configured provider."""
        cache_key = id(self.config)
        if cache_key in GraniteGuardian._model_cache:
            self._model = GraniteGuardian._model_cache[cache_key]
            return

        http_client = httpx.AsyncClient(
            verify=self.config.verify_ssl,
            timeout=self.config.timeout,
        )

        # When we attach the API key to the request, we need to make sure we encrypt the
        # request by communicating through https
        base_url = httpx.URL(self.config.url)
        if self.config.api_key is not None and base_url.scheme != "https":
            raise ValueError(
                "Granite Guardian endpoints with an API key must use HTTPS"
            )

        openai_client = AsyncOpenAI(
            base_url=self.config.url,
            api_key=(
                self.config.api_key.get_secret_value()  # pylint: disable=no-member
                if self.config.api_key is not None
                else "api-key-not-set"
            ),
            max_retries=self.config.max_retries,
            http_client=http_client,
        )

        provider = OpenAIProvider(openai_client=openai_client)

        self._model = OpenAIChatModel(self.config.model_id, provider=provider)
        GraniteGuardian._model_cache[cache_key] = self._model

    async def wrap_run(
        self, ctx: RunContext, *, handler: WrapRunHandler
    ) -> AgentRunResult:
        """Apply input guardrails before the agent run.

        Evaluates the user prompt against all INPUT-point risks. If any risk
        is violated, the run is short-circuited with a rejection message.
        Otherwise, the handler is called to proceed with the real run.

        Parameters:
            ctx: The run context containing the user prompt and usage tracker.
            handler: The handler to call if the input passes all guardrails.

        Returns:
            The agent run result, either a rejection or the handler's result.
        """
        user_prompt = message_to_str(ctx.prompt)

        input_guardrails = _filter_guardrails(self.config.risks, "input")
        batch_size = _get_batch_size(self.config.parallel, len(input_guardrails))
        # TODO: We need to consider how we want to reveal the token usage for Granite Guardian,  # pylint: disable=fixme
        # since combining the token usage with the main inference model is not a right thing to do.
        violation_message, _ = await _run_risk_check(
            user_prompt, self._model, input_guardrails, batch_size
        )

        if violation_message is not None:
            state = GraphAgentState(
                usage=ctx.usage,
                message_history=[
                    ModelRequest.user_text_prompt(user_prompt),
                    ModelResponse(
                        [TextPart(violation_message)],
                        finish_reason="stop",
                    ),
                ],
            )

            conversation_id = extract_conversation_id(ctx.model)
            if conversation_id is not None:
                await append_turn_to_conversation(
                    AsyncOgxClientHolder().get_client(),
                    conversation_id,
                    user_prompt,
                    violation_message,
                )
            else:
                logger.warning(
                    "Unable to determine conversation ID from model settings; "
                    "skipping v1/conversation persistence for rejected question."
                )

            return AgentRunResult(output=violation_message, _state=state)

        return await handler()  # proceed with the real run

    async def run(self, input_text: str) -> ShieldModerationResult:
        """Run standalone shield moderation on the given text.

        Uses ``run_moderation_guardrail_point`` to filter which risks apply.

        Parameters:
            input_text: The text to evaluate.

        Returns:
            A blocked result with the violation message, or a passed result.
        """
        filtered_guardrails = _filter_guardrails(
            self.config.risks, self.run_moderation_guardrail_point
        )
        batch_size = _get_batch_size(self.config.parallel, len(filtered_guardrails))

        violation_message, _ = await _run_risk_check(
            input_text, self._model, filtered_guardrails, batch_size
        )

        if violation_message is not None:
            return ShieldModerationBlocked(
                message=violation_message, moderation_id=f"modr-{uuid4()}"
            )

        return ShieldModerationPassed()
