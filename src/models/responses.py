# pylint: disable=too-many-lines

"""Models for REST API responses."""

from typing import Any, ClassVar, Literal, Optional, Union

from fastapi import status
from pydantic import BaseModel, Field
from pydantic_core import SchemaError

from constants import MEDIA_TYPE_EVENT_STREAM
from models.config import Action, Configuration
from quota.quota_exceed_error import QuotaExceedError
from utils.types import RAGChunk, ReferencedDocument, ToolCallSummary, ToolResultSummary

SUCCESSFUL_RESPONSE_DESCRIPTION = "Successful response"
BAD_REQUEST_DESCRIPTION = "Invalid request format"
UNAUTHORIZED_DESCRIPTION = "Unauthorized"
FORBIDDEN_DESCRIPTION = "Permission denied"
NOT_FOUND_DESCRIPTION = "Resource not found"
UNPROCESSABLE_CONTENT_DESCRIPTION = "Request validation failed"
INVALID_FEEDBACK_PATH_DESCRIPTION = "Invalid feedback storage path"
SERVICE_UNAVAILABLE_DESCRIPTION = "Service unavailable"
QUOTA_EXCEEDED_DESCRIPTION = "Quota limit exceeded"
PROMPT_TOO_LONG_DESCRIPTION = "Prompt is too long"
INTERNAL_SERVER_ERROR_DESCRIPTION = "Internal server error"


class AbstractSuccessfulResponse(BaseModel):
    """Base class for all successful response models."""

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """Generate FastAPI response dict with a single example from model_config."""
        schema = cls.model_json_schema()
        model_examples = schema.get("examples")
        if not model_examples:
            raise SchemaError(f"Examples not found in {cls.__name__}")
        example_value = model_examples[0]
        content = {"application/json": {"example": example_value}}

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "model": cls,
            "content": content,
        }


class ModelsResponse(AbstractSuccessfulResponse):
    """Model representing a response to models request."""

    models: list[dict[str, Any]] = Field(
        ...,
        description="List of models available",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "models": [
                        {
                            "identifier": "openai/gpt-4-turbo",
                            "metadata": {},
                            "api_model_type": "llm",
                            "provider_id": "openai",
                            "type": "model",
                            "provider_resource_id": "gpt-4-turbo",
                            "model_type": "llm",
                        },
                    ],
                }
            ]
        }
    }


class ToolsResponse(AbstractSuccessfulResponse):
    """Model representing a response to tools request."""

    tools: list[dict[str, Any]] = Field(
        description=(
            "List of tools available from all configured MCP servers and built-in toolgroups"
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tools": [
                        {
                            "identifier": "filesystem_read",
                            "description": "Read contents of a file from the filesystem",
                            "parameters": [
                                {
                                    "name": "path",
                                    "description": "Path to the file to read",
                                    "parameter_type": "string",
                                    "required": True,
                                    "default": None,
                                }
                            ],
                            "provider_id": "model-context-protocol",
                            "toolgroup_id": "filesystem-tools",
                            "server_source": "http://localhost:3000",
                            "type": "tool",
                        }
                    ],
                }
            ]
        }
    }


class MCPServerAuthInfo(BaseModel):
    """Information about MCP server client authentication options."""

    name: str = Field(..., description="MCP server name")
    client_auth_headers: list[str] = Field(
        ...,
        description="List of authentication header names for client-provided tokens",
    )


class MCPClientAuthOptionsResponse(AbstractSuccessfulResponse):
    """Response containing MCP servers that accept client-provided authorization."""

    servers: list[MCPServerAuthInfo] = Field(
        default_factory=list,
        description="List of MCP servers that accept client-provided authorization",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "servers": [
                        {
                            "name": "github",
                            "client_auth_headers": ["Authorization"],
                        },
                        {
                            "name": "gitlab",
                            "client_auth_headers": ["Authorization", "X-API-Key"],
                        },
                    ]
                }
            ]
        }
    }


class ShieldsResponse(AbstractSuccessfulResponse):
    """Model representing a response to shields request."""

    shields: list[dict[str, Any]] = Field(
        ...,
        description="List of shields available",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "shields": [
                        {
                            "identifier": "lightspeed_question_validity-shield",
                            "provider_resource_id": "lightspeed_question_validity-shield",
                            "provider_id": "lightspeed_question_validity",
                            "type": "shield",
                            "params": {},
                        }
                    ],
                }
            ]
        }
    }


class RAGInfoResponse(AbstractSuccessfulResponse):
    """Model representing a response with information about RAG DB."""

    id: str = Field(
        ..., description="Vector DB unique ID", examples=["vs_00000000_0000_0000"]
    )
    name: Optional[str] = Field(
        None,
        description="Human readable vector DB name",
        examples=["Faiss Store with Knowledge base"],
    )
    created_at: int = Field(
        ...,
        description="When the vector store was created, represented as Unix time",
        examples=[1763391371],
    )
    last_active_at: Optional[int] = Field(
        None,
        description="When the vector store was last active, represented as Unix time",
        examples=[1763391371],
    )
    usage_bytes: int = Field(
        ...,
        description="Storage byte(s) used by this vector DB",
        examples=[0],
    )
    expires_at: Optional[int] = Field(
        None,
        description="When the vector store expires, represented as Unix time",
        examples=[1763391371],
    )
    object: str = Field(
        ...,
        description="Object type",
        examples=["vector_store"],
    )
    status: str = Field(
        ...,
        description="Vector DB status",
        examples=["completed"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "vs_7b52a8cf-0fa3-489c-beab-27e061d102f3",
                    "name": "Faiss Store with Knowledge base",
                    "created_at": 1763391371,
                    "last_active_at": 1763391371,
                    "usage_bytes": 1024000,
                    "expires_at": None,
                    "object": "vector_store",
                    "status": "completed",
                }
            ]
        }
    }


