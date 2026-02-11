# pylint: disable=no-member
"""Unit tests for rlsapi v1 response models."""

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from models.rlsapi.responses import (
    RlsapiV1InferData,
    RlsapiV1InferResponse,
)
from models.responses import AbstractSuccessfulResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(name="sample_data")
def sample_data_fixture() -> RlsapiV1InferData:
    """Create a sample RlsapiV1InferData for testing."""
    return RlsapiV1InferData(
        text="To list files in Linux, use the `ls` command.",
        request_id="01JDKR8N7QW9ZMXVGK3PB5TQWZ",
    )


@pytest.fixture(name="sample_response")
def sample_response_fixture(sample_data: RlsapiV1InferData) -> RlsapiV1InferResponse:
    """Create a sample RlsapiV1InferResponse for testing."""
    return RlsapiV1InferResponse(data=sample_data)


# ---------------------------------------------------------------------------
# Parameterized tests for common patterns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model_class", "valid_kwargs"),
    [
        (RlsapiV1InferData, {"text": "test"}),
        (RlsapiV1InferResponse, {"data": {"text": "test"}}),
    ],
    ids=["InferData", "InferResponse"],
)
def test_extra_fields_forbidden(
    model_class: type[BaseModel], valid_kwargs: dict[str, Any]
) -> None:
    """Test that extra fields are rejected for all models with extra='forbid'."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        model_class(**valid_kwargs, extra_field="not allowed")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("model_class", "error_match"),
    [
        (RlsapiV1InferData, "Field required"),
        (RlsapiV1InferResponse, "Field required"),
    ],
    ids=["InferData", "InferResponse"],
)
def test_required_fields(model_class: type[BaseModel], error_match: str) -> None:
    """Test that required fields raise ValidationError when missing."""
    with pytest.raises(ValidationError, match=error_match):
        model_class()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RlsapiV1InferData tests
# ---------------------------------------------------------------------------


class TestRlsapiV1InferData:
    """Test cases for RlsapiV1InferData model."""

    def test_constructor_minimal(self) -> None:
        """Test RlsapiV1InferData with only required field."""
        data = RlsapiV1InferData(
            text="Response text here"
        )  # pyright: ignore[reportCallIssue]
        assert data.text == "Response text here"
        assert data.request_id is None

    def test_constructor_full(self, sample_data: RlsapiV1InferData) -> None:
        """Test RlsapiV1InferData with all fields via fixture."""
        assert sample_data.text == "To list files in Linux, use the `ls` command."
        assert sample_data.request_id == "01JDKR8N7QW9ZMXVGK3PB5TQWZ"


# ---------------------------------------------------------------------------
# RlsapiV1InferResponse tests
# ---------------------------------------------------------------------------


class TestRlsapiV1InferResponse:
    """Test cases for RlsapiV1InferResponse model."""

    def test_constructor(self, sample_response: RlsapiV1InferResponse) -> None:
        """Test RlsapiV1InferResponse with valid data via fixture."""
        assert isinstance(sample_response, AbstractSuccessfulResponse)
        assert (
            sample_response.data.text == "To list files in Linux, use the `ls` command."
        )
        assert sample_response.data.request_id == "01JDKR8N7QW9ZMXVGK3PB5TQWZ"

    def test_constructor_with_dict(self) -> None:
        """Test RlsapiV1InferResponse with dict value for data."""
        response = RlsapiV1InferResponse(
            data={  # type: ignore[arg-type]
                "text": "Response from dict",
                "request_id": "test-123",
            }
        )
        assert response.data.text == "Response from dict"
        assert response.data.request_id == "test-123"

    def test_inherits_from_abstract_successful_response(
        self, sample_response: RlsapiV1InferResponse
    ) -> None:
        """Test that RlsapiV1InferResponse inherits from AbstractSuccessfulResponse."""
        assert isinstance(sample_response, AbstractSuccessfulResponse)

    def test_openapi_response(self) -> None:
        """Test RlsapiV1InferResponse.openapi_response() method."""
        result = RlsapiV1InferResponse.openapi_response()
        assert result["description"] == "Successful response"
        assert result["model"] == RlsapiV1InferResponse
        assert "content" in result
        assert "application/json" in result["content"]
        assert "example" in result["content"]["application/json"]

        example = result["content"]["application/json"]["example"]
        assert "data" in example
        assert "text" in example["data"]
        assert "request_id" in example["data"]

    def test_json_schema_example(self) -> None:
        """Test that JSON schema has proper example."""
        schema = RlsapiV1InferResponse.model_json_schema()
        examples = schema.get("examples", [])
        assert len(examples) == 1

        example = examples[0]
        assert "data" in example
        assert (
            example["data"]["text"] == "To list files in Linux, use the `ls` command."
        )
        assert example["data"]["request_id"] == "01JDKR8N7QW9ZMXVGK3PB5TQWZ"

    def test_serialization_roundtrip(
        self, sample_response: RlsapiV1InferResponse
    ) -> None:
        """Test that model can be serialized and deserialized."""
        json_data = sample_response.model_dump_json()
        restored = RlsapiV1InferResponse.model_validate_json(json_data)

        assert restored.data.text == sample_response.data.text
        assert restored.data.request_id == sample_response.data.request_id
