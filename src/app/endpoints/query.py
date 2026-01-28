"""Handler for REST API call to provide answer to query."""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_api.shields import Shield
from llama_stack_client import (
    APIConnectionError,
    APIStatusError,
    RateLimitError,  # type: ignore
)
from llama_stack_client.types.model_list_response import ModelListResponse
from sqlalchemy.exc import SQLAlchemyError

import constants
import metrics
from app.database import get_session
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.azure_token_manager import AzureEntraIDManager
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.cache_entry import CacheEntry
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import Attachment, QueryRequest
from models.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QueryResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from utils.endpoints import (
    check_configuration_loaded,
    store_conversation_into_cache,
    validate_conversation_ownership,
    validate_model_provider_override,
)
from utils.quota import (
    check_tokens_available,
    consume_tokens,
    get_available_quotas,
)
from utils.suid import normalize_conversation_id
from utils.transcripts import store_transcript

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query"])


query_response: dict[int | str, dict[str, Any]] = {
    200: QueryResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["endpoint", "conversation read", "model override"]
    ),
    404: NotFoundResponse.openapi_response(
        examples=["model", "conversation", "provider"]
    ),
    413: PromptTooLongResponse.openapi_response(),
    422: UnprocessableEntityResponse.openapi_response(),
    429: QuotaExceededResponse.openapi_response(),
    500: InternalServerErrorResponse.openapi_response(examples=["configuration"]),
    503: ServiceUnavailableResponse.openapi_response(),
}


def is_transcripts_enabled() -> bool:
    """Check if transcripts is enabled.

    Returns:
        bool: True if transcripts is enabled, False otherwise.
    """
    return configuration.user_data_collection_configuration.transcripts_enabled


def persist_user_conversation_details(
    user_id: str,
    conversation_id: str,
    model: str,
    provider_id: str,
    topic_summary: Optional[str],
) -> None:
    """Associate conversation to user in the database."""
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
                last_used_model=model,
                last_used_provider=provider_id,
                topic_summary=topic_summary,
                message_count=1,
            )
            session.add(conversation)
            logger.debug(
                "Associated conversation %s to user %s", normalized_id, user_id
            )
        else:
            existing_conversation.last_used_model = model
            existing_conversation.last_used_provider = provider_id
            existing_conversation.last_message_at = datetime.now(UTC)
            existing_conversation.message_count += 1
            logger.debug(
                "Updating existing conversation in DB - ID: %s, User: %s, Messages: %d",
                normalized_id,
                user_id,
                existing_conversation.message_count,
            )

        session.commit()
        logger.debug(
            "Successfully committed conversation %s to database", normalized_id
        )


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


