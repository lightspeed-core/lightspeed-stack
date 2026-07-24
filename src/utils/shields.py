"""Utility helpers for shield override validation and conversation persistence."""

from typing import Optional

from fastapi import HTTPException
from ogx_api import OpenAIResponseMessage
from ogx_client import (
    APIConnectionError,
    AsyncOgxClient,
)
from ogx_client import (
    APIStatusError as LLSApiStatusError,
)

from configuration import AppConfig
from models.api.requests import QueryRequest
from models.api.responses.error import (
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnprocessableEntityResponse,
)
from models.common import ShieldModerationPassed, ShieldModerationResult
from models.config import ShieldConfiguration


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
    # Currently stubbed to always pass until LCS-owned input shields are wired.
    return ShieldModerationPassed()


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

    Shield identifiers in the request map to each shield's configured ``name``.

    Args:
        shields: Configured LCS shields.
        shield_ids: Optional list of shield names. If ``None``, all ``shields``
            are returned. An empty list skips all shields. Otherwise only
            shields whose ``name`` is in this list are returned.

    Returns:
        list[ShieldConfiguration]: Shield configurations to run for this request.

    Raises:
        HTTPException: 404 if ``shield_ids`` is provided and any requested
            shield name is not present in ``shields``.
    """
    if shield_ids is None:
        return list(shields)

    if shield_ids == []:
        return []

    requested = set(shield_ids)
    configured_ids = {shield.name for shield in shields}
    missing = requested - configured_ids
    if missing:
        response = NotFoundResponse(
            resource=f"Shield{'s' if len(missing) > 1 else ''}",
            resource_id=", ".join(sorted(missing)),
        )
        raise HTTPException(**response.model_dump())

    return [shield for shield in shields if shield.name in requested]