class RAGListResponse(AbstractSuccessfulResponse):
    """Model representing a response to list RAGs request."""

    rags: list[str] = Field(
        ...,
        title="RAG list response",
        description="List of RAG identifiers",
        examples=[
            "vs_7b52a8cf-0fa3-489c-beab-27e061d102f3",
            "vs_7b52a8cf-0fa3-489c-cafe-27e061d102f3",
        ],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "rags": [
                        "vs_00000000-cafe-babe-0000-000000000000",
                        "vs_7b52a8cf-0fa3-489c-beab-27e061d102f3",
                        "vs_7b52a8cf-0fa3-489c-cafe-27e061d102f3",
                    ]
                }
            ]
        }
    }


class ProvidersListResponse(AbstractSuccessfulResponse):
    """Model representing a response to providers request."""

    providers: dict[str, list[dict[str, Any]]] = Field(
        ...,
        description="List of available API types and their corresponding providers",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "providers": {
                        "inference": [
                            {
                                "provider_id": "sentence-transformers",
                                "provider_type": "inline::sentence-transformers",
                            },
                            {
                                "provider_id": "openai",
                                "provider_type": "remote::openai",
                            },
                        ],
                        "agents": [
                            {
                                "provider_id": "meta-reference",
                                "provider_type": "inline::meta-reference",
                            },
                        ],
                    },
                }
            ]
        }
    }


class ProviderResponse(AbstractSuccessfulResponse):
    """Model representing a response to get specific provider request."""

    api: str = Field(
        ...,
        description="The API this provider implements",
    )
    config: dict[str, Union[bool, float, str, list[Any], object, None]] = Field(
        ...,
        description="Provider configuration parameters",
    )
    health: dict[str, Union[bool, float, str, list[Any], object, None]] = Field(
        ...,
        description="Current health status of the provider",
    )
    provider_id: str = Field(..., description="Unique provider identifier")
    provider_type: str = Field(..., description="Provider implementation type")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "api": "inference",
                    "config": {"api_key": "********"},
                    "health": {"status": "OK", "message": "Healthy"},
                    "provider_id": "openai",
                    "provider_type": "remote::openai",
                }
            ]
        }
    }


class ConversationData(BaseModel):
    """Model representing conversation data returned by cache list operations.

    Attributes:
        conversation_id: The conversation ID
        topic_summary: The topic summary for the conversation (can be None)
        last_message_timestamp: The timestamp of the last message in the conversation
    """

    conversation_id: str
    topic_summary: Optional[str]
    last_message_timestamp: float


class QueryResponse(AbstractSuccessfulResponse):
    """Model representing LLM response to a query.

    Attributes:
        conversation_id: The optional conversation ID (UUID).
        response: The response.
        rag_chunks: Deprecated. List of RAG chunks used to generate the response.
            This information is now available in tool_results under file_search_call type.
        referenced_documents: The URLs and titles for the documents used to generate the response.
        tool_calls: List of tool calls made during response generation.
        tool_results: List of tool results.
        truncated: Whether conversation history was truncated.
        input_tokens: Number of tokens sent to LLM.
        output_tokens: Number of tokens received from LLM.
        available_quotas: Quota available as measured by all configured quota limiters.
    """

    conversation_id: Optional[str] = Field(
        None,
        description="The optional conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    response: str = Field(
        description="Response from LLM",
        examples=[
            "Kubernetes is an open-source container orchestration system for automating ..."
        ],
    )

    rag_chunks: list[RAGChunk] = Field(
        default_factory=list,
        description="Deprecated: List of RAG chunks used to generate the response.",
    )

    referenced_documents: list[ReferencedDocument] = Field(
        default_factory=list,
        description="List of documents referenced in generating the response",
        examples=[
            [
                {
                    "doc_url": "https://docs.openshift.com/"
                    "container-platform/4.15/operators/olm/index.html",
                    "doc_title": "Operator Lifecycle Manager (OLM)",
                }
            ]
        ],
    )

    truncated: bool = Field(
        False,
        description="Deprecated:Whether conversation history was truncated",
        examples=[False, True],
    )

    input_tokens: int = Field(
        0,
        description="Number of tokens sent to LLM",
        examples=[150, 250, 500],
    )

    output_tokens: int = Field(
        0,
        description="Number of tokens received from LLM",
        examples=[50, 100, 200],
    )

    available_quotas: dict[str, int] = Field(
        default_factory=dict,
        description="Quota available as measured by all configured quota limiters",
        examples=[{"daily": 1000, "monthly": 50000}],
    )

    tool_calls: list[ToolCallSummary] = Field(
        default_factory=list,
        description="List of tool calls made during response generation",
    )

    tool_results: list[ToolResultSummary] = Field(
        default_factory=list,
        description="List of tool results",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "response": "Operator Lifecycle Manager (OLM) helps users install...",
                    "referenced_documents": [
                        {
                            "doc_url": "https://docs.openshift.com/container-platform/4.15/"
                            "operators/understanding/olm/olm-understanding-olm.html",
                            "doc_title": "Operator Lifecycle Manager concepts and resources",
                        },
                    ],
                    "truncated": False,
                    "input_tokens": 123,
                    "output_tokens": 456,
                    "available_quotas": {
                        "UserQuotaLimiter": 998911,
                        "ClusterQuotaLimiter": 998911,
                    },
                    "tool_calls": [
                        {"name": "tool1", "args": {}, "id": "1", "type": "tool_call"}
                    ],
                    "tool_results": [
                        {
                            "id": "1",
                            "status": "success",
                            "content": "bla",
                            "type": "tool_result",
                            "round": 1,
                        }
                    ],
                }
            ]
        }
    }


