"""Unit tests for OpenAI request models."""

import pytest
from pydantic import ValidationError

from models.requests import CreateResponseRequest


class TestCreateResponseRequest:
    """Test cases for CreateResponseRequest model."""

    def test_create_response_request_minimal_valid_request(self) -> None:
        """Test CreateResponseRequest with minimal required fields."""
        request = CreateResponseRequest(model="gpt-4", input="What is Kubernetes?")

        assert request.model == "gpt-4"
        assert request.input == "What is Kubernetes?"
        assert request.instructions is None
        assert request.temperature is None
        assert request.max_output_tokens is None

    def test_create_response_request_with_all_fields(self) -> None:
        """Test CreateResponseRequest with all fields populated."""
        request = CreateResponseRequest(
            model="gpt-4",
            input="Explain Docker containers",
            instructions="You are a helpful DevOps assistant",
            temperature=0.7,
            max_output_tokens=1000,
        )

        assert request.model == "gpt-4"
        assert request.input == "Explain Docker containers"
        assert request.instructions == "You are a helpful DevOps assistant"
        assert request.temperature == 0.7
        assert request.max_output_tokens == 1000

    def test_create_response_request_missing_model_field(self) -> None:
        """Test CreateResponseRequest fails when model field is missing."""
        with pytest.raises(ValidationError, match="model"):
            CreateResponseRequest(input="What is Kubernetes?")

    def test_create_response_request_missing_input_field(self) -> None:
        """Test CreateResponseRequest fails when input field is missing."""
        with pytest.raises(ValidationError, match="input"):
            CreateResponseRequest(model="gpt-4")

    def test_create_response_request_empty_model(self) -> None:
        """Test CreateResponseRequest fails with empty model string."""
        with pytest.raises(ValidationError):
            CreateResponseRequest(model="", input="What is Kubernetes?")

    def test_create_response_request_empty_input(self) -> None:
        """Test CreateResponseRequest fails with empty input string."""
        with pytest.raises(ValidationError):
            CreateResponseRequest(model="gpt-4", input="")

    def test_create_response_request_temperature_validation_low(self) -> None:
        """Test CreateResponseRequest temperature validation for values below 0."""
        with pytest.raises(ValidationError, match="temperature"):
            CreateResponseRequest(
                model="gpt-4", input="What is Kubernetes?", temperature=-0.1
            )

    def test_create_response_request_temperature_validation_high(self) -> None:
        """Test CreateResponseRequest temperature validation for values above 2."""
        with pytest.raises(ValidationError, match="temperature"):
            CreateResponseRequest(
                model="gpt-4", input="What is Kubernetes?", temperature=2.1
            )

    def test_create_response_request_temperature_validation_valid_range(self) -> None:
        """Test CreateResponseRequest temperature validation for valid range."""
        # Test boundary values
        request_zero = CreateResponseRequest(
            model="gpt-4", input="What is Kubernetes?", temperature=0.0
        )
        assert request_zero.temperature == 0.0

        request_two = CreateResponseRequest(
            model="gpt-4", input="What is Kubernetes?", temperature=2.0
        )
        assert request_two.temperature == 2.0

        request_mid = CreateResponseRequest(
            model="gpt-4", input="What is Kubernetes?", temperature=1.0
        )
        assert request_mid.temperature == 1.0

    def test_create_response_request_max_output_tokens_validation(self) -> None:
        """Test CreateResponseRequest max_output_tokens validation."""
        # Test valid positive value
        request = CreateResponseRequest(
            model="gpt-4", input="What is Kubernetes?", max_output_tokens=1000
        )
        assert request.max_output_tokens == 1000

        # Test invalid negative value
        with pytest.raises(ValidationError, match="max_output_tokens"):
            CreateResponseRequest(
                model="gpt-4", input="What is Kubernetes?", max_output_tokens=-1
            )

        # Test invalid zero value
        with pytest.raises(ValidationError, match="max_output_tokens"):
            CreateResponseRequest(
                model="gpt-4", input="What is Kubernetes?", max_output_tokens=0
            )

    def test_create_response_request_extra_fields_forbidden(self) -> None:
        """Test CreateResponseRequest rejects extra fields."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            CreateResponseRequest(
                model="gpt-4",
                input="What is Kubernetes?",
                unknown_field="should_fail",  # type: ignore[call-arg]
            )

    def test_create_response_request_input_array_type(self) -> None:
        """Test CreateResponseRequest with input as array (list)."""
        request = CreateResponseRequest(
            model="gpt-4", input=["What is Kubernetes?", "Explain Docker"]
        )

        assert request.model == "gpt-4"
        assert request.input == ["What is Kubernetes?", "Explain Docker"]

    def test_create_response_request_input_array_empty(self) -> None:
        """Test CreateResponseRequest fails with empty array input."""
        with pytest.raises(ValidationError):
            CreateResponseRequest(model="gpt-4", input=[])

    def test_create_response_request_model_config_examples(self) -> None:
        """Test that CreateResponseRequest has proper model_config with examples."""
        # This test verifies the model is configured correctly for OpenAPI docs
        assert hasattr(CreateResponseRequest, "model_config")
        config = CreateResponseRequest.model_config
        assert "json_schema_extra" in config
        assert "examples" in config["json_schema_extra"]
        assert len(config["json_schema_extra"]["examples"]) > 0
