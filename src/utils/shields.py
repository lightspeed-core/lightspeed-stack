"""Utility functions for working with Llama Stack shields."""

from typing import Any, Optional

from fastapi import HTTPException
from llama_stack_api import OpenAIResponseMessage
from llama_stack_client import (
    APIConnectionError,
    AsyncLlamaStackClient,
)
from llama_stack_client import (
    APIStatusError as LLSApiStatusError,
)
from llama_stack_client.types import ShieldListResponse
from openai._exceptions import APIStatusError as OpenAIAPIStatusError

from configuration import AppConfig
from constants import DEFAULT_VIOLATION_MESSAGE
from log import get_logger
from metrics import recording
from models.api.responses import (
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnprocessableEntityResponse,
)
from models.requests import QueryRequest
from utils.query import handle_known_apistatus_errors
from utils.types import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)

logger = get_logger(__name__)


async def get_available_shields(client: AsyncLlamaStackClient) -> list[str]:
    """
    Discover and return available shield identifiers.

    Parameters:
    ----------
        client: The Llama Stack client to query for available shields.

    Returns:
    -------
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
    ----------
        output_items: List of output items from the LLM response to check.

    Returns:
    -------
        bool: True if a shield violation was detected, False otherwise.
    """
    for output_item in output_items:
        item_type = getattr(output_item, "type", None)
        if item_type == "message":
            refusal = getattr(output_item, "refusal", None)
            if refusal:
                # Metric for LLM validation errors (shield violations)
                recording.record_llm_validation_error()
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


async def run_shield_moderation(
    client: AsyncLlamaStackClient,
    input_text: str,
    endpoint_path: str,
    shield_ids: Optional[list[str]] = None,
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
    shields_to_run = await get_shields_for_request(client, shield_ids)
    available_models = {model.id for model in await client.models.list()}
    for shield in shields_to_run:
        # Lightspeed safety providers configure their model internally
        # so provider_resource_id is not necessarily a valid model ID.
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
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        except (LLSApiStatusError, OpenAIAPIStatusError) as e:
            error_response = handle_known_apistatus_errors(
                e, shield.provider_resource_id or ""
            )
            raise HTTPException(**error_response.model_dump()) from e

        if moderation_result.results and moderation_result.results[0].flagged:
            result = moderation_result.results[0]
            recording.record_llm_validation_error(endpoint_path)
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
            backend_name="Llama Stack",
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


async def get_shields_for_request(
    client: AsyncLlamaStackClient,
    shield_ids: Optional[list[str]] = None,
) -> ShieldListResponse:
    """Resolve shields for the request: filtered by shield_ids or all configured.

    Args:
        client: Llama Stack client.
        shield_ids: Optional list of shield IDs. If provided, only shields
            with these identifiers are returned; if None, all configured
            shields are returned.

    Returns:
        ShieldListResponse: List of Shield objects to run for this request.

    Raises:
        HTTPException: 404 if shield_ids is provided and any requested
            shield is not configured in Llama Stack.
    """
    if shield_ids == []:
        return []
    try:
        configured_shields: ShieldListResponse = await client.shields.list()
        if shield_ids is None:
            return configured_shields
        requested = set(shield_ids)
        configured_ids = {s.identifier for s in configured_shields}
        missing = requested - configured_ids
        if missing:
            response = NotFoundResponse(
                resource=f"Shield{'s' if len(missing) > 1 else ''}",
                resource_id=", ".join(missing),
            )
            raise HTTPException(**response.model_dump())

        return [s for s in configured_shields if s.identifier in requested]
    except APIConnectionError as e:
        error_response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**error_response.model_dump()) from e
    except LLSApiStatusError as e:
        error_response = InternalServerErrorResponse.generic()
        raise HTTPException(**error_response.model_dump()) from e
