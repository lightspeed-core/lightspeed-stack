"""Handler for REST API calls to manage conversation history."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from authentication import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from models.cache_entry import CacheEntry
from models.config import Action
from models.requests import ConversationUpdateRequest
from models.responses import (
    BadRequestResponse,
    ConversationDeleteResponse,
    ConversationResponse,
    ConversationsListResponseV2,
    ConversationUpdateResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.suid import check_suid

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["conversations_v2"])


conversation_get_responses: dict[int | str, dict[str, Any]] = {
    200: ConversationResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["conversation"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["conversation cache", "configuration"]
    ),
}

conversation_delete_responses: dict[int | str, dict[str, Any]] = {
    200: ConversationDeleteResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["conversation cache", "configuration"]
    ),
}

conversations_list_responses: dict[int | str, dict[str, Any]] = {
    200: ConversationsListResponseV2.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["conversation cache", "configuration"]
    ),
}

conversation_update_responses: dict[int | str, dict[str, Any]] = {
    200: ConversationUpdateResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["conversation"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["conversation cache", "configuration"]
    ),
}


@router.get("/conversations", responses=conversations_list_responses)
@authorize(Action.LIST_CONVERSATIONS)
async def get_conversations_list_endpoint_handler(
    request: Request,  # pylint: disable=unused-argument
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationsListResponseV2:
    """Handle request to retrieve all conversations for the authenticated user."""
    check_configuration_loaded(configuration)

    user_id = auth[0]

    logger.info("Retrieving conversations for user %s", user_id)

    skip_userid_check = auth[2]

    if configuration.conversation_cache_configuration.type is None:
        logger.warning("Converastion cache is not configured")
        response = InternalServerErrorResponse.cache_unavailable()
        raise HTTPException(**response.model_dump())

    conversations = configuration.conversation_cache.list(user_id, skip_userid_check)
    logger.info("Conversations for user %s: %s", user_id, len(conversations))

    return ConversationsListResponseV2(conversations=conversations)


@router.get("/conversations/{conversation_id}", responses=conversation_get_responses)
@authorize(Action.GET_CONVERSATION)
async def get_conversation_endpoint_handler(
    request: Request,  # pylint: disable=unused-argument
    conversation_id: str,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationResponse:
    """Handle request to retrieve a conversation by ID."""
    check_configuration_loaded(configuration)
    check_valid_conversation_id(conversation_id)

    user_id = auth[0]
    logger.info("Retrieving conversation %s for user %s", conversation_id, user_id)

    skip_userid_check = auth[2]

    if configuration.conversation_cache_configuration.type is None:
        logger.warning("Converastion cache is not configured")
        response = InternalServerErrorResponse.cache_unavailable()
        raise HTTPException(**response.model_dump())

    check_conversation_existence(user_id, conversation_id)

    conversation = configuration.conversation_cache.get(
        user_id, conversation_id, skip_userid_check
    )
    chat_history = [transform_chat_message(entry) for entry in conversation]

    return ConversationResponse(
        conversation_id=conversation_id, chat_history=chat_history
    )


@router.delete(
    "/conversations/{conversation_id}", responses=conversation_delete_responses
)
@authorize(Action.DELETE_CONVERSATION)
async def delete_conversation_endpoint_handler(
    request: Request,  # pylint: disable=unused-argument
    conversation_id: str,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationDeleteResponse:
    """Handle request to delete a conversation by ID."""
    check_configuration_loaded(configuration)
    check_valid_conversation_id(conversation_id)

    user_id = auth[0]
    logger.info("Deleting conversation %s for user %s", conversation_id, user_id)

    skip_userid_check = auth[2]

    if configuration.conversation_cache_configuration.type is None:
        logger.warning("Converastion cache is not configured")
        response = InternalServerErrorResponse.cache_unavailable()
        raise HTTPException(**response.model_dump())

    logger.info("Deleting conversation %s for user %s", conversation_id, user_id)
    deleted = configuration.conversation_cache.delete(
        user_id, conversation_id, skip_userid_check
    )
    return ConversationDeleteResponse(deleted=deleted, conversation_id=conversation_id)


@router.put("/conversations/{conversation_id}", responses=conversation_update_responses)
@authorize(Action.UPDATE_CONVERSATION)
async def update_conversation_endpoint_handler(
    conversation_id: str,
    update_request: ConversationUpdateRequest,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationUpdateResponse:
    """Handle request to update a conversation topic summary by ID."""
    check_configuration_loaded(configuration)
    check_valid_conversation_id(conversation_id)

    user_id = auth[0]
    logger.info(
        "Updating topic summary for conversation %s for user %s",
        conversation_id,
        user_id,
    )

    skip_userid_check = auth[2]

    if configuration.conversation_cache_configuration.type is None:
        logger.warning("Conversation cache is not configured")
        response = InternalServerErrorResponse.cache_unavailable()
        raise HTTPException(**response.model_dump())

    check_conversation_existence(user_id, conversation_id)

    # Update the topic summary in the cache
    configuration.conversation_cache.set_topic_summary(
        user_id, conversation_id, update_request.topic_summary, skip_userid_check
    )

    logger.info(
        "Successfully updated topic summary for conversation %s for user %s",
        conversation_id,
        user_id,
    )

    return ConversationUpdateResponse(
        conversation_id=conversation_id,
        success=True,
        message="Topic summary updated successfully",
    )


def check_valid_conversation_id(conversation_id: str) -> None:
    """Check validity of conversation ID format."""
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        response = BadRequestResponse(
            resource="conversation", resource_id=conversation_id
        )
        raise HTTPException(**response.model_dump())


def check_conversation_existence(user_id: str, conversation_id: str) -> None:
    """Check if conversation exists."""
    # checked already, but we need to make pyright happy
    if configuration.conversation_cache_configuration.type is None:
        return
    conversations = configuration.conversation_cache.list(user_id, False)
    conversation_ids = [conv.conversation_id for conv in conversations]
    if conversation_id not in conversation_ids:
        logger.error("No conversation found for conversation ID %s", conversation_id)
        response = NotFoundResponse(
            resource="conversation", resource_id=conversation_id
        )
        raise HTTPException(**response.model_dump())


def transform_chat_message(entry: CacheEntry) -> dict[str, Any]:
    """Transform the message read from cache into format used by response payload."""
    user_message: dict[str, Any] = {"content": entry.query, "type": "user"}

    # Add attachments to user message if present
    if entry.attachments:
        user_message["attachments"] = [
            att.model_dump(mode="json") for att in entry.attachments
        ]

    assistant_message: dict[str, Any] = {"content": entry.response, "type": "assistant"}

    # If referenced_documents exist on the entry, add them to the assistant message
    if entry.referenced_documents is not None:
        assistant_message["referenced_documents"] = [
            doc.model_dump(mode="json") for doc in entry.referenced_documents
        ]

    return {
        "provider": entry.provider,
        "model": entry.model,
        "messages": [user_message, assistant_message],
        "started_at": entry.started_at,
        "completed_at": entry.completed_at,
    }
