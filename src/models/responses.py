# pylint: disable=too-many-lines

"""Models for REST API responses."""

from typing import Any, Optional, Union

from pydantic import AnyUrl, BaseModel, Field

from llama_stack_client.types import ProviderInfo


class ModelsResponse(BaseModel):
    """Model representing a response to models request."""

    models: list[dict[str, Any]] = Field(
        ...,
        description="List of models available",
        examples=[
            {
                "identifier": "openai/gpt-4-turbo",
                "metadata": {},
                "api_model_type": "llm",
                "provider_id": "openai",
                "type": "model",
                "provider_resource_id": "gpt-4-turbo",
                "model_type": "llm",
            },
            {
                "identifier": "openai/gpt-3.5-turbo-0125",
                "metadata": {},
                "api_model_type": "llm",
                "provider_id": "openai",
                "type": "model",
                "provider_resource_id": "gpt-3.5-turbo-0125",
                "model_type": "llm",
            },
        ],
    )


class ToolsResponse(BaseModel):
    """Model representing a response to tools request."""

    tools: list[dict[str, Any]] = Field(
        description=(
            "List of tools available from all configured MCP servers and built-in toolgroups"
        ),
        examples=[
            [
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
            ]
        ],
    )


class ShieldsResponse(BaseModel):
    """Model representing a response to shields request."""

    shields: list[dict[str, Any]] = Field(
        ...,
        description="List of shields available",
        examples=[
            {
                "identifier": "lightspeed_question_validity-shield",
                "provider_resource_id": "lightspeed_question_validity-shield",
                "provider_id": "lightspeed_question_validity",
                "type": "shield",
                "params": {},
            }
        ],
    )


class ProvidersListResponse(BaseModel):
    """Model representing a response to providers request."""

    providers: dict[str, list[dict[str, Any]]] = Field(
        ...,
        description="List of available API types and their corresponding providers",
        examples=[
            {
                "inference": [
                    {
                        "provider_id": "sentence-transformers",
                        "provider_type": "inline::sentence-transformers",
                    },
                    {"provider_id": "openai", "provider_type": "remote::openai"},
                ],
                "agents": [
                    {
                        "provider_id": "meta-reference",
                        "provider_type": "inline::meta-reference",
                    },
                ],
                "datasetio": [
                    {
                        "provider_id": "huggingface",
                        "provider_type": "remote::huggingface",
                    },
                    {"provider_id": "localfs", "provider_type": "inline::localfs"},
                ],
            },
        ],
    )


class ProviderResponse(ProviderInfo):
    """Model representing a response to get specific provider request."""

    api: str = Field(
        ...,
        description="The API this provider implements",
        example="inference",
    )  # type: ignore
    config: dict[str, Union[bool, float, str, list[Any], object, None]] = Field(
        ...,
        description="Provider configuration parameters",
        example={"api_key": "********"},
    )  # type: ignore
    health: dict[str, Union[bool, float, str, list[Any], object, None]] = Field(
        ...,
        description="Current health status of the provider",
        example={"status": "OK", "message": "Healthy"},
    )  # type: ignore
    provider_id: str = Field(
        ..., description="Unique provider identifier", example="openai"
    )  # type: ignore
    provider_type: str = Field(
        ..., description="Provider implementation type", example="remote::openai"
    )  # type: ignore


class RAGChunk(BaseModel):
    """Model representing a RAG chunk used in the response."""

    content: str = Field(description="The content of the chunk")
    source: Optional[str] = Field(None, description="Source document or URL")
    score: Optional[float] = Field(None, description="Relevance score")


class ToolCall(BaseModel):
    """Model representing a tool call made during response generation."""

    tool_name: str = Field(description="Name of the tool called")
    arguments: dict[str, Any] = Field(description="Arguments passed to the tool")
    result: Optional[dict[str, Any]] = Field(None, description="Result from the tool")

class ConversationData(BaseModel):
    """Model representing conversation data returned by cache list operations.

    Attributes:
        conversation_id: The conversation ID
        topic_summary: The topic summary for the conversation (can be None)
        last_message_timestamp: The timestamp of the last message in the conversation
    """

    conversation_id: str
    topic_summary: str | None
    last_message_timestamp: float

