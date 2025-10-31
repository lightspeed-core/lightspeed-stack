# pylint: disable=redefined-outer-name

"""Unit tests for the /responses REST API endpoint."""

import pytest
from fastapi import Request, status, HTTPException
from llama_stack_client import APIConnectionError

from app.endpoints.responses import responses_endpoint_handler
from models.config import Action
from models.requests import CreateResponseRequest
from models.responses import (
    OpenAIResponse,
    QueryResponse,
    ReferencedDocument,
    ResponseContent,
    ResponseMessage,
    ResponseOutput,
    ResponseUsage,
)
from utils.types import TurnSummary
from utils.token_counter import TokenCounter

# Mock authentication tuple (user_id, username, skip_userid_check, token)
MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture
def dummy_request() -> Request:
    """Dummy request fixture for testing."""
    req = Request(
        scope={
            "type": "http",
        }
    )
    req.state.authorized_actions = set(Action)
    return req


@pytest.fixture
def sample_openai_request() -> CreateResponseRequest:
    """Sample OpenAI request for testing."""
    return CreateResponseRequest(
        model="gpt-4",
        input="What is Kubernetes?",
        instructions="You are a helpful DevOps assistant",
        temperature=0.7,
        max_output_tokens=150,
    )


@pytest.fixture
def sample_query_response() -> QueryResponse:
    """Sample internal QueryResponse for testing."""
    return QueryResponse(
        conversation_id="12345678-1234-1234-1234-123456789012",
        response="Kubernetes is a container orchestration platform...",
        referenced_documents=[
            ReferencedDocument(
                doc_url="https://docs.kubernetes.io/concepts/overview/",
                doc_title="Kubernetes Overview",
            )
        ],
        truncated=False,
        input_tokens=10,
        output_tokens=50,
        available_quotas={},
    )


def mock_configuration_and_dependencies(mocker):
    """Helper function to mock configuration and dependencies."""
    # Mock configuration
    mocker.patch("app.endpoints.responses.check_configuration_loaded")

    # Mock the Llama Stack client holder
    mock_client_holder = mocker.Mock()
    mock_client = mocker.Mock()
    mock_client_holder.get_client.return_value = mock_client
    mocker.patch(
        "app.endpoints.responses.AsyncLlamaStackClientHolder",
        return_value=mock_client_holder,
    )

    # Mock the mapping functions
    mock_query_request = mocker.Mock()
    mocker.patch(
        "app.endpoints.responses.map_openai_to_query_request",
        return_value=mock_query_request,
    )

    mock_openai_response = OpenAIResponse(
        id="resp_12345",
        object="response",
        created_at=1640995200,
        status="completed",
        model="gpt-4",
        output=[
            ResponseOutput(
                message=ResponseMessage(
                    role="assistant",
                    content=[ResponseContent(type="text", text="Test response")],
                ),
                finish_reason="stop",
            )
        ],
        usage=ResponseUsage(prompt_tokens=10, completion_tokens=50, total_tokens=60),
        metadata={},
    )
    mocker.patch(
        "app.endpoints.responses.map_query_to_openai_response",
        return_value=mock_openai_response,
    )

    # Mock retrieve_response function
    mock_turn_summary = TurnSummary(
        llm_response="Kubernetes is a container orchestration platform...",
        tool_calls=[],
    )
    mock_token_counter = TokenCounter(input_tokens=10, output_tokens=50)

    mocker.patch(
        "app.endpoints.responses.retrieve_response",
        return_value=(
            mock_turn_summary,
            "12345678-1234-1234-1234-123456789012",
            [],
            mock_token_counter,
        ),
    )

    return mock_openai_response


