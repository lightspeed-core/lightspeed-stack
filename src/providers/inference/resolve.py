"""Soft-fallback helpers for request-path model resolution."""

from __future__ import annotations

from typing import Optional

from configuration import configuration
from log import get_logger
from providers.inference.types import ProviderId
from utils.endpoints import retrieve_conversation

logger = get_logger(__name__)


def conversation_last_used(
    conversation_id: Optional[str],
) -> Optional[tuple[ProviderId, str]]:
    """Load last-used provider/model ids from a conversation when present.

    Args:
        conversation_id: Conversation id to look up, or None to skip.

    Returns:
        ``(provider_id, model_id)`` from the conversation, or None when the
        conversation id is omitted or not found.

    """
    if conversation_id is None:
        return None

    conversation = retrieve_conversation(conversation_id)
    if conversation is None:
        logger.warning(
            "Conversation %r not found while resolving llm; soft-skipping "
            "last-used fallback",
            conversation_id,
        )
        return None

    return conversation.last_used_provider, conversation.last_used_model


def configured_defaults() -> Optional[tuple[ProviderId, str]]:
    """Return configured default provider/model ids when both are set.

    Returns:
        ``(provider_id, model_id)`` from inference configuration, or None
        when either default is unset.

    """
    inference = configuration.inference
    provider_id = inference.default_provider
    model_id = inference.default_model
    if not provider_id or not model_id:
        logger.warning(
            "Inference default provider/model unset; soft-skipping configured "
            "default fallback"
        )
        return None
    return provider_id, model_id
