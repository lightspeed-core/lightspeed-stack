"""Handler for REST API calls to manage conversation history using Conversations API."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from llama_stack_client import APIConnectionError, NotFoundError

from app.database import get_session
from authentication import get_auth_dependency
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import ConversationUpdateRequest
from models.responses import (
    AccessDeniedResponse,
    BadRequestResponse,
    ConversationDeleteResponse,
    ConversationDetails,
    ConversationResponse,
    ConversationsListResponse,
    ConversationUpdateResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import (
    can_access_conversation,
    check_configuration_loaded,
    delete_conversation,
    retrieve_conversation,
)
from utils.suid import (
    check_suid,
    normalize_conversation_id,
    to_llama_stack_conversation_id,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["conversations_v3"])

conversation_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "model": ConversationResponse,
        "description": "Conversation retrieved successfully",
    },
    400: {
        "model": BadRequestResponse,
        "description": "Invalid request",
    },
    401: {
        "model": UnauthorizedResponse,
        "description": "Unauthorized: Invalid or missing Bearer token",
    },
    403: {
        "model": AccessDeniedResponse,
        "description": "Client does not have permission to access conversation",
    },
    404: {
        "model": NotFoundResponse,
        "description": "Conversation not found",
    },
    503: {
        "model": ServiceUnavailableResponse,
        "description": "Service unavailable",
    },
}

conversation_delete_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "model": ConversationDeleteResponse,
        "description": "Conversation deleted successfully",
    },
    400: {
        "model": BadRequestResponse,
        "description": "Invalid request",
    },
    401: {
        "model": UnauthorizedResponse,
        "description": "Unauthorized: Invalid or missing Bearer token",
    },
    403: {
        "model": AccessDeniedResponse,
        "description": "Client does not have permission to access conversation",
    },
    404: {
        "model": NotFoundResponse,
        "description": "Conversation not found",
    },
    503: {
        "model": ServiceUnavailableResponse,
        "description": "Service unavailable",
    },
}

conversations_list_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "model": ConversationsListResponse,
        "description": "List of conversations retrieved successfully",
    },
    401: {
        "model": UnauthorizedResponse,
        "description": "Unauthorized: Invalid or missing Bearer token",
    },
    503: {
        "model": ServiceUnavailableResponse,
        "description": "Service unavailable",
    },
}

conversation_update_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "model": ConversationUpdateResponse,
        "description": "Topic summary updated successfully",
    },
    400: {
        "model": BadRequestResponse,
        "description": "Invalid request",
    },
    401: {
        "model": UnauthorizedResponse,
        "description": "Unauthorized: Invalid or missing Bearer token",
    },
    403: {
        "model": AccessDeniedResponse,
        "description": "Client does not have permission to access conversation",
    },
    404: {
        "model": NotFoundResponse,
        "description": "Conversation not found",
    },
    503: {
        "model": ServiceUnavailableResponse,
        "description": "Service unavailable",
    },
}


def simplify_conversation_items(items: list[dict]) -> list[dict[str, Any]]:
    """Simplify conversation items to include only essential information.

    Args:
        items: The full conversation items list from llama-stack Conversations API

    Returns:
        Simplified items with only essential message and tool call information
    """
    chat_history = []

    # Group items by turns (user message -> assistant response)
    current_turn: dict[str, Any] = {"messages": []}

    for item in items:
        item_type = item.get("type")
        item_role = item.get("role")

        # Handle message items
        if item_type == "message":
            content = item.get("content", [])

            # Extract text content from content array
            text_content = ""
            for content_part in content:
                if isinstance(content_part, dict):
                    if content_part.get("type") == "text":
                        text_content += content_part.get("text", "")
                elif isinstance(content_part, str):
                    text_content += content_part

            message = {
                "content": text_content,
                "type": item_role,
            }
            current_turn["messages"].append(message)

            # If this is an assistant message, it marks the end of a turn
            if item_role == "assistant" and current_turn["messages"]:
                chat_history.append(current_turn)
                current_turn = {"messages": []}

    # Add any remaining turn
    if current_turn["messages"]:
        chat_history.append(current_turn)

    return chat_history


@router.get("/conversations", responses=conversations_list_responses)
@authorize(Action.LIST_CONVERSATIONS)
async def get_conversations_list_endpoint_handler(
    request: Request,
    auth: Any = Depends(get_auth_dependency()),
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
                    topic_summary=conv.topic_summary,
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


@router.get("/conversations/{conversation_id}", responses=conversation_responses)
@authorize(Action.GET_CONVERSATION)
async def get_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationResponse:
    """Handle request to retrieve a conversation by ID using Conversations API.

    Retrieve a conversation's chat history by its ID using the LlamaStack
    Conversations API. This endpoint fetches the conversation items from
    the backend, simplifies them to essential chat history, and returns
    them in a structured response. Raises HTTP 400 for invalid IDs, 404
    if not found, 503 if the backend is unavailable, and 500 for
    unexpected errors.

    Args:
        request: The FastAPI request object
        conversation_id: Unique identifier of the conversation to retrieve
        auth: Authentication tuple from dependency

    Returns:
        ConversationResponse: Structured response containing the conversation
        ID and simplified chat history
    """
    check_configuration_loaded(configuration)

    # Validate conversation ID format
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=BadRequestResponse(
                resource="conversation", resource_id=conversation_id
            ).dump_detail(),
        )

    # Normalize the conversation ID for database operations (strip conv_ prefix if present)
    normalized_conv_id = normalize_conversation_id(conversation_id)
    logger.debug(
        "GET conversation - original ID: %s, normalized ID: %s",
        conversation_id,
        normalized_conv_id,
    )

    user_id = auth[0]
    if not can_access_conversation(
        normalized_conv_id,
        user_id,
        others_allowed=(
            Action.READ_OTHERS_CONVERSATIONS in request.state.authorized_actions
        ),
    ):
        logger.warning(
            "User %s attempted to read conversation %s they don't have access to",
            user_id,
            normalized_conv_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AccessDeniedResponse(
                user_id=user_id,
                resource="conversation",
                resource_id=normalized_conv_id,
                action="read",
            ).dump_detail(),
        )

    # If reached this, user is authorized to retrieve this conversation
    # Note: We check if conversation exists in DB but don't fail if it doesn't,
    # as it might exist in llama-stack but not be persisted yet
    conversation = retrieve_conversation(normalized_conv_id)
    if conversation is None:
        logger.warning(
            "Conversation %s not found in database, will try llama-stack",
            normalized_conv_id,
        )

    logger.info(
        "Retrieving conversation %s using Conversations API", normalized_conv_id
    )

    try:
        client = AsyncLlamaStackClientHolder().get_client()

        # Convert to llama-stack format (add 'conv_' prefix if needed)
        llama_stack_conv_id = to_llama_stack_conversation_id(normalized_conv_id)
        logger.debug(
            "Calling llama-stack list_items with conversation_id: %s",
            llama_stack_conv_id,
        )

        # Use Conversations API to retrieve conversation items
        from llama_stack_client import NOT_GIVEN

        conversation_items_response = await client.conversations.items.list(
            conversation_id=llama_stack_conv_id,
            after=NOT_GIVEN,  # No pagination cursor
            include=NOT_GIVEN,  # Include all available data
            limit=1000,  # Max items to retrieve
            order="asc",  # Get items in chronological order
        )

        items = (
            conversation_items_response.data
            if hasattr(conversation_items_response, "data")
            else []
        )

        # Convert items to dict format for processing
        items_dicts = [
            item.model_dump() if hasattr(item, "model_dump") else dict(item)
            for item in items
        ]

        logger.info(
            "Successfully retrieved %d items for conversation %s",
            len(items_dicts),
            conversation_id,
        )

        # Simplify the conversation items to include only essential information
        chat_history = simplify_conversation_items(items_dicts)

        return ConversationResponse(
            conversation_id=normalized_conv_id,
            chat_history=chat_history,
        )

    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ServiceUnavailableResponse(
                backend_name="Llama Stack", cause=str(e)
            ).dump_detail(),
        ) from e

    except NotFoundError as e:
        logger.error("Conversation not found: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=NotFoundResponse(
                resource="conversation", resource_id=normalized_conv_id
            ).dump_detail(),
        ) from e

    except HTTPException:
        raise

    except Exception as e:
        # Handle case where conversation doesn't exist or other errors
        logger.exception("Error retrieving conversation %s: %s", normalized_conv_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unknown error",
                "cause": f"Unknown error while getting conversation {normalized_conv_id} : {str(e)}",
            },
        ) from e


@router.delete(
    "/conversations/{conversation_id}", responses=conversation_delete_responses
)
@authorize(Action.DELETE_CONVERSATION)
async def delete_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationDeleteResponse:
    """Handle request to delete a conversation by ID using Conversations API.

    Validates the conversation ID format and attempts to delete the
    conversation from the Llama Stack backend using the Conversations API.
    Raises HTTP errors for invalid IDs, not found conversations, connection
    issues, or unexpected failures.

    Args:
        request: The FastAPI request object
        conversation_id: Unique identifier of the conversation to delete
        auth: Authentication tuple from dependency

    Returns:
        ConversationDeleteResponse: Response indicating the result of the deletion operation
    """
    check_configuration_loaded(configuration)

    # Validate conversation ID format
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=BadRequestResponse(
                resource="conversation", resource_id=conversation_id
            ).dump_detail(),
        )

    # Normalize the conversation ID for database operations (strip conv_ prefix if present)
    normalized_conv_id = normalize_conversation_id(conversation_id)

    user_id = auth[0]
    if not can_access_conversation(
        normalized_conv_id,
        user_id,
        others_allowed=(
            Action.DELETE_OTHERS_CONVERSATIONS in request.state.authorized_actions
        ),
    ):
        logger.warning(
            "User %s attempted to delete conversation %s they don't have access to",
            user_id,
            normalized_conv_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AccessDeniedResponse(
                user_id=user_id,
                resource="conversation",
                resource_id=normalized_conv_id,
                action="delete",
            ).dump_detail(),
        )

    # If reached this, user is authorized to delete this conversation
    conversation = retrieve_conversation(normalized_conv_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=NotFoundResponse(
                resource="conversation", resource_id=normalized_conv_id
            ).dump_detail(),
        )

    logger.info("Deleting conversation %s using Conversations API", normalized_conv_id)

    try:
        # Get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()

        # Convert to llama-stack format (add 'conv_' prefix if needed)
        llama_stack_conv_id = to_llama_stack_conversation_id(normalized_conv_id)

        # Use Conversations API to delete the conversation
        await client.conversations.delete(conversation_id=llama_stack_conv_id)

        logger.info("Successfully deleted conversation %s", normalized_conv_id)

        # Also delete from local database
        delete_conversation(conversation_id=normalized_conv_id)

        return ConversationDeleteResponse(
            conversation_id=normalized_conv_id,
            success=True,
            response="Conversation deleted successfully",
        )

    except APIConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ServiceUnavailableResponse(
                backend_name="Llama Stack", cause=str(e)
            ).dump_detail(),
        ) from e

    except NotFoundError:
        # If not found in LlamaStack, still try to delete from local DB
        logger.warning(
            "Conversation %s not found in LlamaStack, cleaning up local DB",
            normalized_conv_id,
        )
        delete_conversation(conversation_id=normalized_conv_id)

        return ConversationDeleteResponse(
            conversation_id=normalized_conv_id,
            success=True,
            response="Conversation deleted successfully",
        )

    except HTTPException:
        raise

    except Exception as e:
        # Handle case where conversation doesn't exist or other errors
        logger.exception("Error deleting conversation %s: %s", normalized_conv_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unknown error",
                "cause": f"Unknown error while deleting conversation {normalized_conv_id} : {str(e)}",
            },
        ) from e


@router.put("/conversations/{conversation_id}", responses=conversation_update_responses)
@authorize(Action.UPDATE_CONVERSATION)
async def update_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    update_request: ConversationUpdateRequest,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationUpdateResponse:
    """Handle request to update a conversation metadata using Conversations API.

    Updates the conversation metadata (including topic summary) in both the
    LlamaStack backend using the Conversations API and the local database.

    Args:
        request: The FastAPI request object
        conversation_id: Unique identifier of the conversation to update
        update_request: Request containing the topic summary to update
        auth: Authentication tuple from dependency

    Returns:
        ConversationUpdateResponse: Response indicating the result of the update operation
    """
    check_configuration_loaded(configuration)

    # Validate conversation ID format
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=BadRequestResponse(
                resource="conversation", resource_id=conversation_id
            ).dump_detail(),
        )

    # Normalize the conversation ID for database operations (strip conv_ prefix if present)
    normalized_conv_id = normalize_conversation_id(conversation_id)

    user_id = auth[0]
    if not can_access_conversation(
        normalized_conv_id,
        user_id,
        others_allowed=(
            Action.QUERY_OTHERS_CONVERSATIONS in request.state.authorized_actions
        ),
    ):
        logger.warning(
            "User %s attempted to update conversation %s they don't have access to",
            user_id,
            normalized_conv_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=AccessDeniedResponse(
                user_id=user_id,
                resource="conversation",
                resource_id=normalized_conv_id,
                action="update",
            ).dump_detail(),
        )

    # If reached this, user is authorized to update this conversation
    conversation = retrieve_conversation(normalized_conv_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=NotFoundResponse(
                resource="conversation", resource_id=normalized_conv_id
            ).dump_detail(),
        )

    logger.info(
        "Updating metadata for conversation %s using Conversations API",
        normalized_conv_id,
    )

    try:
        # Get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()

        # Convert to llama-stack format (add 'conv_' prefix if needed)
        llama_stack_conv_id = to_llama_stack_conversation_id(normalized_conv_id)

        # Prepare metadata with topic summary
        metadata = {"topic_summary": update_request.topic_summary}

        # Use Conversations API to update the conversation metadata
        await client.conversations.update_conversation(
            conversation_id=llama_stack_conv_id,
            metadata=metadata,
        )

        logger.info(
            "Successfully updated metadata for conversation %s in LlamaStack",
            normalized_conv_id,
        )

        # Also update in local database
        with get_session() as session:
            db_conversation = (
                session.query(UserConversation).filter_by(id=normalized_conv_id).first()
            )
            if db_conversation:
                db_conversation.topic_summary = update_request.topic_summary
                session.commit()
                logger.info(
                    "Successfully updated topic summary in local database for conversation %s",
                    normalized_conv_id,
                )

        return ConversationUpdateResponse(
            conversation_id=normalized_conv_id,
            success=True,
            message="Topic summary updated successfully",
        )

    except APIConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ServiceUnavailableResponse(
                backend_name="Llama Stack", cause=str(e)
            ).dump_detail(),
        ) from e

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=NotFoundResponse(
                resource="conversation", resource_id=normalized_conv_id
            ).dump_detail(),
        ) from e

    except HTTPException:
        raise

    except Exception as e:
        # Handle case where conversation doesn't exist or other errors
        logger.exception("Error updating conversation %s: %s", normalized_conv_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unknown error",
                "cause": f"Unknown error while updating conversation {normalized_conv_id} : {str(e)}",
            },
        ) from e
