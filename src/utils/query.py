"""Utility functions for query endpoints."""

from datetime import datetime, UTC
import logging
from typing import Annotated, Any

from llama_stack_client import APIConnectionError
from llama_stack_client.types.model_list_response import ModelListResponse
from llama_stack_client.types import Shield

from fastapi import HTTPException, Request, status, Depends

from authentication.interface import AuthTuple
from configuration import configuration
from app.database import get_session
import metrics
import constants
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import QueryRequest, Attachment
from models.responses import UnauthorizedResponse, ForbiddenResponse
from utils.endpoints import (
    check_configuration_loaded,
    validate_conversation_ownership,
    validate_model_provider_override,
)
from utils.transcripts import store_transcript
from utils.types import TurnSummary

logger = logging.getLogger("utils.query")

# Response schemas for OpenAPI documentation
query_response: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "response": "LLM answer",
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
    500: {
        "detail": {
            "response": "Unable to connect to Llama Stack",
            "cause": "Connection error.",
        }
    },
}


def is_transcripts_enabled() -> bool:
    """Check if transcripts is enabled.

    Returns:
        bool: True if transcripts is enabled, False otherwise.
    """
    return configuration.user_data_collection_configuration.transcripts_enabled


def persist_user_conversation_details(
    user_id: str, conversation_id: str, model: str, provider_id: str
) -> None:
    """Associate conversation to user in the database."""
    with get_session() as session:
        existing_conversation = (
            session.query(UserConversation).filter_by(id=conversation_id).first()
        )

        if not existing_conversation:
            conversation = UserConversation(
                id=conversation_id,
                user_id=user_id,
                last_used_model=model,
                last_used_provider=provider_id,
                message_count=1,
            )
            session.add(conversation)
            logger.debug(
                "Associated conversation %s to user %s", conversation_id, user_id
            )
        else:
            existing_conversation.last_used_model = model
            existing_conversation.last_used_provider = provider_id
            existing_conversation.last_message_at = datetime.now(UTC)
            existing_conversation.message_count += 1

        session.commit()


def evaluate_model_hints(
    user_conversation: UserConversation | None,
    query_request: QueryRequest,
) -> tuple[str | None, str | None]:
    """Evaluate model hints from user conversation."""
    model_id: str | None = query_request.model
    provider_id: str | None = query_request.provider

    if user_conversation is not None:
        if query_request.model is not None:
            if query_request.model != user_conversation.last_used_model:
                logger.debug(
                    "Model specified in request: %s, preferring it over user conversation model %s",
                    query_request.model,
                    user_conversation.last_used_model,
                )
        else:
            logger.debug(
                "No model specified in request, using latest model from user conversation: %s",
                user_conversation.last_used_model,
            )
            model_id = user_conversation.last_used_model

        if query_request.provider is not None:
            if query_request.provider != user_conversation.last_used_provider:
                logger.debug(
                    "Provider specified in request: %s, "
                    "preferring it over user conversation provider %s",
                    query_request.provider,
                    user_conversation.last_used_provider,
                )
        else:
            logger.debug(
                "No provider specified in request, "
                "using latest provider from user conversation: %s",
                user_conversation.last_used_provider,
            )
            provider_id = user_conversation.last_used_provider

    return model_id, provider_id


def select_model_and_provider_id(
    models: ModelListResponse, model_id: str | None, provider_id: str | None
) -> tuple[str, str, str]:
    """
    Select the model ID and provider ID based on the request or available models.

    Determine and return the appropriate model and provider IDs for
    a query request.

    If the request specifies both model and provider IDs, those are used.
    Otherwise, defaults from configuration are applied. If neither is
    available, selects the first available LLM model from the provided model
    list. Validates that the selected model exists among the available models.

    Returns:
        A tuple containing the combined model ID (in the format
        "provider/model") and the provider ID.

    Raises:
        HTTPException: If no suitable LLM model is found or the selected model is not available.
    """
    # If model_id and provider_id are provided in the request, use them

    # If model_id is not provided in the request, check the configuration
    if not model_id or not provider_id:
        logger.debug(
            "No model ID or provider ID specified in request, checking configuration"
        )
        model_id = configuration.inference.default_model  # type: ignore[reportAttributeAccessIssue]
        provider_id = (
            configuration.inference.default_provider  # type: ignore[reportAttributeAccessIssue]
        )

    # If no model is specified in the request or configuration, use the first available LLM
    if not model_id or not provider_id:
        logger.debug(
            "No model ID or provider ID specified in request or configuration, "
            "using the first available LLM"
        )
        try:
            model = next(
                m
                for m in models
                if m.model_type == "llm"  # pyright: ignore[reportAttributeAccessIssue]
            )
            model_id = model.identifier
            provider_id = model.provider_id
            logger.info("Selected model: %s", model)
            return model_id, model_id, provider_id
        except (StopIteration, AttributeError) as e:
            message = "No LLM model found in available models"
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            ) from e

    llama_stack_model_id = f"{provider_id}/{model_id}"
    # Validate that the model_id and provider_id are in the available models
    logger.debug("Searching for model: %s, provider: %s", model_id, provider_id)
    if not any(
        m.identifier == llama_stack_model_id and m.provider_id == provider_id
        for m in models
    ):
        message = f"Model {model_id} from provider {provider_id} not found in available models"
        logger.error(message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                "cause": message,
            },
        )

    return llama_stack_model_id, model_id, provider_id


