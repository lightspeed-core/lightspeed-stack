"""Utility functions for conversation management endpoints."""

import logging
from typing import Any, Callable, Awaitable

from llama_stack_client import APIConnectionError, NotFoundError

from fastapi import HTTPException, Request, status

from client import AsyncLlamaStackClientHolder
from configuration import configuration
from app.database import get_session
from models.config import Action
from models.database.conversations import UserConversation
from models.responses import (
    ConversationDeleteResponse,
    ConversationsListResponse,
    ConversationDetails,
    UnauthorizedResponse,
)
from utils.endpoints import (
    check_configuration_loaded,
    delete_conversation,
    validate_conversation_ownership,
)
from utils.suid import check_suid

logger = logging.getLogger("utils.conversations")

# Response schemas for OpenAPI documentation
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
    503: {
        "detail": {
            "response": "Unable to connect to Llama Stack",
            "cause": "Connection error.",
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
    503: {
        "detail": {
            "response": "Unable to connect to Llama Stack",
            "cause": "Connection error.",
        }
    },
}

conversations_list_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "conversations": [
            {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "created_at": "2024-01-01T00:00:00Z",
                "last_message_at": "2024-01-01T00:05:00Z",
                "last_used_model": "gemini/gemini-1.5-flash",
                "last_used_provider": "gemini",
                "message_count": 5,
            },
            {
                "conversation_id": "456e7890-e12b-34d5-a678-901234567890",
                "created_at": "2024-01-01T01:00:00Z",
                "last_message_at": "2024-01-01T01:02:00Z",
                "last_used_model": "gemini/gemini-2.0-flash",
                "last_used_provider": "gemini",
                "message_count": 2,
            },
        ]
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    401: {
        "description": "Unauthorized: Invalid or missing Bearer token",
        "model": UnauthorizedResponse,
    },
    503: {
        "detail": {
            "response": "Unable to connect to Llama Stack",
            "cause": "Connection error.",
        }
    },
}


def simplify_session_data(session_data: dict) -> list[dict[str, Any]]:
    """Simplify session data to include only essential conversation information.

    Args:
        session_data: The full session data dict from llama-stack

    Returns:
        Simplified session data with only input_messages and output_message per turn
    """
    # Create simplified structure
    chat_history = []

    # Extract only essential data from each turn
    for turn in session_data.get("turns", []):
        # Clean up input messages
        cleaned_messages = []
        for msg in turn.get("input_messages", []):
            cleaned_msg = {
                "content": msg.get("content"),
                "type": msg.get("role"),  # Rename role to type
            }
            cleaned_messages.append(cleaned_msg)

        # Clean up output message
        output_msg = turn.get("output_message", {})
        cleaned_messages.append(
            {
                "content": output_msg.get("content"),
                "type": output_msg.get("role"),  # Rename role to type
            }
        )

        simplified_turn = {
            "messages": cleaned_messages,
            "started_at": turn.get("started_at"),
            "completed_at": turn.get("completed_at"),
        }
        chat_history.append(simplified_turn)

    return chat_history


def get_conversations_list_base(
    request: Request,
    auth: Any,
) -> ConversationsListResponse:
    """Handle request to retrieve all conversations for the authenticated user."""
    check_configuration_loaded(configuration)

    user_id = auth[0]

    logger.info("Retrieving conversations for user %s", user_id)

    with get_session() as session:
        try:
            query = session.query(UserConversation)

            filtered_query = (
                query
                if Action.LIST_OTHERS_CONVERSATIONS in request.state.authorized_actions
                else query.filter_by(user_id=user_id)
            )

            user_conversations = filtered_query.all()

            # Return conversation summaries with metadata
            conversations = [
                ConversationDetails(
                    conversation_id=conv.id,
                    created_at=conv.created_at.isoformat() if conv.created_at else None,
                    last_message_at=(
                        conv.last_message_at.isoformat()
                        if conv.last_message_at
                        else None
                    ),
                    message_count=conv.message_count,
                    last_used_model=conv.last_used_model,
                    last_used_provider=conv.last_used_provider,
                )
                for conv in user_conversations
            ]

            logger.info(
                "Found %d conversations for user %s", len(conversations), user_id
            )

            return ConversationsListResponse(conversations=conversations)

        except Exception as e:
            logger.exception(
                "Error retrieving conversations for user %s: %s", user_id, e
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "response": "Unknown error",
                    "cause": f"Unknown error while getting conversations for user {user_id}",
                },
            ) from e


