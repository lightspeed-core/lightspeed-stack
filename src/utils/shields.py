"""Utility functions for working with Llama Stack shields."""

from typing import Any

from fastapi import HTTPException
from llama_stack_api import OpenAIResponseContentPartRefusal, OpenAIResponseMessage
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient

import metrics
from log import get_logger
from models.responses import (
    InternalServerErrorResponse,
    NotFoundResponse,
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


async def run_shield_moderation(
    client: AsyncLlamaStackClient,
    input_text: str,
) -> ShieldModerationResult:
    """
    Run shield moderation on input text.

    Iterates through all configured shields and runs moderation checks.
    Raises HTTPException if shield model is not found.

    Parameters:
        client: The Llama Stack client.
        input_text: The text to moderate.

    Returns:
        ShieldModerationResult: Passed (no attributes) or blocked with message.
    """
    available_models = {model.id for model in await client.models.list()}

    shields = await client.shields.list()
    for shield in shields:
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
