# pylint: disable=unsupported-membership-test,unsubscriptable-object

"""Unit tests for all error response models."""

from pydantic_core import SchemaError
import pytest
from fastapi import status

from models.responses import (
    BAD_REQUEST_DESCRIPTION,
    FORBIDDEN_DESCRIPTION,
    INTERNAL_SERVER_ERROR_DESCRIPTION,
    NOT_FOUND_DESCRIPTION,
    PROMPT_TOO_LONG_DESCRIPTION,
    QUOTA_EXCEEDED_DESCRIPTION,
    SERVICE_UNAVAILABLE_DESCRIPTION,
    UNAUTHORIZED_DESCRIPTION,
    UNPROCESSABLE_CONTENT_DESCRIPTION,
    AbstractErrorResponse,
    BadRequestResponse,
    DetailModel,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
    PromptTooLongResponse,
    QuotaExceededResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
    UnprocessableEntityResponse,
)
from quota.quota_exceed_error import QuotaExceedError


class TestBadRequestResponse:
    """Test cases for BadRequestResponse."""

    def test_constructor(self) -> None:
        """Test BadRequestResponse with valid parameters."""
        response = BadRequestResponse(
            resource="conversation", resource_id="test-id-123"
        )
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Invalid conversation ID format"
        assert (
            response.detail.cause
            == "The conversation ID test-id-123 has invalid format."
        )

    def test_different_resource_types(self) -> None:
        """Test BadRequestResponse with different resource types."""
        response = BadRequestResponse(resource="model", resource_id="model-123")
        assert response.detail.response == "Invalid model ID format"
        assert response.detail.cause == "The model ID model-123 has invalid format."

        response = BadRequestResponse(resource="provider", resource_id="provider-456")
        assert response.detail.response == "Invalid provider ID format"
        assert (
            response.detail.cause == "The provider ID provider-456 has invalid format."
        )

    def test_openapi_response(self) -> None:
        """Test BadRequestResponse.openapi_response() method.

        Verify that BadRequestResponse.openapi_response() produces an OpenAPI
        entry with the correct description, model reference, and JSON examples,
        and that the examples list matches the model schema's examples and
        contains a `conversation_id` example whose detail.response equals
        "Invalid conversation ID format".
        """
        schema = BadRequestResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = BadRequestResponse.openapi_response()
        assert result["description"] == BAD_REQUEST_DESCRIPTION
        assert result["model"] == BadRequestResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 1

        # Verify example structure
        assert "conversation_id" in examples
        conversation_example = examples["conversation_id"]
        assert "value" in conversation_example
        assert "detail" in conversation_example["value"]
        assert conversation_example["value"]["detail"]["response"] == (
            "Invalid conversation ID format"
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test BadRequestResponse.openapi_response() with explicit examples.

        Verify BadRequestResponse.openapi_response returns only the specified
        example when explicit example labels are provided.

        Asserts that calling
        BadRequestResponse.openapi_response(examples=["conversation_id"])
        produces application/json examples containing exactly one entry with
        the key "conversation_id".
        """
        result = BadRequestResponse.openapi_response(examples=["conversation_id"])
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "conversation_id" in examples


class TestUnauthorizedResponse:
    """Test cases for UnauthorizedResponse."""

    def test_constructor(self) -> None:
        """Test UnauthorizedResponse with cause."""
        response = UnauthorizedResponse(cause="Token has expired")
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert isinstance(response.detail, DetailModel)
        assert (
            response.detail.response
            == "Missing or invalid credentials provided by client"
        )
        assert response.detail.cause == "Token has expired"

    def test_different_causes(self) -> None:
        """Test UnauthorizedResponse with different causes."""
        response = UnauthorizedResponse(cause="No Authorization header found")
        assert response.detail.cause == "No Authorization header found"

        response = UnauthorizedResponse(cause="Invalid token signature")
        assert response.detail.cause == "Invalid token signature"

        response = UnauthorizedResponse(cause="Token missing claim: user_id")
        assert response.detail.cause == "Token missing claim: user_id"

    def test_openapi_response(self) -> None:
        """Test UnauthorizedResponse.openapi_response() method."""
        schema = UnauthorizedResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = UnauthorizedResponse.openapi_response()
        assert result["description"] == UNAUTHORIZED_DESCRIPTION
        assert result["model"] == UnauthorizedResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 8

        # Verify all labeled examples are present
        assert "missing header" in examples
        assert "missing token" in examples
        assert "expired token" in examples
        assert "invalid signature" in examples
        assert "invalid key" in examples
        assert "missing claim" in examples
        assert "invalid k8s token" in examples
        assert "invalid jwk token" in examples

        # Verify example structure for one example
        missing_creds_example = examples["missing header"]
        assert "value" in missing_creds_example
        assert "detail" in missing_creds_example["value"]
        assert missing_creds_example["value"]["detail"]["response"] == (
            "Missing or invalid credentials provided by client"
        )
        assert (
            missing_creds_example["value"]["detail"]["cause"]
            == "No Authorization header found"
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test UnauthorizedResponse.openapi_response() with explicit examples."""
        result = UnauthorizedResponse.openapi_response(examples=["expired token"])
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "expired token" in examples
        assert "missing credentials" not in examples


class TestForbiddenResponse:
    """Test cases for ForbiddenResponse."""

    def test_factory_conversation(self) -> None:
        """Test ForbiddenResponse.conversation() factory method."""
        response = ForbiddenResponse.conversation("read", "conv-123", "user-456")
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert isinstance(response.detail, DetailModel)
        assert (
            response.detail.response
            == "User does not have permission to perform this action"
        )
        assert response.detail.cause == (
            "User user-456 does not have permission to read conversation "
            "with ID conv-123"
        )

    def test_factory_endpoint(self) -> None:
        """Test ForbiddenResponse.endpoint() factory method."""
        response = ForbiddenResponse.endpoint("user-789")
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert isinstance(response.detail, DetailModel)
        assert (
            response.detail.response
            == "User does not have permission to access this endpoint"
        )
        assert (
            response.detail.cause
            == "User user-789 is not authorized to access this endpoint."
        )

    def test_factory_feedback_disabled(self) -> None:
        """Test ForbiddenResponse.feedback_disabled() factory method.

        Verifies that ForbiddenResponse.feedback_disabled() produces a 403
        AbstractErrorResponse with the expected detail message and cause.
        """
        response = ForbiddenResponse.feedback_disabled()
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Storing feedback is disabled"
        assert response.detail.cause == "Storing feedback is disabled."

    def test_openapi_response(self) -> None:
        """Test ForbiddenResponse.openapi_response() method."""
        schema = ForbiddenResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ForbiddenResponse.openapi_response()
        assert result["description"] == FORBIDDEN_DESCRIPTION
        assert result["model"] == ForbiddenResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 5

        # Verify all labeled examples are present
        assert "conversation read" in examples
        assert "conversation delete" in examples
        assert "endpoint" in examples
        assert "feedback" in examples

        # Verify example structure for one example
        feedback_example = examples["feedback"]
        assert "value" in feedback_example
        assert "detail" in feedback_example["value"]
        assert (
            feedback_example["value"]["detail"]["response"]
            == "Storing feedback is disabled"
        )
        assert (
            feedback_example["value"]["detail"]["cause"]
            == "Storing feedback is disabled."
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test ForbiddenResponse.openapi_response() with explicit examples."""
        result = ForbiddenResponse.openapi_response(examples=["feedback"])
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "feedback" in examples
        assert "conversation read" not in examples


class TestUnprocessableEntityResponse:
    """Test cases for UnprocessableEntityResponse."""

    def test_constructor(self) -> None:
        """Test UnprocessableEntityResponse with valid parameters."""
        response = UnprocessableEntityResponse(
            response="Invalid attribute value",
            cause="Field 'temperature' must be a number between 0 and 2",
        )
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Invalid attribute value"
        assert (
            response.detail.cause
            == "Field 'temperature' must be a number between 0 and 2"
        )

    def test_different_responses(self) -> None:
        """Test UnprocessableEntityResponse with different response messages."""
        response = UnprocessableEntityResponse(
            response="Invalid request format",
            cause="Invalid request format. The request body could not be parsed.",
        )
        assert response.detail.response == "Invalid request format"
        assert response.detail.cause == (
            "Invalid request format. The request body could not be parsed."
        )

        response = UnprocessableEntityResponse(
            response="Missing required attributes",
            cause="Missing required attributes: ['query', 'model', 'provider']",
        )
        assert response.detail.response == "Missing required attributes"
        assert response.detail.cause == (
            "Missing required attributes: ['query', 'model', 'provider']"
        )

    def test_openapi_response(self) -> None:
        """Test UnprocessableEntityResponse.openapi_response() method."""
        schema = UnprocessableEntityResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = UnprocessableEntityResponse.openapi_response()
        assert result["description"] == UNPROCESSABLE_CONTENT_DESCRIPTION
        assert result["model"] == UnprocessableEntityResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 3

        # Verify all labeled examples are present
        assert "invalid format" in examples
        assert "missing attributes" in examples
        assert "invalid value" in examples

        # Verify example structure for one example
        invalid_format_example = examples["invalid format"]
        assert "value" in invalid_format_example
        assert "detail" in invalid_format_example["value"]
        assert (
            invalid_format_example["value"]["detail"]["response"]
            == "Invalid request format"
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test UnprocessableEntityResponse.openapi_response() with explicit examples."""
        result = UnprocessableEntityResponse.openapi_response(
            examples=["missing attributes"]
        )
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "missing attributes" in examples
        assert "invalid format" not in examples


class TestQuotaExceededResponse:
    """Test cases for QuotaExceededResponse."""

    def test_factory_model(self) -> None:
        """Test QuotaExceededResponse.model() factory method."""
        response = QuotaExceededResponse.model("gpt-4-turbo")
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "The model quota has been exceeded"
        assert (
            response.detail.cause
            == "The token quota for model gpt-4-turbo has been exceeded."
        )

    def test_factory_from_exception(self) -> None:
        """Test QuotaExceededResponse.from_exception() factory method."""
        exc = QuotaExceedError("123", "u", 0, 0)
        response = QuotaExceededResponse.from_exception(exc)
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "The quota has been exceeded"
        assert response.detail.cause == "User 123 has no available tokens"

    def test_openapi_response(self) -> None:
        """Test QuotaExceededResponse.openapi_response() method."""
        schema = QuotaExceededResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = QuotaExceededResponse.openapi_response()
        assert result["description"] == QUOTA_EXCEEDED_DESCRIPTION
        assert result["model"] == QuotaExceededResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 7

        # Verify all labeled examples are present
        assert "model" in examples
        assert "user none" in examples
        assert "cluster none" in examples
        assert "subject none" in examples
        assert "user insufficient" in examples
        assert "cluster insufficient" in examples
        assert "subject insufficient" in examples

        # Verify example structure for one example
        model_example = examples["model"]
        assert "value" in model_example
        assert "detail" in model_example["value"]
        assert model_example["value"]["detail"]["response"] == (
            "The model quota has been exceeded"
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test QuotaExceededResponse.openapi_response() with explicit examples."""
        result = QuotaExceededResponse.openapi_response(examples=["model"])
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "model" in examples
        assert "user none" not in examples


class TestNotFoundResponse:
    """Test cases for NotFoundResponse."""

    def test_constructor(self) -> None:
        """Test NotFoundResponse with valid parameters."""
        response = NotFoundResponse(resource="conversation", resource_id="conv-123")
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Conversation not found"
        assert response.detail.cause == "Conversation with ID conv-123 does not exist"

    def test_different_resources(self) -> None:
        """Test NotFoundResponse with different resource types."""
        response = NotFoundResponse(resource="provider", resource_id="openai")
        assert response.detail.response == "Provider not found"
        assert response.detail.cause == "Provider with ID openai does not exist"

        response = NotFoundResponse(resource="model", resource_id="gpt-4")
        assert response.detail.response == "Model not found"
        assert response.detail.cause == "Model with ID gpt-4 does not exist"

    def test_resource_title_capitalization(self) -> None:
        """Test NotFoundResponse properly capitalizes resource names."""
        response = NotFoundResponse(resource="conversation", resource_id="test")
        assert response.detail.response == "Conversation not found"

        response = NotFoundResponse(resource="MODEL", resource_id="test")
        assert response.detail.response == "Model not found"

    def test_openapi_response(self) -> None:
        """Test NotFoundResponse.openapi_response() method."""
        schema = NotFoundResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = NotFoundResponse.openapi_response()
        assert result["description"] == NOT_FOUND_DESCRIPTION
        assert result["model"] == NotFoundResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 5

        # Verify all labeled examples are present
        assert "conversation" in examples
        assert "provider" in examples
        assert "model" in examples
        assert "rag" in examples
        assert "streaming request" in examples

        # Verify example structure for one example
        conversation_example = examples["conversation"]
        assert "value" in conversation_example
        assert "detail" in conversation_example["value"]
        assert (
            conversation_example["value"]["detail"]["response"]
            == "Conversation not found"
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test NotFoundResponse.openapi_response() with explicit examples."""
        result = NotFoundResponse.openapi_response(examples=["provider"])
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "provider" in examples
        assert "conversation" not in examples


class TestInternalServerErrorResponse:
    """Test cases for InternalServerErrorResponse."""

    def test_factory_generic(self) -> None:
        """Test InternalServerErrorResponse.generic() factory method."""
        response = InternalServerErrorResponse.generic()
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Internal server error"
        assert (
            response.detail.cause
            == "An unexpected error occurred while processing the request."
        )

    def test_factory_configuration_not_loaded(self) -> None:
        """Test InternalServerErrorResponse.configuration_not_loaded() factory method."""
        response = InternalServerErrorResponse.configuration_not_loaded()
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Configuration is not loaded"
        assert (
            response.detail.cause
            == "Lightspeed Stack configuration has not been initialized."
        )

    def test_factory_feedback_path_invalid(self) -> None:
        """Test InternalServerErrorResponse.feedback_path_invalid() factory method."""
        response = InternalServerErrorResponse.feedback_path_invalid(
            "/path/to/feedback"
        )
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Failed to store feedback"
        assert (
            response.detail.cause
            == "Failed to store feedback at directory: /path/to/feedback"
        )

    def test_factory_query_failed(self) -> None:
        """Test InternalServerErrorResponse.query_failed() factory method."""
        custom_cause = "Failed to call backend: https://api.example.com"
        response = InternalServerErrorResponse.query_failed(custom_cause)
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Error while processing query"
        assert response.detail.cause == custom_cause

    def test_factory_cache_unavailable(self) -> None:
        """Test InternalServerErrorResponse.cache_unavailable() factory method."""
        response = InternalServerErrorResponse.cache_unavailable()
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Conversation cache not configured"
        assert (
            response.detail.cause
            == "Conversation cache is not configured or unavailable."
        )

    def test_factory_database_error(self) -> None:
        """Test InternalServerErrorResponse.database_error() factory method."""
        response = InternalServerErrorResponse.database_error()
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Database query failed"
        assert response.detail.cause == "Failed to query the database"

    def test_openapi_response(self) -> None:
        """Test InternalServerErrorResponse.openapi_response() method."""
        schema = InternalServerErrorResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = InternalServerErrorResponse.openapi_response()
        assert result["description"] == INTERNAL_SERVER_ERROR_DESCRIPTION
        assert result["model"] == InternalServerErrorResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 6

        # Verify all labeled examples are present
        assert "internal" in examples
        assert "configuration" in examples
        assert "feedback storage" in examples
        assert "query" in examples
        assert "conversation cache" in examples
        assert "database" in examples

        # Verify example structure for one example
        internal_example = examples["internal"]
        assert "value" in internal_example
        assert "detail" in internal_example["value"]
        assert (
            internal_example["value"]["detail"]["response"] == "Internal server error"
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test InternalServerErrorResponse.openapi_response() with explicit examples."""
        result = InternalServerErrorResponse.openapi_response(
            examples=["configuration"]
        )
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "configuration" in examples
        assert "internal" not in examples


class TestServiceUnavailableResponse:
    """Test cases for ServiceUnavailableResponse."""

    def test_constructor(self) -> None:
        """Test ServiceUnavailableResponse with valid parameters."""
        response = ServiceUnavailableResponse(
            backend_name="Llama Stack", cause="Connection timeout"
        )
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Unable to connect to Llama Stack"
        assert response.detail.cause == "Connection timeout"

    def test_different_backend_names(self) -> None:
        """Test ServiceUnavailableResponse with different backend names."""
        response = ServiceUnavailableResponse(
            backend_name="Kubernetes API",
            cause="Unable to initialize Kubernetes client",
        )
        assert response.detail.response == "Unable to connect to Kubernetes API"
        assert response.detail.cause == "Unable to initialize Kubernetes client"

    def test_openapi_response(self) -> None:
        """Test ServiceUnavailableResponse.openapi_response() method."""
        schema = ServiceUnavailableResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = ServiceUnavailableResponse.openapi_response()
        assert result["description"] == SERVICE_UNAVAILABLE_DESCRIPTION
        assert result["model"] == ServiceUnavailableResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 1

        # Verify example structure
        assert "llama stack" in examples
        llama_example = examples["llama stack"]
        assert "value" in llama_example
        assert "detail" in llama_example["value"]
        assert (
            llama_example["value"]["detail"]["response"]
            == "Unable to connect to Llama Stack"
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test ServiceUnavailableResponse.openapi_response() with explicit examples."""
        result = ServiceUnavailableResponse.openapi_response(examples=["llama stack"])
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "llama stack" in examples


class TestPromptTooLongResponse:
    """Test cases for PromptTooLongResponse."""

    def test_constructor_with_default_response(self) -> None:
        """Test PromptTooLongResponse with default response."""
        response = PromptTooLongResponse(
            cause="The prompt exceeds the maximum allowed length."
        )
        assert isinstance(response, AbstractErrorResponse)
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert isinstance(response.detail, DetailModel)
        assert response.detail.response == "Prompt is too long"
        assert response.detail.cause == "The prompt exceeds the maximum allowed length."

    def test_openapi_response(self) -> None:
        """Test PromptTooLongResponse.openapi_response() method."""
        schema = PromptTooLongResponse.model_json_schema()
        model_examples = schema.get("examples", [])
        expected_count = len(model_examples)

        result = PromptTooLongResponse.openapi_response()
        assert result["description"] == PROMPT_TOO_LONG_DESCRIPTION
        assert result["model"] == PromptTooLongResponse
        assert "examples" in result["content"]["application/json"]
        examples = result["content"]["application/json"]["examples"]

        # Verify example count matches schema examples count
        assert len(examples) == expected_count
        assert expected_count == 1

        # Verify example structure
        assert "prompt too long" in examples
        prompt_example = examples["prompt too long"]
        assert "value" in prompt_example
        assert "detail" in prompt_example["value"]
        assert prompt_example["value"]["detail"]["response"] == "Prompt is too long"
        assert (
            prompt_example["value"]["detail"]["cause"]
            == "The prompt exceeds the maximum allowed length."
        )

    def test_openapi_response_with_explicit_examples(self) -> None:
        """Test PromptTooLongResponse.openapi_response() with explicit examples."""
        result = PromptTooLongResponse.openapi_response(examples=["prompt too long"])
        examples = result["content"]["application/json"]["examples"]

        # Verify only 1 example is returned when explicitly specified
        assert len(examples) == 1
        assert "prompt too long" in examples


class TestAbstractErrorResponse:  # pylint: disable=too-few-public-methods
    """Test cases for AbstractErrorResponse edge cases."""

    def test_openapi_response_missing_label(self) -> None:
        """Test openapi_response() raises SchemaError when example has no label."""

        # Create a class with examples missing labels
        class InvalidErrorResponse(AbstractErrorResponse):
            """Class with invalid examples (missing label)."""

            status_code: int = 400
            detail: DetailModel = DetailModel(response="Test error", cause="Test cause")

            model_config = {
                "json_schema_extra": {
                    "examples": [
                        {
                            # Missing "label" key
                            "value": {
                                "detail": {
                                    "response": "Test error",
                                    "cause": "Test cause",
                                }
                            },
                        },
                    ]
                }
            }

        with pytest.raises(SchemaError, match="has no label"):
            InvalidErrorResponse.openapi_response()
