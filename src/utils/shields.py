"""Utility helpers for shield override validation and moderation."""

import uuid
from typing import Literal, Optional

from fastapi import HTTPException
from opentelemetry import trace
from pydantic_ai.exceptions import AgentRunError

from configuration import AppConfig
from constants import OBFUSCATION_REJECTION_MESSAGE
from log import get_logger
from models.api.requests import QueryRequest
from models.api.responses.error import (
    NotFoundResponse,
    UnprocessableEntityResponse,
)
from models.common.moderation import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)
from models.config import (
    GraniteGuardianConfig,
    QuestionValidityConfig,
    RedactionConfig,
    ShieldConfiguration,
)
from pydantic_ai_lightspeed.capabilities.base import AbstractSafetyCapability
from pydantic_ai_lightspeed.capabilities.granite_guardian import (
    GraniteGuardian,
)
from pydantic_ai_lightspeed.capabilities.question_validity._capability import (
    QuestionValidity,
)
from pydantic_ai_lightspeed.capabilities.redaction._capability import (
    PiiRedactionCapability,
)
from pydantic_ai_lightspeed.capabilities.redaction.core import redact_text
from utils.agents.error_handler import map_agent_inference_error
from utils.input_sanitization import sanitize_input
from utils.otel_tracing import (
    SpanEvents,
    add_span_event,
    set_span_attributes,
    shield_span_attributes,
)
from utils.types import TextRedactor

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)


def validate_shield_ids_override(
    query_request: QueryRequest, config: AppConfig
) -> None:
    """
    Validate that shield_ids override is allowed by configuration.

    If configuration disables shield_ids override
    (config.customization.disable_shield_ids_override) and the incoming
    query_request contains shield_ids, an HTTP 422 Unprocessable Entity
    is raised instructing the client to remove the field.

    Parameters:
    ----------
        query_request: The incoming query payload; may contain shield_ids.
        config: Application configuration which may include customization flags.

    Raises:
    ------
        HTTPException: If shield_ids override is disabled but shield_ids is provided.

    """
    shield_ids_override_disabled = (
        config.customization is not None
        and config.customization.disable_shield_ids_override
    )
    if shield_ids_override_disabled and query_request.shield_ids is not None:
        response = UnprocessableEntityResponse(
            response="Shield IDs customization is disabled",
            cause=(
                "This instance does not support customizing shield IDs in the "
                "query request (disable_shield_ids_override is set). Please remove the "
                "shield_ids field from your request."
            ),
        )
        raise HTTPException(**response.model_dump())


async def run_shield_moderation_v2(
    input_text: str,
    shield_configs: list[ShieldConfiguration],
    selected_shield_ids: Optional[list[str]] = None,
    guardrail_point: Literal["input", "output", "tool"] = "input",
) -> ShieldModerationResult:
    """Run v2 shield moderation on input text.

    Iterates through configured shields and runs moderation checks.

    Parameters:
        input_text: The text to moderate.
        shield_configs: List of shield configurations to evaluate.
        selected_shield_ids: Optional list of shield names to filter by.

    Returns:
        Result indicating if content was blocked or passed.

    """
    with tracer.start_as_current_span("shield.moderate") as span:
        # Sanitize input before running any shields (OFFSEC-307 / LCORE-2749).
        # Normalizes Unicode and rejects obfuscated content (unusual Unicode
        # blocks, binary/hex encoding, XML injection patterns).
        normalized_text, rejection_reason = sanitize_input(input_text)
        if rejection_reason:
            logger.warning("Input blocked by sanitization: %s", rejection_reason)
            blocked = ShieldModerationBlocked(
                decision="blocked",
                message=OBFUSCATION_REJECTION_MESSAGE,
                moderation_id=f"modr-{uuid.uuid4()}",
            )
            set_span_attributes(span, shield_span_attributes(blocked))
            return blocked
        input_text = normalized_text

        selected_shield_configs = get_shields_for_request(
            shield_configs, selected_shield_ids
        )

        for shield_config in selected_shield_configs:
            shield = build_shield(shield_config, guardrail_point)

            try:
                shield_result = await shield.run(input_text)
            # ApiException from OGX should not be raised from model_request,
            # because they will be caught inside AsyncOpenAI and transferred into
            # openai's APIStatusError. The openai's exceptions will further be
            # transferred into ModelHTTPError or ModelAPIError by _map_api_errors
            # in OpenAIResponseModel.
            except (AgentRunError, RuntimeError) as exc:
                model_id = getattr(
                    shield_config.config, "model_id", "unknown-shield-model"
                )
                response = map_agent_inference_error(exc, model_id)
                raise HTTPException(**response.model_dump()) from exc

            if shield_result.decision == "blocked":
                set_span_attributes(span, shield_span_attributes(shield_result))
                add_span_event(span, SpanEvents.SHIELD_REJECTED)
                return shield_result

        set_span_attributes(span, shield_span_attributes(ShieldModerationPassed()))
        return ShieldModerationPassed()