class StreamingQueryResponse(AbstractSuccessfulResponse):
    """Documentation-only model for streaming query responses using Server-Sent Events (SSE)."""

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """Generate FastAPI response dict for SSE streaming with examples.

        Note: This is used for OpenAPI documentation only. The actual endpoint
        returns a StreamingResponse object, not this Pydantic model.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples")
        if not model_examples:
            raise SchemaError(f"Examples not found in {cls.__name__}")
        example_value = model_examples[0]
        content = {
            MEDIA_TYPE_EVENT_STREAM: {
                "schema": {"type": "string", "format": MEDIA_TYPE_EVENT_STREAM},
                "example": example_value,
            }
        }

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "content": content,
            # Note: No "model" key since we're not actually serializing this model
        }

    model_config = {
        "json_schema_extra": {
            "examples": [
                (
                    'data: {"event": "start", "data": {'
                    '"conversation_id": "123e4567-e89b-12d3-a456-426614174000"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 0, "token": "No Violation"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 1, "token": ""}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 2, "token": "Hello"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 3, "token": "!"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 4, "token": " How"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 5, "token": " can"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 6, "token": " I"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 7, "token": " assist"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 8, "token": " you"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 9, "token": " today"}}\n\n'
                    'data: {"event": "token", "data": {'
                    '"id": 10, "token": "?"}}\n\n'
                    'data: {"event": "turn_complete", "data": {'
                    '"token": "Hello! How can I assist you today?"}}\n\n'
                    'data: {"event": "end", "data": {'
                    '"referenced_documents": [], '
                    '"truncated": null, "input_tokens": 11, "output_tokens": 19}, '
                    '"available_quotas": {}}\n\n'
                ),
            ]
        }
    }


class InfoResponse(AbstractSuccessfulResponse):
    """Model representing a response to an info request.

    Attributes:
        name: Service name.
        service_version: Service version.
        llama_stack_version: Llama Stack version.

    Example:
        ```python
        info_response = InfoResponse(
            name="Lightspeed Stack",
            service_version="1.0.0",
            llama_stack_version="0.2.22",
        )
        ```
    """

    name: str = Field(
        description="Service name",
        examples=["Lightspeed Stack"],
    )

    service_version: str = Field(
        description="Service version",
        examples=["0.1.0", "0.2.0", "1.0.0"],
    )

    llama_stack_version: str = Field(
        description="Llama Stack version",
        examples=["0.2.1", "0.2.2", "0.2.18", "0.2.21", "0.2.22"],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Lightspeed Stack",
                    "service_version": "1.0.0",
                    "llama_stack_version": "1.0.0",
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

    provider_id: str = Field(
        description="The ID of the provider",
    )
    status: str = Field(
        description="The health status",
        examples=["ok", "unhealthy", "not_implemented"],
    )
    message: Optional[str] = Field(
        None,
        description="Optional message about the health status",
        examples=["All systems operational", "Llama Stack is unavailable"],
    )


class ReadinessResponse(AbstractSuccessfulResponse):
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
                    status="unhealthy",
                    message="Server is unavailable"
                )
            ]
        )
        ```
    """

    ready: bool = Field(
        ...,
        description="Flag indicating if service is ready",
        examples=[True, False],
    )

    reason: str = Field(
        ...,
        description="The reason for the readiness",
        examples=["Service is ready"],
    )

    providers: list[ProviderHealthStatus] = Field(
        ...,
        description="List of unhealthy providers in case of readiness failure.",
        examples=[],
    )

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


class LivenessResponse(AbstractSuccessfulResponse):
    """Model representing a response to a liveness request.

    Attributes:
        alive: If app is alive.

    Example:
        ```python
        liveness_response = LivenessResponse(alive=True)
        ```
    """

    alive: bool = Field(
        ...,
        description="Flag indicating that the app is alive",
        examples=[True, False],
    )

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


class FeedbackResponse(AbstractSuccessfulResponse):
    """Model representing a response to a feedback request.

    Attributes:
        response: The response of the feedback request.

    Example:
        ```python
        feedback_response = FeedbackResponse(response="feedback received")
        ```
    """

    response: str = Field(
        ...,
        description="The response of the feedback request.",
        examples=["feedback received"],
    )

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


class StatusResponse(AbstractSuccessfulResponse):
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

    functionality: str = Field(
        ...,
        description="The functionality of the service",
        examples=["feedback"],
    )

    status: dict = Field(
        ...,
        description="The status of the service",
        examples=[{"enabled": True}],
    )

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


