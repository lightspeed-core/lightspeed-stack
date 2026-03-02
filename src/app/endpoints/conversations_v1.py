"""Handler for REST API calls to manage conversation history using Conversations API."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from llama_stack_client import (
    APIConnectionError,
    APIStatusError,
)
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_session
from authentication import get_auth_dependency
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.database.conversations import (
    UserTurn,
    UserConversation,
)
from models.requests import ConversationUpdateRequest
from models.responses import (
    BadRequestResponse,
    ConversationDeleteResponse,
    ConversationDetails,
    ConversationResponse,
    ConversationsListResponse,
    ConversationUpdateResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)
from utils.endpoints import (
    can_access_conversation,
    check_configuration_loaded,
    delete_conversation,
    retrieve_conversation,
    validate_and_retrieve_conversation,
)
from utils.suid import (
    check_suid,
    normalize_conversation_id,
    to_llama_stack_conversation_id,
)
from utils.conversations import build_conversation_turns_from_items
from log import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["conversations_v1"])

conversation_get_responses: dict[int | str, dict[str, Any]] = {
    200: ConversationResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["conversation read", "endpoint"]),
    404: NotFoundResponse.openapi_response(examples=["conversation"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["database", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(),
}

conversation_delete_responses: dict[int | str, dict[str, Any]] = {
    200: ConversationDeleteResponse.openapi_response(),
    400: BadRequestResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(
        examples=["conversation delete", "endpoint"]
    ),
    500: InternalServerErrorResponse.openapi_response(
        examples=["database", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(),
}

conversations_list_responses: dict[int | str, dict[str, Any]] = {
    200: ConversationsListResponse.openapi_response(),
    401: UnauthorizedResponse.openapi_response(
        examples=["missing header", "missing token"]
    ),
    403: ForbiddenResponse.openapi_response(examples=["endpoint"]),
    500: InternalServerErrorResponse.openapi_response(
        examples=["database", "configuration"]
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
        examples=["database", "configuration"]
    ),
    503: ServiceUnavailableResponse.openapi_response(),
}


@router.get(
    "/conversations",
    responses=conversations_list_responses,
    summary="Conversations List Endpoint Handler V1",
)
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

        except SQLAlchemyError as e:
            logger.exception(
                "Error retrieving conversations for user %s: %s", user_id, e
            )
            response = InternalServerErrorResponse.database_error()
            raise HTTPException(**response.model_dump()) from e


@router.get(
    "/conversations/{conversation_id}",
    responses=conversation_get_responses,
    summary="Conversation Get Endpoint Handler V1",
)
@authorize(Action.GET_CONVERSATION)
async def get_conversation_endpoint_handler(  # pylint: disable=too-many-locals,too-many-statements
    request: Request,
    conversation_id: str,
    auth: Any = Depends(get_auth_dependency()),
) -> ConversationResponse:
    """Handle request to retrieve a conversation identified by ID using Conversations API.

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
        response = BadRequestResponse(
            resource="conversation", resource_id=conversation_id
        ).model_dump()
        raise HTTPException(**response)

    # Normalize the conversation ID for database operations (strip conv_ prefix if present)
    normalized_conv_id = normalize_conversation_id(conversation_id)
    logger.debug(
        "GET conversation - original ID: %s, normalized ID: %s",
        conversation_id,
        normalized_conv_id,
    )

    user_id = auth[0]
    conversation = validate_and_retrieve_conversation(
        normalized_conv_id=normalized_conv_id,
        user_id=user_id,
        others_allowed=(
            Action.READ_OTHERS_CONVERSATIONS in request.state.authorized_actions
        ),
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
        conversation_items_response = await client.conversations.items.list(
            conversation_id=llama_stack_conv_id,
            after=None,
            include=None,
            limit=None,
            order="asc",  # oldest first
        )

        if not conversation_items_response.data:
            logger.error("No items found for conversation %s", conversation_id)
            response = NotFoundResponse(
                resource="conversation", resource_id=normalized_conv_id
            ).model_dump()
            raise HTTPException(**response)

        items = conversation_items_response.data

        logger.info(
            "Successfully retrieved %d items for conversation %s",
            len(items),
            conversation_id,
        )
        # Retrieve turns metadata from database
        db_turns: list[UserTurn] = []
        try:
            with get_session() as session:
                db_turns = (
                    session.query(UserTurn)
                    .filter_by(conversation_id=normalized_conv_id)
                    .order_by(UserTurn.turn_number)
                    .all()
                )
        except SQLAlchemyError as e:
            logger.error(
                "Database error occurred while retrieving conversation turns for %s.",
                normalized_conv_id,
            )
            response = InternalServerErrorResponse.database_error()
            raise HTTPException(**response.model_dump()) from e

        # Build conversation turns from items and populate turns metadata
        # Use conversation.created_at for legacy conversations without turn metadata
        chat_history = build_conversation_turns_from_items(
            items, db_turns, conversation.created_at
        )

        return ConversationResponse(
            conversation_id=normalized_conv_id,
            chat_history=chat_history,
        )

    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(
            backend_name="Llama Stack", cause=str(e)
        ).model_dump()
        raise HTTPException(**response) from e

    except APIStatusError as e:
        logger.error("Conversation not found: %s", e)
        response = NotFoundResponse(
            resource="conversation", resource_id=normalized_conv_id
        ).model_dump()
        raise HTTPException(**response) from e


@router.delete(
    "/conversations/{conversation_id}",
    responses=conversation_delete_responses,
    summary="Conversation Delete Endpoint Handler V1",
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
        response = BadRequestResponse(
            resource="conversation", resource_id=conversation_id
        ).model_dump()
        raise HTTPException(**response)

    # Normalize the conversation ID for database operations (strip conv_ prefix if present)
    normalized_conv_id = normalize_conversation_id(conversation_id)

    # Check if user has access to delete this conversation
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
        response = ForbiddenResponse.conversation(
            action="delete",
            resource_id=normalized_conv_id,
            user_id=user_id,
        ).model_dump()
        raise HTTPException(**response)

    # If reached this, user is authorized to delete this conversation
    try:
        local_deleted = delete_conversation(normalized_conv_id)
        if not local_deleted:
            logger.info(
                "Conversation %s not found locally when deleting.",
                normalized_conv_id,
            )
    except SQLAlchemyError as e:
        logger.error(
            "Database error while deleting conversation %s",
            normalized_conv_id,
        )
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e

    logger.info("Deleting conversation %s using Conversations API", normalized_conv_id)

    try:
        # Get Llama Stack client
        client = AsyncLlamaStackClientHolder().get_client()

        # Convert to llama-stack format (add 'conv_' prefix if needed)
        llama_stack_conv_id = to_llama_stack_conversation_id(normalized_conv_id)

        # Use Conversations API to delete the conversation
        delete_response = await client.conversations.delete(
            conversation_id=llama_stack_conv_id
        )
        logger.info(
            "Remote deletion of %s successful (remote_deleted=%s)",
            normalized_conv_id,
            delete_response.deleted,
        )

    except APIConnectionError as e:
        response = ServiceUnavailableResponse(backend_name="Llama Stack", cause=str(e))
        raise HTTPException(**response.model_dump()) from e

    except APIStatusError:
        logger.warning(
            "Conversation %s in LlamaStack not found. Treating as already deleted.",
            normalized_conv_id,
        )

    return ConversationDeleteResponse(
        conversation_id=normalized_conv_id,
        deleted=local_deleted,
    )


@router.put(
    "/conversations/{conversation_id}",
    responses=conversation_update_responses,
    summary="Conversation Update Endpoint Handler V1",
)
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
        response = BadRequestResponse(
            resource="conversation", resource_id=conversation_id
        ).model_dump()
        raise HTTPException(**response)

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
        response = ForbiddenResponse.conversation(
            action="update", resource_id=normalized_conv_id, user_id=user_id
        ).model_dump()
        raise HTTPException(**response)

    # If reached this, user is authorized to update this conversation
    try:
        conversation = retrieve_conversation(normalized_conv_id)
        if conversation is None:
            response = NotFoundResponse(
                resource="conversation", resource_id=normalized_conv_id
            ).model_dump()
            raise HTTPException(**response)

    except SQLAlchemyError as e:
        logger.error(
            "Database error occurred while retrieving conversation %s.",
            normalized_conv_id,
        )
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e

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
        await client.conversations.update(
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
        response = ServiceUnavailableResponse(
            backend_name="Llama Stack", cause=str(e)
        ).model_dump()
        raise HTTPException(**response) from e

    except APIStatusError as e:
        logger.error("Conversation not found: %s", e)
        response = NotFoundResponse(
            resource="conversation", resource_id=normalized_conv_id
        ).model_dump()
        raise HTTPException(**response) from e

    except SQLAlchemyError as e:
        logger.error(
            "Database error occurred while updating conversation %s.",
            normalized_conv_id,
        )
        response = InternalServerErrorResponse.database_error()
        raise HTTPException(**response.model_dump()) from e
