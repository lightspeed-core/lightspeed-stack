"""Handler for REST API calls to manage conversation history."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from authentication import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from models.cache_entry import CacheEntry
from models.config import Action
from models.requests import ConversationUpdateRequest
from models.responses import (
    ConversationDeleteResponse,
    ConversationResponse,
    ConversationUpdateResponse,
    ConversationsListResponseV2,
    UnauthorizedResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.suid import check_suid

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["conversations_v2"])


conversation_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "chat_history": [
            {
                "messages": [
                    {"content": "Hi", "type": "user"},
                    {"content": "Hello!", "type": "assistant"},
                ],
                "started_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:00:05Z",
                "provider": "provider ID",
                "model": "model ID",
            }
        ],
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    401: {
        "description": "Unauthorized: Invalid or missing Bearer token",
        "model": UnauthorizedResponse,
    },
    404: {
        "detail": {
            "response": "Conversation not found",
            "cause": "The specified conversation ID does not exist.",
        }
    },
}

conversation_delete_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "success": True,
        "message": "Conversation deleted successfully",
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    401: {
        "description": "Unauthorized: Invalid or missing Bearer token",
        "model": UnauthorizedResponse,
    },
    404: {
        "detail": {
            "response": "Conversation not found",
            "cause": "The specified conversation ID does not exist.",
        }
    },
}

conversations_list_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "conversations": [
            {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "topic_summary": "This is a topic summary",
                "last_message_timestamp": "2024-01-01T00:00:00Z",
            }
        ]
    }
}

conversation_update_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "success": True,
        "message": "Topic summary updated successfully",
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    401: {
        "description": "Unauthorized: Invalid or missing Bearer token",
        "model": UnauthorizedResponse,
    },
    404: {
        "detail": {
            "response": "Conversation not found",
            "cause": "The specified conversation ID does not exist.",
        }
    },
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

    if configuration.conversation_cache is None:
        logger.warning("Converastion cache is not configured")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "Conversation cache is not configured",
                "cause": "Conversation cache is not configured",
            },
        )

    conversations = configuration.conversation_cache.list(user_id, skip_userid_check)
    logger.info("Conversations for user %s: %s", user_id, len(conversations))

    return ConversationsListResponseV2(conversations=conversations)


@router.get("/conversations/{conversation_id}", responses=conversation_responses)
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

    if configuration.conversation_cache is None:
        logger.warning("Converastion cache is not configured")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "Conversation cache is not configured",
                "cause": "Conversation cache is not configured",
            },
        )

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

    if configuration.conversation_cache is None:
        logger.warning("Converastion cache is not configured")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "Conversation cache is not configured",
                "cause": "Conversation cache is not configured",
            },
        )

    check_conversation_existence(user_id, conversation_id)

    logger.info("Deleting conversation %s for user %s", conversation_id, user_id)
    deleted = configuration.conversation_cache.delete(
        user_id, conversation_id, skip_userid_check
    )

    if deleted:
        return ConversationDeleteResponse(
            conversation_id=conversation_id,
            success=True,
            response="Conversation deleted successfully",
        )
    return ConversationDeleteResponse(
        conversation_id=conversation_id,
        success=True,
        response="Conversation can not be deleted",
    )


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

    if configuration.conversation_cache is None:
        logger.warning("Conversation cache is not configured")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "Conversation cache is not configured",
                "cause": "Conversation cache is not configured",
            },
        )

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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "response": "Invalid conversation ID format",
                "cause": f"Conversation ID {conversation_id} is not a valid UUID",
            },
        )


def check_conversation_existence(user_id: str, conversation_id: str) -> None:
    """Check if conversation exists."""
    # checked already, but we need to make pyright happy
    if configuration.conversation_cache is None:
        return
    conversations = configuration.conversation_cache.list(user_id, False)
    conversation_ids = [conv.conversation_id for conv in conversations]
    if conversation_id not in conversation_ids:
        logger.error("No conversation found for conversation ID %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "Conversation not found",
                "cause": f"Conversation {conversation_id} could not be retrieved.",
            },
        )


def transform_chat_message(entry: CacheEntry) -> dict[str, Any]:
    """Transform the message read from cache into format used by response payload."""
    user_message = {
        "content": entry.query, 
        "type": "user"
    }
    assistant_message: dict[str, Any] = {
        "content": entry.response,
        "type": "assistant"
    }

    # If referenced_documents exist on the entry, add them to the assistant message
    if entry.referenced_documents is not None:
        assistant_message["referenced_documents"] = [
            doc.model_dump(mode='json') for doc in entry.referenced_documents
        ]

    return {
        "provider": entry.provider,
        "model": entry.model,
        "messages": [user_message, assistant_message],
        "started_at": entry.started_at,
        "completed_at": entry.completed_at,
    }
