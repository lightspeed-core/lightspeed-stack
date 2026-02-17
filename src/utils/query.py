"""Utility functions for working with queries."""

from datetime import UTC, datetime
from typing import Optional

from llama_stack_client import (
    APIConnectionError,
    APIStatusError as LLSApiStatusError,
    AsyncLlamaStackClient,
)
from openai._exceptions import APIStatusError as OpenAIAPIStatusError
from llama_stack_client.types import ModelListResponse, Shield

from fastapi import HTTPException
from sqlalchemy import func
from configuration import AppConfig, configuration
from models.cache_entry import CacheEntry
from models.config import Action
from models.database.conversations import UserConversation, UserTurn
import constants
from models.requests import Attachment, QueryRequest
from models.responses import (
    AbstractErrorResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnprocessableEntityResponse,
)
from authorization.azure_token_manager import AzureEntraIDManager
from cache.cache_error import CacheError
import psycopg2
import sqlite3
from sqlalchemy.exc import SQLAlchemyError
from app.database import get_session
from client import AsyncLlamaStackClientHolder
from utils.transcripts import store_transcript
from utils.quota import consume_tokens
from utils.suid import normalize_conversation_id
from utils.token_counter import TokenCounter
from utils.types import TurnSummary
from log import get_logger

logger = get_logger(__name__)


def store_conversation_into_cache(
    config: AppConfig,
    user_id: str,
    conversation_id: str,
    cache_entry: CacheEntry,
    _skip_userid_check: bool,
    topic_summary: Optional[str],
) -> None:
    """
    Store one part of conversation into conversation history cache.

    If a conversation cache type is configured but the cache instance is not
    initialized, the function logs a warning and returns without persisting
    anything.

    Parameters:
        config (AppConfig): Application configuration that may contain
                            conversation cache settings and instance.
        user_id (str): Owner identifier used as the cache key.
        conversation_id (str): Conversation identifier used as the cache key.
        cache_entry (CacheEntry): Entry to insert or append to the conversation history.
        _skip_userid_check (bool): When true, bypasses enforcing that the cache
                                   operation must match the user id.
        topic_summary (Optional[str]): Optional topic summary to store alongside
                                    the conversation; ignored if None or empty.
    """
    if config.conversation_cache_configuration.type is not None:
        cache = config.conversation_cache
        if cache is None:
            logger.warning("Conversation cache configured but not initialized")
            return
        cache.insert_or_append(
            user_id, conversation_id, cache_entry, _skip_userid_check
        )
        if topic_summary:
            cache.set_topic_summary(
                user_id, conversation_id, topic_summary, _skip_userid_check
            )


def select_model_and_provider_id(
    models: ModelListResponse, model_id: Optional[str], provider_id: Optional[str]
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
        "provider/model"), and its separated parts: the model label and the provider ID.

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
                if m.custom_metadata and m.custom_metadata.get("model_type") == "llm"
            )
            model_id = model.id
            # Extract provider_id from custom_metadata
            provider_id = (
                str(model.custom_metadata.get("provider_id", ""))
                if model.custom_metadata
                else ""
            )
            logger.info("Selected model: %s", model)
            model_label = model_id.split("/", 1)[1] if "/" in model_id else model_id
            return model_id, model_label, provider_id
        except (StopIteration, AttributeError) as e:
            message = "No LLM model found in available models"
            logger.error(message)
            response = NotFoundResponse(resource="model", resource_id=model_id or "")
            raise HTTPException(**response.model_dump()) from e

    llama_stack_model_id = f"{provider_id}/{model_id}"
    # Validate that the model_id and provider_id are in the available models
    logger.debug("Searching for model: %s, provider: %s", model_id, provider_id)
    # TODO: Create separate validation of provider
    if not any(
        m.id in (llama_stack_model_id, model_id)
        and (
            m.custom_metadata
            and str(m.custom_metadata.get("provider_id", "")) == provider_id
        )
        for m in models
    ):
        message = f"Model {model_id} from provider {provider_id} not found in available models"
        logger.error(message)
        response = NotFoundResponse(resource="model", resource_id=model_id)
        raise HTTPException(**response.model_dump())
    return llama_stack_model_id, model_id, provider_id