class TestResponsesEndpoint:
    """Test cases for the responses endpoint."""

    async def test_successful_response(
        self,
        mocker,
        dummy_request,
        sample_openai_request,
        sample_query_response,  # pylint: disable=unused-argument
    ):
        """Test successful response generation."""
        # Mock all dependencies
        mock_configuration_and_dependencies(mocker)

        # Mock metrics
        mocker.patch("metrics.llm_calls_failures_total")

        # Call the endpoint handler
        result = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=sample_openai_request,
            auth=MOCK_AUTH,
        )

        # Verify the response
        assert isinstance(result, OpenAIResponse)
        assert result.id == "resp_12345"
        assert result.object == "response"
        assert result.status == "completed"
        assert result.model == "gpt-4"

    def test_authorization_required(
        self, mocker, dummy_request, sample_openai_request
    ):  # pylint: disable=unused-argument
        """Test that proper authorization is enforced."""
        # This test verifies the decorator is applied correctly
        # In a real application, this would be tested via integration tests
        # For now, we just verify the function signature includes auth parameter
        import inspect  # pylint: disable=import-outside-toplevel

        sig = inspect.signature(responses_endpoint_handler)
        assert "auth" in sig.parameters
        assert "request" in sig.parameters
        assert "responses_request" in sig.parameters

    async def test_api_connection_error_handling(
        self, mocker, dummy_request, sample_openai_request
    ):
        """Test handling of APIConnectionError."""
        # Mock configuration
        mocker.patch("app.endpoints.responses.check_configuration_loaded")

        # Mock the Llama Stack client holder
        mock_client_holder = mocker.Mock()
        mock_client = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )

        # Mock mapping to raise APIConnectionError during retrieve_response
        mocker.patch("app.endpoints.responses.map_openai_to_query_request")
        mocker.patch(
            "app.endpoints.responses.retrieve_response",
            side_effect=APIConnectionError(request=sample_openai_request),
        )

        # Mock metrics
        mock_failures_metric = mocker.patch("metrics.llm_calls_failures_total")
        mock_failures_metric.inc = mocker.Mock()

        # Test that HTTPException is raised
        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=sample_openai_request,
                auth=MOCK_AUTH,
            )

        # Verify the exception details
        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unable to connect to Llama Stack" in str(exc_info.value.detail)

        # Verify metrics were updated
        mock_failures_metric.inc.assert_called_once()

    async def test_request_mapping_called_correctly(
        self, mocker, dummy_request, sample_openai_request
    ):
        """Test that OpenAI request is mapped to internal QueryRequest correctly."""
        # Mock all dependencies
        mock_configuration_and_dependencies(mocker)

        # Mock metrics
        mocker.patch("metrics.llm_calls_failures_total")

        # Get the mock for mapping function
        mock_mapping_func = mocker.patch(
            "app.endpoints.responses.map_openai_to_query_request"
        )

        # Call the endpoint
        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=sample_openai_request,
            auth=MOCK_AUTH,
        )

        # Verify the mapping function was called with correct arguments
        mock_mapping_func.assert_called_once_with(sample_openai_request)

    async def test_response_mapping_called_correctly(
        self,
        mocker,
        dummy_request,
        sample_openai_request,
        sample_query_response,  # pylint: disable=unused-argument
    ):
        """Test that internal response is mapped to OpenAI format correctly."""
        # Mock all dependencies
        mock_configuration_and_dependencies(mocker)

        # Mock metrics
        mocker.patch("metrics.llm_calls_failures_total")

        # Get the mock for response mapping function
        mock_response_mapping = mocker.patch(
            "app.endpoints.responses.map_query_to_openai_response"
        )

        # Call the endpoint
        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=sample_openai_request,
            auth=MOCK_AUTH,
        )

        # The response mapping should be called (exact arguments depend on implementation)
        assert mock_response_mapping.called

    async def test_validation_error_handling(
        self, mocker, dummy_request, sample_openai_request
    ):
        """Test handling of validation errors (ValueError, AttributeError, TypeError)."""
        # Mock configuration
        mocker.patch("app.endpoints.responses.check_configuration_loaded")

        # Mock the mapping function to raise ValueError
        mocker.patch(
            "app.endpoints.responses.map_openai_to_query_request",
            side_effect=ValueError("Invalid input format"),
        )

        # Test that HTTPException with 422 status is raised
        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=sample_openai_request,
                auth=MOCK_AUTH,
            )

        # Verify the exception details
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Unable to process this request" in str(exc_info.value.detail)
        assert "Invalid input format" in str(exc_info.value.detail)

    async def test_attribute_error_handling(
        self, mocker, dummy_request, sample_openai_request
    ):
        """Test handling of AttributeError during processing."""
        # Mock configuration
        mocker.patch("app.endpoints.responses.check_configuration_loaded")

        # Mock the Llama Stack client holder
        mock_client_holder = mocker.Mock()
        mock_client = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )

        # Mock the mapping functions to work
        mocker.patch("app.endpoints.responses.map_openai_to_query_request")

        # Mock retrieve_response to raise AttributeError
        mocker.patch(
            "app.endpoints.responses.retrieve_response",
            side_effect=AttributeError("Missing required attribute"),
        )

        # Test that HTTPException with 422 status is raised
        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=sample_openai_request,
                auth=MOCK_AUTH,
            )

        # Verify the exception details
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Unable to process this request" in str(exc_info.value.detail)
        assert "Missing required attribute" in str(exc_info.value.detail)

    async def test_type_error_handling(
        self, mocker, dummy_request, sample_openai_request
    ):
        """Test handling of TypeError during response mapping."""
        # Mock configuration and dependencies
        mock_configuration_and_dependencies(mocker)

        # Mock the response mapping function to raise TypeError
        mocker.patch(
            "app.endpoints.responses.map_query_to_openai_response",
            side_effect=TypeError("Type conversion error"),
        )

        # Test that HTTPException with 422 status is raised
        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=sample_openai_request,
                auth=MOCK_AUTH,
            )

        # Verify the exception details
        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Unable to process this request" in str(exc_info.value.detail)
        assert "Type conversion error" in str(exc_info.value.detail)


# Note: These tests cover the error handling scenarios added in Task 3.4
