"""Handler for REST API calls to manage agentic display-history conversations."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from opentelemetry import trace

from authentication import get_auth_dependency
from authorization.middleware import authorize
from configuration import configuration
from conversations.display_history.ids import validate_conversation_id
from conversations.display_history.persistence.facade.conversation import (
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation_topic,
)
from log import get_logger
from models.api.requests import ConversationUpdateRequest
from models.api.responses.constants import UNAUTHORIZED_OPENAPI_EXAMPLES
from models.api.responses.error import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from models.api.responses.successful import (
    AgenticConversationGetResponse,
    AgenticConversationListResponse,
    ConversationDeleteResponse,
    ConversationUpdateResponse,
)
from models.config import Action
from utils.endpoints import check_configuration_loaded
from utils.types import Responses

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)
router = APIRouter(tags=["conversations_v3"])


conversation_get_responses: Responses = {
    200: AgenticConversationGetResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(examples=["conversation_id"]),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["conversation read", "endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["conversation"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["database operation", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}

conversation_delete_responses: Responses = {
    200: ConversationDeleteResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(examples=["conversation_id"]),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(
        examples=["conversation delete", "endpoint"]
    ),
    500: InternalServerErrorResponse.openapi_response(
        examples=["database operation", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}

conversations_list_responses: Responses = {
    200: AgenticConversationListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["database operation", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}

conversation_update_responses: Responses = {
    200: ConversationUpdateResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(examples=["conversation_id"]),
    401: UnauthorizedResponse.openapi_response(examples=UNAUTHORIZED_OPENAPI_EXAMPLES),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["conversation"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["database operation", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(examples=["kubernetes api"]),
}


@router.get("/conversations", responses=conversations_list_responses)
@authorize(Action.LIST_CONVERSATIONS)
async def get_conversations_list_endpoint_handler(
    request: Request,
    auth: Any = Depends(get_auth_dependency()),
) -> AgenticConversationListResponse:
    """
    Handle request to retrieve all conversations for the authenticated user.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - auth: Auth context tuple resolved from the authentication dependency.

    ### Returns:
    - AgenticConversationListResponse: Metadata for conversations visible to the caller.

    ### Raises:
    - HTTPException:
    - 401: Unauthorized - Missing or invalid credentials
    - 403: Forbidden - Insufficient permissions
    - 500: Internal Server Error - Configuration not loaded or database failure
    - 503: Service Unavailable - Kubernetes API unavailable when required by auth
    """
    with tracer.start_as_current_span("conversations_v3.list") as span:
        check_configuration_loaded(configuration)
        user_id, _, _, _ = auth
        others_allowed = (
            Action.LIST_OTHERS_CONVERSATIONS in request.state.authorized_actions
        )
        logger.info("Retrieving conversations for user %s", user_id)
        conversations = await run_in_threadpool(
            list_conversations, user_id, others_allowed
        )
        span.set_attribute("conversations.count", len(conversations))
        return AgenticConversationListResponse(conversations=conversations)


@router.get(
    "/conversations/{conversation_id}",
    responses=conversation_get_responses,
)
@authorize(Action.GET_CONVERSATION)
async def get_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(get_auth_dependency()),
) -> AgenticConversationGetResponse:
    """
    Handle request to retrieve a conversation identified by its ID.

    Loads agent display history from persistence, including ordered agent turns.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - conversation_id: Unique identifier of the conversation to retrieve.
    - auth: Auth context tuple resolved from the authentication dependency.

    ### Returns:
    - AgenticConversationGetResponse: Conversation metadata and agent turn history.

    ### Raises:
    - HTTPException:
    - 400: Bad Request - Invalid conversation ID format
    - 401: Unauthorized - Missing or invalid credentials
    - 403: Forbidden - Insufficient permissions to read this conversation
    - 404: Not Found - Conversation does not exist
    - 500: Internal Server Error - Configuration not loaded or database failure
    - 503: Service Unavailable - Kubernetes API unavailable when required by auth
    """
    with tracer.start_as_current_span("conversations_v3.get") as span:
        check_configuration_loaded(configuration)
        validate_conversation_id(conversation_id)
        user_id, _, _, _ = auth
        others_allowed = (
            Action.READ_OTHERS_CONVERSATIONS in request.state.authorized_actions
        )
        logger.info("Retrieving conversation %s for user %s", conversation_id, user_id)
        conversation = await run_in_threadpool(
            get_conversation, conversation_id, user_id, others_allowed
        )
        span.set_attribute("conversations.found", True)
        span.set_attribute("conversations.turns.count", len(conversation.chat_history))
        return AgenticConversationGetResponse.model_validate(conversation)


@router.delete(
    "/conversations/{conversation_id}", responses=conversation_delete_responses
)
@authorize(Action.DELETE_CONVERSATION)
async def delete_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationDeleteResponse:
    """
    Handle request to delete a conversation by ID.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - conversation_id: Unique identifier of the conversation to delete.
    - auth: Auth context tuple resolved from the authentication dependency.

    ### Returns:
    - ConversationDeleteResponse: Whether the conversation was deleted.

    ### Raises:
    - HTTPException:
    - 400: Bad Request - Invalid conversation ID format
    - 401: Unauthorized - Missing or invalid credentials
    - 403: Forbidden - Insufficient permissions to delete this conversation
    - 500: Internal Server Error - Configuration not loaded or database failure
    - 503: Service Unavailable - Kubernetes API unavailable when required by auth
    """
    with tracer.start_as_current_span("conversations_v3.delete") as span:
        check_configuration_loaded(configuration)
        validate_conversation_id(conversation_id)
        user_id, _, _, _ = auth
        others_allowed = (
            Action.DELETE_OTHERS_CONVERSATIONS in request.state.authorized_actions
        )
        logger.info("Deleting conversation %s for user %s", conversation_id, user_id)
        deleted = await run_in_threadpool(
            delete_conversation, conversation_id, user_id, others_allowed
        )
        span.set_attribute("conversations.deleted", deleted)
        return ConversationDeleteResponse(
            deleted=deleted, conversation_id=conversation_id
        )


@router.put("/conversations/{conversation_id}", responses=conversation_update_responses)
@authorize(Action.UPDATE_CONVERSATION)
async def update_conversation_endpoint_handler(
    request: Request,
    conversation_id: str,
    update_request: ConversationUpdateRequest,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationUpdateResponse:
    """
    Handle request to update a conversation topic summary by ID.

    ### Parameters:
    - request: The incoming HTTP request (used by middleware).
    - conversation_id: Unique identifier of the conversation to update.
    - update_request: Request body containing the new topic summary.
    - auth: Auth context tuple resolved from the authentication dependency.

    ### Returns:
    - ConversationUpdateResponse: Result of the update operation.

    ### Raises:
    - HTTPException:
    - 400: Bad Request - Invalid conversation ID format
    - 401: Unauthorized - Missing or invalid credentials
    - 403: Forbidden - Insufficient permissions to update this conversation
    - 404: Not Found - Conversation does not exist
    - 500: Internal Server Error - Configuration not loaded or database failure
    - 503: Service Unavailable - Kubernetes API unavailable when required by auth
    """
    with tracer.start_as_current_span("conversations_v3.update") as span:
        check_configuration_loaded(configuration)
        validate_conversation_id(conversation_id)
        user_id, _, _, _ = auth
        others_allowed = (
            Action.QUERY_OTHERS_CONVERSATIONS in request.state.authorized_actions
        )
        logger.info(
            "Updating topic summary for conversation %s for user %s",
            conversation_id,
            user_id,
        )
        result = await run_in_threadpool(
            update_conversation_topic,
            conversation_id,
            user_id,
            others_allowed,
            update_request.topic_summary,
        )
        span.set_attribute("conversations.updated", result)
        return ConversationUpdateResponse(
            conversation_id=conversation_id,
            success=result,
        )