def validate_model_provider_override(
    query_request: QueryRequest, authorized_actions: set[Action] | frozenset[Action]
) -> None:
    """Validate whether model/provider overrides are allowed by RBAC.

    Raises:
        HTTPException: HTTP 403 if the request includes model or provider and
        the caller lacks Action.MODEL_OVERRIDE permission.
    """
    if (query_request.model is not None or query_request.provider is not None) and (
        Action.MODEL_OVERRIDE not in authorized_actions
    ):
        response = ForbiddenResponse.model_override()
        raise HTTPException(**response.model_dump())


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


def evaluate_model_hints(
    user_conversation: Optional[UserConversation],
    query_request: QueryRequest,
) -> tuple[Optional[str], Optional[str]]:
    """Evaluate model hints from user conversation."""
    model_id: Optional[str] = query_request.model
    provider_id: Optional[str] = query_request.provider

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


async def update_azure_token(
    client: AsyncLlamaStackClient,
) -> AsyncLlamaStackClient:
    """
    Update the client with a fresh Azure token.

    Updates the client with the fresh Azure token. Should be called after
    verifying that token refresh is needed and successful.

    Args:
        client: The current AsyncLlamaStackClient instance

    Returns:
        AsyncLlamaStackClient: The client instance (reloaded or updated with fresh token)
    """
    if AsyncLlamaStackClientHolder().is_library_client:
        return await AsyncLlamaStackClientHolder().reload_library_client()
    try:
        providers = await client.providers.list()
        azure_config = next(
            p.config for p in providers if p.provider_type == "remote::azure"
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

    return AsyncLlamaStackClientHolder().update_provider_data(
        {
            "azure_api_key": AzureEntraIDManager().access_token.get_secret_value(),
            "azure_api_base": str(azure_config.get("api_base")),
        }
    )


def prepare_input(query_request: QueryRequest) -> str:
    """
    Prepare input text for Responses API by appending attachments.

    Takes the query text and appends any attachment content with type labels.

    Args:
        query_request: The query request containing the query and optional attachments

    Returns:
        str: The input text with attachments appended (if any)
    """
    input_text = query_request.query
    if query_request.attachments:
        for attachment in query_request.attachments:
            # Append attachment content with type label
            input_text += (
                f"\n\n[Attachment: {attachment.attachment_type}]\n{attachment.content}"
            )
    return input_text


def store_query_results(  # pylint: disable=too-many-arguments,too-many-locals
    user_id: str,
    conversation_id: str,
    model: str,
    started_at: str,
    completed_at: str,
    summary: TurnSummary,
    query_request: QueryRequest,
    configuration: AppConfig,
    skip_userid_check: bool,
    topic_summary: Optional[str],
) -> None:
    """
    Store query results: transcript, conversation details, and cache.

    This function handles post-query storage operations including:
    - Storing transcripts (if enabled)
    - Persisting conversation details to database
    - Storing conversation in cache

    Args:
        user_id: The authenticated user ID
        conversation_id: The conversation ID
        model: The model identifier
        started_at: ISO formatted timestamp when the request started
        completed_at: ISO formatted timestamp when the request completed
        summary: Summary of the turn including LLM response and tool calls
        query_request: The original query request
        configuration: Application configuration
        skip_userid_check: Whether to skip user ID validation
        topic_summary: Optional topic summary for the conversation

    Raises:
        HTTPException: On any database, cache, or IO errors during processing
    """
    provider_id, model_id = extract_provider_and_model_from_model_id(model)
    # Store transcript if enabled
    if is_transcripts_enabled():
        try:
            # Convert RAG chunks to dictionary format once for reuse
            logger.info("Storing transcript")
            rag_chunks_dict = [chunk.model_dump() for chunk in summary.rag_chunks]
            store_transcript(
                user_id=user_id,
                conversation_id=conversation_id,
                model_id=model_id,
                provider_id=provider_id,
                query_is_valid=True,  # TODO(lucasagomes): implement as part of query validation
                query=query_request.query,
                query_request=query_request,
                summary=summary,
                rag_chunks=rag_chunks_dict,
                truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
                attachments=query_request.attachments or [],
            )
        except (IOError, OSError) as e:
            logger.exception("Error storing transcript: %s", e)
            response = InternalServerErrorResponse.generic()
            raise HTTPException(**response.model_dump()) from e
    else:
        logger.debug("Transcript collection is disabled in the configuration")

    # Persist conversation details
    try:
        logger.info("Persisting conversation details")
        # Extract provider_id from model_id (format: "provider/model")
        persist_user_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id,
            started_at=started_at,
            completed_at=completed_at,
            model_id=model_id,
            provider_id=provider_id,
            topic_summary=topic_summary,
        )
    except SQLAlchemyError as e:
        logger.exception("Error persisting conversation details.")
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e

    # Store conversation in cache
    try:
        cache_entry = CacheEntry(
            query=query_request.query,
            response=summary.llm_response,
            provider=provider_id,
            model=model_id,
            started_at=started_at,
            completed_at=completed_at,
            referenced_documents=summary.referenced_documents,
            tool_calls=summary.tool_calls,
            tool_results=summary.tool_results,
        )

        logger.info("Storing conversation in cache")
        store_conversation_into_cache(
            config=configuration,
            user_id=user_id,
            conversation_id=conversation_id,
            cache_entry=cache_entry,
            _skip_userid_check=skip_userid_check,
            topic_summary=topic_summary,
        )
    except (CacheError, ValueError, psycopg2.Error, sqlite3.Error) as e:
        logger.exception("Error storing conversation in cache: %s", e)
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e


