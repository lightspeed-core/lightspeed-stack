# pylint: disable=too-many-lines

"""Models for REST API responses."""

from typing import Any, ClassVar, Literal, Optional, cast

from llama_stack_api.openai_responses import (
    OpenAIResponseError as Error,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoice as ToolChoice,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutput as Output,
)
from llama_stack_api.openai_responses import (
    OpenAIResponsePrompt as Prompt,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseReasoning as Reasoning,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseText as Text,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseTool as OutputTool,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseUsage as Usage,
)
from pydantic import BaseModel, Field, computed_field
from pydantic_core import SchemaError

from constants import MEDIA_TYPE_EVENT_STREAM
from log import get_logger
from models.api.responses.constants import SUCCESSFUL_RESPONSE_DESCRIPTION
from models.config import Configuration
from utils.types import RAGChunk, ReferencedDocument, ToolCallSummary, ToolResultSummary

logger = get_logger(__name__)


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


class AbstractDeleteResponse(BaseModel):
    """Base model for successful delete responses."""

    deleted: bool = Field(
        ...,
        description="Whether the deletion was successful.",
        examples=[True, False],
    )
    resource_name: ClassVar[str]

    @computed_field
    def response(self) -> str:
        """Human-readable outcome of the delete operation."""
        return (
            f"{self.resource_name} deleted successfully"
            if self.deleted
            else f"{self.resource_name} not found"
        )

    @computed_field(json_schema_extra={"deprecated": True})
    def success(self) -> bool:
        """Successful response flag."""
        logger.warning("DEPRECATED: Will be removed in a future release.")
        return True

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """Build FastAPI/OpenAPI metadata with named application/json examples.

        Returns:
            A response dict with description, model, and content keys.

        Raises:
            SchemaError: If the model JSON schema has no examples list.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples")
        if not model_examples:
            raise SchemaError(f"Examples not found in {cls.__name__}")

        examples: dict[str, dict[str, Any]] = {}
        for index, example in enumerate(model_examples):
            if "label" not in example:
                raise SchemaError(
                    f"Example at index {index} in {cls.__name__} has no label"
                )
            if "value" not in example:
                raise SchemaError(
                    f"Example at index {index} in {cls.__name__} has no value"
                )
            examples[example["label"]] = {"value": example["value"]}

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "model": cls,
            "content": {"application/json": {"examples": examples}},
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


class MCPServerInfo(BaseModel):
    """Information about a registered MCP server.

    Attributes:
        name: Unique name of the MCP server.
        url: URL of the MCP server endpoint.
        provider_id: MCP provider identification.
        source: Whether the server was registered statically (config) or dynamically (api).
    """

    name: str = Field(..., description="MCP server name")
    url: str = Field(..., description="MCP server URL")
    provider_id: str = Field(..., description="MCP provider identification")
    source: str = Field(
        ...,
        description="How the server was registered: 'config' (static) or 'api' (dynamic)",
        examples=["config", "api"],
    )


class MCPServerRegistrationResponse(AbstractSuccessfulResponse):
    """Response for a successful MCP server registration."""

    name: str = Field(..., description="Registered MCP server name")
    url: str = Field(..., description="Registered MCP server URL")
    provider_id: str = Field(..., description="MCP provider identification")
    message: str = Field(..., description="Status message")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "mcp-integration-tools",
                    "url": "http://host.docker.internal:7008/api/mcp-actions/v1",
                    "provider_id": "model-context-protocol",
                    "message": "MCP server 'mcp-integration-tools' registered successfully",
                }
            ]
        }
    }


class MCPServerListResponse(AbstractSuccessfulResponse):
    """Response listing all registered MCP servers."""

    servers: list[MCPServerInfo] = Field(
        default_factory=list,
        description="List of all registered MCP servers (static and dynamic)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "servers": [
                        {
                            "name": "mcp-integration-tools",
                            "url": "http://host.docker.internal:7008/api/mcp-actions/v1",
                            "provider_id": "model-context-protocol",
                            "source": "config",
                        },
                        {
                            "name": "test-mcp-server",
                            "url": "http://host.docker.internal:8888/mcp",
                            "provider_id": "model-context-protocol",
                            "source": "api",
                        },
                    ]
                }
            ]
        }
    }


class MCPServerDeleteResponse(AbstractSuccessfulResponse):
    """Response for a successful MCP server deletion."""

    name: str = Field(..., description="Deleted MCP server name")
    message: str = Field(..., description="Status message")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "test-mcp-server",
                    "message": "MCP server 'test-mcp-server' unregistered successfully",
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
    config: dict[str, Any] = Field(
        ...,
        description="Provider configuration parameters",
    )
    health: dict[str, Any] = Field(
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
                    '"conversation_id": "123e4567-e89b-12d3-a456-426614174000", '
                    '"request_id": "123e4567-e89b-12d3-a456-426614174001"}}\n\n'
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


class StreamingInterruptResponse(AbstractSuccessfulResponse):
    """Model representing a response to a streaming interrupt request.

    Attributes:
        request_id: The streaming request ID targeted by the interrupt call.
        interrupted: Whether an in-progress stream was interrupted.
        message: Human-readable interruption status message.

    Example:
        ```python
        response = StreamingInterruptResponse(
            request_id="123e4567-e89b-12d3-a456-426614174000",
            interrupted=True,
            message="Streaming request interrupted",
        )
        ```
    """

    request_id: str = Field(
        description="The streaming request ID targeted by the interrupt call",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )

    interrupted: bool = Field(
        description="Whether an in-progress stream was interrupted",
        examples=[True],
    )

    message: str = Field(
        description="Human-readable interruption status message",
        examples=["Streaming request interrupted"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "request_id": "123e4567-e89b-12d3-a456-426614174000",
                    "interrupted": True,
                    "message": "Streaming request interrupted",
                }
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
        referenced_documents: Optional list of documents referenced in an assistant response.
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
    referenced_documents: Optional[list[ReferencedDocument]] = Field(
        None,
        description="List of documents referenced in the response (assistant messages only)",
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


class ConversationDeleteResponse(AbstractDeleteResponse):
    """Response for deleting a conversation."""

    resource_name: ClassVar[str] = "Conversation"
    conversation_id: str = Field(
        ...,
        description="Conversation identifier that was passed to delete.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )

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


class ResponsesResponse(AbstractSuccessfulResponse):
    """Model representing a response from the Responses API following LCORE specification.

    Attributes:
        created_at: Unix timestamp when the response was created.
        completed_at: Unix timestamp when the response was completed, if applicable.
        error: Error details if the response failed or was blocked.
        id: Unique identifier for this response.
        model: Model identifier in "provider/model" format used for generation.
        object: Object type identifier, always "response".
        output: List of structured output items containing messages, tool calls, and
            other content. This is the primary response content.
        parallel_tool_calls: Whether the model can make multiple tool calls in parallel.
        previous_response_id: Identifier of the previous response in a multi-turn
            conversation.
        prompt: The input prompt object that was sent to the model.
        status: Current status of the response (e.g., "completed", "blocked",
            "in_progress").
        temperature: Temperature parameter used for generation (controls randomness).
        text: Text response configuration object used for OpenAI responses.
        top_p: Top-p sampling parameter used for generation.
        tools: List of tools available to the model during generation.
        tool_choice: Tool selection strategy used (e.g., "auto", "required", "none").
        truncation: Strategy used for handling content that exceeds context limits.
        usage: Token usage statistics including input_tokens, output_tokens, and
            total_tokens.
        instructions: System instructions or guidelines provided to the model.
        max_tool_calls: Maximum number of tool calls allowed in a single response.
        reasoning: Reasoning configuration (effort level) used for the response.
        max_output_tokens: Upper bound for tokens generated in the response.
        safety_identifier: Safety/guardrail identifier applied to the request.
        metadata: Additional metadata dictionary with custom key-value pairs.
        store: Whether the response was stored.
        conversation: Conversation ID linking this response to a conversation thread
            (LCORE-specific).
        available_quotas: Remaining token quotas for the user (LCORE-specific).
        output_text: Aggregated text output from all output_text items in the
            output array.
    """

    created_at: int
    completed_at: Optional[int] = None
    error: Optional[Error] = None
    id: str
    model: str
    object: Literal["response"] = "response"
    output: list[Output]
    parallel_tool_calls: bool = True
    previous_response_id: Optional[str] = None
    prompt: Optional[Prompt] = None
    status: str
    temperature: Optional[float] = None
    text: Optional[Text] = None
    top_p: Optional[float] = None
    tools: Optional[list[OutputTool]] = None
    tool_choice: Optional[ToolChoice] = None
    truncation: Optional[str] = None
    usage: Optional[Usage] = None
    instructions: Optional[str] = None
    max_tool_calls: Optional[int] = None
    reasoning: Optional[Reasoning] = None
    max_output_tokens: Optional[int] = None
    safety_identifier: Optional[str] = None
    metadata: Optional[dict[str, str]] = None
    store: Optional[bool] = None
    # LCORE-specific attributes
    conversation: Optional[str] = None
    available_quotas: dict[str, int]
    output_text: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "created_at": 1704067200,
                    "completed_at": 1704067250,
                    "id": "resp_abc123",
                    "model": "openai/gpt-4-turbo",
                    "object": "response",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": (
                                        "Kubernetes is an open-source container "
                                        "orchestration system..."
                                    ),
                                }
                            ],
                        }
                    ],
                    "parallel_tool_calls": True,
                    "status": "completed",
                    "temperature": 0.7,
                    "text": {"format": {"type": "text"}},
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "total_tokens": 150,
                        "input_tokens_details": {"cached_tokens": 0},
                        "output_tokens_details": {"reasoning_tokens": 0},
                    },
                    "instructions": "You are a helpful assistant",
                    "store": True,
                    "conversation": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
                    "available_quotas": {"daily": 1000, "monthly": 50000},
                    "output_text": (
                        "Kubernetes is an open-source container "
                        "orchestration system..."
                    ),
                }
            ],
            "sse_example": (
                "event: response.created\n"
                'data: {"type":"response.created","sequence_number":0,'
                '"response":{"id":"resp_abc","object":"response",'
                '"created_at":1704067200,"status":"in_progress","model":"openai/gpt-4o-mini",'
                '"output":[],"store":true,"text":{"format":{"type":"text"}},'
                '"conversation":"0d21ba731f21f798dc9680125d5d6f49",'
                '"available_quotas":{},"output_text":""}}\n\n'
                "event: response.output_item.added\n"
                'data: {"type":"response.output_item.added","sequence_number":1,'
                '"response_id":"resp_abc","output_index":0,'
                '"item":{"id":"msg_abc","type":"message","status":"in_progress",'
                '"role":"assistant","content":[]}}\n\n'
                "...\n\n"
                "event: response.completed\n"
                'data: {"type":"response.completed","sequence_number":30,'
                '"response":{"id":"resp_abc","object":"response",'
                '"created_at":1704067200,"status":"completed","model":"openai/gpt-4o-mini",'
                '"output":[{"id":"msg_abc","type":"message","status":"completed",'
                '"role":"assistant","content":[{"type":"output_text",'
                '"text":"Hello! How can I help?","annotations":[]}]}],'
                '"store":true,"text":{"format":{"type":"text"}},'
                '"usage":{"input_tokens":10,"output_tokens":6,"total_tokens":16,'
                '"input_tokens_details":{"cached_tokens":0},'
                '"output_tokens_details":{"reasoning_tokens":0}},'
                '"conversation":"0d21ba731f21f798dc9680125d5d6f49",'
                '"available_quotas":{"daily":1000,"monthly":50000},'
                '"output_text":"Hello! How can I help?"}}\n\n'
                "data: [DONE]\n\n"
            ),
        }
    }

    @classmethod
    def openapi_response(cls) -> dict[str, Any]:
        """
        Build OpenAPI response dict with application/json and text/event-stream.

        Uses the single JSON example from the model schema and adds
        text/event-stream example from json_schema_extra.sse_example.
        """
        schema = cls.model_json_schema()
        model_examples = schema.get("examples", [])
        json_example = model_examples[0] if model_examples else None

        schema_extra = (
            cast(dict[str, Any], dict(cls.model_config)).get("json_schema_extra") or {}
        )
        sse_example = schema_extra.get("sse_example", "")

        content: dict[str, Any] = {
            "application/json": {"example": json_example} if json_example else {},
            "text/event-stream": {
                "schema": {"type": "string"},
                "example": sse_example,
            },
        }

        return {
            "description": SUCCESSFUL_RESPONSE_DESCRIPTION,
            "model": cls,
            "content": content,
        }


class VectorStoreResponse(AbstractSuccessfulResponse):
    """Response model containing a single vector store.

    Attributes:
        id: Vector store ID.
        name: Vector store name.
        created_at: Unix timestamp when created.
        last_active_at: Unix timestamp of last activity.
        expires_at: Optional Unix timestamp when it expires.
        status: Vector store status.
        usage_bytes: Storage usage in bytes.
        metadata: Optional metadata dictionary for storing session information.
    """

    id: str = Field(..., description="Vector store ID")
    name: str = Field(..., description="Vector store name")
    created_at: int = Field(..., description="Unix timestamp when created")
    last_active_at: Optional[int] = Field(
        None, description="Unix timestamp of last activity"
    )
    expires_at: Optional[int] = Field(
        None, description="Unix timestamp when it expires"
    )
    status: str = Field(..., description="Vector store status")
    usage_bytes: int = Field(default=0, description="Storage usage in bytes")
    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Metadata dictionary for storing session information",
        examples=[
            {"conversation_id": "conv_123", "document_ids": ["doc_456", "doc_789"]}
        ],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "id": "vs_abc123",
                    "name": "customer_support_docs",
                    "created_at": 1704067200,
                    "last_active_at": 1704153600,
                    "expires_at": None,
                    "status": "active",
                    "usage_bytes": 1048576,
                    "metadata": {
                        "conversation_id": "conv_123",
                        "document_ids": ["doc_456", "doc_789"],
                    },
                }
            ]
        },
    }


class VectorStoresListResponse(AbstractSuccessfulResponse):
    """Response model containing a list of vector stores.

    Attributes:
        data: List of vector store objects.
        object: Object type (always "list").
    """

    data: list[VectorStoreResponse] = Field(
        default_factory=list, description="List of vector stores"
    )
    object: str = Field(default="list", description="Object type")

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {
                            "id": "vs_abc123",
                            "name": "customer_support_docs",
                            "created_at": 1704067200,
                            "last_active_at": 1704153600,
                            "expires_at": None,
                            "status": "active",
                            "usage_bytes": 1048576,
                            "metadata": {"conversation_id": "conv_123"},
                        },
                        {
                            "id": "vs_def456",
                            "name": "product_documentation",
                            "created_at": 1704070800,
                            "last_active_at": 1704157200,
                            "expires_at": None,
                            "status": "active",
                            "usage_bytes": 2097152,
                            "metadata": None,
                        },
                    ],
                    "object": "list",
                }
            ]
        },
    }


class VectorStoreDeleteResponse(AbstractDeleteResponse):
    """Result of deleting a vector store (always HTTP 200)."""

    resource_name: ClassVar[str] = "Vector store"
    vector_store_id: str = Field(
        ...,
        description="Vector store identifier that was passed to delete.",
        examples=["vs_abc123"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "deleted",
                    "value": {
                        "vector_store_id": "vs_abc123",
                        "deleted": True,
                        "response": "Vector store deleted successfully",
                    },
                },
                {
                    "label": "not found",
                    "value": {
                        "vector_store_id": "vs_abc123",
                        "deleted": False,
                        "response": "Vector store not found",
                    },
                },
            ]
        }
    }


class VectorStoreFileDeleteResponse(AbstractDeleteResponse):
    """Result of deleting a file from a vector store (always HTTP 200)."""

    resource_name: ClassVar[str] = "Vector store file"
    file_id: str = Field(
        ...,
        description="File identifier that was passed to delete.",
        examples=["file_abc123"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "deleted",
                    "value": {
                        "file_id": "file_abc123",
                        "deleted": True,
                        "response": "Vector store file deleted successfully",
                    },
                },
                {
                    "label": "not found",
                    "value": {
                        "file_id": "file_abc123",
                        "deleted": False,
                        "response": "Vector store file not found",
                    },
                },
            ]
        }
    }


class PromptResourceResponse(AbstractSuccessfulResponse):
    """A stored prompt template as returned by Llama Stack."""

    prompt_id: str = Field(..., description="Prompt identifier from Llama Stack")
    version: int = Field(..., description="Version number for this prompt")
    is_default: Optional[bool] = Field(
        None, description="Whether this version is the default"
    )
    prompt: Optional[str] = Field(None, description="Prompt text with placeholders")
    variables: Optional[list[str]] = Field(
        None, description="Variable names used in the template"
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                    "version": 1,
                    "is_default": True,
                    "prompt": "Summarize: {{text}}",
                    "variables": ["text"],
                }
            ]
        },
    }


class PromptsListResponse(AbstractSuccessfulResponse):
    """List of stored prompt templates returned by Llama Stack."""

    data: list[PromptResourceResponse] = Field(
        default_factory=list,
        description="Prompt entries (as returned by Llama Stack list)",
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {
                            "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                            "version": 1,
                            "is_default": True,
                            "prompt": "Summarize: {{text}}",
                            "variables": ["text"],
                        }
                    ],
                }
            ]
        },
    }


class PromptDeleteResponse(AbstractDeleteResponse):
    """Result of deleting a stored prompt (always HTTP 200, like conversations v2)."""

    resource_name: ClassVar[str] = "Prompt"
    prompt_id: str = Field(
        ...,
        description="Prompt identifier that was passed to delete.",
        examples=["pmpt_0123456789abcdef0123456789abcdef01234567"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "label": "deleted",
                    "value": {
                        "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                        "deleted": True,
                        "response": "Prompt deleted successfully",
                    },
                },
                {
                    "label": "not found",
                    "value": {
                        "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                        "deleted": False,
                        "response": "Prompt not found",
                    },
                },
            ]
        }
    }


class FileResponse(AbstractSuccessfulResponse):
    """Response model containing a file object.

    Attributes:
        id: File ID.
        filename: File name.
        bytes: File size in bytes.
        created_at: Unix timestamp when created.
        purpose: File purpose.
        object: Object type (always "file").
    """

    id: str = Field(..., description="File ID")
    filename: str = Field(..., description="File name")
    bytes: int = Field(..., description="File size in bytes")
    created_at: int = Field(..., description="Unix timestamp when created")
    purpose: str = Field(default="assistants", description="File purpose")
    object: str = Field(default="file", description="Object type")

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "id": "file_abc123",
                    "filename": "documentation.pdf",
                    "bytes": 524288,
                    "created_at": 1704067200,
                    "purpose": "assistants",
                    "object": "file",
                }
            ]
        },
    }


class VectorStoreFileResponse(AbstractSuccessfulResponse):
    """Response model containing a vector store file object.

    Attributes:
        id: Vector store file ID.
        vector_store_id: ID of the vector store.
        status: File processing status.
        attributes: Optional metadata key-value pairs.
        last_error: Optional error message if processing failed.
        object: Object type (always "vector_store.file").
    """

    id: str = Field(..., description="Vector store file ID")
    vector_store_id: str = Field(..., description="ID of the vector store")
    status: str = Field(..., description="File processing status")
    attributes: Optional[dict[str, str | float | bool]] = Field(
        None,
        description=(
            "Set of up to 16 key-value pairs for storing additional information. "
            "Keys: strings (max 64 chars). Values: strings (max 512 chars), booleans, or numbers."
        ),
    )
    last_error: Optional[str] = Field(
        None, description="Error message if processing failed"
    )
    object: str = Field(default="vector_store.file", description="Object type")

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "id": "file_abc123",
                    "vector_store_id": "vs_abc123",
                    "status": "completed",
                    "attributes": {"chunk_size": "512", "indexed": True},
                    "last_error": None,
                    "object": "vector_store.file",
                }
            ]
        },
    }


class VectorStoreFilesListResponse(AbstractSuccessfulResponse):
    """Response model containing a list of vector store files.

    Attributes:
        data: List of vector store file objects.
        object: Object type (always "list").
    """

    data: list[VectorStoreFileResponse] = Field(
        default_factory=list, description="List of vector store files"
    )
    object: str = Field(default="list", description="Object type")

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "data": [
                        {
                            "id": "file_abc123",
                            "vector_store_id": "vs_abc123",
                            "status": "completed",
                            "attributes": {"chunk_size": "512"},
                            "last_error": None,
                            "object": "vector_store.file",
                        },
                        {
                            "id": "file_def456",
                            "vector_store_id": "vs_abc123",
                            "status": "processing",
                            "attributes": None,
                            "last_error": None,
                            "object": "vector_store.file",
                        },
                    ],
                    "object": "list",
                }
            ]
        },
    }
