"""Utility functions for working with Lightspeed Core Stack shields."""

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from ogx_api import OpenAIResponseMessage
from ogx_client import APIConnectionError, AsyncOgxClient
from ogx_client import APIStatusError as LLSApiStatusError

import constants
from configuration import AppConfig
from log import get_logger
from models.api.responses.error import (
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnprocessableEntityResponse,
)
from models.common.moderation import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)
from models.config import ShieldConfiguration
from pydantic_ai_lightspeed.capabilities.question_validity.core import (
    check_question_validity,
)
from pydantic_ai_lightspeed.capabilities.redaction.core import redact_text
from utils.suid import get_suid

logger = get_logger(__name__)


@dataclass
class InputShieldsResult:
    """Outcome of running configured input shields on plain text.

    Attributes:
        text: Input text after any PII redaction.
        blocked: True when a blocking shield rejected the input.
        moderation: Passed or blocked moderation result for API compatibility.
    """

    text: str
    blocked: bool
    moderation: ShieldModerationResult


async def get_available_shields(config: AppConfig) -> list[str]:
    """
    Discover and return available shield identifiers from LCORE config.

    Parameters:
    ----------
        config: The application configuration.

    Returns:
    -------
        list[str]: List of available shield identifiers; empty if no shields
        are configured.
    """
    available_shields = [shield.shield_id for shield in config.shields]
    if not available_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info("Available shields: %s", available_shields)
    return available_shields


def validate_shield_ids_override(
    shield_ids: Optional[list[str]], config: AppConfig
) -> None:
    """
    Validate that shield_ids override is allowed by configuration.

    If configuration disables shield_ids override
    (config.customization.disable_shield_ids_override) and the incoming
    request contains shield_ids, an HTTP 422 Unprocessable Entity
    is raised instructing the client to remove the field.

    Parameters:
    ----------
        shield_ids: Optional list of shield IDs from the request.
        config: Application configuration which may include customization flags.

    Raises:
    ------
        HTTPException: If shield_ids override is disabled but shield_ids is provided.
    """
    shield_ids_override_disabled = (
        config.customization is not None
        and config.customization.disable_shield_ids_override
    )
    if shield_ids_override_disabled and shield_ids is not None:
        response = UnprocessableEntityResponse(
            response="Shield IDs customization is disabled",
            cause=(
                "This instance does not support customizing shield IDs in the "
                "request (disable_shield_ids_override is set). Please remove the "
                "shield_ids field from your request."
            ),
        )
        raise HTTPException(**response.model_dump())


async def run_input_shields(
    text: str,
    shields: list[ShieldConfiguration],
    *,
    client: AsyncOgxClient,
) -> InputShieldsResult:
    """Run configured input shields on plain text.

    Applies shields in configuration order. PII redaction rewrites ``text``;
    question validity may block and return a moderation-compat refusal.

    Args:
        text: User input to shield.
        shields: Shield configurations to run (already filtered for the request).
        client: OGX client used by LLM-backed shields.

    Returns:
        InputShieldsResult with possibly redacted text and moderation outcome.
    """
    current_text = text
    for shield in shields:
        if shield.shield_id == constants.PII_REDACTION_SHIELD_ID:
            redaction_config = shield.to_redaction_config()
            redaction_result = redact_text(
                current_text, redaction_config.compiled_patterns
            )
            current_text = redaction_result.content
            continue

        if shield.shield_id == constants.QUESTION_VALIDITY_SHIELD_ID:
            validity_config = shield.to_question_validity_config()
            classification = await check_question_validity(
                current_text,
                validity_config,
                client=client,
            )
            if not classification.allowed:
                refusal_message = validity_config.invalid_question_response
                moderation_id = f"modr_{get_suid()}"
                logger.info(
                    "Question validity shield blocked request; moderation_id=%s",
                    moderation_id,
                )
                return InputShieldsResult(
                    text=current_text,
                    blocked=True,
                    moderation=ShieldModerationBlocked(
                        message=refusal_message,
                        moderation_id=moderation_id,
                        refusal_response=create_refusal_response(refusal_message),
                    ),
                )
            continue

        logger.warning(
            "Skipping unsupported shield_id=%s in run_input_shields",
            shield.shield_id,
        )

    return InputShieldsResult(
        text=current_text,
        blocked=False,
        moderation=ShieldModerationPassed(),
    )


async def append_turn_to_conversation(
    client: AsyncOgxClient,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """
    Append a user/assistant turn to a conversation after shield violation.

    Used to record the conversation turn when a shield blocks the request,
    storing both the user's original message and the violation response.

    Parameters:
    ----------
        client: The Llama Stack client.
        conversation_id: The Llama Stack conversation ID.
        user_message: The user's input message.
        assistant_message: The shield violation response message.
    """
    try:
        await client.conversations.items.create(
            conversation_id,
            items=[
                {"type": "message", "role": "user", "content": user_message},
                {"type": "message", "role": "assistant", "content": assistant_message},
            ],
        )
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="OGX",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except LLSApiStatusError as e:
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e


def create_refusal_response(refusal_message: str) -> OpenAIResponseMessage:
    """Create a refusal response message object.

    Args:
        refusal_message: The refusal message text.

    Returns:
        OpenAIResponseMessage with refusal message.
    """
    return OpenAIResponseMessage(
        role="assistant",
        content=refusal_message,
    )


def get_shields_for_request(
    shields: list[ShieldConfiguration],
    shield_ids: Optional[list[str]] = None,
) -> list[ShieldConfiguration]:
    """Return configured shields, optionally filtered by request ``shield_ids``.

    Args:
        shields: Configured LCORE shields.
        shield_ids: Optional list of shield IDs. If ``None``, all ``shields``
            are returned. Otherwise only shields whose ``shield_id`` is in
            this list are returned. An empty list skips all shields.

    Returns:
        list[ShieldConfiguration]: Shield configurations to run for this request.

    Raises:
        HTTPException: 404 if ``shield_ids`` is provided and any requested
            shield is not present in ``shields``.
    """
    if shield_ids is None:
        return list(shields)

    requested = set(shield_ids)
    configured_ids = {shield.shield_id for shield in shields}
    missing = requested - configured_ids
    if missing:
        response = NotFoundResponse(
            resource=f"Shield{'s' if len(missing) > 1 else ''}",
            resource_id=", ".join(sorted(missing)),
        )
        raise HTTPException(**response.model_dump())

    return [shield for shield in shields if shield.shield_id in requested]
