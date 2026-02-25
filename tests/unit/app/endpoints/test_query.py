# pylint: disable=redefined-outer-name, import-error,too-many-locals,too-many-lines
# pyright: reportCallIssue=false
"""Unit tests for the /query (v2) REST API endpoint using Responses API."""

from typing import Any

import pytest
from fastapi import HTTPException, Request
from llama_stack_api.openai_responses import OpenAIResponseObject
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient
from pytest_mock import MockerFixture

from app.endpoints.query import query_endpoint_handler, retrieve_response
from configuration import AppConfig
from models.database.conversations import UserConversation
from models.requests import Attachment, QueryRequest
from models.responses import QueryResponse
from utils.token_counter import TokenCounter
from utils.types import (
    ResponsesApiParams,
    ToolCallSummary,
    ToolResultSummary,
    TurnSummary,
)

# User ID must be proper UUID
MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture(name="dummy_request")
def create_dummy_request() -> Request:
    """Create dummy request fixture for testing.

    Create a minimal FastAPI Request object suitable for unit tests.

    Returns:
        request (fastapi.Request): A Request constructed with a bare HTTP scope
        (type "http") for use in tests.
    """
    req = Request(scope={"type": "http"})
    return req


@pytest.fixture(name="setup_configuration")
def setup_configuration_fixture() -> AppConfig:
    """Set up configuration for tests.

    Create a reusable application configuration tailored for unit tests.

    The returned AppConfig is initialized from a fixed dictionary that sets:
    - a lightweight service configuration (localhost, port 8080, minimal workers, logging enabled),
    - a test Llama Stack configuration (test API key and URL, not used as a library client),
    - user data collection with transcripts disabled,
    - an empty MCP servers list,
    - a noop conversation cache.

    Returns:
        AppConfig: an initialized configuration instance suitable for test fixtures.
    """
    config_dict: dict[Any, Any] = {
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
        "customization": None,
        "conversation_cache": {
            "type": "noop",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    return cfg


class TestQueryEndpointHandler:
    """Tests for query_endpoint_handler function."""

    @pytest.mark.asyncio
    async def test_successful_query_no_conversation(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful query without existing conversation."""
        query_request = QueryRequest(
            query="What is Kubernetes?"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.query.configuration", setup_configuration)
        mocker.patch("app.endpoints.query.check_configuration_loaded")
        mocker.patch("app.endpoints.query.check_tokens_available")
        mocker.patch("app.endpoints.query.validate_model_provider_override")

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
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
            "app.endpoints.query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mock_turn_summary = TurnSummary()
        mock_turn_summary.llm_response = (
            "Kubernetes is a container orchestration platform"
        )

        async def mock_retrieve_response(*_args: Any, **_kwargs: Any) -> TurnSummary:
            return mock_turn_summary

        mocker.patch(
            "app.endpoints.query.retrieve_response", side_effect=mock_retrieve_response
        )

        mocker.patch(
            "app.endpoints.query.normalize_conversation_id", return_value="123"
        )
        mocker.patch("app.endpoints.query.store_query_results")
        mocker.patch("app.endpoints.query.consume_query_tokens")
        mocker.patch("app.endpoints.query.get_available_quotas", return_value={})

        response = await query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        assert isinstance(response, QueryResponse)
        assert response.conversation_id == "123"
        assert response.response == "Kubernetes is a container orchestration platform"

    @pytest.mark.asyncio
    async def test_successful_query_with_conversation(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful query with existing conversation."""
        query_request = QueryRequest(
            query="What is Kubernetes?",
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.query.configuration", setup_configuration)
        mocker.patch("app.endpoints.query.check_configuration_loaded")
        mocker.patch("app.endpoints.query.check_tokens_available")
        mocker.patch("app.endpoints.query.validate_model_provider_override")
        mocker.patch(
            "app.endpoints.query.normalize_conversation_id", return_value="123"
        )
        mock_validate_conv = mocker.patch(
            "app.endpoints.query.validate_and_retrieve_conversation",
            return_value=mocker.Mock(spec=UserConversation),
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncLlamaStackClientHolder",
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
            "app.endpoints.query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mocker.patch(
            "app.endpoints.query.retrieve_response",
            new=mocker.AsyncMock(return_value=TurnSummary()),
        )
        mocker.patch("app.endpoints.query.store_query_results")
        mocker.patch("app.endpoints.query.consume_query_tokens")
        mocker.patch("app.endpoints.query.get_available_quotas", return_value={})

        response = await query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        assert isinstance(response, QueryResponse)
        mock_validate_conv.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_attachments(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test query with attachments validation."""
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

        mocker.patch("app.endpoints.query.configuration", setup_configuration)
        mocker.patch("app.endpoints.query.check_configuration_loaded")
        mocker.patch("app.endpoints.query.check_tokens_available")
        mocker.patch("app.endpoints.query.validate_model_provider_override")
        mock_validate = mocker.patch(
            "app.endpoints.query.validate_attachments_metadata"
        )

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
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
            "app.endpoints.query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        async def mock_retrieve_response(*_args: Any, **_kwargs: Any) -> TurnSummary:
            return TurnSummary()

        mocker.patch(
            "app.endpoints.query.retrieve_response", side_effect=mock_retrieve_response
        )
        mocker.patch(
            "app.endpoints.query.normalize_conversation_id", return_value="123"
        )
        mocker.patch("app.endpoints.query.store_query_results")
        mocker.patch("app.endpoints.query.consume_query_tokens")
        mocker.patch("app.endpoints.query.get_available_quotas", return_value={})

        await query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_validate.assert_called_once_with(query_request.attachments)

    @pytest.mark.asyncio
    async def test_query_with_topic_summary(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test query generates topic summary for new conversation."""
        query_request = QueryRequest(
            query="What is Kubernetes?", generate_topic_summary=True
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.query.configuration", setup_configuration)
        mocker.patch("app.endpoints.query.check_configuration_loaded")
        mocker.patch("app.endpoints.query.check_tokens_available")
        mocker.patch("app.endpoints.query.validate_model_provider_override")

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncLlamaStackClientHolder",
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
            "app.endpoints.query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mocker.patch(
            "app.endpoints.query.retrieve_response",
            new=mocker.AsyncMock(return_value=TurnSummary()),
        )
        mock_get_topic_summary = mocker.patch(
            "app.endpoints.query.get_topic_summary",
            new=mocker.AsyncMock(return_value="Topic: Kubernetes"),
        )
        mocker.patch(
            "app.endpoints.query.normalize_conversation_id", return_value="123"
        )
        mocker.patch("app.endpoints.query.store_query_results")
        mocker.patch("app.endpoints.query.consume_query_tokens")
        mocker.patch("app.endpoints.query.get_available_quotas", return_value={})

        await query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_get_topic_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_azure_token_refresh(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test query refreshes Azure token when needed."""
        query_request = QueryRequest(
            query="What is Kubernetes?"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.query.configuration", setup_configuration)
        mocker.patch("app.endpoints.query.check_configuration_loaded")
        mocker.patch("app.endpoints.query.check_tokens_available")
        mocker.patch("app.endpoints.query.validate_model_provider_override")

        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
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
            "app.endpoints.query.prepare_responses_params",
            new=mocker.AsyncMock(return_value=mock_responses_params),
        )

        mock_azure_manager = mocker.Mock()
        mock_azure_manager.is_entra_id_configured = True
        mock_azure_manager.is_token_expired = True
        mock_azure_manager.refresh_token.return_value = True
        mocker.patch(
            "app.endpoints.query.AzureEntraIDManager", return_value=mock_azure_manager
        )

        mock_updated_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_response_obj_updated = mocker.Mock()
        mock_response_obj_updated.output = []
        mock_updated_client.responses = mocker.Mock()
        mock_updated_client.responses.create = mocker.AsyncMock(
            return_value=mock_response_obj_updated
        )
        mock_update_token = mocker.patch(
            "app.endpoints.query.update_azure_token",
            new=mocker.AsyncMock(return_value=mock_updated_client),
        )
        mocker.patch(
            "app.endpoints.query.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )

        async def mock_retrieve_response(*_args: Any, **_kwargs: Any) -> TurnSummary:
            return TurnSummary()

        mocker.patch(
            "app.endpoints.query.retrieve_response", side_effect=mock_retrieve_response
        )
        mocker.patch(
            "app.endpoints.query.normalize_conversation_id", return_value="123"
        )
        mocker.patch("app.endpoints.query.store_query_results")
        mocker.patch("app.endpoints.query.consume_query_tokens")
        mocker.patch("app.endpoints.query.get_available_quotas", return_value={})

        await query_endpoint_handler(
            request=dummy_request,
            query_request=query_request,
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_update_token.assert_called_once()


class TestRetrieveResponse:
    """Tests for retrieve_response function."""

    @pytest.mark.asyncio
    async def test_retrieve_response_success(self, mocker: MockerFixture) -> None:
        """Test successful response retrieval."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.input = "test query"
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mock_output_item = mocker.Mock()
        mock_output_item.type = "message"
        mock_output_item.content = "Response text"

        mock_usage = mocker.Mock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 5
        mock_response = mocker.Mock(spec=OpenAIResponseObject)
        mock_response.output = [mock_output_item]
        mock_response.usage = mock_usage

        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            return_value=mocker.Mock(blocked=False),
        )
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)

        mock_summary = TurnSummary()
        mock_summary.llm_response = "Response text"
        mock_summary.token_usage = TokenCounter(input_tokens=10, output_tokens=5)
        mocker.patch(
            "app.endpoints.query.build_turn_summary",
            return_value=mock_summary,
        )

        result = await retrieve_response(mock_client, mock_responses_params)

        assert isinstance(result, TurnSummary)
        assert result.llm_response == "Response text"
        assert result.token_usage.input_tokens == 10
        assert result.token_usage.output_tokens == 5

    @pytest.mark.asyncio
    async def test_retrieve_response_shield_blocked(
        self, mocker: MockerFixture
    ) -> None:
        """Test response retrieval when shield moderation blocks the request."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.input = "test query"
        mock_responses_params.conversation = "conv_123"
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mock_moderation_result = mocker.Mock()
        mock_moderation_result.blocked = True
        mock_moderation_result.message = "Content blocked by moderation"
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            return_value=mock_moderation_result,
        )
        mock_append = mocker.patch("app.endpoints.query.append_turn_to_conversation")

        result = await retrieve_response(mock_client, mock_responses_params)

        assert isinstance(result, TurnSummary)
        assert result.llm_response == "Content blocked by moderation"
        mock_append.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_response_connection_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response retrieval raises HTTPException on connection error."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.input = "test query"
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            return_value=mocker.Mock(blocked=False),
        )
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed", request=mocker.Mock()
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_response(mock_client, mock_responses_params)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_retrieve_response_api_status_error(
        self, mocker: MockerFixture
    ) -> None:
        """Test response retrieval raises HTTPException on API status error."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.input = "test query"
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            return_value=mocker.Mock(blocked=False),
        )
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="API error", response=mocker.Mock(request=None), body=None
            )
        )
        mocker.patch(
            "app.endpoints.query.handle_known_apistatus_errors",
            return_value=mocker.Mock(
                model_dump=lambda: {
                    "status_code": 500,
                    "detail": {"response": "Error", "cause": "API error"},
                }
            ),
        )

        with pytest.raises(HTTPException):
            await retrieve_response(mock_client, mock_responses_params)

    @pytest.mark.asyncio
    async def test_retrieve_response_runtime_error_context_length(
        self, mocker: MockerFixture
    ) -> None:
        """Test retrieve_response handles RuntimeError with context_length."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            return_value=mocker.Mock(blocked=False),
        )
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_response(mock_client, mock_responses_params)

        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_retrieve_response_runtime_error_other(
        self, mocker: MockerFixture
    ) -> None:
        """Test retrieve_response re-raises RuntimeError without context_length."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.input = "test query"
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            return_value=mocker.Mock(blocked=False),
        )
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("Some other error")
        )

        with pytest.raises(RuntimeError):
            await retrieve_response(mock_client, mock_responses_params)

    @pytest.mark.asyncio
    async def test_retrieve_response_with_tool_calls(
        self, mocker: MockerFixture
    ) -> None:
        """Test response retrieval processes tool calls."""
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_responses_params = mocker.Mock(spec=ResponsesApiParams)
        mock_responses_params.input = "test query"
        mock_responses_params.model = "provider1/model1"
        mock_responses_params.model_dump.return_value = {
            "input": "test query",
            "model": "provider1/model1",
        }

        mock_usage = mocker.Mock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 5
        mock_response = mocker.Mock(spec=OpenAIResponseObject)
        mock_response.output = [mocker.Mock(type="message")]
        mock_response.usage = mock_usage

        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            return_value=mocker.Mock(blocked=False),
        )
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)

        mock_tool_call = ToolCallSummary(id="1", name="test", args={})
        mock_tool_result = ToolResultSummary(
            id="1", status="success", content="result", round=1
        )
        mock_summary = TurnSummary()
        mock_summary.llm_response = "Response text"
        mock_summary.tool_calls = [mock_tool_call]
        mock_summary.tool_results = [mock_tool_result]
        mock_summary.token_usage = TokenCounter(input_tokens=10, output_tokens=5)
        mocker.patch(
            "app.endpoints.query.build_turn_summary",
            return_value=mock_summary,
        )

        result = await retrieve_response(mock_client, mock_responses_params)

        assert result.llm_response == "Response text"
        assert len(result.tool_calls) == 1
        assert len(result.tool_results) == 1
        assert result.token_usage.input_tokens == 10
        assert result.token_usage.output_tokens == 5
        assert result.rag_chunks == []
        assert result.referenced_documents == []
        assert result.pre_rag_documents == []
