# pylint: disable=redefined-outer-name,import-error, too-many-function-args
"""Unit tests for the /streaming_query (v2) endpoint using Responses API."""

# pylint: disable=too-many-lines,too-many-function-args
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api.openai_responses import (
    OpenAIResponseObject,
    OpenAIResponseObjectStream,
    OpenAIResponseObjectStreamResponseCompleted as CompletedChunk,
    OpenAIResponseObjectStreamResponseFailed as FailedChunk,
    OpenAIResponseObjectStreamResponseIncomplete as IncompleteChunk,
    OpenAIResponseObjectStreamResponseMcpCallArgumentsDone as MCPArgsDoneChunk,
    OpenAIResponseObjectStreamResponseOutputItemAdded as OutputItemAddedChunk,
    OpenAIResponseObjectStreamResponseOutputItemDone as OutputItemDoneChunk,
    OpenAIResponseObjectStreamResponseOutputTextDelta as TextDeltaChunk,
    OpenAIResponseObjectStreamResponseOutputTextDone as TextDoneChunk,
    OpenAIResponseOutputMessageMCPCall as MCPCall,
)
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient
from pydantic import AnyUrl
from pytest_mock import MockerFixture

from app.endpoints.streaming_query import (
    generate_response,
    retrieve_response_generator,
    response_generator,
    shield_violation_generator,
    stream_end_event,
    stream_event,
    stream_http_error_event,
    stream_start_event,
    streaming_query_endpoint_handler,
)
from configuration import AppConfig
from constants import (
    LLM_TOKEN_EVENT,
    LLM_TOOL_CALL_EVENT,
    LLM_TOOL_RESULT_EVENT,
    MEDIA_TYPE_JSON,
    MEDIA_TYPE_TEXT,
)
from models.config import Action
from models.context import ResponseGeneratorContext
from models.requests import Attachment, QueryRequest
from models.responses import InternalServerErrorResponse
from utils.token_counter import TokenCounter
from utils.types import ReferencedDocument, ResponsesApiParams, TurnSummary

