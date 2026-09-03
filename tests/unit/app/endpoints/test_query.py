# pylint: disable=too-many-locals
"""Unit tests for the /query (v2) REST API endpoint using Responses API."""

from typing import Any

import pytest
from fastapi import Request
from ogx_client import AsyncOgxClient
from pytest_mock import MockerFixture

from app.endpoints.query import query_endpoint_handler
from configuration import AppConfig
from models.api.requests import QueryRequest
from models.api.responses.successful import QueryResponse
from models.common.moderation import ShieldModerationPassed
from models.common.query import Attachment
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import (
    RAGChunk,
    RAGContext,
    ReferencedDocument,
    TurnSummary,
)
from models.database.conversations import UserConversation

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
    return Request(scope={"type": "http", "headers": []})


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

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncOgxClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.maybe_get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
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

        async def mock_retrieve_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> TurnSummary:
            return mock_turn_summary

        mocker.patch(
            "app.endpoints.query.retrieve_agent_response",
            side_effect=mock_retrieve_agent_response,
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
    async def test_query_merges_inline_and_tool_rag_chunks_and_documents(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that inline RAG and tool-based RAG chunks/docs are correctly merged."""
        query_request = QueryRequest(
            query="What is Kubernetes?"
        )  # pyright: ignore[reportCallIssue]

        mocker.patch("app.endpoints.query.configuration", setup_configuration)
        mocker.patch("app.endpoints.query.check_configuration_loaded")
        mocker.patch("app.endpoints.query.check_tokens_available")
        mocker.patch("app.endpoints.query.validate_model_provider_override")

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncOgxClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
        )

        inline_chunk = RAGChunk(content="inline chunk content", source="byok")
        inline_doc = ReferencedDocument(
            doc_title="Inline Doc", document_id="inline_doc_1"
        )
        inline_rag = RAGContext(
            context_text="",
            rag_chunks=[inline_chunk],
            referenced_documents=[inline_doc],
        )
        mocker.patch(
            "app.endpoints.query.build_rag_context",
            new=mocker.AsyncMock(return_value=inline_rag),
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

        tool_chunk = RAGChunk(content="tool chunk content", source="vs-1")
        tool_doc = ReferencedDocument(doc_title="Tool Doc", document_id="tool_doc_1")
        mock_turn_summary = TurnSummary()
        mock_turn_summary.rag_chunks = [tool_chunk]
        mock_turn_summary.referenced_documents = [tool_doc]

        mocker.patch(
            "app.endpoints.query.retrieve_agent_response",
            new=mocker.AsyncMock(return_value=mock_turn_summary),
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
        assert len(response.rag_chunks) == 2
        assert response.rag_chunks[0].content == "inline chunk content"
        assert response.rag_chunks[1].content == "tool chunk content"
        assert len(response.referenced_documents) == 2
        assert response.referenced_documents[0].doc_title == "Inline Doc"
        assert response.referenced_documents[1].doc_title == "Tool Doc"

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

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncOgxClientHolder",
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
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
        )
        mocker.patch(
            "app.endpoints.query.retrieve_agent_response",
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

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncOgxClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.maybe_get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
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

        async def mock_retrieve_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> TurnSummary:
            return TurnSummary()

        mocker.patch(
            "app.endpoints.query.retrieve_agent_response",
            side_effect=mock_retrieve_agent_response,
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

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncOgxClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
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
            "app.endpoints.query.retrieve_agent_response",
            new=mocker.AsyncMock(return_value=TurnSummary()),
        )
        mock_maybe_get_topic_summary = mocker.patch(
            "app.endpoints.query.maybe_get_topic_summary",
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

        mock_maybe_get_topic_summary.assert_called_once()

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

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_response_obj = mocker.Mock()
        mock_response_obj.output = []
        mock_client.responses = mocker.Mock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response_obj)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.query.AsyncOgxClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.query.maybe_get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(
            "app.endpoints.query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
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

        mock_updated_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder.update_azure_token = mocker.AsyncMock(
            return_value=mock_updated_client
        )

        async def mock_retrieve_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> TurnSummary:
            return TurnSummary()

        mocker.patch(
            "app.endpoints.query.retrieve_agent_response",
            side_effect=mock_retrieve_agent_response,
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

        mock_client_holder.update_azure_token.assert_called_once()