class ReferencedDocument(BaseModel):
    """Model representing a document referenced in generating a response.

    Attributes:
        doc_url: Url to the referenced doc.
        doc_title: Title of the referenced doc.
    """

    doc_url: Optional[AnyUrl] = Field(
        None, description="URL of the referenced document"
    )

    doc_title: str | None = Field(
        None, description="Title of the referenced document"
    )


class QueryResponse(BaseModel):
    """Model representing LLM response to a query.

    Attributes:
        conversation_id: The optional conversation ID (UUID).
        response: The response.
        rag_chunks: List of RAG chunks used to generate the response.
        referenced_documents: The URLs and titles for the documents used to generate the response.
        tool_calls: List of tool calls made during response generation.
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
        [],
        description="List of RAG chunks used to generate the response",
    )

    tool_calls: Optional[list[ToolCall]] = Field(
        None,
        description="List of tool calls made during response generation",
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
        description="Whether conversation history was truncated",
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

    # provides examples for /docs endpoint
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "response": "Operator Lifecycle Manager (OLM) helps users install...",
                    "rag_chunks": [
                        {
                            "content": "OLM is a component of the Operator Framework toolkit...",
                            "source": "kubernetes-docs/operators.md",
                            "score": 0.95,
                        }
                    ],
                    "tool_calls": [
                        {
                            "tool_name": "knowledge_search",
                            "arguments": {"query": "operator lifecycle manager"},
                            "result": {"chunks_found": 5},
                        }
                    ],
                    "referenced_documents": [
                        {
                            "doc_url": "https://docs.openshift.com/"
                            "container-platform/4.15/operators/olm/index.html",
                            "doc_title": "Operator Lifecycle Manager (OLM)",
                        }
                    ],
                    "truncated": False,
                    "input_tokens": 150,
                    "output_tokens": 75,
                    "available_quotas": {"daily": 1000, "monthly": 50000},
                }
            ]
        }
    }


class InfoResponse(BaseModel):
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


class LivenessResponse(BaseModel):
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


class NotAvailableResponse(BaseModel):
    """Model representing error response for readiness endpoint."""

    detail: dict[str, str] = Field(
        ...,
        description="Detailed information about readiness state",
        examples=[
            {
                "response": "Service is not ready",
                "cause": "Index is not ready",
            },
            {
                "response": "Service is not ready",
                "cause": "LLM is not ready",
            },
        ],
    )

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


class AuthorizedResponse(BaseModel):
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

    conversation_id: str = Field(
        ...,
        description="Conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    chat_history: list[dict[str, Any]] = Field(
        ...,
        description="The simplified chat history as a list of conversation turns",
        examples=[
            {
                "messages": [
                    {"content": "Hello", "type": "user"},
                    {"content": "Hi there!", "type": "assistant"},
                ],
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
        last_used_model: The last model used for the conversation.
        last_used_provider: The provider of the last used model.
        topic_summary: The topic summary for the conversation.

    Example:
        ```python
        conversation = ConversationDetails(
            conversation_id="123e4567-e89b-12d3-a456-426614174000"
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
                    last_used_model="gemini/gemini-2.0-flash",
                    last_used_provider="gemini",
                    topic_summary="Openshift Microservices Deployment Strategies",
                ),
                ConversationDetails(
                    conversation_id="456e7890-e12b-34d5-a678-901234567890"
                    created_at="2024-01-01T01:00:00Z",
                    message_count=2,
                    last_used_model="gemini/gemini-2.0-flash",
                    last_used_provider="gemini",
                    topic_summary="RHDH Purpose Summary",
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


class ConversationsListResponseV2(BaseModel):
    """Model representing a response for listing conversations of a user.

    Attributes:
        conversations: List of conversation data associated with the user.
    """

    conversations: list[ConversationData]


class ErrorResponse(BaseModel):
    """Model representing error response for query endpoint."""

    detail: dict[str, str] = Field(
        description="Error details",
        examples=[
            {
                "response": "Error while validation question",
                "cause": "Failed to handle request to https://bam-api.res.ibm.com/v2/text",
            },
            {
                "response": "Error retrieving conversation history",
                "cause": "Invalid conversation ID 1237-e89b-12d3-a456-426614174000",
            },
        ],
    )

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


class FeedbackStatusUpdateResponse(BaseModel):
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


class ConversationUpdateResponse(BaseModel):
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


class DetailModel(BaseModel):
    """Nested detail model for error responses."""

    response: str = Field(..., description="Short summary of the error")
    cause: str = Field(..., description="Detailed explanation of what caused the error")


class AbstractErrorResponse(BaseModel):
    """Base class for all error responses.

    Contains a nested `detail` field.
    """

    detail: DetailModel

    def dump_detail(self) -> dict:
        """Return dict in FastAPI HTTPException format."""
        return self.detail.model_dump()


class BadRequestResponse(AbstractErrorResponse):
    """400 Bad Request - Invalid resource identifier."""

    def __init__(self, resource: str, resource_id: str):
        """Initialize a BadRequestResponse for invalid resource identifiers."""
        super().__init__(
            detail=DetailModel(
                response="Invalid conversation ID format",
                cause=f"{resource.title()} ID {resource_id} has invalid format",
            )
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Invalid conversation ID format",
                        "cause": "Conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format",  # pylint: disable=line-too-long
                    }
                }
            ]
        }
    }


class AccessDeniedResponse(AbstractErrorResponse):
    """403 Access Denied - User does not have permission to perform the action."""

    def __init__(self, user_id: str, resource: str, resource_id: str, action: str):
        """Initialize an AccessDeniedResponse when user lacks permission for an action."""
        super().__init__(
            detail=DetailModel(
                response="Access denied",
                cause=f"User {user_id} does not have permission to {action} {resource} with ID {resource_id}.",  # pylint: disable=line-too-long
            )
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Access denied",
                        "cause": "User 6789 does not have permission to access conversation with ID 123e4567-e89b-12d3-a456-426614174000.",  # pylint: disable=line-too-long
                    }
                }
            ]
        }
    }


class NotFoundResponse(AbstractErrorResponse):
    """404 Not Found - Resource does not exist."""

    def __init__(self, resource: str, resource_id: str):
        """Initialize a NotFoundResponse when a resource cannot be located."""
        super().__init__(
            detail=DetailModel(
                response=f"{resource.title()} not found",
                cause=f"{resource.title()} with ID {resource_id} does not exist.",
            )
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Conversation not found",
                        "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist.",  # pylint: disable=line-too-long
                    }
                }
            ]
        }
    }


class ServiceUnavailableResponse(AbstractErrorResponse):
    """503 Backend Unavailable - Unable to reach backend service."""

    def __init__(self, backend_name: str, cause: str):
        """Initialize a ServiceUnavailableResponse when a backend service is unreachable."""
        super().__init__(
            detail=DetailModel(
                response=f"Unable to connect to {backend_name}", cause=cause
            )
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Unable to connect to Llama Stack",
                        "cause": "Connection error while trying to reach Llama Stack API.",
                    }
                }
            ]
        }
    }


class UnauthorizedResponse(AbstractErrorResponse):
    """401 Unauthorized - Missing or invalid credentials."""

    def __init__(self, user_id: str | None = None):
        """Initialize an UnauthorizedResponse when authentication fails."""
        cause_msg = (
            f"User {user_id} is unauthorized"
            if user_id
            else "Missing or invalid credentials provided by client"
        )
        super().__init__(detail=DetailModel(response="Unauthorized", cause=cause_msg))

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Unauthorized",
                        "cause": "Missing or invalid credentials provided by client",
                    }
                }
            ]
        }
    }


class ForbiddenResponse(UnauthorizedResponse):
    """403 Forbidden - User does not have access to this resource."""

    def __init__(self, user_id: str, resource: str, resource_id: str):
        """Initialize a ForbiddenResponse when user is authenticated but lacks resource access."""
        super().__init__(user_id=user_id)
        self.detail = DetailModel(
            response="Access denied",
            cause=f"User {user_id} is not allowed to access {resource} with ID {resource_id}.",
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": {
                        "response": "Access denied",
                        "cause": "User 42 is not allowed to access conversation with ID 123e4567-e89b-12d3-a456-426614174000.",  # pylint: disable=line-too-long
                    }
                }
            ]
        }
    }
