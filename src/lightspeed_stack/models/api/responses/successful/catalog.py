"""Successful response bodies for catalog-style endpoints."""

from typing import Any, Optional

from pydantic import Field

from models.api.responses.successful.bases import AbstractSuccessfulResponse


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