def build_shield(
    shield_config: ShieldConfiguration,
    guardrail_point: Literal["input", "output", "tool"] = "input",
) -> AbstractSafetyCapability:
    """Build a safety capability instance from a shield configuration.

    Parameters:
        shield_config: The shield configuration to build from.

    Returns:
        The constructed safety capability.

    """
    match shield_config.config:
        case QuestionValidityConfig():
            return QuestionValidity(shield_config.config)
        case RedactionConfig():
            return PiiRedactionCapability(shield_config.config)
        case GraniteGuardianConfig():
            return GraniteGuardian(shield_config.config, guardrail_point)
        case _:
            raise ValueError(
                f"Unsupported shield config type for shield '{shield_config.name}': "
                f"{type(shield_config.config).__name__}"
            )


def get_shields_for_request(
    shields: list[ShieldConfiguration],
    shield_ids: Optional[list[str]] = None,
) -> list[ShieldConfiguration]:
    """Return configured shields, optionally filtered by request shield_ids.

    Args:
        shields: Configured LCS shields.
        shield_ids: Optional list of shield names. If None, all shields are
            returned. An empty list skips all shields. Otherwise only shields
            whose name is in this list are returned.

    Returns:
        list[ShieldConfiguration]: Shield configurations to run for this request.

    Raises:
        HTTPException: 404 if shield_ids is provided and any requested shield
            name is not present in shields.

    """
    if shield_ids is None:
        return list(shields)

    if shield_ids == []:
        return []

    requested = set(shield_ids)
    configured_names = {shield.name for shield in shields}
    missing = requested - configured_names
    if missing:
        response = NotFoundResponse(
            resource=f"Shield{'s' if len(missing) > 1 else ''}",
            resource_id=", ".join(sorted(missing)),
        )
        raise HTTPException(**response.model_dump())

    return [shield for shield in shields if shield.name in requested]


def request_redactor(
    shields: list[ShieldConfiguration],
    shield_ids: Optional[list[str]] = None,
) -> Optional[TextRedactor]:
    """Build the text redaction of the shields a request selects.

    The rules of the selected redaction shields are applied one after another
    in configuration order, the order in which their capabilities run on an
    agent. It is for the places where lightspeed-stack builds or stores text
    that the redaction capability does not see.

    Parameters:
        shields: Configured LCS shields.
        shield_ids: The shield selection of the request, with the meaning it
            has for ``get_shields_for_request``.

    Returns:
        A function that redacts a text, or ``None`` when the selection holds
        no redaction rule.

    Raises:
        HTTPException: 404 if shield_ids names a shield that is not configured.

    """
    patterns = [
        compiled
        for shield in get_shields_for_request(shields, shield_ids)
        if isinstance(shield.config, RedactionConfig)
        for compiled in shield.config.compiled_patterns
    ]
    if not patterns:
        return None

    def redact(text: str) -> str:
        """Apply the selected redaction rules to a text."""
        return redact_text(text, patterns).content

    return redact
