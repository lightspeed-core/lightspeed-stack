"""Handler for REST API calls to manage conversation history."""

import logging
from typing import Any

from llama_stack_client import APIConnectionError, NotFoundError

from fastapi import APIRouter, HTTPException, status, Depends

from client import LlamaStackClientHolder
from configuration import configuration
from models.responses import ConversationResponse, ConversationDeleteResponse
from auth import get_auth_dependency
from utils.endpoints import check_configuration_loaded
from utils.suid import check_suid
from services.agent_manager import PersistentAgentManager
from services.persistence import PersistenceManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["conversations"])
auth_dependency = get_auth_dependency()

# Legacy in-memory mapping (fallback)
conversation_id_to_agent_id: dict[str, str] = {}

conversation_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "session_data": {
            "session_id": "123e4567-e89b-12d3-a456-426614174000",
            "turns": [],
            "started_at": "2024-01-01T00:00:00Z",
        },
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


def get_persistent_agent_manager() -> PersistentAgentManager | None:
    """Get the persistent agent manager from the query module."""
    try:
        from app.endpoints.query import get_persistent_agent_manager
        return get_persistent_agent_manager()
    except ImportError:
        return None


def get_agent_id_from_persistent_storage(conversation_id: str) -> str | None:
    """Get agent ID from persistent storage."""
    try:
        persistent_manager = get_persistent_agent_manager()
        if persistent_manager:
            # Try to get from persistent storage
            conversation_history = persistent_manager.get_conversation_history(conversation_id)
            if conversation_history:
                # Extract agent_id from conversation metadata
                # This is a simplified approach - in a real implementation,
                # you'd have a more direct way to get the agent_id
                return None  # TODO: Implement proper agent_id retrieval
    except Exception as e:
        logger.error("Failed to get agent_id from persistent storage: %s", e)
    
    # Fallback to in-memory mapping
    return conversation_id_to_agent_id.get(conversation_id)


def simplify_session_data(session_data: Any) -> list[dict[str, Any]]:
    """Simplify session data to include only essential conversation information.

    Args:
        session_data: The full session data from llama-stack

    Returns:
        Simplified session data with only input_messages and output_message per turn
    """
    session_dict = session_data.model_dump()
    # Create simplified structure
    chat_history = []

    # Extract only essential data from each turn
    for turn in session_dict.get("turns", []):
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


@router.get("/conversations/{conversation_id}", responses=conversation_responses)
def get_conversation_endpoint_handler(
    conversation_id: str,
    _auth: Any = Depends(auth_dependency),
) -> ConversationResponse:
    """Handle request to retrieve a conversation by ID."""
    check_configuration_loaded(configuration)

    # Validate conversation ID format
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "response": "Invalid conversation ID format",
                "cause": f"Conversation ID {conversation_id} is not a valid UUID",
            },
        )

    # Try to get conversation from persistent storage first
    persistent_manager = get_persistent_agent_manager()
    if persistent_manager:
        try:
            conversation_history = persistent_manager.get_conversation_history(conversation_id)
            if conversation_history:
                logger.info("Retrieved conversation %s from persistent storage", conversation_id)
                return ConversationResponse(
                    conversation_id=conversation_id,
                    chat_history=conversation_history,
                )
        except Exception as e:
            logger.error("Failed to get conversation from persistent storage: %s", e)

    # Fallback to llama-stack session retrieval
    agent_id = get_agent_id_from_persistent_storage(conversation_id)
    if not agent_id:
        logger.error("Agent ID not found for conversation %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "conversation ID not found",
                "cause": f"conversation ID {conversation_id} not found!",
            },
        )

    logger.info("Retrieving conversation %s from llama-stack", conversation_id)

    try:
        client = LlamaStackClientHolder().get_client()

        session_data = client.agents.session.retrieve(
            agent_id=agent_id, session_id=conversation_id
        )

        logger.info("Successfully retrieved conversation %s", conversation_id)

        # Simplify the session data to include only essential conversation information
        chat_history = simplify_session_data(session_data)

        return ConversationResponse(
            conversation_id=conversation_id,
            chat_history=chat_history,
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
                "cause": f"Conversation {conversation_id} could not be retrieved: {str(e)}",
            },
        ) from e
    except Exception as e:
        # Handle case where session doesn't exist or other errors
        logger.exception("Error retrieving conversation %s: %s", conversation_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unknown error",
                "cause": f"Unknown error while getting conversation {conversation_id} : {str(e)}",
            },
        ) from e


@router.delete(
    "/conversations/{conversation_id}", responses=conversation_delete_responses
)
def delete_conversation_endpoint_handler(
    conversation_id: str,
    _auth: Any = Depends(auth_dependency),
) -> ConversationDeleteResponse:
    """Handle request to delete a conversation by ID."""
    check_configuration_loaded(configuration)

    # Validate conversation ID format
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "response": "Invalid conversation ID format",
                "cause": f"Conversation ID {conversation_id} is not a valid UUID",
            },
        )

    # Try to delete from persistent storage first
    persistent_manager = get_persistent_agent_manager()
    if persistent_manager:
        try:
            success = persistent_manager.delete_conversation(conversation_id)
            if success:
                logger.info("Successfully deleted conversation %s from persistent storage", conversation_id)
                return ConversationDeleteResponse(
                    conversation_id=conversation_id,
                    success=True,
                    response="Conversation deleted successfully",
                )
        except Exception as e:
            logger.error("Failed to delete conversation from persistent storage: %s", e)

    # Fallback to llama-stack session deletion
    agent_id = get_agent_id_from_persistent_storage(conversation_id)
    if not agent_id:
        logger.error("Agent ID not found for conversation %s", conversation_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "response": "conversation ID not found",
                "cause": f"conversation ID {conversation_id} not found!",
            },
        )
    logger.info("Deleting conversation %s from llama-stack", conversation_id)

    try:
        # Get Llama Stack client
        client = LlamaStackClientHolder().get_client()
        # Delete session using the conversation_id as session_id
        # In this implementation, conversation_id and session_id are the same
        client.agents.session.delete(agent_id=agent_id, session_id=conversation_id)

        logger.info("Successfully deleted conversation %s", conversation_id)

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
