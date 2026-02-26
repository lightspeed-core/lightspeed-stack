"""Utility functions for working with Llama Stack shields."""

from typing import Any, Optional

from fastapi import HTTPException
from llama_stack_api import OpenAIResponseContentPartRefusal, OpenAIResponseMessage
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient

import metrics
from configuration import AppConfig
from log import get_logger
from models.requests import QueryRequest
from models.responses import (
    InternalServerErrorResponse,
    NotFoundResponse,
    UnprocessableEntityResponse,
    ServiceUnavailableResponse,
)
from utils.suid import get_suid
from utils.types import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)

logger = get_logger(__name__)

DEFAULT_VIOLATION_MESSAGE = "I cannot process this request due to policy restrictions."


async def get_available_shields(client: AsyncLlamaStackClient) -> list[str]:
    """
    Discover and return available shield identifiers.

    Parameters:
        client: The Llama Stack client to query for available shields.

    Returns:
        list[str]: List of available shield identifiers; empty if no shields are available.
    """
    available_shields = [shield.identifier for shield in await client.shields.list()]
    if not available_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info("Available shields: %s", available_shields)
    return available_shields


def detect_shield_violations(output_items: list[Any]) -> bool:
    """
    Check output items for shield violations and update metrics.

    Iterates through output items looking for message items with refusal
    attributes. If a refusal is found, increments the validation error
    metric and logs a warning.

    Parameters:
        output_items: List of output items from the LLM response to check.

    Returns:
        bool: True if a shield violation was detected, False otherwise.
    """
    for output_item in output_items:
        item_type = getattr(output_item, "type", None)
        if item_type == "message":
            refusal = getattr(output_item, "refusal", None)
            if refusal:
                # Metric for LLM validation errors (shield violations)
                metrics.llm_calls_validation_errors_total.inc()
                logger.warning("Shield violation detected: %s", refusal)
                return True
    return False


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
        query_request: The incoming query payload; may contain shield_ids.
        config: Application configuration which may include customization flags.

    Raises:
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


async def run_shield_moderation(
    client: AsyncLlamaStackClient,
    input_text: str,
    shield_ids: Optional[list[str]] = None,
) -> ShieldModerationResult:
    """
    Run shield moderation on input text.

    Iterates through configured shields and runs moderation checks.
    Raises HTTPException if shield model is not found.

    Parameters:
        client: The Llama Stack client.
        input_text: The text to moderate.
        shield_ids: Optional list of shield IDs to use. If None, uses all shields.
                   If empty list, skips all shields.

    Returns:
        ShieldModerationResult: Result indicating if content was blocked and the message.

    Raises:
        HTTPException: If shield's provider_resource_id is not configured or model not found.
    """
    all_shields = await client.shields.list()

    # Filter shields based on shield_ids parameter
    if shield_ids is not None:
        if len(shield_ids) == 0:
            response = UnprocessableEntityResponse(
                response="Invalid shield configuration",
                cause=(
                    "shield_ids provided but no shields selected. "
                    "Remove the parameter to use default shields."
                ),
            )
            raise HTTPException(**response.model_dump())

        shields_to_run = [s for s in all_shields if s.identifier in shield_ids]

        # Log warning if requested shield not found
        requested = set(shield_ids)
        available = {s.identifier for s in shields_to_run}
        missing = requested - available
        if missing:
            logger.warning("Requested shields not found: %s", missing)

        # Reject if no requested shields were found (prevents accidental bypass)
        if not shields_to_run:
            response = UnprocessableEntityResponse(
                response="Invalid shield configuration",
                cause=f"Requested shield_ids not found: {sorted(missing)}",
            )
            raise HTTPException(**response.model_dump())
    else:
        shields_to_run = list(all_shields)

    available_models = {model.id for model in await client.models.list()}

    for shield in shields_to_run:
        # Only validate provider_resource_id against models for llama-guard.
        # Llama Stack does not verify that the llama-guard model is registered,
        # so we check it here to fail fast with a clear error.
        # Custom shield providers (e.g. lightspeed_question_validity) configure
        # their model internally, so provider_resource_id is not a model ID.
        if shield.provider_id == "llama-guard" and (
            not shield.provider_resource_id
            or shield.provider_resource_id not in available_models
        ):
            logger.error("Shield model not found: %s", shield.provider_resource_id)
            response = NotFoundResponse(
                resource="Shield model", resource_id=shield.provider_resource_id or ""
            )
            raise HTTPException(**response.model_dump())

        try:
            moderation_result = await client.moderations.create(
                input=input_text, model=shield.provider_resource_id
            )
        # Known Llama Stack bug: error is raised when violation is present
        # in the shield LLM response but has wrong format that cannot be parsed.
        except ValueError:
            logger.warning(
                "Shield violation detected, treating as blocked",
            )
            metrics.llm_calls_validation_errors_total.inc()
            return ShieldModerationBlocked(
                message=DEFAULT_VIOLATION_MESSAGE,
                moderation_id=f"modr_{get_suid()}",
                refusal_response=create_refusal_response(DEFAULT_VIOLATION_MESSAGE),
            )

        if moderation_result.results and moderation_result.results[0].flagged:
            result = moderation_result.results[0]
            metrics.llm_calls_validation_errors_total.inc()
            logger.warning(
                "Shield '%s' flagged content: categories=%s",
                shield.identifier,
                result.categories,
            )
            violation_message = result.user_message or DEFAULT_VIOLATION_MESSAGE
            return ShieldModerationBlocked(
                message=violation_message,
                moderation_id=moderation_result.id,
                refusal_response=create_refusal_response(violation_message),
            )

    return ShieldModerationPassed()


async def append_turn_to_conversation(
    client: AsyncLlamaStackClient,
    conversation_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """
    Append a user/assistant turn to a conversation after shield violation.

    Used to record the conversation turn when a shield blocks the request,
    storing both the user's original message and the violation response.

    Parameters:
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
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except APIStatusError as e:
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e


def create_refusal_response(refusal_message: str) -> OpenAIResponseMessage:
    """Create a refusal response message object.

    Creates an OpenAIResponseMessage with assistant role containing a refusal
    content part. This can be used for both conversation items and response output.

    Args:
        refusal_message: The refusal message text.

    Returns:
        OpenAIResponseMessage with refusal content.
    """
    refusal_content = OpenAIResponseContentPartRefusal(refusal=refusal_message)
    return OpenAIResponseMessage(
        type="message",
        role="assistant",
        content=[refusal_content],
    )
