"""Handler for REST API calls to manage conversation history using Agent API."""

import logging
from typing import Any

from llama_stack_client import APIConnectionError, NotFoundError

from fastapi import APIRouter, HTTPException, Request, status, Depends

from client import AsyncLlamaStackClientHolder
from authentication import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from models.config import Action
from models.responses import (
    ConversationResponse,
    ConversationDeleteResponse,
    ConversationsListResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.conversations import (
    conversation_responses,
    conversation_delete_responses,
    conversations_list_responses,
    simplify_session_data,
    get_conversations_list_base,
    validate_conversation_id,
    validate_conversation_access,
    delete_conversation_base,
)

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["conversations"])
auth_dependency = get_auth_dependency()


@router.get("/conversations", responses=conversations_list_responses)
@authorize(Action.LIST_CONVERSATIONS)
async def get_conversations_list_endpoint_handler(
    request: Request,
    auth: Any = Depends(auth_dependency),
) -> ConversationsListResponse:
    """Handle request to retrieve all conversations for the authenticated user."""
    return get_conversations_list_base(request, auth)


@router.get("/conversations/{conversation_id}", responses=conversation_responses)
@authorize(Action.GET_CONVERSATION)
async def get_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(auth_dependency),
) -> ConversationResponse:
    """
    Handle request to retrieve a conversation by ID using Agent API.

    Retrieve a conversation's chat history by its ID. Then fetches
    the conversation session from the Llama Stack backend using Agent API,
    simplifies the session data to essential chat history, and
    returns it in a structured response. Raises HTTP 400 for
    invalid IDs, 404 if not found, 503 if the backend is
    unavailable, and 500 for unexpected errors.

    Parameters:
        conversation_id (str): Unique identifier of the conversation to retrieve.

    Returns:
        ConversationResponse: Structured response containing the conversation
        ID and simplified chat history.
    """
    # Ensure configuration is loaded
    check_configuration_loaded(configuration)

    # Validate conversation ID format
    validate_conversation_id(conversation_id)

    user_id = auth[0]

    validate_conversation_access(
        user_id=user_id,
        conversation_id=conversation_id,
        request=request,
        action_read_others=Action.READ_OTHERS_CONVERSATIONS,
    )

    agent_id = conversation_id
    logger.info("Retrieving conversation %s using Agent API", conversation_id)

    try:
        client = AsyncLlamaStackClientHolder().get_client()

        # Agent API specific logic
        agent_sessions = (await client.agents.session.list(agent_id=agent_id)).data
        if not agent_sessions:
            logger.error("No sessions found for conversation %s", conversation_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "response": "Conversation not found",
                    "cause": f"Conversation {conversation_id} could not be retrieved.",
                },
            )
        session_id = str(agent_sessions[0].get("session_id"))

        session_response = await client.agents.session.retrieve(
            agent_id=agent_id, session_id=session_id
        )
        session_data = session_response.model_dump()

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
    except HTTPException:
        raise
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


async def get_agent_sessions(client: Any, conversation_id: str) -> list[dict[str, Any]]:
    """Get agent sessions for a conversation."""
    agent_id = conversation_id
    return (await client.agents.session.list(agent_id=agent_id)).data


async def delete_agent_sessions(
    client: Any, conversation_id: str, sessions: list[dict[str, Any]]
) -> None:
    """Delete agent sessions for a conversation."""
    agent_id = conversation_id
    session_id = str(sessions[0].get("session_id"))
    await client.agents.session.delete(agent_id=agent_id, session_id=session_id)


@router.delete(
    "/conversations/{conversation_id}", responses=conversation_delete_responses
)
@authorize(Action.DELETE_CONVERSATION)
async def delete_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(auth_dependency),
) -> ConversationDeleteResponse:
    """
    Handle request to delete a conversation by ID using Agent API.

    Validates the conversation ID format and attempts to delete the
    corresponding session from the Llama Stack backend using Agent API.
    Raises HTTP errors for invalid IDs, not found conversations, connection
    issues, or unexpected failures.

    Returns:
        ConversationDeleteResponse: Response indicating the result of the deletion operation.
    """
    return await delete_conversation_base(
        request=request,
        conversation_id=conversation_id,
        auth=auth,
        get_session_func=get_agent_sessions,
        delete_session_func=delete_agent_sessions,
    )
