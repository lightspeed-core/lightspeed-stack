"""Successful responses for vector stores and vector store files."""

from typing import Any, ClassVar, Optional

from pydantic import Field

from models.api.responses.successful.bases import (
    AbstractDeleteResponse,
    AbstractSuccessfulResponse,
)


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
