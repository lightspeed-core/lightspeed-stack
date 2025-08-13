"""Models for service responses."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ModelsResponse(BaseModel):
    """Model representing a response to models request."""

    models: list[dict[str, Any]]


# TODO(lucasagomes): a lot of fields to add to QueryResponse. For now
# we are keeping it simple. The missing fields are:
# - referenced_documents: The optional URLs and titles for the documents used
#   to generate the response.
# - truncated: Set to True if conversation history was truncated to be within context window.
# - input_tokens: Number of tokens sent to LLM
# - output_tokens: Number of tokens received from LLM
# - available_quotas: Quota available as measured by all configured quota limiters
# - tool_calls: List of tool requests.
# - tool_results: List of tool results.
# See LLMResponse in ols-service for more details.
class QueryResponse(BaseModel):
    """Model representing LLM response to a query.

    Attributes:
        conversation_id: The optional conversation ID (UUID).
        response: The response.
    """

    conversation_id: Optional[str] = None
    response: str

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "response": "Operator Lifecycle Manager (OLM) helps users install...",
                }
            ]
        }
    }


class InfoResponse(BaseModel):
    """Model representing a response to a info request.

    Attributes:
        name: Service name.
        version: Service version.

    Example:
        ```python
        info_response = InfoResponse(
            name="Lightspeed Stack",
            version="1.0.0",
        )
        ```
    """

    name: str
    version: str

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Lightspeed Stack",
                    "version": "1.0.0",
                }
            ]
        }
    }


class ProviderHealthStatus(BaseModel):
    """Model representing the health status of a provider.

    Attributes:
        provider_id: The ID of the provider.
        status: The health status ('ok', 'unhealthy', 'not_implemented').
        message: Optional message about the health status.
    """

    provider_id: str
    status: str
    message: Optional[str] = None


class ReadinessResponse(BaseModel):
    """Model representing response to a readiness request.

    Attributes:
        ready: If service is ready.
        reason: The reason for the readiness.
        providers: List of unhealthy providers in case of readiness failure.

    Example:
        ```python
        readiness_response = ReadinessResponse(
            ready=False,
            reason="Service is not ready",
            providers=[
                ProviderHealthStatus(
                    provider_id="ollama",
                    status="Error",
                    message="Server is unavailable"
                )
            ]
        )
        ```
    """

    ready: bool
    reason: str
    providers: list[ProviderHealthStatus]

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "ready": True,
                    "reason": "Service is ready",
                    "providers": [],
                }
            ]
        }
    }


class LivenessResponse(BaseModel):
    """Model representing a response to a liveness request.

    Attributes:
        alive: If app is alive.

    Example:
        ```python
        liveness_response = LivenessResponse(alive=True)
        ```
    """

    alive: bool

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "alive": True,
                }
            ]
        }
    }


class NotAvailableResponse(BaseModel):
    """Model representing error response for readiness endpoint."""

    detail: dict[str, str]

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Service is not ready",
                        "cause": "Index is not ready",
                    }
                },
                {
                    "detail": {
                        "response": "Service is not ready",
                        "cause": "LLM is not ready",
                    },
                },
            ]
        }
    }


class FeedbackResponse(BaseModel):
    """Model representing a response to a feedback request.

    Attributes:
        response: The response of the feedback request.

    Example:
        ```python
        feedback_response = FeedbackResponse(response="feedback received")
        ```
    """

    response: str

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "response": "feedback received",
                }
            ]
        }
    }


class StatusResponse(BaseModel):
    """Model representing a response to a status request.

    Attributes:
        functionality: The functionality of the service.
        status: The status of the service.

    Example:
        ```python
        status_response = StatusResponse(
            functionality="feedback",
            status={"enabled": True},
        )
        ```
    """

    functionality: str
    status: dict

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "functionality": "feedback",
                    "status": {"enabled": True},
                }
            ]
        }
    }


class AuthorizedResponse(BaseModel):
    """Model representing a response to an authorization request.

    Attributes:
        user_id: The ID of the logged in user.
        username: The name of the logged in user.
    """

    user_id: str = Field(
        ...,
        description="User ID, for example UUID",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )
    username: str = Field(
        ...,
        description="User name",
        examples=["John Doe", "Adam Smith"],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "user1",
                }
            ]
        }
    }


class UnauthorizedResponse(BaseModel):
    """Model representing response for missing or invalid credentials."""

    detail: str

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": "Unauthorized: No auth header found",
                },
            ]
        }
    }


class ForbiddenResponse(UnauthorizedResponse):
    """Model representing response for forbidden access."""

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": "Forbidden: User is not authorized to access this resource",
                },
            ]
        }
    }


class ConversationResponse(BaseModel):
    """Model representing a response for retrieving a conversation.

    Attributes:
        conversation_id: The conversation ID (UUID).
        chat_history: The simplified chat history as a list of conversation turns.

    Example:
        ```python
        conversation_response = ConversationResponse(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            chat_history=[
                {
                    "messages": [
                        {"content": "Hello", "type": "user"},
                        {"content": "Hi there!", "type": "assistant"}
                    ],
                    "started_at": "2024-01-01T00:01:00Z",
                    "completed_at": "2024-01-01T00:01:05Z"
                }
            ]
        )
        ```
    """

    conversation_id: str
    chat_history: list[dict[str, Any]]

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
                            "started_at": "2024-01-01T00:01:00Z",
                            "completed_at": "2024-01-01T00:01:05Z",
                        }
                    ],
                }
            ]
        }
    }


class ConversationDeleteResponse(BaseModel):
    """Model representing a response for deleting a conversation.

    Attributes:
        conversation_id: The conversation ID (UUID) that was deleted.
        success: Whether the deletion was successful.
        response: A message about the deletion result.

    Example:
        ```python
        delete_response = ConversationDeleteResponse(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            success=True,
            response="Conversation deleted successfully"
        )
        ```
    """

    conversation_id: str
    success: bool
    response: str

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "success": True,
                    "response": "Conversation deleted successfully",
                }
            ]
        }
    }


class ConversationDetails(BaseModel):
    """Model representing the details of a user conversation.

    Attributes:
        conversation_id: The conversation ID (UUID).
        created_at: When the conversation was created.
        last_message_at: When the last message was sent.
        message_count: Number of user messages in the conversation.
        model: The model used for the conversation.

    Example:
        ```python
        conversation = ConversationSummary(
            conversation_id="123e4567-e89b-12d3-a456-426614174000"
            created_at="2024-01-01T00:00:00Z",
            last_message_at="2024-01-01T00:05:00Z",
            message_count=5,
            model="gemini/gemini-2.0-flash"
        )
        ```
    """

    conversation_id: str
    created_at: Optional[str] = None
    last_message_at: Optional[str] = None
    message_count: Optional[int] = None
    last_used_model: Optional[str] = None
    last_used_provider: Optional[str] = None


class ConversationsListResponse(BaseModel):
    """Model representing a response for listing conversations of a user.

    Attributes:
        conversations: List of conversation details associated with the user.

    Example:
        ```python
        conversations_list = ConversationsListResponse(
            conversations=[
                ConversationDetails(
                    conversation_id="123e4567-e89b-12d3-a456-426614174000",
                    created_at="2024-01-01T00:00:00Z",
                    last_message_at="2024-01-01T00:05:00Z",
                    message_count=5,
                    model="gemini/gemini-2.0-flash"
                ),
                ConversationDetails(
                    conversation_id="456e7890-e12b-34d5-a678-901234567890"
                    created_at="2024-01-01T01:00:00Z",
                    message_count=2,
                    model="gemini/gemini-2.5-flash"
                )
            ]
        )
        ```
    """

    conversations: list[ConversationDetails]

    # provides examples for /docs endpoint
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
                            "model": "gemini/gemini-2.0-flash",
                        },
                        {
                            "conversation_id": "456e7890-e12b-34d5-a678-901234567890",
                            "created_at": "2024-01-01T01:00:00Z",
                            "message_count": 2,
                            "model": "gemini/gemini-2.5-flash",
                        },
                    ]
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Model representing error response for query endpoint."""

    detail: dict[str, str]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Error while validation question",
                        "cause": "Failed to handle request to https://bam-api.res.ibm.com/v2/text",
                    },
                },
                {
                    "detail": {
                        "response": "Error retrieving conversation history",
                        "cause": "Invalid conversation ID 1237-e89b-12d3-a456-426614174000",
                    },
                },
            ]
        }
    }
