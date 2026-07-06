"""Unit tests for Vector Store request models."""

import pytest
from pydantic import ValidationError

from models.api.requests import (
    VectorStoreCreateRequest,
    VectorStoreFileCreateRequest,
    VectorStoreUpdateRequest,
)


class TestVectorStoreCreateRequest:
    """Test cases for the VectorStoreCreateRequest model."""

    def test_valid_create_with_name_only(self) -> None:
        """Test valid create request with only required name field."""
        request = VectorStoreCreateRequest(name="test_store")
        assert request.name == "test_store"
        assert request.embedding_model is None
        assert request.embedding_dimension is None
        assert request.provider_id is None

    def test_valid_create_with_all_fields(self) -> None:
        """Test valid create request with all optional fields."""
        request = VectorStoreCreateRequest(
            name="test_store",
            embedding_model="text-embedding-ada-002",
            embedding_dimension=1536,
            provider_id="rhdh-docs",
            metadata={"user_id": "user123"},
        )
        assert request.name == "test_store"
        assert request.embedding_model == "text-embedding-ada-002"
        assert request.embedding_dimension == 1536
        assert request.provider_id == "rhdh-docs"
        assert request.metadata == {"user_id": "user123"}

    def test_name_required(self) -> None:
        """Test that name field is required."""
        with pytest.raises(ValidationError):
            VectorStoreCreateRequest()  # pyright: ignore[reportCallIssue]

    def test_name_cannot_be_empty(self) -> None:
        """Test that name cannot be an empty string."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            VectorStoreCreateRequest(name="")

    def test_name_max_length_256(self) -> None:
        """Test that name cannot exceed 256 characters."""
        with pytest.raises(ValidationError, match="at most 256 characters"):
            VectorStoreCreateRequest(name="a" * 257)

    def test_name_at_max_length(self) -> None:
        """Test that name at exactly 256 characters is accepted."""
        request = VectorStoreCreateRequest(name="a" * 256)
        assert len(request.name) == 256

    def test_embedding_dimension_must_be_positive(self) -> None:
        """Test that embedding_dimension must be greater than 0."""
        with pytest.raises(ValidationError, match="greater than 0"):
            VectorStoreCreateRequest(name="test_store", embedding_dimension=0)

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            VectorStoreCreateRequest(
                name="test_store",
                unknown_field="value",  # pyright: ignore[reportCallIssue]
            )


class TestVectorStoreUpdateRequest:
    """Test cases for the VectorStoreUpdateRequest model."""

    def test_valid_update_with_name(self) -> None:
        """Test valid update request with name field."""
        request = VectorStoreUpdateRequest(
            name="updated_store"
        )  # pyright: ignore[reportCallIssue]
        assert request.name == "updated_store"
        assert request.expires_at is None
        assert request.metadata is None

    def test_valid_update_with_expires_at(self) -> None:
        """Test valid update request with expires_at field."""
        request = VectorStoreUpdateRequest(
            expires_at=1735689600
        )  # pyright: ignore[reportCallIssue]
        assert request.name is None
        assert request.expires_at == 1735689600
        assert request.metadata is None

    def test_valid_update_with_metadata(self) -> None:
        """Test valid update request with metadata field."""
        metadata = {"user_id": "user123"}
        request = VectorStoreUpdateRequest(
            metadata=metadata
        )  # pyright: ignore[reportCallIssue]
        assert request.name is None
        assert request.expires_at is None
        assert request.metadata == metadata

    def test_valid_update_with_multiple_fields(self) -> None:
        """Test valid update request with multiple fields."""
        request = VectorStoreUpdateRequest(
            name="updated_store",
            expires_at=1735689600,
            metadata={"user_id": "user123"},
        )
        assert request.name == "updated_store"
        assert request.expires_at == 1735689600
        assert request.metadata == {"user_id": "user123"}

    def test_empty_update_rejected(self) -> None:
        """Test that empty update request is rejected."""
        with pytest.raises(
            ValueError,
            match="At least one field must be provided: name, expires_at, or metadata",
        ):
            VectorStoreUpdateRequest()  # pyright: ignore[reportCallIssue]


class TestVectorStoreFileCreateRequest:
    """Test cases for the VectorStoreFileCreateRequest model."""

    def test_valid_request_basic(self) -> None:
        """Test valid request with only file_id."""
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=None, chunking_strategy=None
        )
        assert request.file_id == "file-abc123"
        assert request.attributes is None
        assert request.chunking_strategy is None

    def test_valid_attributes_basic(self) -> None:
        """Test valid request with attributes."""
        attributes: dict[str, str | float | bool] = {"key1": "value1", "key2": "value2"}
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes, chunking_strategy=None
        )
        assert request.file_id == "file-abc123"
        assert request.attributes == attributes

    def test_attributes_max_16_pairs(self) -> None:
        """Test that attributes can have exactly 16 pairs."""
        attributes: dict[str, str | float | bool] = {
            f"key{i}": f"value{i}" for i in range(16)
        }
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes, chunking_strategy=None
        )
        assert len(request.attributes) == 16  # pyright: ignore[reportArgumentType]

    def test_attributes_exceeds_16_pairs(self) -> None:
        """Test that attributes with more than 16 pairs is rejected."""
        attributes: dict[str, str | float | bool] = {
            f"key{i}": f"value{i}" for i in range(17)
        }
        with pytest.raises(
            ValueError, match="attributes can have at most 16 pairs, got 17"
        ):
            VectorStoreFileCreateRequest(
                file_id="file-abc123", attributes=attributes, chunking_strategy=None
            )

    def test_attributes_key_max_64_chars(self) -> None:
        """Test that attribute keys can be exactly 64 characters."""
        key_64_chars = "a" * 64
        attributes: dict[str, str | float | bool] = {key_64_chars: "value"}
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes, chunking_strategy=None
        )
        assert (
            key_64_chars in request.attributes
        )  # pyright: ignore[reportOperatorIssue]

    def test_attributes_key_exceeds_64_chars(self) -> None:
        """Test that attribute keys exceeding 64 characters are rejected."""
        key_65_chars = "a" * 65
        attributes: dict[str, str | float | bool] = {key_65_chars: "value"}
        with pytest.raises(ValueError, match="exceeds 64 characters"):
            VectorStoreFileCreateRequest(
                file_id="file-abc123", attributes=attributes, chunking_strategy=None
            )

    def test_attributes_string_value_max_512_chars(self) -> None:
        """Test that string attribute values can be exactly 512 characters."""
        value_512_chars = "b" * 512
        attributes: dict[str, str | float | bool] = {"key": value_512_chars}
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes, chunking_strategy=None
        )
        assert isinstance(request.attributes, dict)
        assert "key" in request.attributes
        assert request.attributes["key"] == value_512_chars

    def test_attributes_string_value_exceeds_512_chars(self) -> None:
        """Test that string attribute values exceeding 512 characters are rejected."""
        value_513_chars = "b" * 513
        attributes: dict[str, str | float | bool] = {"key": value_513_chars}
        with pytest.raises(ValueError, match="exceeds 512 characters"):
            VectorStoreFileCreateRequest(
                file_id="file-abc123", attributes=attributes, chunking_strategy=None
            )

    def test_attributes_non_string_values_allowed(self) -> None:
        """Test that non-string attribute values (numbers, booleans) are not length-checked."""
        attributes: dict[str, str | float | bool] = {
            "bool_key": True,
            "int_key": 12345,
            "float_key": 3.14159,
        }
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes, chunking_strategy=None
        )
        assert request.attributes == attributes

    def test_attributes_mixed_value_types(self) -> None:
        """Test that mixed value types in attributes are validated correctly."""
        attributes: dict[str, str | float | bool] = {
            "string_key": "value",
            "bool_key": False,
            "number_key": 42,
        }
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes, chunking_strategy=None
        )
        assert request.attributes == attributes

    def test_attributes_none_is_valid(self) -> None:
        """Test that None attributes is valid (optional field)."""
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=None, chunking_strategy=None
        )
        assert request.attributes is None

    def test_file_id_required(self) -> None:
        """Test that file_id is required."""
        with pytest.raises(ValidationError):
            VectorStoreFileCreateRequest()  # pyright: ignore[reportCallIssue]

    def test_file_id_cannot_be_empty(self) -> None:
        """Test that file_id cannot be an empty string."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            VectorStoreFileCreateRequest(
                file_id="", attributes=None, chunking_strategy=None
            )