def validate_conversation_id(conversation_id: str) -> None:
    """Validate conversation ID format."""
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "response": "Invalid conversation ID format",
                "cause": f"Conversation ID {conversation_id} is not a valid UUID",
            },
        )


def validate_conversation_access(
    user_id: str,
    conversation_id: str,
    request: Request,
    action_read_others: Action,
    action_delete_others: Action | None = None,
) -> UserConversation | None:
    """Validate conversation ownership and access permissions."""
    others_allowed_action = (
        action_read_others if action_delete_others is None else action_delete_others
    )

    user_conversation = validate_conversation_ownership(
        user_id=user_id,
        conversation_id=conversation_id,
        others_allowed=(others_allowed_action in request.state.authorized_actions),
    )

    if user_conversation is None:
        action_name = "read" if action_delete_others is None else "delete"
        logger.warning(
            "User %s attempted to %s conversation %s they don't own",
            user_id,
            action_name,
            conversation_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "response": "Access denied",
                "cause": f"You do not have permission to {action_name} this conversation",
            },
        )

    return user_conversation


async def delete_conversation_base(
    request: Request,
    conversation_id: str,
    auth: Any,
    get_session_func: Callable[[Any, str], Awaitable[list[Any]]],
    delete_session_func: Callable[[Any, str, list[Any]], Awaitable[None]],
) -> ConversationDeleteResponse:
    """
    Handle request to delete a conversation by ID.

    Base implementation for deleting conversations that can be used by both
    Agent API and Response API implementations.

    Parameters:
        request: FastAPI request object
        conversation_id: ID of conversation to delete
        auth: Authentication tuple
        get_session_func: Function to get session(s) for the conversation
        delete_session_func: Function to delete the session(s)

    Returns:
        ConversationDeleteResponse: Response indicating the result of the deletion operation.
    """
    check_configuration_loaded(configuration)

    # Validate conversation ID format
    validate_conversation_id(conversation_id)

    user_id = auth[0]

    validate_conversation_access(
        user_id=user_id,
        conversation_id=conversation_id,
        request=request,
        action_read_others=Action.DELETE_OTHERS_CONVERSATIONS,
        action_delete_others=Action.DELETE_OTHERS_CONVERSATIONS,
    )

    logger.info("Deleting conversation %s", conversation_id)

    try:
        # Get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()

        # Get sessions for the conversation
        sessions = await get_session_func(client, conversation_id)

        if not sessions:
            # If no sessions are found, do not raise an error, just return a success response
            logger.info("No sessions found for conversation %s", conversation_id)
            return ConversationDeleteResponse(
                conversation_id=conversation_id,
                success=True,
                response="Conversation deleted successfully",
            )

        # Delete the session(s)
        await delete_session_func(client, conversation_id, sessions)

        logger.info("Successfully deleted conversation %s", conversation_id)

        delete_conversation(conversation_id=conversation_id)

        return ConversationDeleteResponse(
            conversation_id=conversation_id,
            success=True,
            response="Conversation deleted successfully",
        )

    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "response": "Unable to connect to Llama Stack",
                "cause": str(e),
            },
        ) from e
    except NotFoundError as e:
        logger.error("Conversation not found: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "Conversation not found",
                "cause": f"Conversation {conversation_id} could not be deleted: {str(e)}",
            },
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        # Handle case where session doesn't exist or other errors
        logger.exception("Error deleting conversation %s: %s", conversation_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unknown error",
                "cause": f"Unknown error while deleting conversation {conversation_id} : {str(e)}",
            },
        ) from e
