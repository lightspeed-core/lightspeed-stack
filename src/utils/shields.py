"""Utility helpers for shield override validation and moderation."""

from typing import Optional

from fastapi import HTTPException
from ogx_client import AsyncOgxClient
from opentelemetry import trace
from pydantic_ai.exceptions import AgentRunError

from configuration import AppConfig
from log import get_logger
from models.api.requests import QueryRequest
from models.api.responses.error import (
    NotFoundResponse,
    UnprocessableEntityResponse,
)
from models.common.moderation import (
    ShieldModerationPassed,
    ShieldModerationResult,
)
from models.config import QuestionValidityConfig, RedactionConfig, ShieldConfiguration
from pydantic_ai_lightspeed.capabilities.base import AbstractSafetyCapability
from pydantic_ai_lightspeed.capabilities.question_validity._capability import (
    QuestionValidity,
)
from pydantic_ai_lightspeed.capabilities.redaction._capability import (
    PiiRedactionCapability,
)
from utils.agents.error_handler import map_agent_inference_error
from utils.otel_tracing import SpanAttributes

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
    selected_shield_configs = get_shields_for_request(
        shield_configs, selected_shield_ids
    )

    for shield_config in selected_shield_configs:
        shield = build_shield(shield_config)

        try:
            shield_result = await shield.run(input_text)
        # APIConnectionError and APIStatusError from ogx should not be raised from model_request,
        # because they will be caught inside AsyncOpenAI and transferred into openai's
        # APIConnectionError. The openai's exceptions will further transferred into ModelHTTPError
        # or ModelAPIError by _map_api_errors in OpenAIResponseModel.
        except (AgentRunError, RuntimeError) as exc:
            model_id = getattr(shield_config.config, "model_id", "unknown-shield-model")
            response = map_agent_inference_error(exc, model_id)
            raise HTTPException(**response.model_dump()) from exc

        if shield_result.decision == "blocked":
            return shield_result

    return ShieldModerationPassed()


async def run_output_shield_moderation(
    response_text: str,
    output_shield_configs: list[ShieldConfiguration],
) -> ShieldModerationResult:
    """Run shield moderation on LLM output text.

    Iterates through configured output shields and checks the LLM
    response for non-technical or off-topic content before it is
    returned to the user.

    Addresses pentest finding OFFSEC-310 (LCORE-2750): the model can
    be manipulated into generating creative content outside its intended
    scope as a RHEL technical assistant.

    Parameters:
        response_text: The LLM response text to classify.
        output_shield_configs: List of output shield configurations.

    Returns:
        Result indicating if the output was blocked or passed.
    """
    if not output_shield_configs:
        return ShieldModerationPassed()

    for shield_config in output_shield_configs:
        shield = build_shield(shield_config)

        try:
            shield_result = await shield.run(response_text)
        except (AgentRunError, RuntimeError) as exc:
            model_id = getattr(
                shield_config.config, "model_id", "unknown-shield-model"
            )
            logger.warning(
                "Output shield %s failed (model=%s): %s",
                shield_config.name,
                model_id,
                exc,
            )
            # Don't block the response if the output shield itself fails —
            # return the original response rather than an error.
            continue

        if shield_result.decision == "blocked":
            logger.info(
                "Output shield %s blocked response",
                shield_config.name,
            )
            return shield_result

    return ShieldModerationPassed()


def build_shield(shield_config: ShieldConfiguration) -> AbstractSafetyCapability:
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


async def run_shield_moderation(
    _client: AsyncOgxClient,
    _input_text: str,
    _endpoint_path: str,
    _shield_ids: Optional[list[str]] = None,
) -> ShieldModerationResult:
    """
    Run shield moderation on input text.

    Iterates through configured shields and runs moderation checks.
    Raises HTTPException if shield model is not found.

    Parameters:
    ----------
        client: The Llama Stack client.
        input_text: The text to moderate.
        endpoint_path: The API endpoint path for metric labeling.
        shield_ids: Optional list of shield IDs to use. If None, uses all shields.
                   If empty list, skips all shields.

    Returns:
    -------
        ShieldModerationResult: Result indicating if content was blocked and the message.

    Raises:
    ------
        HTTPException: If shield's provider_resource_id is not configured or model not found.
    """
    with tracer.start_as_current_span("shield.moderate") as span:
        # Currently stubbed to always pass until LCS-owned input shields are wired.
        result = ShieldModerationPassed()
        span.set_attribute(SpanAttributes.SHIELD_RESULT, "passed")
        return result


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