def _is_inout_shield(shield: Shield) -> bool:
    """
    Determine if the shield identifier indicates an input/output shield.

    Parameters:
        shield (Shield): The shield to check.

    Returns:
        bool: True if the shield identifier starts with "inout_", otherwise False.
    """
    return shield.identifier.startswith("inout_")


def is_output_shield(shield: Shield) -> bool:
    """
    Determine if the shield is for monitoring output.

    Return True if the given shield is classified as an output or
    inout shield.

    A shield is considered an output shield if its identifier
    starts with "output_" or "inout_".
    """
    return _is_inout_shield(shield) or shield.identifier.startswith("output_")


def is_input_shield(shield: Shield) -> bool:
    """
    Determine if the shield is for monitoring input.

    Return True if the shield is classified as an input or inout
    shield.

    Parameters:
        shield (Shield): The shield identifier to classify.

    Returns:
        bool: True if the shield is for input or both input/output monitoring; False otherwise.
    """
    return _is_inout_shield(shield) or not is_output_shield(shield)


def validate_attachments_metadata(attachments: list[Attachment]) -> None:
    """Validate the attachments metadata provided in the request.

    Raises:
        HTTPException: If any attachment has an invalid type or content type,
        an HTTP 422 error is raised.
    """
    for attachment in attachments:
        if attachment.attachment_type not in constants.ATTACHMENT_TYPES:
            message = (
                f"Attachment with improper type {attachment.attachment_type} detected"
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            )
        if attachment.content_type not in constants.ATTACHMENT_CONTENT_TYPES:
            message = f"Attachment with improper content type {attachment.content_type} detected"
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            )


def validate_query_request(
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends],
) -> tuple[str, UserConversation | None, str]:
    """
    Validate query request and return user_id and user_conversation.

    Returns:
        tuple: (user_id, user_conversation, token)
    """
    check_configuration_loaded(configuration)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(query_request, request.state.authorized_actions)

    # log Llama Stack configuration
    logger.info("Llama stack config: %s", configuration.llama_stack_configuration)

    user_id, _, _, token = auth

    user_conversation: UserConversation | None = None
    if query_request.conversation_id:
        logger.debug(
            "Conversation ID specified in query: %s", query_request.conversation_id
        )
        user_conversation = validate_conversation_ownership(
            user_id=user_id,
            conversation_id=query_request.conversation_id,
            others_allowed=(
                Action.QUERY_OTHERS_CONVERSATIONS in request.state.authorized_actions
            ),
        )

        if user_conversation is None:
            logger.warning(
                "User %s attempted to query conversation %s they don't own",
                user_id,
                query_request.conversation_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "response": "Access denied",
                    "cause": "You do not have permission to access this conversation",
                },
            )
    else:
        logger.debug("Query does not contain conversation ID")

    return user_id, user_conversation, token


def handle_api_connection_error(e: APIConnectionError) -> None:
    """Handle API connection errors consistently."""
    # Update metrics for the LLM call failure
    metrics.llm_calls_failures_total.inc()
    logger.error("Unable to connect to Llama Stack: %s", e)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "response": "Unable to connect to Llama Stack",
            "cause": str(e),
        },
    ) from e


def process_transcript_and_persist_conversation(
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: str,
    query_request: QueryRequest,
    summary: TurnSummary,
) -> None:
    """Process transcript storage and persist conversation details."""
    if not is_transcripts_enabled():
        logger.debug("Transcript collection is disabled in the configuration")
    else:
        store_transcript(
            user_id=user_id,
            conversation_id=conversation_id,
            model_id=model_id,
            provider_id=provider_id,
            query_is_valid=True,  # TODO(lucasagomes): implement as part of query validation
            query=query_request.query,
            query_request=query_request,
            summary=summary,
            rag_chunks=[],  # TODO(lucasagomes): implement rag_chunks
            truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
            attachments=query_request.attachments or [],
        )

    persist_user_conversation_details(
        user_id=user_id,
        conversation_id=conversation_id,
        model=model_id,
        provider_id=provider_id,
    )