def consume_query_tokens(
    user_id: str,
    model_id: str,
    token_usage: TokenCounter,
    configuration: AppConfig,
) -> None:
    """Consume tokens from quota limiters for a query.

    This function handles token consumption with proper error handling.
    It should be called after token usage has been determined but before
    returning the response to the client (especially for streaming responses).

    Args:
        user_id: The authenticated user ID
        model_id: The full model identifier in "provider/model" format
        token_usage: TokenCounter object with input and output token counts
        configuration: Application configuration

    Raises:
        HTTPException: On database errors during token consumption
    """
    provider, model = extract_provider_and_model_from_model_id(model_id)
    try:
        logger.info("Consuming tokens")
        consume_tokens(
            quota_limiters=configuration.quota_limiters,
            token_usage_history=configuration.token_usage_history,
            user_id=user_id,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            model_id=model,
            provider_id=provider,
        )
    except (psycopg2.Error, sqlite3.Error, ValueError) as e:
        logger.exception("Error consuming tokens: %s", e)
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e


def is_transcripts_enabled() -> bool:
    """Check if transcripts is enabled.

    Returns:
        bool: True if transcripts is enabled, False otherwise.
    """
    return configuration.user_data_collection_configuration.transcripts_enabled


def persist_user_conversation_details(
    user_id: str,
    conversation_id: str,
    started_at: str,
    completed_at: str,
    model_id: str,
    provider_id: str,
    topic_summary: Optional[str],
) -> None:
    """Associate conversation to user in the database.

    Args:
        user_id: The authenticated user ID
        conversation_id: The conversation ID
        started_at: The timestamp when the conversation started
        completed_at: The timestamp when the conversation completed
        model_id: The model identifier
        provider_id: The provider identifier
        topic_summary: Optional topic summary for the conversation
    """
    # Normalize the conversation ID (strip 'conv_' prefix if present)
    normalized_id = normalize_conversation_id(conversation_id)
    logger.debug(
        "persist_user_conversation_details - original conv_id: %s, normalized: %s, user: %s",
        conversation_id,
        normalized_id,
        user_id,
    )

    with get_session() as session:
        existing_conversation = (
            session.query(UserConversation).filter_by(id=normalized_id).first()
        )

        if not existing_conversation:
            conversation = UserConversation(
                id=normalized_id,
                user_id=user_id,
                last_used_model=model_id,
                last_used_provider=provider_id,
                topic_summary=topic_summary or "",
                message_count=1,
            )
            session.add(conversation)
            logger.debug(
                "Associated conversation %s to user %s", normalized_id, user_id
            )
        else:
            existing_conversation.last_used_model = model_id
            existing_conversation.last_used_provider = provider_id
            existing_conversation.last_message_at = datetime.now(UTC)
            existing_conversation.message_count += 1
            logger.debug(
                "Updating existing conversation in DB - ID: %s, User: %s, Messages: %d",
                normalized_id,
                user_id,
                existing_conversation.message_count,
            )

        max_turn_number = (
            session.query(func.max(UserTurn.turn_number))
            .filter_by(conversation_id=normalized_id)
            .scalar()
        )
        turn_number = (max_turn_number or 0) + 1
        turn = UserTurn(
            conversation_id=normalized_id,
            turn_number=turn_number,
            started_at=datetime.fromisoformat(started_at),
            completed_at=datetime.fromisoformat(completed_at),
            provider=provider_id,
            model=model_id,
        )
        session.add(turn)
        logger.debug(
            "Created conversation turn - Conversation: %s, Turn: %d",
            normalized_id,
            turn_number,
        )

        session.commit()
        logger.debug(
            "Successfully committed conversation %s to database", normalized_id
        )