MOCK_AUTH_STREAMING = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture(autouse=True, name="setup_configuration")
def setup_configuration_fixture() -> AppConfig:
    """Set up configuration for tests."""
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "transcripts_enabled": False,
        },
        "mcp_servers": [],
        "conversation_cache": {
            "type": "noop",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    return cfg


# ============================================================================
# OLS Compatibility Tests
# ============================================================================


class TestOLSStreamEventFormatting:
    """Test the stream_event function for both media types (OLS compatibility)."""

    def test_stream_event_json_token(self) -> None:
        """Test token event formatting for JSON media type."""
        data = {"id": 0, "token": "Hello"}
        result = stream_event(data, LLM_TOKEN_EVENT, MEDIA_TYPE_JSON)

        expected = 'data: {"event": "token", "data": {"id": 0, "token": "Hello"}}\n\n'
        assert result == expected

    def test_stream_event_text_token(self) -> None:
        """Test token event formatting for text media type."""
        data = {"id": 0, "token": "Hello"}
        result = stream_event(data, LLM_TOKEN_EVENT, MEDIA_TYPE_TEXT)

        assert result == "Hello"

    def test_stream_event_json_tool_call(self) -> None:
        """Test tool call event formatting for JSON media type."""
        data = {
            "id": 0,
            "token": {"tool_name": "search", "arguments": {"query": "test"}},
        }
        result = stream_event(data, LLM_TOOL_CALL_EVENT, MEDIA_TYPE_JSON)

        expected = (
            'data: {"event": "tool_call", "data": {"id": 0, "token": '
            '{"tool_name": "search", "arguments": {"query": "test"}}}}\n\n'
        )
        assert result == expected

    def test_stream_event_text_tool_call(self) -> None:
        """Test tool call event formatting for text media type."""
        data = {
            "id": 0,
            "function_name": "search",
            "arguments": {"query": "test"},
        }
        result = stream_event(data, LLM_TOOL_CALL_EVENT, MEDIA_TYPE_TEXT)

        expected = "[Tool Call: search]\n"
        assert result == expected

    def test_stream_event_json_tool_result(self) -> None:
        """Test tool result event formatting for JSON media type."""
        data = {
            "id": 0,
            "token": {"tool_name": "search", "response": "Found results"},
        }
        result = stream_event(data, LLM_TOOL_RESULT_EVENT, MEDIA_TYPE_JSON)

        expected = (
            'data: {"event": "tool_result", "data": {"id": 0, "token": '
            '{"tool_name": "search", "response": "Found results"}}}\n\n'
        )
        assert result == expected

    def test_stream_event_text_tool_result(self) -> None:
        """Test tool result event formatting for text media type."""
        data = {
            "id": 0,
            "tool_name": "search",
            "response": "Found results",
        }
        result = stream_event(data, LLM_TOOL_RESULT_EVENT, MEDIA_TYPE_TEXT)

        expected = "[Tool Result]\n"
        assert result == expected

    def test_stream_event_unknown_type(self) -> None:
        """Test handling of unknown event types."""
        data = {"id": 0, "token": "test"}
        result = stream_event(data, "unknown_event", MEDIA_TYPE_TEXT)

        assert result == ""


class TestOLSStreamEndEvent:
    """Test the stream_end_event function for both media types (OLS compatibility)."""

    def test_stream_end_event_json(self) -> None:
        """Test end event formatting for JSON media type."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents = [
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc1"), doc_title="Test Doc 1"
            ),
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc2"), doc_title="Test Doc 2"
            ),
        ]
        result = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_JSON,
        )

        data_part = result.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "end"
        assert "referenced_documents" in parsed["data"]
        assert len(parsed["data"]["referenced_documents"]) == 2
        assert parsed["data"]["referenced_documents"][0]["doc_title"] == "Test Doc 1"
        assert (
            parsed["data"]["referenced_documents"][0]["doc_url"]
            == "https://example.com/doc1"
        )
        assert "available_quotas" in parsed

    def test_stream_end_event_text(self) -> None:
        """Test end event formatting for text media type."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents = [
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc1"), doc_title="Test Doc 1"
            ),
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc2"), doc_title="Test Doc 2"
            ),
        ]
        result = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_TEXT,
        )

        expected = (
            "\n\n---\n\nTest Doc 1: https://example.com/doc1\n"
            "Test Doc 2: https://example.com/doc2"
        )
        assert result == expected

    def test_stream_end_event_text_no_docs(self) -> None:
        """Test end event formatting for text media type with no documents."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents: list[ReferencedDocument] = []
        result = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_TEXT,
        )

        assert result == ""


class TestOLSCompatibilityIntegration:
    """Integration tests for OLS compatibility."""

    def test_media_type_validation(self) -> None:
        """Test that media type validation works correctly."""
        valid_request = QueryRequest(
            query="test", media_type="application/json"
        )  # pyright: ignore[reportCallIssue]
        assert valid_request.media_type == "application/json"

        valid_request = QueryRequest(
            query="test", media_type="text/plain"
        )  # pyright: ignore[reportCallIssue]
        assert valid_request.media_type == "text/plain"

        with pytest.raises(ValueError, match="media_type must be either"):
            QueryRequest(
                query="test", media_type="invalid/type"
            )  # pyright: ignore[reportCallIssue]

    def test_ols_end_event_structure(self) -> None:
        """Test that end event follows OLS structure."""
        token_usage = TokenCounter(input_tokens=100, output_tokens=50)
        available_quotas: dict[str, int] = {}
        referenced_documents = [
            ReferencedDocument(
                doc_url=AnyUrl("https://example.com/doc"), doc_title="Test Doc"
            ),
        ]
        end_event = stream_end_event(
            token_usage,
            available_quotas,
            referenced_documents,
            MEDIA_TYPE_JSON,
        )
        data_part = end_event.replace("data: ", "").strip()
        parsed = json.loads(data_part)

        assert parsed["event"] == "end"
        assert "referenced_documents" in parsed["data"]
        assert "truncated" in parsed["data"]
        assert "input_tokens" in parsed["data"]
        assert "output_tokens" in parsed["data"]
        assert "available_quotas" in parsed


# ============================================================================
# Endpoint Handler Tests
# ============================================================================


@pytest.fixture(name="dummy_request")
def dummy_request() -> Request:
    """Dummy request fixture for testing."""
    req = Request(scope={"type": "http"})
    req.state.authorized_actions = set(Action)
    return req


class TestStreamingQueryEndpointHandler:
    """Tests for streaming_query_endpoint_handler function."""

    @pytest.mark.asyncio
    async def test_successful_streaming_query(
        self,
        dummy_request: Request,  # pylint: disable=redefined-outer-name
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful streaming query."""
        query_request = QueryRequest(
            query="What is Kubernetes?"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.streaming_query.configuration", setup_configuration)
        mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")
        mocker.patch("app.endpoints.streaming_query.check_tokens_available")
        mocker.patch("app.endpoints.streaming_query.validate_model_provider_override")
        mocker.patch(
            "app.endpoints.streaming_query.perform_vector_search",
            new=mocker.AsyncMock(return_value=([], [], [], [])),
        )
        mocker.patch(
            "app.endpoints.streaming_query.perform_vector_search",
            new=mocker.AsyncMock(return_value=([], [], [], [])),
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None
        mock_responses_params.model_dump.return_value = {
            "input": "test",
            "model": "provider1/model1",
        }
        mocker.patch(
            "app.endpoints.streaming_query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.metrics.llm_calls_total")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_response_generator",
            return_value=(mock_generator(), mock_turn_summary),
        )

        async def mock_generate_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_response",
            side_effect=mock_generate_response,
        )
        mocker.patch(
            "app.endpoints.streaming_query.normalize_conversation_id",
            return_value="123",
        )

        response = await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH_STREAMING,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_streaming_query_text_media_type_header(
        self,
        dummy_request: Request,  # pylint: disable=redefined-outer-name
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query uses plain text header when requested."""
        query_request = QueryRequest(
            query="What is Kubernetes?", media_type=MEDIA_TYPE_TEXT
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.streaming_query.configuration", setup_configuration)
        mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")
        mocker.patch("app.endpoints.streaming_query.check_tokens_available")
        mocker.patch("app.endpoints.streaming_query.validate_model_provider_override")
        mocker.patch(
            "app.endpoints.streaming_query.perform_vector_search",
            new=mocker.AsyncMock(return_value=([], [], [], [])),
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None
        mock_responses_params.model_dump.return_value = {
            "input": "test",
            "model": "provider1/model1",
        }
        mocker.patch(
            "app.endpoints.streaming_query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.metrics.llm_calls_total")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_response_generator",
            return_value=(mock_generator(), mock_turn_summary),
        )

        async def mock_generate_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_response",
            side_effect=mock_generate_response,
        )
        mocker.patch(
            "app.endpoints.streaming_query.normalize_conversation_id",
            return_value="123",
        )

        response = await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH_STREAMING,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == MEDIA_TYPE_TEXT

    @pytest.mark.asyncio
    async def test_streaming_query_with_conversation(
        self,
        dummy_request: Request,  # pylint: disable=redefined-outer-name
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query with existing conversation."""
        query_request = QueryRequest(
            query="What is Kubernetes?",
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
        )  # pyright: ignore[reportCallIssue]

        mock_conversation = mocker.Mock()

        mocker.patch("app.endpoints.streaming_query.configuration", setup_configuration)
        mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")
        mocker.patch("app.endpoints.streaming_query.check_tokens_available")
        mocker.patch("app.endpoints.streaming_query.validate_model_provider_override")
        mocker.patch(
            "app.endpoints.streaming_query.perform_vector_search",
            new=mocker.AsyncMock(return_value=([], [], [], [])),
        )
        mocker.patch(
            "app.endpoints.streaming_query.normalize_conversation_id",
            return_value="normalized_123",
        )
        mock_validate_conv = mocker.patch(
            "app.endpoints.streaming_query.validate_and_retrieve_conversation",
            return_value=mock_conversation,
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None
        mock_responses_params.model_dump.return_value = {
            "input": "test",
            "model": "provider1/model1",
        }
        mocker.patch(
            "app.endpoints.streaming_query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.metrics.llm_calls_total")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_response_generator",
            return_value=(mock_generator(), mock_turn_summary),
        )

        async def mock_generate_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_response",
            side_effect=mock_generate_response,
        )
        mocker.patch(
            "app.endpoints.streaming_query.normalize_conversation_id",
            return_value="123",
        )

        await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH_STREAMING,
            mcp_headers={},
        )

        mock_validate_conv.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_query_with_attachments(
        self,
        dummy_request: Request,  # pylint: disable=redefined-outer-name
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query with attachments validation."""
        query_request = QueryRequest(
            query="What is Kubernetes?",
            attachments=[
                Attachment(
                    attachment_type="log",
                    content_type="text/plain",
                    content="log content",
                )
            ],
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.streaming_query.configuration", setup_configuration)
        mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")
        mocker.patch("app.endpoints.streaming_query.check_tokens_available")
        mocker.patch("app.endpoints.streaming_query.validate_model_provider_override")
        mocker.patch(
            "app.endpoints.streaming_query.perform_vector_search",
            new=mocker.AsyncMock(return_value=([], [], [], [])),
        )
        mock_validate = mocker.patch(
            "app.endpoints.streaming_query.validate_attachments_metadata"
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None
        mock_responses_params.model_dump.return_value = {
            "input": "test",
            "model": "provider1/model1",
        }
        mocker.patch(
            "app.endpoints.streaming_query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.metrics.llm_calls_total")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_response_generator",
            return_value=(mock_generator(), mock_turn_summary),
        )

        async def mock_generate_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_response",
            side_effect=mock_generate_response,
        )
        mocker.patch(
            "app.endpoints.streaming_query.normalize_conversation_id",
            return_value="123",
        )

        await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH_STREAMING,
            mcp_headers={},
        )

        mock_validate.assert_called_once_with(query_request.attachments)

    @pytest.mark.asyncio
    async def test_streaming_query_azure_token_refresh(
        self,
        dummy_request: Request,  # pylint: disable=redefined-outer-name
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query refreshes Azure token when needed."""
        query_request = QueryRequest(
            query="What is Kubernetes?"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.streaming_query.configuration", setup_configuration)
        mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")
        mocker.patch("app.endpoints.streaming_query.check_tokens_available")
        mocker.patch("app.endpoints.streaming_query.validate_model_provider_override")
        mocker.patch(
            "app.endpoints.streaming_query.perform_vector_search",
            new=mocker.AsyncMock(return_value=([], [], [], [])),
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "azure/model1"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None
        mock_responses_params.model_dump.return_value = {
            "input": "test",
            "model": "azure/model1",
        }
        mocker.patch(
            "app.endpoints.streaming_query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mock_azure_manager = mocker.Mock()
        mock_azure_manager.is_entra_id_configured = True
        mock_azure_manager.is_token_expired = True
        mock_azure_manager.refresh_token.return_value = True
        mocker.patch(
            "app.endpoints.streaming_query.AzureEntraIDManager",
            return_value=mock_azure_manager,
        )

        mock_updated_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_update_token = mocker.patch(
            "app.endpoints.streaming_query.update_azure_token",
            new=mocker.AsyncMock(return_value=mock_updated_client),
        )

        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("azure", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.metrics.llm_calls_total")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_response_generator",
            return_value=(mock_generator(), mock_turn_summary),
        )

        async def mock_generate_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_response",
            side_effect=mock_generate_response,
        )
        mocker.patch(
            "app.endpoints.streaming_query.normalize_conversation_id",
            return_value="123",
        )

        await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH_STREAMING,
            mcp_headers={},
        )

        mock_update_token.assert_called_once()


class TestCreateResponseGenerator:
    """Tests for retrieve_response_generator function."""

    @pytest.mark.asyncio
    async def test_retrieve_response_generator_success(
        self, mocker: MockerFixture
    ) -> None:
        """Test successful response generator creation."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None  # No tools for this test
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.client = mock_client
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]

        async def mock_response_gen() -> AsyncIterator[str]:
            yield "test"

        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=mocker.Mock(blocked=False)),
        )
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(
            return_value=mock_response_gen()
        )

        async def mock_response_generator(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_response_gen():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.response_generator",
            side_effect=mock_response_generator,
        )

        generator, turn_summary = await retrieve_response_generator(
            mock_responses_params, mock_context, []
        )

        assert isinstance(turn_summary, TurnSummary)
        assert hasattr(generator, "__aiter__")

    @pytest.mark.asyncio
    async def test_retrieve_response_generator_shield_blocked(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator creation when shield blocks."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.conversation = "conv_123"

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.client = mock_client
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_TEXT
        )  # pyright: ignore[reportCallIssue]

        mock_moderation_result = mocker.Mock()
        mock_moderation_result.blocked = True
        mock_moderation_result.message = "Content blocked"
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=mock_moderation_result),
        )
        mocker.patch(
            "app.endpoints.streaming_query.append_turn_to_conversation",
            new=mocker.AsyncMock(),
        )

        _generator, turn_summary = await retrieve_response_generator(
            mock_responses_params, mock_context, []
        )

        assert isinstance(turn_summary, TurnSummary)
        assert turn_summary.llm_response == "Content blocked"

    @pytest.mark.asyncio
    async def test_retrieve_response_generator_connection_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator creation raises HTTPException on connection error."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None  # No tools for this test
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
            "conversation": "conv_123",
        }

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.client = mock_client
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=mocker.Mock(blocked=False)),
        )
        mock_request_obj = mocker.Mock()
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed", request=mock_request_obj
            )
        )

        mock_error_response = mocker.Mock()
        mock_error_response.model_dump.return_value = {
            "status_code": 503,
            "detail": {
                "response": "Unable to connect to Llama Stack",
                "cause": "Connection failed",
            },
        }
        mocker.patch(
            "app.endpoints.streaming_query.ServiceUnavailableResponse",
            return_value=mock_error_response,
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_response_generator(mock_responses_params, mock_context, [])

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_retrieve_response_generator_api_status_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator creation raises HTTPException on API status error."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None  # No tools for this test
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
            "conversation": "conv_123",
        }

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.client = mock_client
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=mocker.Mock(blocked=False)),
        )
        mock_request_obj = mocker.Mock()
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="API error", response=mock_request_obj, body=None
            )
        )

        mock_error_response = mocker.Mock()
        mock_error_response.model_dump.return_value = {
            "status_code": 500,
            "detail": {"response": "Error", "cause": "API error"},
        }
        mocker.patch(
            "app.endpoints.streaming_query.handle_known_apistatus_errors",
            return_value=mock_error_response,
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_response_generator(mock_responses_params, mock_context, [])

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_retrieve_response_generator_runtime_error_context_length(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator raises HTTPException on RuntimeError with context_length."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None  # No tools for this test
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
            "conversation": "conv_123",
        }

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.client = mock_client
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=mocker.Mock(blocked=False)),
        )
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )

        mock_error_response = mocker.Mock()
        mock_error_response.model_dump.return_value = {
            "status_code": 413,
            "detail": {"response": "Prompt too long", "model": "provider1/model1"},
        }
        mocker.patch(
            "app.endpoints.streaming_query.PromptTooLongResponse",
            return_value=mock_error_response,
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_response_generator(mock_responses_params, mock_context, [])

        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_retrieve_response_generator_runtime_error_other(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator creation re-raises RuntimeError without context_length."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.tools = None  # No tools for this test
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
            "conversation": "conv_123",
        }

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.client = mock_client
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=mocker.Mock(blocked=False)),
        )
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("Some other error")
        )

        with pytest.raises(RuntimeError):
            await retrieve_response_generator(mock_responses_params, mock_context, [])


class TestGenerateResponse:
    """Tests for generate_response function."""

    @pytest.mark.asyncio
    async def test_generate_response_success(self, mocker: MockerFixture) -> None:
        """Test successful response generation."""

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: token\n\n"
            yield "data: end\n\n"

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.conversation_id = "conv_123"
        mock_context.user_id = "user_123"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]
        mock_context.started_at = "2024-01-01T00:00:00Z"
        mock_context.skip_userid_check = False

        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_context.client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_context.client.responses = mocker.Mock()
        mock_context.client.responses.create = mocker.AsyncMock(
            return_value=mock_response_obj
        )

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"

        mock_turn_summary = TurnSummary()
        mock_turn_summary.token_usage = TokenCounter(input_tokens=10, output_tokens=5)

        mock_config = mocker.Mock()
        mock_config.quota_limiters = []
        mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
        mocker.patch("app.endpoints.streaming_query.consume_query_tokens")
        mocker.patch(
            "app.endpoints.streaming_query.get_available_quotas", return_value={}
        )
        mocker.patch("app.endpoints.streaming_query.store_query_results")

        result = []
        async for item in generate_response(
            mock_generator(), mock_context, mock_responses_params, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("start" in item for item in result)
        assert any("end" in item for item in result)

    @pytest.mark.asyncio
    async def test_generate_response_with_topic_summary(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generation with topic summary."""

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: token\n\n"

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.conversation_id = "conv_123"
        mock_context.user_id = "user_123"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test", generate_topic_summary=True
        )  # pyright: ignore[reportCallIssue]
        mock_context.started_at = "2024-01-01T00:00:00Z"
        mock_context.skip_userid_check = False
        mock_context.client = mocker.AsyncMock(spec=AsyncLlamaStackClient)

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"

        mock_turn_summary = TurnSummary()
        mock_turn_summary.token_usage = TokenCounter(input_tokens=10, output_tokens=5)

        mock_config = mocker.Mock()
        mock_config.quota_limiters = []
        mocker.patch("app.endpoints.streaming_query.configuration", mock_config)
        mocker.patch("app.endpoints.streaming_query.consume_query_tokens")
        mocker.patch(
            "app.endpoints.streaming_query.get_available_quotas", return_value={}
        )
        mocker.patch(
            "app.endpoints.streaming_query.get_topic_summary",
            new=mocker.AsyncMock(return_value="Topic summary"),
        )
        mocker.patch("app.endpoints.streaming_query.store_query_results")

        result = []
        async for item in generate_response(
            mock_generator(), mock_context, mock_responses_params, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_response_connection_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generation handles connection error."""

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: token\n\n"
            raise APIConnectionError(message="Connection failed", request=mocker.Mock())

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.conversation_id = "conv_123"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]
        mock_context.started_at = "2024-01-01T00:00:00Z"
        mock_context.skip_userid_check = False

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"

        mock_turn_summary = TurnSummary()

        result = []
        async for item in generate_response(
            mock_generator(), mock_context, mock_responses_params, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("error" in item for item in result)

    @pytest.mark.asyncio
    async def test_generate_response_api_status_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generation handles API status error."""
        mock_request_obj = mocker.Mock()

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: token\n\n"
            raise APIStatusError(
                message="API error", response=mock_request_obj, body=None
            )

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.conversation_id = "conv_123"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test"
        )  # pyright: ignore[reportCallIssue]
        mock_context.started_at = "2024-01-01T00:00:00Z"
        mock_context.skip_userid_check = False

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"

        mock_turn_summary = TurnSummary()

        mock_error_response = InternalServerErrorResponse.query_failed("API error")
        mocker.patch(
            "app.endpoints.streaming_query.handle_known_apistatus_errors",
            return_value=mock_error_response,
        )

        result = []
        async for item in generate_response(
            mock_generator(), mock_context, mock_responses_params, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("error" in item for item in result)

    @pytest.mark.asyncio
    async def test_generate_response_runtime_error_context_length(
        self, mocker: MockerFixture
    ) -> None:
        """Test generate_response handles RuntimeError with context_length."""

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: start\n\n"
            raise RuntimeError("context_length exceeded")

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.conversation_id = "conv_123"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"

        mock_turn_summary = TurnSummary()

        mock_error_response = mocker.Mock()
        mock_error_response.status_code = 413
        mock_error_response.detail = mocker.Mock()
        mock_error_response.detail.response = "Prompt too long"
        mock_error_response.detail.cause = None
        mocker.patch(
            "app.endpoints.streaming_query.PromptTooLongResponse",
            return_value=mock_error_response,
        )

        result = []
        async for item in generate_response(
            mock_generator(), mock_context, mock_responses_params, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("error" in item for item in result)

    @pytest.mark.asyncio
    async def test_generate_response_runtime_error_other(
        self, mocker: MockerFixture
    ) -> None:
        """Test generate_response handles RuntimeError without context_length."""

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: start\n\n"
            raise RuntimeError("Some other error")

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.conversation_id = "conv_123"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]

        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"

        mock_turn_summary = TurnSummary()

        mock_error_response = mocker.Mock()
        mock_error_response.status_code = 500
        mock_error_response.detail = mocker.Mock()
        mock_error_response.detail.response = "Internal server error"
        mock_error_response.detail.cause = None
        mocker.patch(
            "app.endpoints.streaming_query.InternalServerErrorResponse.generic",
            return_value=mock_error_response,
        )

        result = []
        async for item in generate_response(
            mock_generator(), mock_context, mock_responses_params, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("error" in item for item in result)


class TestResponseGenerator:
    """Tests for response_generator function."""

    @pytest.mark.asyncio
    async def test_response_generator_text_delta(self, mocker: MockerFixture) -> None:
        """Test response generator processes text delta events."""

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=TextDeltaChunk)
            chunk.type = "response.output_text.delta"
            chunk.delta = "Hello"
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_response_generator_content_part_added(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator processes content part added events."""

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock()
            chunk.type = "response.content_part.added"
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_response_generator_output_text_done(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator processes output text done events."""

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=TextDoneChunk)
            chunk.type = "response.output_text.done"
            chunk.text = "Complete response"
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        async for _ in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            pass

        assert mock_turn_summary.llm_response == "Complete response"

    @pytest.mark.asyncio
    async def test_response_generator_output_item_done_message_type(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator skips message type items."""
        mock_output_item = mocker.Mock()
        mock_output_item.type = "message"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=OutputItemDoneChunk)
            chunk.type = "response.output_item.done"
            chunk.item = mock_output_item
            chunk.output_index = 0
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_response_generator_output_item_done(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator processes output item done events."""
        mock_output_item = mocker.Mock()
        mock_output_item.type = "tool_call"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=OutputItemDoneChunk)
            chunk.type = "response.output_item.done"
            chunk.item = mock_output_item
            chunk.output_index = 0
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mock_tool_call = mocker.Mock()
        mock_tool_call.model_dump.return_value = {"tool": "test"}
        mocker.patch(
            "app.endpoints.streaming_query.build_tool_call_summary",
            return_value=(mock_tool_call, None),
        )

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_response_generator_output_item_done_with_tool_result(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator processes output item done events with tool result."""
        mock_output_item = mocker.Mock()
        mock_output_item.type = "tool_call"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=OutputItemDoneChunk)
            chunk.type = "response.output_item.done"
            chunk.item = mock_output_item
            chunk.output_index = 0
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mock_tool_call = mocker.Mock()
        mock_tool_call.model_dump.return_value = {"tool": "test"}
        mock_tool_result = mocker.Mock()
        mock_tool_result.model_dump.return_value = {"result": "test_result"}
        mocker.patch(
            "app.endpoints.streaming_query.build_tool_call_summary",
            return_value=(mock_tool_call, mock_tool_result),
        )

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert len(mock_turn_summary.tool_results) == 1

    @pytest.mark.asyncio
    async def test_response_generator_response_completed(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator processes response completed events."""
        mock_response_obj = mocker.Mock(spec=OpenAIResponseObject)
        mock_response_obj.usage = mocker.Mock(input_tokens=10, output_tokens=5)

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=CompletedChunk)
            chunk.type = "response.completed"
            chunk.response = mock_response_obj
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()
        mock_turn_summary.llm_response = "Response"

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=10, output_tokens=5),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        async for _ in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            pass

        assert mock_turn_summary.token_usage.input_tokens == 10

    @pytest.mark.asyncio
    async def test_response_generator_response_completed_uses_text_parts(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator uses text_parts when llm_response is empty."""
        mock_response_obj = mocker.Mock(spec=OpenAIResponseObject)
        mock_response_obj.usage = mocker.Mock(input_tokens=10, output_tokens=5)

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            # Add text delta first
            delta_chunk = mocker.Mock(spec=TextDeltaChunk)
            delta_chunk.type = "response.output_text.delta"
            delta_chunk.delta = "Hello"
            yield delta_chunk

            # Then completed (without output_text.done, so llm_response is empty)
            completed_chunk = mocker.Mock(spec=CompletedChunk)
            completed_chunk.type = "response.completed"
            completed_chunk.response = mock_response_obj
            yield completed_chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=10, output_tokens=5),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        # Should use text_parts for turn_complete event
        assert len(result) > 0
        assert any("turn_complete" in item for item in result)

    @pytest.mark.asyncio
    async def test_response_generator_response_incomplete(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator processes incomplete response events."""

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=IncompleteChunk)
            chunk.type = "response.incomplete"
            mock_response = mocker.Mock()
            mock_response.output = []
            # Create a simple object with message attribute as a string
            mock_error = type("Error", (), {"message": "context_length exceeded"})()
            mock_response.error = mock_error
            chunk.response = mock_response
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("error" in item for item in result)

    @pytest.mark.asyncio
    async def test_response_generator_response_failed(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator processes failed response events."""
        mock_error = mocker.Mock()
        mock_error.message = "Error message"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=FailedChunk)
            chunk.type = "response.failed"
            mock_response = mocker.Mock()
            mock_response.output = []
            mock_response.error = mock_error
            chunk.response = mock_response
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("error" in item for item in result)

    @pytest.mark.asyncio
    async def test_response_generator_response_failed_no_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator handles failed response with no error object."""

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=FailedChunk)
            chunk.type = "response.failed"
            mock_response = mocker.Mock()
            mock_response.output = []
            mock_response.error = None
            chunk.response = mock_response
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_response_generator_response_failed_context_length(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator handles failed response with context_length error."""
        mock_error = mocker.Mock()
        mock_error.message = "context_length exceeded"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=FailedChunk)
            chunk.type = "response.failed"
            mock_response = mocker.Mock()
            mock_response.output = []
            mock_response.error = mock_error
            chunk.response = mock_response
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_response_generator_response_incomplete_no_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator handles incomplete response with no error object."""

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=IncompleteChunk)
            chunk.type = "response.incomplete"
            mock_response = mocker.Mock()
            mock_response.output = []
            mock_response.error = None
            chunk.response = mock_response
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        assert len(result) > 0
        assert any("error" in item for item in result)


class TestStreamHttpErrorEvent:
    """Tests for stream_http_error_event function."""

    def test_stream_http_error_event_json(self, mocker: MockerFixture) -> None:
        """Test HTTP error event formatting for JSON media type."""
        error = InternalServerErrorResponse.query_failed("Test error")
        mocker.patch("app.endpoints.streaming_query.logger")

        result = stream_http_error_event(error, MEDIA_TYPE_JSON)

        assert "error" in result
        assert "Test error" in result

    def test_stream_http_error_event_text(self, mocker: MockerFixture) -> None:
        """Test HTTP error event formatting for text media type."""
        error = InternalServerErrorResponse.query_failed("Test error")
        mocker.patch("app.endpoints.streaming_query.logger")

        result = stream_http_error_event(error, MEDIA_TYPE_TEXT)

        assert "Status:" in result
        assert "500" in result
        assert "Test error" in result

    def test_stream_http_error_event_default(self, mocker: MockerFixture) -> None:
        """Test HTTP error event formatting with default media type."""
        error = InternalServerErrorResponse.query_failed("Test error")
        mocker.patch("app.endpoints.streaming_query.logger")

        result = stream_http_error_event(error)

        assert "error" in result
        assert "500" in result or "status_code" in result


class TestStreamStartEvent:  # pylint: disable=too-few-public-methods
    """Tests for stream_start_event function."""

    def test_stream_start_event(self) -> None:
        """Test start event formatting."""
        result = stream_start_event("conv_123")

        assert "start" in result
        assert "conv_123" in result


class TestShieldViolationGenerator:
    """Tests for shield_violation_generator function."""

    @pytest.mark.asyncio
    async def test_shield_violation_generator_json(self) -> None:
        """Test shield violation generator for JSON media type."""
        result = []
        async for item in shield_violation_generator(
            "Violation message", MEDIA_TYPE_JSON
        ):
            result.append(item)

        assert len(result) > 0
        assert any("Violation message" in item for item in result)

    @pytest.mark.asyncio
    async def test_shield_violation_generator_text(self) -> None:
        """Test shield violation generator for text media type."""
        result = []
        async for item in shield_violation_generator(
            "Violation message", MEDIA_TYPE_TEXT
        ):
            result.append(item)

        assert len(result) > 0


class TestResponseGeneratorMCPCalls:
    """Tests for MCP call specific event handling in response_generator."""

    @pytest.mark.asyncio
    async def test_response_generator_mcp_call_output_item_added(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator stores MCP call item info when output_item.added."""
        mock_mcp_item = mocker.Mock(spec=MCPCall)
        mock_mcp_item.type = "mcp_call"
        mock_mcp_item.id = "mcp_call_123"
        mock_mcp_item.name = "test_mcp_tool"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            chunk = mocker.Mock(spec=OutputItemAddedChunk)
            chunk.type = "response.output_item.added"
            chunk.item = mock_mcp_item
            chunk.output_index = 0
            yield chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        # Should process without error
        assert True

    @pytest.mark.asyncio
    async def test_response_generator_mcp_call_arguments_done(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator emits tool call when MCP arguments.done."""
        mock_mcp_item = mocker.Mock(spec=MCPCall)
        mock_mcp_item.type = "mcp_call"
        mock_mcp_item.id = "mcp_call_123"
        mock_mcp_item.name = "test_mcp_tool"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            # First, output_item.added
            added_chunk = mocker.Mock(spec=OutputItemAddedChunk)
            added_chunk.type = "response.output_item.added"
            added_chunk.item = mock_mcp_item
            added_chunk.output_index = 0
            yield added_chunk

            # Then, arguments.done
            args_chunk = mocker.Mock(spec=MCPArgsDoneChunk)
            args_chunk.type = "response.mcp_call.arguments.done"
            args_chunk.output_index = 0
            args_chunk.arguments = '{"param": "value"}'
            yield args_chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mock_tool_call = mocker.Mock()
        mock_tool_call.model_dump.return_value = {
            "id": "mcp_call_123",
            "name": "test_mcp_tool",
        }
        mocker.patch(
            "app.endpoints.streaming_query.build_mcp_tool_call_from_arguments_done",
            return_value=mock_tool_call,
        )

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        # Should emit tool call event
        assert len(result) > 0
        assert len(mock_turn_summary.tool_calls) == 1

    @pytest.mark.asyncio
    async def test_response_generator_mcp_call_output_item_done_with_arguments_done(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator emits only result when MCP output_item.done after arguments."""
        mock_mcp_item = mocker.Mock(spec=MCPCall)
        mock_mcp_item.type = "mcp_call"
        mock_mcp_item.id = "mcp_call_123"
        mock_mcp_item.name = "test_mcp_tool"
        mock_mcp_item.error = None
        mock_mcp_item.output = "Result output"

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            # First, output_item.added
            added_chunk = mocker.Mock(spec=OutputItemAddedChunk)
            added_chunk.type = "response.output_item.added"
            added_chunk.item = mock_mcp_item
            added_chunk.output_index = 0
            yield added_chunk

            # Then, arguments.done (removes from mcp_calls dict)
            args_chunk = mocker.Mock(spec=MCPArgsDoneChunk)
            args_chunk.type = "response.mcp_call.arguments.done"
            args_chunk.output_index = 0
            args_chunk.arguments = '{"param": "value"}'
            yield args_chunk

            # Finally, output_item.done (should only emit result)
            done_chunk = mocker.Mock(spec=OutputItemDoneChunk)
            done_chunk.type = "response.output_item.done"
            done_chunk.item = mock_mcp_item
            done_chunk.output_index = 0
            yield done_chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mock_tool_call = mocker.Mock()
        mock_tool_call.model_dump.return_value = {"id": "mcp_call_123"}

        # Use side_effect to actually remove item from mcp_calls dict
        def build_mcp_tool_call_side_effect(
            output_index: int,
            arguments: str,
            mcp_call_items: dict[int, tuple[str, str]],
        ) -> Any:
            # Remove item from dict to simulate real behavior
            # arguments parameter is required by function signature but unused here
            _ = arguments  # noqa: F841
            if output_index in mcp_call_items:
                del mcp_call_items[output_index]
            return mock_tool_call

        mocker.patch(
            "app.endpoints.streaming_query.build_mcp_tool_call_from_arguments_done",
            side_effect=build_mcp_tool_call_side_effect,
        )

        mock_tool_result = mocker.Mock()
        mock_tool_result.model_dump.return_value = {
            "id": "mcp_call_123",
            "status": "success",
        }
        mocker.patch(
            "app.endpoints.streaming_query.build_tool_result_from_mcp_output_item_done",
            return_value=mock_tool_result,
        )

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        # Should have one tool call (from arguments.done) and one tool result
        assert len(mock_turn_summary.tool_calls) == 1
        assert len(mock_turn_summary.tool_results) == 1

    @pytest.mark.asyncio
    async def test_response_generator_mcp_call_output_item_done_without_arguments_done(
        self, mocker: MockerFixture
    ) -> None:
        """Test response generator emits both call and result when MCP output_item.done."""
        mock_mcp_item = mocker.Mock(spec=MCPCall)
        mock_mcp_item.type = "mcp_call"
        mock_mcp_item.id = "mcp_call_123"
        mock_mcp_item.name = "test_mcp_tool"
        mock_mcp_item.error = None
        mock_mcp_item.output = "Result output"
        mock_mcp_item.arguments = '{"param": "value"}'
        mock_mcp_item.server_label = None

        async def mock_turn_response() -> AsyncIterator[OpenAIResponseObjectStream]:
            # Only output_item.added (arguments.done was missed)
            added_chunk = mocker.Mock(spec=OutputItemAddedChunk)
            added_chunk.type = "response.output_item.added"
            added_chunk.item = mock_mcp_item
            added_chunk.output_index = 0
            yield added_chunk

            # output_item.done (should emit both call and result since arguments.done didn't happen)
            done_chunk = mocker.Mock(spec=OutputItemDoneChunk)
            done_chunk.type = "response.output_item.done"
            done_chunk.item = mock_mcp_item
            done_chunk.output_index = 0
            yield done_chunk

        mock_context = mocker.Mock(spec=ResponseGeneratorContext)
        mock_context.query_request = QueryRequest(
            query="test", media_type=MEDIA_TYPE_JSON
        )  # pyright: ignore[reportCallIssue]
        mock_context.model_id = "provider1/model1"
        mock_context.vector_store_ids = []
        mock_context.rag_id_mapping = {}

        mock_turn_summary = TurnSummary()

        mock_tool_call = mocker.Mock()
        mock_tool_call.model_dump.return_value = {"id": "mcp_call_123"}
        mock_tool_result = mocker.Mock()
        mock_tool_result.model_dump.return_value = {
            "id": "mcp_call_123",
            "status": "success",
        }
        mocker.patch(
            "app.endpoints.streaming_query.build_tool_call_summary",
            return_value=(mock_tool_call, mock_tool_result),
        )

        mocker.patch(
            "app.endpoints.streaming_query.extract_token_usage",
            return_value=TokenCounter(input_tokens=0, output_tokens=0),
        )
        mocker.patch(
            "app.endpoints.streaming_query.parse_referenced_documents", return_value=[]
        )

        result = []
        async for item in response_generator(
            mock_turn_response(), mock_context, mock_turn_summary
        ):
            result.append(item)

        # Should have both tool call and result (fallback behavior)
        assert len(mock_turn_summary.tool_calls) == 1
        assert len(mock_turn_summary.tool_results) == 1
