"""Unit tests for OpenAI API mapping utilities."""

from unittest.mock import patch

import pytest
from pydantic import AnyUrl

from models.requests import CreateResponseRequest, QueryRequest
from models.responses import (
    QueryResponse,
    OpenAIResponse,
    ReferencedDocument,
    ResponseContent,
    ResponseMessage,
    ResponseOutput,
    ResponseUsage,
)
from utils.openai_mapping import (
    map_openai_to_query_request,
    map_query_to_openai_response,
)


class TestMapOpenAIToQueryRequest:
    """Test cases for map_openai_to_query_request function."""

    def test_map_openai_to_query_request_minimal(self) -> None:
        """Test mapping with minimal OpenAI request."""
        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="What is Kubernetes?",
        )

        query_request = map_openai_to_query_request(openai_request)

        assert isinstance(query_request, QueryRequest)
        assert query_request.query == "What is Kubernetes?"
        assert query_request.model is None  # MVP: use default model
        assert query_request.provider is None  # MVP: use default provider
        assert query_request.system_prompt is None
        assert query_request.conversation_id is None  # MVP: new conversation each time
        assert query_request.attachments is None
        assert query_request.no_tools is False
        assert query_request.media_type is None

    def test_map_openai_to_query_request_with_instructions(self) -> None:
        """Test mapping with OpenAI instructions to system_prompt."""
        openai_request = CreateResponseRequest(
            model="gpt-3.5-turbo",
            input="Explain Docker containers",
            instructions="You are a helpful DevOps assistant",
        )

        query_request = map_openai_to_query_request(openai_request)

        assert query_request.query == "Explain Docker containers"
        assert query_request.model is None  # MVP: use default model
        assert query_request.system_prompt == "You are a helpful DevOps assistant"

    def test_map_openai_to_query_request_with_all_fields(self) -> None:
        """Test mapping with all OpenAI request fields."""
        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="What are containers?",
            instructions="You are an expert system administrator",
            temperature=0.7,
            max_output_tokens=1000,
        )

        query_request = map_openai_to_query_request(openai_request)

        assert query_request.query == "What are containers?"
        assert query_request.model is None  # MVP: use default model
        assert query_request.system_prompt == "You are an expert system administrator"
        # Note: temperature and max_output_tokens are OpenAI-specific
        # and not mapped to QueryRequest in MVP

    def test_map_openai_to_query_request_array_input_raises_error(self) -> None:
        """Test that array input raises ValueError in MVP."""
        openai_request = CreateResponseRequest(
            model="gpt-4",
            input=["What is Kubernetes?", "Explain Docker"],
        )

        with pytest.raises(ValueError, match="Array input not supported in MVP"):
            map_openai_to_query_request(openai_request)

    def test_map_openai_to_query_request_empty_instructions(self) -> None:
        """Test mapping with empty instructions."""
        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="What is Kubernetes?",
            instructions="",
        )

        query_request = map_openai_to_query_request(openai_request)

        assert query_request.system_prompt == ""