def validate_attachments_metadata(attachments: list[Attachment]) -> None:
    """Validate the attachments metadata provided in the request.

    Raises:
        HTTPException: If any attachment has an invalid type or content type,
        an HTTP 422 error is raised.
    """
    for attachment in attachments:
        if attachment.attachment_type not in constants.ATTACHMENT_TYPES:
            message = (
                f"Invalid attachment type {attachment.attachment_type}: "
                f"must be one of {constants.ATTACHMENT_TYPES}"
            )
            logger.error(message)
            response = UnprocessableEntityResponse(
                response="Invalid attribute value", cause=message
            )
            raise HTTPException(**response.model_dump())
        if attachment.content_type not in constants.ATTACHMENT_CONTENT_TYPES:
            message = (
                f"Invalid attachment content type {attachment.content_type}: "
                f"must be one of {constants.ATTACHMENT_CONTENT_TYPES}"
            )
            logger.error(message)
            response = UnprocessableEntityResponse(
                response="Invalid attribute value", cause=message
            )
            raise HTTPException(**response.model_dump())


def extract_provider_and_model_from_model_id(model_id: str) -> tuple[str, str]:
    """Extract model and provider from model ID.

    Args:
        model_id: The model ID to extract from.

    Returns:
        tuple[str, str]: The model and provider.
    """
    split = model_id.split("/", 1)
    if len(split) == 2:
        return split[0], split[1]
    return "", model_id


def handle_known_apistatus_errors(
    error: LLSApiStatusError | OpenAIAPIStatusError, model_id: str
) -> AbstractErrorResponse:
    """Handle known API status errors from both Llama Stack and OpenAI.

    Args:
        error: The API status error to handle (can be from Llama Stack or OpenAI).
        model_id: The model ID for quota exceeded responses.

    Returns:
        AbstractErrorResponse: The error response model.
    """
    if error.status_code == 400:
        error_message = getattr(error, "message", str(error))
        if (
            "context_length" in error_message.lower()
            or "context length" in error_message.lower()
        ):
            return PromptTooLongResponse(model=model_id)
    elif error.status_code == 429:
        return QuotaExceededResponse.model(model_id)
    return InternalServerErrorResponse.generic()