class AuthorizedResponse(AbstractSuccessfulResponse):
    """Model representing a response to an authorization request.

    Attributes:
        user_id: The ID of the logged in user.
        username: The name of the logged in user.
        skip_userid_check: Whether to skip the user ID check.
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
    skip_userid_check: bool = Field(
        ...,
        description="Whether to skip the user ID check",
        examples=[True, False],
    )

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "123e4567-e89b-12d3-a456-426614174000",
                    "username": "user1",
                    "skip_userid_check": False,
                }
            ]
        }
    }


class Message(BaseModel):
    """Model representing a message in a conversation turn.

    Attributes:
        content: The message content.
        type: The type of message.
    """

    content: str = Field(
        ...,
        description="The message content",
        examples=["Hello, how can I help you?"],
    )
    type: Literal["user", "assistant", "system", "developer"] = Field(
        ...,
        description="The type of message",
        examples=["user", "assistant", "system", "developer"],
    )


class ConversationTurn(BaseModel):
    """Model representing a single conversation turn.

    Attributes:
        messages: List of messages in this turn.
        tool_calls: List of tool calls made in this turn.
        tool_results: List of tool results from this turn.
        provider: Provider identifier used for this turn.
        model: Model identifier used for this turn.
        started_at: ISO 8601 timestamp when the turn started.
        completed_at: ISO 8601 timestamp when the turn completed.
    """

    messages: list[Message] = Field(
        default_factory=list,
        description="List of messages in this turn",
    )
    tool_calls: list[ToolCallSummary] = Field(
        default_factory=list,
        description="List of tool calls made in this turn",
    )
    tool_results: list[ToolResultSummary] = Field(
        default_factory=list,
        description="List of tool results from this turn",
    )
    provider: str = Field(
        ...,
        description="Provider identifier used for this turn",
        examples=["openai"],
    )
    model: str = Field(
        ...,
        description="Model identifier used for this turn",
        examples=["gpt-4o-mini"],
    )
    started_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the turn started",
        examples=["2024-01-01T00:01:00Z"],
    )
    completed_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the turn completed",
        examples=["2024-01-01T00:01:05Z"],
    )


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


class ConversationDeleteResponse(AbstractSuccessfulResponse):
    """Model representing a response for deleting a conversation.

    Attributes:
        conversation_id: The conversation ID (UUID) that was deleted.
        success: Whether the deletion was successful.
        response: A message about the deletion result.
    """

    conversation_id: str = Field(
        ...,
        description="The conversation ID (UUID) that was deleted.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    success: bool = Field(
        ..., description="Whether the deletion was successful.", examples=[True, False]
    )
    response: str = Field(
        ...,
        description="A message about the deletion result.",
        examples=[
            "Conversation deleted successfully",
            "Conversation cannot be deleted",
        ],
    )

    def __init__(self, *, deleted: bool, conversation_id: str) -> None:
        """
        Initialize a ConversationDeleteResponse and populate its public fields.

        If `deleted` is True the response message is "Conversation deleted
        successfully"; otherwise it is "Conversation cannot be deleted".

        Parameters:
            deleted (bool): Whether the conversation was successfully deleted.
            conversation_id (str): The ID of the conversation.
        """
        response_msg = (
            "Conversation deleted successfully"
            if deleted
            else "Conversation cannot be deleted"
        )
        super().__init__(
            conversation_id=conversation_id,  # type: ignore[call-arg]
            success=True,  # type: ignore[call-arg]
            response=response_msg,  # type: ignore[call-arg]
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "deleted",
                    "value": {
                        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                        "success": True,
                        "response": "Conversation deleted successfully",
                    },
                },
                {
                    "label": "not found",
                    "value": {
                        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                        "success": True,
                        "response": "Conversation can not be deleted",
                    },
                },
            ]
        }
    }

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """
        Build an OpenAPI-compatible FastAPI response dict using the model's examples.

        Extracts labeled examples from the model's JSON schema `examples` and
        places them under `application/json` -> `examples`. The returned
        mapping includes a `description` ("Successful response"), the `model`
        (the class itself), and `content` containing the assembled examples.

        Returns:
            response (dict[str, Any]): A dict with keys `description`, `model`,
            and `content` suitable for FastAPI/OpenAPI response registration.

        Raises:
            SchemaError: If any example in the model's JSON schema is missing a
                         required `label` or `value`.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples", [])

        named_examples: dict[str, Any] = {}

        for ex in model_examples:
            label = ex.get("label")
            if label is None:
                raise SchemaError(f"Example {ex} in {cls.__name__} has no label")

            value = ex.get("value")
            if value is None:
                raise SchemaError(f"Example '{label}' in {cls.__name__} has no value")

            named_examples[label] = {"value": value}

        content = {"application/json": {"examples": named_examples or None}}

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "model": cls,
            "content": content,
        }


class ConversationDetails(BaseModel):
    """Model representing the details of a user conversation.

    Attributes:
        conversation_id: The conversation ID (UUID).
        created_at: When the conversation was created.
        last_message_at: When the last message was sent.
        message_count: Number of user messages in the conversation.
        last_used_model: The last model used for the conversation.
        last_used_provider: The provider of the last used model.
        topic_summary: The topic summary for the conversation.

    Example:
        ```python
        conversation = ConversationDetails(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            created_at="2024-01-01T00:00:00Z",
            last_message_at="2024-01-01T00:05:00Z",
            message_count=5,
            last_used_model="gemini/gemini-2.0-flash",
            last_used_provider="gemini",
            topic_summary="Openshift Microservices Deployment Strategies",
        )
        ```
    """

    conversation_id: str = Field(
        ...,
        description="Conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    created_at: Optional[str] = Field(
        None,
        description="When the conversation was created",
        examples=["2024-01-01T01:00:00Z"],
    )

    last_message_at: Optional[str] = Field(
        None,
        description="When the last message was sent",
        examples=["2024-01-01T01:00:00Z"],
    )

    message_count: Optional[int] = Field(
        None,
        description="Number of user messages in the conversation",
        examples=[42],
    )

    last_used_model: Optional[str] = Field(
        None,
        description="Identification of the last model used for the conversation",
        examples=["gpt-4-turbo", "gpt-3.5-turbo-0125"],
    )

    last_used_provider: Optional[str] = Field(
        None,
        description="Identification of the last provider used for the conversation",
        examples=["openai", "gemini"],
    )

    topic_summary: Optional[str] = Field(
        None,
        description="Topic summary for the conversation",
        examples=["Openshift Microservices Deployment Strategies"],
    )


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


