"""Handlers for conversation management using the Response API (v2)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from authentication import get_auth_dependency
from authorization.middleware import authorize
from models.config import Action
from models.responses import (
    ConversationDeleteResponse,
    ConversationResponse,
    ConversationsListResponse,
)
from utils.conversations import (
    conversations_list_responses,
    conversation_delete_responses,
    conversation_responses,
    get_conversations_list_base,
    delete_conversation_base,
    validate_conversation_id,
    validate_conversation_access,
)


logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["conversations_v2"])
auth_dependency = get_auth_dependency()


async def get_response_sessions(
    _client: Any, _conversation_id: str
) -> list[dict[str, str]]:
    """Placeholder for Response API session listing.

    For now, we rely on the shared base which works without direct
    backend calls until a dedicated Responses API endpoint is wired.
    """
    return [
        {"session_id": _conversation_id},
    ]


async def delete_response_sessions(
    _client: Any, _conversation_id: str, _sessions: list[dict[str, str]]
) -> None:
    """Placeholder for Response API session deletion."""
    return None


@router.get("/conversations", responses=conversations_list_responses)
@authorize(Action.LIST_CONVERSATIONS)
async def get_conversations_list_endpoint_handler_v2(
    request: Request,
    auth: Any = Depends(auth_dependency),
) -> ConversationsListResponse:
    """List conversations for the authenticated user using Response API semantics."""
    return get_conversations_list_base(request, auth)


@router.get("/conversations/{conversation_id}", responses=conversation_responses)
@authorize(Action.GET_CONVERSATION)
async def get_conversation_endpoint_handler_v2(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(auth_dependency),
) -> ConversationResponse:
    """Retrieve a conversation by ID using Response API semantics.

    For now, validate access and return an empty chat history. The
    Response API memory-backed retrieval can be wired later.
    """
    validate_conversation_id(conversation_id)
    user_id = auth[0]
    validate_conversation_access(
        user_id=user_id,
        conversation_id=conversation_id,
        request=request,
        action_read_others=Action.READ_OTHERS_CONVERSATIONS,
    )
    return ConversationResponse(conversation_id=conversation_id, chat_history=[])


@router.delete(
    "/conversations/{conversation_id}", responses=conversation_delete_responses
)
@authorize(Action.DELETE_CONVERSATION)
async def delete_conversation_endpoint_handler_v2(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(auth_dependency),
) -> ConversationDeleteResponse:
    """Delete a conversation by ID using Response API semantics."""
    return await delete_conversation_base(
        request=request,
        conversation_id=conversation_id,
        auth=auth,
        get_session_func=get_response_sessions,
        delete_session_func=delete_response_sessions,
    )
