"""Utility functions for working with Llama Stack shields."""

import logging
from typing import Any, Optional, cast

from fastapi import HTTPException
from llama_stack_client import AsyncLlamaStackClient, BadRequestError
from llama_stack_client.types import CreateResponse

import metrics
from models.responses import NotFoundResponse
from utils.types import ShieldModerationResult

logger = logging.getLogger(__name__)

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
            logger.info("shield_ids=[] provided, skipping all shields")
            return ShieldModerationResult(blocked=False)

        shields_to_run = [s for s in all_shields if s.identifier in shield_ids]

        # Log warning if requested shield not found
        requested = set(shield_ids)
        available = {s.identifier for s in shields_to_run}
        missing = requested - available
        if missing:
            logger.warning("Requested shields not found: %s", missing)
    else:
        shields_to_run = list(all_shields)

    available_models = {model.id for model in await client.models.list()}

    for shield in shields_to_run:
        if (
            not shield.provider_resource_id
            or shield.provider_resource_id not in available_models
        ):
            response = NotFoundResponse(
                resource="Shield model", resource_id=shield.provider_resource_id or ""
            )
            raise HTTPException(**response.model_dump())

        try:
            moderation = await client.moderations.create(
                input=input_text, model=shield.provider_resource_id
            )
            moderation_result = cast(CreateResponse, moderation)

            if moderation_result.results and moderation_result.results[0].flagged:
                result = moderation_result.results[0]
                metrics.llm_calls_validation_errors_total.inc()
                logger.warning(
                    "Shield '%s' flagged content: categories=%s",
                    shield.identifier,
                    result.categories,
                )
                violation_message = result.user_message or DEFAULT_VIOLATION_MESSAGE
                return ShieldModerationResult(
                    blocked=True,
                    message=violation_message,
                    shield_model=shield.provider_resource_id,
                )

        # Known Llama Stack bug: error is raised when violation is present
        # in the shield LLM response but has wrong format that cannot be parsed.
        except (BadRequestError, ValueError):
            logger.warning(
                "Shield '%s' violation detected, treating as blocked",
                shield.identifier,
            )
            metrics.llm_calls_validation_errors_total.inc()
            return ShieldModerationResult(
                blocked=True,
                message=DEFAULT_VIOLATION_MESSAGE,
                shield_model=shield.provider_resource_id,
            )

    return ShieldModerationResult(blocked=False)


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
    await client.conversations.items.create(
        conversation_id,
        items=[
            {"type": "message", "role": "user", "content": user_message},
            {"type": "message", "role": "assistant", "content": assistant_message},
        ],
    )