class TestMapQueryToOpenAIResponse:
    """Test cases for map_query_to_openai_response function."""

    def test_map_query_to_openai_response_minimal(self) -> None:
        """Test mapping with minimal QueryResponse."""
        query_response = QueryResponse(
            conversation_id="12345678-1234-5678-9012-123456789012",
            response="Kubernetes is an open-source container orchestration platform.",
            input_tokens=50,
            output_tokens=25,
        )

        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="What is Kubernetes?",
        )

        with (
            patch("utils.openai_mapping.uuid4") as mock_uuid4,
            patch("utils.openai_mapping.time.time") as mock_time,
        ):
            mock_uuid4.return_value.hex = "abc123def456ghi789"
            mock_time.return_value = 1640995200

            openai_response = map_query_to_openai_response(
                query_response, openai_request
            )

        assert isinstance(openai_response, OpenAIResponse)
        assert openai_response.id == "resp_abc123def456ghi789"
        assert openai_response.object == "response"
        assert openai_response.created_at == 1640995200
        assert openai_response.status == "completed"
        assert openai_response.model == "gpt-4"

        # Check output structure
        assert len(openai_response.output) == 1
        output = openai_response.output[0]
        assert isinstance(output, ResponseOutput)
        assert output.finish_reason == "stop"

        # Check message structure
        message = output.message
        assert isinstance(message, ResponseMessage)
        assert message.role == "assistant"
        assert len(message.content) == 1

        # Check content structure
        content = message.content[0]
        assert isinstance(content, ResponseContent)
        assert content.type == "text"
        assert (
            content.text
            == "Kubernetes is an open-source container orchestration platform."
        )

        # Check usage
        usage = openai_response.usage
        assert isinstance(usage, ResponseUsage)
        assert getattr(usage, "prompt_tokens") == 50
        assert getattr(usage, "completion_tokens") == 25
        assert getattr(usage, "total_tokens") == 75

        # No metadata for minimal response
        assert openai_response.metadata is None

    def test_map_query_to_openai_response_with_referenced_documents(self) -> None:
        """Test mapping with referenced documents in metadata."""
        referenced_docs = [
            ReferencedDocument(
                doc_url=AnyUrl(
                    "https://docs.openshift.com/container-platform/4.15/operators/olm/index.html"
                ),
                doc_title="Operator Lifecycle Manager (OLM)",
            ),
            ReferencedDocument(
                doc_url=AnyUrl("https://kubernetes.io/docs/concepts/"),
                doc_title="Kubernetes Concepts",
            ),
        ]

        query_response = QueryResponse(
            conversation_id="12345678-1234-5678-9012-123456789012",
            response="OpenShift operators use OLM for lifecycle management.",
            referenced_documents=referenced_docs,
            input_tokens=100,
            output_tokens=50,
        )

        openai_request = CreateResponseRequest(
            model="gpt-3.5-turbo",
            input="Tell me about OpenShift operators",
        )

        with (
            patch("utils.openai_mapping.uuid4") as mock_uuid4,
            patch("utils.openai_mapping.time.time") as mock_time,
        ):
            mock_uuid4.return_value.hex = "def456ghi789jkl012"
            mock_time.return_value = 1641081600

            openai_response = map_query_to_openai_response(
                query_response, openai_request
            )

        # Check metadata with referenced documents
        assert openai_response.metadata is not None
        assert "referenced_documents" in openai_response.metadata
        ref_docs = openai_response.metadata["referenced_documents"]
        assert len(ref_docs) == 2

        # Check first document
        first_doc = ref_docs[0]
        assert (
            first_doc["doc_url"]
            == "https://docs.openshift.com/container-platform/4.15/operators/olm/index.html"
        )
        assert first_doc["doc_title"] == "Operator Lifecycle Manager (OLM)"

        # Check second document
        second_doc = ref_docs[1]
        assert second_doc["doc_url"] == "https://kubernetes.io/docs/concepts/"
        assert second_doc["doc_title"] == "Kubernetes Concepts"

    def test_map_query_to_openai_response_with_none_doc_url(self) -> None:
        """Test mapping with referenced document that has None URL."""
        referenced_docs = [
            ReferencedDocument(
                doc_url=None,
                doc_title="Internal Documentation",
            ),
        ]

        query_response = QueryResponse(
            response="Here's some internal information.",
            referenced_documents=referenced_docs,
            input_tokens=20,
            output_tokens=10,
        )

        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="Tell me about internal docs",
        )

        openai_response = map_query_to_openai_response(query_response, openai_request)

        # Check metadata with None URL
        assert openai_response.metadata is not None
        ref_docs = openai_response.metadata["referenced_documents"]
        assert len(ref_docs) == 1
        assert ref_docs[0]["doc_url"] is None
        assert ref_docs[0]["doc_title"] == "Internal Documentation"

    def test_map_query_to_openai_response_empty_referenced_documents(self) -> None:
        """Test mapping with empty referenced documents list."""
        query_response = QueryResponse(
            response="Generic response without references.",
            referenced_documents=[],  # Empty list
            input_tokens=30,
            output_tokens=15,
        )

        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="Generic question",
        )

        openai_response = map_query_to_openai_response(query_response, openai_request)

        # Empty list should not create metadata
        assert openai_response.metadata is None

    def test_map_query_to_openai_response_id_generation(self) -> None:
        """Test that response ID is properly generated with uuid4."""
        query_response = QueryResponse(
            response="Test response.",
            input_tokens=10,
            output_tokens=5,
        )

        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="Test input",
        )

        # Test multiple calls generate different IDs
        with patch("utils.openai_mapping.uuid4") as mock_uuid4:
            mock_uuid4.side_effect = [
                type("MockUUID", (), {"hex": "first_uuid"})(),
                type("MockUUID", (), {"hex": "second_uuid"})(),
            ]

            response1 = map_query_to_openai_response(query_response, openai_request)
            response2 = map_query_to_openai_response(query_response, openai_request)

            assert response1.id == "resp_first_uuid"
            assert response2.id == "resp_second_uuid"
            assert response1.id != response2.id

    def test_map_query_to_openai_response_timestamp_generation(self) -> None:
        """Test that created_at timestamp is properly generated."""
        query_response = QueryResponse(
            response="Test response.",
            input_tokens=10,
            output_tokens=5,
        )

        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="Test input",
        )

        # Mock time to verify timestamp generation
        with patch("utils.openai_mapping.time.time") as mock_time:
            mock_time.return_value = 1234567890.5

            openai_response = map_query_to_openai_response(
                query_response, openai_request
            )

            assert openai_response.created_at == 1234567890  # Should be int

    def test_map_query_to_openai_response_token_calculation(self) -> None:
        """Test token usage calculation."""
        query_response = QueryResponse(
            response="Response with token counts.",
            input_tokens=150,
            output_tokens=75,
        )

        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="Calculate tokens",
        )

        openai_response = map_query_to_openai_response(query_response, openai_request)

        usage = openai_response.usage
        assert getattr(usage, "prompt_tokens") == 150
        assert getattr(usage, "completion_tokens") == 75
        assert getattr(usage, "total_tokens") == 225  # 150 + 75

    def test_map_query_to_openai_response_zero_tokens(self) -> None:
        """Test mapping with zero token counts."""
        query_response = QueryResponse(
            response="Response with no tokens.",
            input_tokens=0,
            output_tokens=0,
        )

        openai_request = CreateResponseRequest(
            model="gpt-4",
            input="Zero tokens",
        )

        openai_response = map_query_to_openai_response(query_response, openai_request)

        usage = openai_response.usage
        assert getattr(usage, "prompt_tokens") == 0
        assert getattr(usage, "completion_tokens") == 0
        assert getattr(usage, "total_tokens") == 0

    def test_map_query_to_openai_response_model_preservation(self) -> None:
        """Test that the model from the original request is preserved."""
        query_response = QueryResponse(
            response="Test response.",
            input_tokens=10,
            output_tokens=5,
        )

        models_to_test = ["gpt-4", "gpt-3.5-turbo", "custom-model-name"]

        for model in models_to_test:
            openai_request = CreateResponseRequest(
                model=model,
                input="Test input",
            )

            openai_response = map_query_to_openai_response(
                query_response, openai_request
            )
            assert openai_response.model == model