class FeedbackStatusUpdateResponse(AbstractSuccessfulResponse):
    """
    Model representing a response to a feedback status update request.

    Attributes:
        status: The previous and current status of the service and who updated it.

    Example:
        ```python
        status_response = StatusResponse(
            status={
                "previous_status": true,
                "updated_status": false,
                "updated_by": "user/test",
                "timestamp": "2023-03-15 12:34:56"
            },
        )
        ```
    """

    status: dict

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": {
                        "previous_status": True,
                        "updated_status": False,
                        "updated_by": "user/test",
                        "timestamp": "2023-03-15 12:34:56",
                    },
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

    Example:
        ```python
        update_response = ConversationUpdateResponse(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            success=True,
            message="Topic summary updated successfully",
        )
        ```
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


class ConfigurationResponse(AbstractSuccessfulResponse):
    """Success response model for the config endpoint."""

    configuration: Configuration

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "configuration": {
                        "name": "lightspeed-stack",
                        "service": {
                            "host": "localhost",
                            "port": 8080,
                            "auth_enabled": False,
                            "workers": 1,
                            "color_log": True,
                            "access_log": True,
                            "tls_config": {
                                "tls_certificate_path": None,
                                "tls_key_path": None,
                                "tls_key_password": None,
                            },
                            "cors": {
                                "allow_origins": ["*"],
                                "allow_credentials": False,
                                "allow_methods": ["*"],
                                "allow_headers": ["*"],
                            },
                        },
                        "llama_stack": {
                            "url": "http://localhost:8321",
                            "api_key": "*****",
                            "use_as_library_client": False,
                            "library_client_config_path": None,
                        },
                        "user_data_collection": {
                            "feedback_enabled": True,
                            "feedback_storage": "/tmp/data/feedback",
                            "transcripts_enabled": False,
                            "transcripts_storage": "/tmp/data/transcripts",
                        },
                        "database": {
                            "sqlite": {"db_path": "/tmp/lightspeed-stack.db"},
                            "postgres": None,
                        },
                        "mcp_servers": [
                            {
                                "name": "server1",
                                "provider_id": "provider1",
                                "url": "http://url.com:1",
                            },
                        ],
                        "authentication": {
                            "module": "noop",
                            "skip_tls_verification": False,
                        },
                        "authorization": {"access_rules": []},
                        "customization": None,
                        "inference": {
                            "default_model": "gpt-4-turbo",
                            "default_provider": "openai",
                        },
                        "conversation_cache": {
                            "type": None,
                            "memory": None,
                            "sqlite": None,
                            "postgres": None,
                        },
                        "byok_rag": [],
                        "quota_handlers": {
                            "sqlite": None,
                            "postgres": None,
                            "limiters": [],
                            "scheduler": {"period": 1},
                            "enable_token_history": False,
                        },
                    }
                }
            ]
        }
    }


class DetailModel(BaseModel):
    """Nested detail model for error responses."""

    response: str = Field(..., description="Short summary of the error")
    cause: str = Field(..., description="Detailed explanation of what caused the error")


