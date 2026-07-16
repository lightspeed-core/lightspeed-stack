"""Request models for vector store and file endpoints."""

from typing import Any, Optional, Self

from pydantic import BaseModel, Field, field_validator, model_validator


class VectorStoreCreateRequest(BaseModel):
    """Model representing a request to create a vector store.

    Attributes:
        name: Name of the vector store.
        embedding_model: Optional embedding model to use.
        embedding_dimension: Optional embedding dimension.
        chunking_strategy: Optional chunking strategy configuration.
        provider_id: Optional vector store provider identifier.
        metadata: Optional metadata dictionary for storing session information.
    """

    name: str = Field(
        ...,
        description="Name of the vector store",
        examples=["my_vector_store"],
        min_length=1,
        max_length=256,
    )

    embedding_model: Optional[str] = Field(
        None,
        description="Embedding model to use for the vector store",
        examples=["text-embedding-ada-002"],
    )

    embedding_dimension: Optional[int] = Field(
        None,
        description="Dimension of the embedding vectors",
        examples=[1536],
        gt=0,
    )

    chunking_strategy: Optional[dict[str, Any]] = Field(
        None,
        description="Chunking strategy configuration",
        examples=[{"type": "fixed", "chunk_size": 512, "chunk_overlap": 50}],
    )

    provider_id: Optional[str] = Field(
        None,
        description="Vector store provider identifier",
        examples=["rhdh-docs"],
    )

    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Metadata dictionary for storing session information",
        examples=[{"user_id": "user123", "session_id": "sess456"}],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "my_vector_store",
                    "embedding_model": "text-embedding-ada-002",
                    "embedding_dimension": 1536,
                    "provider_id": "rhdh-docs",
                    "metadata": {"user_id": "user123"},
                },
            ]
        },
    }


class VectorStoreUpdateRequest(BaseModel):
    """Model representing a request to update a vector store.

    Attributes:
        name: New name for the vector store.
        expires_at: Optional expiration timestamp.
        metadata: Optional metadata dictionary for storing session information.
    """

    name: Optional[str] = Field(
        None,
        description="New name for the vector store",
        examples=["updated_vector_store"],
        min_length=1,
        max_length=256,
    )

    expires_at: Optional[int] = Field(
        None,
        description="Unix timestamp when the vector store should expire",
        examples=[1735689600],
        gt=0,
    )

    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Metadata dictionary for storing session information",
        examples=[{"user_id": "user123", "session_id": "sess456"}],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "name": "updated_vector_store",
                    "expires_at": 1735689600,
                    "metadata": {"user_id": "user123"},
                },
            ]
        },
    }

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> Self:
        """Ensure at least one field is provided for update.

        Raises:
            ValueError: If all fields are None (empty update).

        Returns:
            Self: The validated model instance.
        """
        if self.name is None and self.expires_at is None and self.metadata is None:
            raise ValueError(
                "At least one field must be provided: name, expires_at, or metadata"
            )
        return self


class VectorStoreFileCreateRequest(BaseModel):
    """Model representing a request to add a file to a vector store.

    Attributes:
        file_id: ID of the file to add to the vector store.
        attributes: Optional metadata key-value pairs (max 16 pairs).
        chunking_strategy: Optional chunking strategy configuration.
    """

    file_id: str = Field(
        ...,
        description="ID of the file to add to the vector store",
        examples=["file-abc123"],
        min_length=1,
    )

    attributes: Optional[dict[str, str | float | bool]] = Field(
        None,
        description=(
            "Set of up to 16 key-value pairs for storing additional information. "
            "Keys: strings (max 64 chars). Values: strings (max 512 chars), booleans, or numbers."
        ),
        examples=[
            {"created_at": "2026-04-04T15:20:00Z", "updated_at": "2026-04-04T15:20:00Z"}
        ],
    )

    chunking_strategy: Optional[dict[str, Any]] = Field(
        None,
        description="Chunking strategy configuration for this file",
        examples=[{"type": "fixed", "chunk_size": 512, "chunk_overlap": 50}],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "file_id": "file-abc123",
                    "attributes": {"created_at": "2026-04-04T15:20:00Z"},
                    "chunking_strategy": {"type": "fixed", "chunk_size": 512},
                },
            ]
        },
    }

    @field_validator("attributes")
    @classmethod
    def validate_attributes(
        cls, value: Optional[dict[str, str | float | bool]]
    ) -> Optional[dict[str, str | float | bool]]:
        """Validate attributes field constraints.

        Ensures:
        - Maximum 16 key-value pairs
        - Keys are max 64 characters
        - String values are max 512 characters

        Parameters:
            value: The attributes dictionary to validate.

        Raises:
            ValueError: If constraints are violated.

        Returns:
            The validated attributes dictionary.
        """
        if value is None:
            return value

        if len(value) > 16:
            raise ValueError(f"attributes can have at most 16 pairs, got {len(value)}")

        for key, val in value.items():
            if len(key) > 64:
                raise ValueError(f"attribute key '{key}' exceeds 64 characters")

            if isinstance(val, str) and len(val) > 512:
                raise ValueError(f"attribute value for '{key}' exceeds 512 characters")

        return value
