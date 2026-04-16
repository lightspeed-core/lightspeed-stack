"""Unit tests for Vector Store request models."""

import pytest
from pydantic import ValidationError

from models.requests import VectorStoreFileCreateRequest, VectorStoreUpdateRequest


class TestVectorStoreUpdateRequest:
    """Test cases for the VectorStoreUpdateRequest model."""

    def test_valid_update_with_name(self) -> None:
        """Test valid update request with name field."""
        request = VectorStoreUpdateRequest(name="updated_store")
        assert request.name == "updated_store"
        assert request.expires_at is None
        assert request.metadata is None

    def test_valid_update_with_expires_at(self) -> None:
        """Test valid update request with expires_at field."""
        request = VectorStoreUpdateRequest(expires_at=1735689600)
        assert request.name is None
        assert request.expires_at == 1735689600
        assert request.metadata is None

    def test_valid_update_with_metadata(self) -> None:
        """Test valid update request with metadata field."""
        metadata = {"user_id": "user123"}
        request = VectorStoreUpdateRequest(metadata=metadata)
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
            VectorStoreUpdateRequest()


class TestVectorStoreFileCreateRequest:
    """Test cases for the VectorStoreFileCreateRequest model."""

    def test_valid_request_basic(self) -> None:
        """Test valid request with only file_id."""
        request = VectorStoreFileCreateRequest(file_id="file-abc123")
        assert request.file_id == "file-abc123"
        assert request.attributes is None
        assert request.chunking_strategy is None

    def test_valid_attributes_basic(self) -> None:
        """Test valid request with attributes."""
        attributes = {"key1": "value1", "key2": "value2"}
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes
        )
        assert request.file_id == "file-abc123"
        assert request.attributes == attributes

    def test_attributes_max_16_pairs(self) -> None:
        """Test that attributes can have exactly 16 pairs."""
        attributes = {f"key{i}": f"value{i}" for i in range(16)}
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes
        )
        assert len(request.attributes) == 16  # type: ignore

    def test_attributes_exceeds_16_pairs(self) -> None:
        """Test that attributes with more than 16 pairs is rejected."""
        attributes = {f"key{i}": f"value{i}" for i in range(17)}
        with pytest.raises(
            ValueError, match="attributes can have at most 16 pairs, got 17"
        ):
            VectorStoreFileCreateRequest(file_id="file-abc123", attributes=attributes)

    def test_attributes_key_max_64_chars(self) -> None:
        """Test that attribute keys can be exactly 64 characters."""
        key_64_chars = "a" * 64
        attributes = {key_64_chars: "value"}
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes
        )
        assert key_64_chars in request.attributes  # type: ignore

    def test_attributes_key_exceeds_64_chars(self) -> None:
        """Test that attribute keys exceeding 64 characters are rejected."""
        key_65_chars = "a" * 65
        attributes = {key_65_chars: "value"}
        with pytest.raises(ValueError, match="exceeds 64 characters"):
            VectorStoreFileCreateRequest(file_id="file-abc123", attributes=attributes)

    def test_attributes_string_value_max_512_chars(self) -> None:
        """Test that string attribute values can be exactly 512 characters."""
        value_512_chars = "b" * 512
        attributes = {"key": value_512_chars}
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes
        )
        assert request.attributes["key"] == value_512_chars  # type: ignore

    def test_attributes_string_value_exceeds_512_chars(self) -> None:
        """Test that string attribute values exceeding 512 characters are rejected."""
        value_513_chars = "b" * 513
        attributes = {"key": value_513_chars}
        with pytest.raises(ValueError, match="exceeds 512 characters"):
            VectorStoreFileCreateRequest(file_id="file-abc123", attributes=attributes)

    def test_attributes_non_string_values_allowed(self) -> None:
        """Test that non-string attribute values (numbers, booleans) are not length-checked."""
        attributes = {
            "bool_key": True,
            "int_key": 12345,
            "float_key": 3.14159,
        }
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes
        )
        assert request.attributes == attributes

    def test_attributes_mixed_value_types(self) -> None:
        """Test that mixed value types in attributes are validated correctly."""
        attributes = {
            "string_key": "value",
            "bool_key": False,
            "number_key": 42,
        }
        request = VectorStoreFileCreateRequest(
            file_id="file-abc123", attributes=attributes
        )
        assert request.attributes == attributes

    def test_attributes_none_is_valid(self) -> None:
        """Test that None attributes is valid (optional field)."""
        request = VectorStoreFileCreateRequest(file_id="file-abc123", attributes=None)
        assert request.attributes is None

    def test_file_id_required(self) -> None:
        """Test that file_id is required."""
        with pytest.raises(ValidationError):
            VectorStoreFileCreateRequest()  # type: ignore

    def test_file_id_cannot_be_empty(self) -> None:
        """Test that file_id cannot be an empty string."""
        with pytest.raises(ValidationError, match="at least 1 character"):
            VectorStoreFileCreateRequest(file_id="")