async def query_endpoint_handler_base(  # pylint: disable=R0914
    request: Request,
    query_request: QueryRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
    mcp_headers: dict[str, dict[str, str]],
    retrieve_response_func: Any,
    get_topic_summary_func: Any,
) -> QueryResponse:
    """
    Handle query endpoints (shared by Agent API and Responses API).

    Processes a POST request to a query endpoint, forwarding the
    user's query to a selected Llama Stack LLM and returning the generated response.

    Validates configuration and authentication, selects the appropriate model
    and provider, retrieves the LLM response, updates metrics, and optionally
    stores a transcript of the interaction. Handles connection errors to the
    Llama Stack service by returning an HTTP 500 error.

    Args:
        request: The FastAPI request object
        query_request: The query request containing the user's question
        auth: Authentication tuple from dependency
        mcp_headers: MCP headers from dependency
        retrieve_response_func: The retrieve_response function to use (Agent or Responses API)
        get_topic_summary_func: The get_topic_summary function to use (Agent or Responses API)

    Returns:
        QueryResponse: Contains the conversation ID and the LLM-generated response.
    """
    check_configuration_loaded(configuration)

    # Enforce RBAC: optionally disallow overriding model/provider in requests
    validate_model_provider_override(query_request, request.state.authorized_actions)

    # log Llama Stack configuration
    logger.info("Llama stack config: %s", configuration.llama_stack_configuration)

    user_id, _, _skip_userid_check, token = auth

    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    user_conversation: Optional[UserConversation] = None
    if query_request.conversation_id:
        logger.debug(
            "Conversation ID specified in query: %s", query_request.conversation_id
        )
        # Normalize the conversation ID for database lookup (strip conv_ prefix if present)
        normalized_conv_id_for_lookup = normalize_conversation_id(
            query_request.conversation_id
        )
        user_conversation = validate_conversation_ownership(
            user_id=user_id,
            conversation_id=normalized_conv_id_for_lookup,
            others_allowed=(
                Action.QUERY_OTHERS_CONVERSATIONS in request.state.authorized_actions
            ),
        )

        if user_conversation is None:
            logger.warning(
                "Conversation %s not found for user %s",
                query_request.conversation_id,
                user_id,
            )
            response = NotFoundResponse(
                resource="conversation", resource_id=query_request.conversation_id
            )
            raise HTTPException(**response.model_dump())

    else:
        logger.debug("Query does not contain conversation ID")

    try:
        check_tokens_available(configuration.quota_limiters, user_id)
        # try to get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()
        llama_stack_model_id, model_id, provider_id = select_model_and_provider_id(
            await client.models.list(),
            *evaluate_model_hints(
                user_conversation=user_conversation, query_request=query_request
            ),
        )

        if (
            provider_id == "azure"
            and AzureEntraIDManager().is_entra_id_configured
            and AzureEntraIDManager().is_token_expired
            and AzureEntraIDManager().refresh_token()
        ):
            if AsyncLlamaStackClientHolder().is_library_client:
                client = await AsyncLlamaStackClientHolder().reload_library_client()
            else:
                azure_config = next(
                    p.config
                    for p in await client.providers.list()
                    if p.provider_type == "remote::azure"
                )
                client = AsyncLlamaStackClientHolder().update_provider_data(
                    {
                        "azure_api_key": AzureEntraIDManager().access_token.get_secret_value(),
                        "azure_api_base": str(azure_config.get("api_base")),
                    }
                )

        summary, conversation_id, referenced_documents, token_usage = (
            await retrieve_response_func(
                client,
                llama_stack_model_id,
                query_request,
                token,
                mcp_headers=mcp_headers,
                provider_id=provider_id,
            )
        )

        # Get the initial topic summary for the conversation
        topic_summary = None
        with get_session() as session:
            existing_conversation = (
                session.query(UserConversation).filter_by(id=conversation_id).first()
            )
            if not existing_conversation:
                # Check if topic summary should be generated (default: True)
                should_generate = query_request.generate_topic_summary

                if should_generate:
                    logger.debug("Generating topic summary for new conversation")
                    topic_summary = await get_topic_summary_func(
                        query_request.query, client, llama_stack_model_id
                    )
                else:
                    logger.debug(
                        "Topic summary generation disabled by request parameter"
                    )
                    topic_summary = None
        # Convert RAG chunks to dictionary format once for reuse
        logger.info("Processing RAG chunks...")
        rag_chunks_dict = [chunk.model_dump() for chunk in summary.rag_chunks]

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
                rag_chunks=rag_chunks_dict,
                truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
                attachments=query_request.attachments or [],
            )

        logger.info("Persisting conversation details...")
        persist_user_conversation_details(
            user_id=user_id,
            conversation_id=conversation_id,
            model=model_id,
            provider_id=provider_id,
            topic_summary=topic_summary,
        )

        completed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        cache_entry = CacheEntry(
            query=query_request.query,
            response=summary.llm_response,
            provider=provider_id,
            model=model_id,
            started_at=started_at,
            completed_at=completed_at,
            referenced_documents=referenced_documents if referenced_documents else None,
            tool_calls=summary.tool_calls if summary.tool_calls else None,
            tool_results=summary.tool_results if summary.tool_results else None,
        )

        consume_tokens(
            configuration.quota_limiters,
            configuration.token_usage_history,
            user_id,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            model_id=model_id,
            provider_id=provider_id,
        )

        store_conversation_into_cache(
            configuration,
            user_id,
            conversation_id,
            cache_entry,
            _skip_userid_check,
            topic_summary,
        )

        # Convert tool calls to response format
        logger.info("Processing tool calls...")

        logger.info("Using referenced documents from response...")

        available_quotas = get_available_quotas(configuration.quota_limiters, user_id)

        logger.info("Building final response...")
        response = QueryResponse(
            conversation_id=conversation_id,
            response=summary.llm_response,
            tool_calls=summary.tool_calls,
            tool_results=summary.tool_results,
            rag_chunks=summary.rag_chunks,
            referenced_documents=referenced_documents,
            truncated=False,  # TODO: implement truncation detection
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            available_quotas=available_quotas,
        )
        logger.info("Query processing completed successfully!")
        return response

    # connection to Llama Stack server
    except APIConnectionError as e:
        # Update metrics for the LLM call failure
        metrics.llm_calls_failures_total.inc()
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(
            backend_name="Llama Stack",
            cause=str(e),
        )
        raise HTTPException(**response.model_dump()) from e
    except SQLAlchemyError as e:
        logger.exception("Error persisting conversation details.")
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e
    except RateLimitError as e:
        used_model = getattr(e, "model", "")
        if used_model:
            response = QuotaExceededResponse.model(used_model)
        else:
            response = QuotaExceededResponse(
                response="The quota has been exceeded", cause=str(e)
            )
        raise HTTPException(**response.model_dump()) from e
    except APIStatusError as e:
        logger.exception("Error in query endpoint handler: %s", e)
        response = InternalServerErrorResponse.generic()
        raise HTTPException(**response.model_dump()) from e


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
    # TODO: Create sepparate validation of provider
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
                f"Invalid attatchment type {attachment.attachment_type}: "
                f"must be one of {constants.ATTACHMENT_TYPES}"
            )
            logger.error(message)
            response = UnprocessableEntityResponse(
                response="Invalid attribute value", cause=message
            )
            raise HTTPException(**response.model_dump())
        if attachment.content_type not in constants.ATTACHMENT_CONTENT_TYPES:
            message = (
                f"Invalid attatchment content type {attachment.content_type}: "
                f"must be one of {constants.ATTACHMENT_CONTENT_TYPES}"
            )
            logger.error(message)
            response = UnprocessableEntityResponse(
                response="Invalid attribute value", cause=message
            )
            raise HTTPException(**response.model_dump())