class AbstractErrorResponse(BaseModel):
    """
    Base class for error responses.

    Attributes:
        status_code (int): HTTP status code for the error response.
        detail (DetailModel): The detail model containing error summary and cause.
    """

    status_code: int
    detail: DetailModel

    def __init__(self, *, response: str, cause: str, status_code: int):
        """
        Create an error response model with an HTTP status code and detailed message.

        Parameters:
            response (str): A short, user-facing summary of the error.
            cause (str): A more detailed explanation of the error cause.
            status_code (int): The HTTP status code to associate with this error response.
        """
        super().__init__(
            status_code=status_code, detail=DetailModel(response=response, cause=cause)
        )

    @classmethod
    def get_description(cls) -> str:
        """
        Retrieve the class description.

        Returns:
            str: The class `description` attribute if present; otherwise the
                 class docstring; if neither is present, an empty string.
        """
        return getattr(cls, "description", cls.__doc__ or "")

    @classmethod
    def openapi_response(cls, examples: Optional[list[str]] = None) -> dict[str, Any]:
        """
        Build an OpenAPI/FastAPI response dictionary that exposes the model's labeled examples.

        Extracts examples from the model's JSON schema and includes them as
        named application/json examples in the returned response mapping. If
        the optional `examples` list is provided, only examples whose labels
        appear in that list are included. Each included example is exposed
        under its label with a `value` containing a `detail` payload.

        Parameters:
            examples (Optional[list[str]]): If provided, restricts which
                                            labeled examples to include by label.

        Returns:
            dict[str, Any]: A response mapping with keys:
                - "description": the response description,
                - "model": the model class,
                - "content": a mapping for "application/json" to the examples
                             object (or None if no examples).

        Raises:
            SchemaError: If any example in the model schema lacks a `label`.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples", [])

        named_examples: dict[str, Any] = {}
        for ex in model_examples:
            label = ex.get("label", None)
            if label is None:
                raise SchemaError(f"Example {ex} in {cls.__name__} has no label")
            if examples is None or label in examples:
                detail = ex.get("detail")
                if detail is not None:
                    named_examples[label] = {"value": {"detail": detail}}

        content: dict[str, Any] = {
            "application/json": {"examples": named_examples or None}
        }

        return {
            "description": cls.get_description(),
            "model": cls,
            "content": content,
        }


class BadRequestResponse(AbstractErrorResponse):
    """400 Bad Request. Invalid resource identifier."""

    description: ClassVar[str] = BAD_REQUEST_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "conversation_id",
                    "detail": {
                        "response": "Invalid conversation ID format",
                        "cause": (
                            "The conversation ID "
                            "123e4567-e89b-12d3-a456-426614174000 has invalid format."
                        ),
                    },
                }
            ]
        }
    }

    def __init__(self, *, resource: str, resource_id: str):
        """
        Create a 400 Bad Request response for an invalid resource ID format.

        Parameters:
            resource (str): Type of the resource (for message), e.g., "conversation" or "provider".
            resource_id (str): The invalid resource identifier used in the error message.
        """
        response = f"Invalid {resource} ID format"
        cause = f"The {resource} ID {resource_id} has invalid format."
        super().__init__(
            response=response, cause=cause, status_code=status.HTTP_400_BAD_REQUEST
        )


class UnauthorizedResponse(AbstractErrorResponse):
    """401 Unauthorized - Missing or invalid credentials."""

    description: ClassVar[str] = UNAUTHORIZED_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "missing header",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "No Authorization header found",
                    },
                },
                {
                    "label": "missing token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "No token found in Authorization header",
                    },
                },
                {
                    "label": "expired token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Token has expired",
                    },
                },
                {
                    "label": "invalid signature",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Invalid token signature",
                    },
                },
                {
                    "label": "invalid key",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Token signed by unknown key",
                    },
                },
                {
                    "label": "missing claim",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Token missing claim: user_id",
                    },
                },
                {
                    "label": "invalid k8s token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Invalid or expired Kubernetes token",
                    },
                },
                {
                    "label": "invalid jwk token",
                    "detail": {
                        "response": "Missing or invalid credentials provided by client",
                        "cause": "Authentication key server returned invalid data",
                    },
                },
            ]
        }
    }

    def __init__(self, *, cause: str):
        """
        Create an UnauthorizedResponse describing missing or invalid client credentials.

        Initializes the error with a standardized response message and the
        provided cause, and sets the HTTP status to 401 Unauthorized.

        Parameters:
                cause (str): Human-readable explanation of why the request is
                             unauthorized (e.g. "missing token", "token expired").
        """
        response_msg = "Missing or invalid credentials provided by client"
        super().__init__(
            response=response_msg, cause=cause, status_code=status.HTTP_401_UNAUTHORIZED
        )


class ForbiddenResponse(AbstractErrorResponse):
    """403 Forbidden. Access denied."""

    description: ClassVar[str] = FORBIDDEN_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "conversation read",
                    "detail": {
                        "response": "User does not have permission to perform this action",
                        "cause": (
                            "User 6789 does not have permission to read conversation "
                            "with ID 123e4567-e89b-12d3-a456-426614174000"
                        ),
                    },
                },
                {
                    "label": "conversation delete",
                    "detail": {
                        "response": "User does not have permission to perform this action",
                        "cause": (
                            "User 6789 does not have permission to delete conversation "
                            "with ID 123e4567-e89b-12d3-a456-426614174000"
                        ),
                    },
                },
                {
                    "label": "endpoint",
                    "detail": {
                        "response": "User does not have permission to access this endpoint",
                        "cause": "User 6789 is not authorized to access this endpoint.",
                    },
                },
                {
                    "label": "feedback",
                    "detail": {
                        "response": "Storing feedback is disabled",
                        "cause": "Storing feedback is disabled.",
                    },
                },
                {
                    "label": "model override",
                    "detail": {
                        "response": (
                            "This instance does not permit overriding model/provider in the "
                            "query request (missing permission: MODEL_OVERRIDE). Please remove "
                            "the model and provider fields from your request."
                        ),
                        "cause": (
                            "User lacks model_override permission required "
                            "to override model/provider."
                        ),
                    },
                },
            ]
        }
    }

    @classmethod
    def conversation(
        cls, action: str, resource_id: str, user_id: str
    ) -> "ForbiddenResponse":
        """
        Create a ForbiddenResponse for a denied conversation action.

        Parameters:
            action (str): The attempted action (e.g., "read", "delete", "update").
            resource_id (str): The conversation identifier targeted by the action.
            user_id (str): The identifier of the user who attempted the action.

        Returns:
            ForbiddenResponse: Error response indicating the user is not
            permitted to perform the specified action on the conversation, with
            `response` and `cause` fields populated.
        """
        response = "User does not have permission to perform this action"
        cause = (
            f"User {user_id} does not have permission to "
            f"{action} conversation with ID {resource_id}"
        )
        return cls(response=response, cause=cause)

    @classmethod
    def endpoint(cls, user_id: str) -> "ForbiddenResponse":
        """
        Create a ForbiddenResponse indicating the specified user is denied access to the endpoint.

        Parameters:
            user_id (str): Identifier of the user denied access.

        Returns:
            ForbiddenResponse: Error response with a message and a cause
            referencing the given `user_id`.
        """
        response = "User does not have permission to access this endpoint"
        cause = f"User {user_id} is not authorized to access this endpoint."
        return cls(response=response, cause=cause)

    @classmethod
    def feedback_disabled(cls) -> "ForbiddenResponse":
        """
        Create a ForbiddenResponse indicating that storing feedback is disabled.

        Returns:
            ForbiddenResponse: Error response with `response` set to "Storing
            feedback is disabled" and `cause` set to "Storing feedback is
            disabled."
        """
        return cls(
            response="Storing feedback is disabled",
            cause="Storing feedback is disabled.",
        )

    @classmethod
    def model_override(cls) -> "ForbiddenResponse":
        """
        Create a ForbiddenResponse indicating that overriding the model or provider is disallowed.

        Returns:
            ForbiddenResponse: An error response with a user-facing message
            instructing removal of model/provider fields and a cause stating
            the missing `MODEL_OVERRIDE` permission.
        """
        return cls(
            response=(
                "This instance does not permit overriding model/provider in the "
                "query request (missing permission: MODEL_OVERRIDE). Please remove "
                "the model and provider fields from your request."
            ),
            cause=(
                f"User lacks {Action.MODEL_OVERRIDE.value} permission required "
                "to override model/provider."
            ),
        )

    def __init__(self, *, response: str, cause: str):
        """
        Construct a ForbiddenResponse with a public response message and an internal cause.

        Parameters:
                response (str): Human-facing error message describing the forbidden action.
                cause (str): Detailed cause or reason for the denial intended
                for logs or diagnostics.
        """
        super().__init__(
            response=response, cause=cause, status_code=status.HTTP_403_FORBIDDEN
        )


class NotFoundResponse(AbstractErrorResponse):
    """404 Not Found - Resource does not exist."""

    description: ClassVar[str] = NOT_FOUND_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "conversation",
                    "detail": {
                        "response": "Conversation not found",
                        "cause": (
                            "Conversation with ID "
                            "123e4567-e89b-12d3-a456-426614174000 does not exist"
                        ),
                    },
                },
                {
                    "label": "provider",
                    "detail": {
                        "response": "Provider not found",
                        "cause": "Provider with ID openai does not exist",
                    },
                },
                {
                    "label": "model",
                    "detail": {
                        "response": "Model not found",
                        "cause": "Model with ID gpt-4-turbo is not configured",
                    },
                },
                {
                    "label": "rag",
                    "detail": {
                        "response": "Rag not found",
                        "cause": (
                            "Rag with ID vs_7b52a8cf-0fa3-489c-beab-27e061d102f3 does not exist"
                        ),
                    },
                },
            ]
        }
    }

    def __init__(self, *, resource: str, resource_id: str | None = None):
        """
        Create a NotFoundResponse for a missing resource and set the HTTP status to 404.

        Parameters:
            resource (str): Resource type that was not found (e.g., "conversation", "model").
            resource_id (str | None): Identifier of the missing resource. If None, indicates
                the resource type is not configured (e.g., no model selected).
        """
        response = f"{resource.title()} not found"
        if resource_id is None:
            cause = f"No {resource.title()} is configured"
        else:
            cause = f"{resource.title()} with ID {resource_id} does not exist"
        super().__init__(
            response=response, cause=cause, status_code=status.HTTP_404_NOT_FOUND
        )


class PromptTooLongResponse(AbstractErrorResponse):
    """413 Payload Too Large - Prompt is too long."""

    description: ClassVar[str] = PROMPT_TOO_LONG_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "prompt too long",
                    "detail": {
                        "response": "Prompt is too long",
                        "cause": "The prompt exceeds the maximum allowed length.",
                    },
                },
            ]
        }
    }

    def __init__(
        self,
        *,
        response: str = "Prompt is too long",
        cause: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize a PromptTooLongResponse.

        Args:
            response: Short summary of the error. Defaults to "Prompt is too long".
            cause: Detailed explanation of what caused the error. If not provided,
                   will be generated to include model information if model is provided.
            model: The model identifier for which the prompt is too long.
        """
        if cause is None:
            if model:
                cause = f"The input exceeds the context window size of model '{model}'."
            else:
                cause = "The prompt exceeds the maximum allowed length."

        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )


