"""Successful responses for conversation CRUD and listing."""

from typing import ClassVar

from pydantic import Field, computed_field

from log import get_logger
from models.api.responses.successful.bases import (
    AbstractDeleteResponse,
    AbstractSuccessfulResponse,
)
from models.common.conversation import (
    ConversationData,
    ConversationDetails,
    ConversationTurn,
)

logger = get_logger(__name__)


class ConversationResponse(AbstractSuccessfulResponse):
    """Model representing a response for retrieving a conversation.

    Attributes:
        conversation_id: The conversation ID (UUID).
        chat_history: The chat history as a list of conversation turns.
    """

    conversation_id: str = Field(
        ...,
        description="Conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    chat_history: list[ConversationTurn] = Field(
        ...,
        description="The simplified chat history as a list of conversation turns",
        examples=[
            {
                "messages": [
                    {"content": "Hello", "type": "user"},
                    {"content": "Hi there!", "type": "assistant"},
                ],
                "tool_calls": [],
                "tool_results": [],
                "provider": "openai",
                "model": "gpt-4o-mini",
                "started_at": "2024-01-01T00:01:00Z",
                "completed_at": "2024-01-01T00:01:05Z",
            }
        ],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "chat_history": [
                        {
                            "messages": [
                                {"content": "Hello", "type": "user"},
                                {"content": "Hi there!", "type": "assistant"},
                            ],
                            "tool_calls": [],
                            "tool_results": [],
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "started_at": "2024-01-01T00:01:00Z",
                            "completed_at": "2024-01-01T00:01:05Z",
                        }
                    ],
                }
            ]
        }
    }


class ConversationDeleteResponse(AbstractDeleteResponse):
    """Response for deleting a conversation."""

    resource_name: ClassVar[str] = "Conversation"
    conversation_id: str = Field(
        ...,
        description="Conversation identifier that was passed to delete.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )

    @computed_field(json_schema_extra={"deprecated": True})
    def success(self) -> bool:
        """Successful response flag."""
        logger.warning("DEPRECATED: Will be removed in a future release.")
        return True

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "deleted",
                    "value": {
                        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                        "deleted": True,
                        "response": "Conversation deleted successfully",
                    },
                },
                {
                    "label": "not found",
                    "value": {
                        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                        "deleted": False,
                        "response": "Conversation not found",
                    },
                },
            ]
        }
    }


class ConversationsListResponse(AbstractSuccessfulResponse):
    """Model representing a response for listing conversations of a user.

    Attributes:
        conversations: List of conversation details associated with the user.
    """

    conversations: list[ConversationDetails]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversations": [
                        {
                            "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                            "created_at": "2024-01-01T00:00:00Z",
                            "last_message_at": "2024-01-01T00:05:00Z",
                            "message_count": 5,
                            "last_used_model": "gemini/gemini-2.0-flash",
                            "last_used_provider": "gemini",
                            "topic_summary": "Openshift Microservices Deployment Strategies",
                        },
                        {
                            "conversation_id": "456e7890-e12b-34d5-a678-901234567890",
                            "created_at": "2024-01-01T01:00:00Z",
                            "message_count": 2,
                            "last_used_model": "gemini/gemini-2.5-flash",
                            "last_used_provider": "gemini",
                            "topic_summary": "RHDH Purpose Summary",
                        },
                    ]
                }
            ]
        }
    }


class ConversationsListResponseV2(AbstractSuccessfulResponse):
    """Model representing a response for listing conversations of a user.

    Attributes:
        conversations: List of conversation data associated with the user.
    """

    conversations: list[ConversationData]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversations": [
                        {
                            "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                            "topic_summary": "Openshift Microservices Deployment Strategies",
                            "last_message_timestamp": 1704067200.0,
                        }
                    ],
                }
            ]
        }
    }


class ConversationUpdateResponse(AbstractSuccessfulResponse):
    """Model representing a response for updating a conversation topic summary.

    Attributes:
        conversation_id: The conversation ID (UUID) that was updated.
        success: Whether the update was successful.
        message: A message about the update result.
    """

    conversation_id: str = Field(
        ...,
        description="The conversation ID (UUID) that was updated",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    success: bool = Field(
        ...,
        description="Whether the update was successful",
        examples=[True],
    )
    message: str = Field(
        ...,
        description="A message about the update result",
        examples=["Topic summary updated successfully"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "success": True,
                    "message": "Topic summary updated successfully",
                }
            ]
        }
    }