class UnprocessableEntityResponse(AbstractErrorResponse):
    """422 Unprocessable Entity - Request validation failed."""

    description: ClassVar[str] = UNPROCESSABLE_CONTENT_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "invalid format",
                    "detail": {
                        "response": "Invalid request format",
                        "cause": "Invalid request format. The request body could not be parsed.",
                    },
                },
                {
                    "label": "missing attributes",
                    "detail": {
                        "response": "Missing required attributes",
                        "cause": "Missing required attributes: ['query', 'model', 'provider']",
                    },
                },
                {
                    "label": "invalid value",
                    "detail": {
                        "response": "Invalid attribute value",
                        "cause": "Invalid attachment type: must be one of ['text/plain', "
                        "'application/json', 'application/yaml', 'application/xml']",
                    },
                },
            ]
        }
    }

    def __init__(self, *, response: str, cause: str):
        """
        Create a 422 Unprocessable Entity error response.

        Parameters:
            response (str): Human-readable error message describing what was unprocessable.
            cause (str): Specific cause or diagnostic information explaining the error.
        """
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


class QuotaExceededResponse(AbstractErrorResponse):
    """429 Too Many Requests - Quota limit exceeded."""

    description: ClassVar[str] = QUOTA_EXCEEDED_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "model",
                    "detail": {
                        "response": "The model quota has been exceeded",
                        "cause": "The token quota for model gpt-4-turbo has been exceeded.",
                    },
                },
                {
                    "label": "user none",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "User 123 has no available tokens.",
                    },
                },
                {
                    "label": "cluster none",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Cluster has no available tokens.",
                    },
                },
                {
                    "label": "subject none",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Unknown subject 999 has no available tokens.",
                    },
                },
                {
                    "label": "user insufficient",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "User 123 has 5 tokens, but 10 tokens are needed.",
                    },
                },
                {
                    "label": "cluster insufficient",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Cluster has 500 tokens, but 900 tokens are needed.",
                    },
                },
                {
                    "label": "subject insufficient",
                    "detail": {
                        "response": "The quota has been exceeded",
                        "cause": "Unknown subject 999 has 3 tokens, but 6 tokens are needed.",
                    },
                },
            ]
        }
    }

    @classmethod
    def model(cls, model_name: str) -> "QuotaExceededResponse":
        """
        Create a QuotaExceededResponse for a specific model.

        Parameters:
            model_name (str): The model identifier whose token quota was exceeded.

        Returns:
            QuotaExceededResponse: Response with a standard response message
            and a cause that includes the model name.
        """
        response = "The model quota has been exceeded"
        cause = f"The token quota for model {model_name} has been exceeded."
        return cls(response=response, cause=cause)

    @classmethod
    def from_exception(cls, exc: QuotaExceedError) -> "QuotaExceededResponse":
        """
        Construct a QuotaExceededResponse representing the provided QuotaExceedError.

        Parameters:
            exc: The QuotaExceedError instance whose message will be used as
                 the cause.

        Returns:
            QuotaExceededResponse initialized with a standard quota-exceeded
            message and the exception's text as the cause.
        """
        response = "The quota has been exceeded"
        cause = str(exc)
        return cls(response=response, cause=cause)

    def __init__(self, *, response: str, cause: str) -> None:
        """
        Create a QuotaExceededResponse with a public message and an explanatory cause.

        Parameters:
            response (str): Public-facing error message describing the quota condition.
            cause (str): Detailed cause or internal explanation for the quota
                         exceedance; stored in the error detail.

        Notes:
            Sets the response's HTTP status code to 429 (Too Many Requests).
        """
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class InternalServerErrorResponse(AbstractErrorResponse):
    """500 Internal Server Error."""

    description: ClassVar[str] = INTERNAL_SERVER_ERROR_DESCRIPTION

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "internal",
                    "detail": {
                        "response": "Internal server error",
                        "cause": "An unexpected error occurred while processing the request.",
                    },
                },
                {
                    "label": "configuration",
                    "detail": {
                        "response": "Configuration is not loaded",
                        "cause": "Lightspeed Stack configuration has not been initialized.",
                    },
                },
                {
                    "label": "feedback storage",
                    "detail": {
                        "response": "Failed to store feedback",
                        "cause": "Failed to store feedback at directory: /path/example",
                    },
                },
                {
                    "label": "query",
                    "detail": {
                        "response": "Error while processing query",
                        "cause": "Failed to call backend API",
                    },
                },
                {
                    "label": "conversation cache",
                    "detail": {
                        "response": "Conversation cache not configured",
                        "cause": "Conversation cache is not configured or unavailable.",
                    },
                },
                {
                    "label": "database",
                    "detail": {
                        "response": "Database query failed",
                        "cause": "Failed to query the database",
                    },
                },
            ]
        }
    }

    @classmethod
    def generic(cls) -> "InternalServerErrorResponse":
        """
        Create an InternalServerErrorResponse representing a generic internal server error.

        @returns InternalServerErrorResponse: instance with a standard response
        message ("Internal server error") and a cause explaining an unexpected
        processing error.
        """
        return cls(
            response="Internal server error",
            cause="An unexpected error occurred while processing the request.",
        )

    @classmethod
    def configuration_not_loaded(cls) -> "InternalServerErrorResponse":
        """
        Create an InternalServerErrorResponse indicating the service config was not initialized.

        @returns InternalServerErrorResponse with response "Configuration is
        not loaded" and cause "Lightspeed Stack configuration has not been
        initialized."
        """
        return cls(
            response="Configuration is not loaded",
            cause="Lightspeed Stack configuration has not been initialized.",
        )

    @classmethod
    def feedback_path_invalid(cls, path: str) -> "InternalServerErrorResponse":
        """
        Create an InternalServerErrorResponse describing a failure to store feedback.

        Parameters:
            path (str): Filesystem directory where feedback storage was attempted.

        Returns:
            InternalServerErrorResponse: Error response with a response message
            "Failed to store feedback" and a cause indicating the failed
            directory.
        """
        return cls(
            response="Failed to store feedback",
            cause=f"Failed to store feedback at directory: {path}",
        )

    @classmethod
    def query_failed(cls, cause: str) -> "InternalServerErrorResponse":
        """
        Create an InternalServerErrorResponse representing a failed query.

        Parameters:
            cause (str): The error cause message.

        Returns:
            InternalServerErrorResponse: An error response with response "Error
            while processing query" and the provided cause.
        """
        return cls(
            response="Error while processing query",
            cause=cause,
        )

    @classmethod
    def cache_unavailable(cls) -> "InternalServerErrorResponse":
        """
        Create an InternalServerErrorResponse indicating the conversation cache is unavailable.

        Returns:
            InternalServerErrorResponse: Error response with a message that the
            conversation cache is not configured and a corresponding cause.
        """
        return cls(
            response="Conversation cache not configured",
            cause="Conversation cache is not configured or unavailable.",
        )

    @classmethod
    def database_error(cls) -> "InternalServerErrorResponse":
        """
        Create an InternalServerErrorResponse representing a database query failure.

        Returns:
            InternalServerErrorResponse: Instance with response "Database query
            failed" and cause "Failed to query the database".
        """
        return cls(
            response="Database query failed",
            cause="Failed to query the database",
        )

    def __init__(self, *, response: str, cause: str) -> None:
        """
        Initialize the error response for internal server errors and set the HTTP status code.

        Parameters:
            response (str): Public-facing error message.
            cause (str): Internal explanation of the error cause.
        """
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ServiceUnavailableResponse(AbstractErrorResponse):
    """503 Backend Unavailable."""

    description: ClassVar[str] = SERVICE_UNAVAILABLE_DESCRIPTION
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "llama stack",
                    "detail": {
                        "response": "Unable to connect to Llama Stack",
                        "cause": "Connection error while trying to reach backend service.",
                    },
                }
            ]
        }
    }

    def __init__(self, *, backend_name: str, cause: str):
        """
        Construct a ServiceUnavailableResponse indicating the specified backend cannot be reached.

        Parameters:
            backend_name (str): Name of the backend service that could not be contacted.
            cause (str): Detailed explanation of why the service is unavailable.
        """
        response = f"Unable to connect to {backend_name}"
        super().__init__(
            response=response,
            cause=cause,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
