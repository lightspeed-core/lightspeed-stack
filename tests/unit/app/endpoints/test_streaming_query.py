"""Unit tests for the /streaming_query (v2) endpoint using Responses API."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from ogx_client import AsyncOgxClient
from pytest_mock import MockerFixture

from app.endpoints.streaming_query import (
    streaming_query_endpoint_handler,
)
from configuration import AppConfig
from constants import (
    INTERRUPTED_RESPONSE_MESSAGE,
    MEDIA_TYPE_TEXT,
)
from models.api.requests import QueryRequest
from models.common.moderation import ShieldModerationPassed
from models.common.query import Attachment
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import (
    RAGContext,
    TurnSummary,
)
from models.config import Action

INTERRUPTED_INDICATOR = f"\n\n*{INTERRUPTED_RESPONSE_MESSAGE}*"

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


class TestOLSCompatibilityIntegration:  # pylint: disable=too-few-public-methods
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


# ============================================================================
# Endpoint Handler Tests
# ============================================================================


@pytest.fixture(name="dummy_request")
def dummy_request() -> Request:
    """Dummy request fixture for testing."""
    req = Request(scope={"type": "http", "headers": []})
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
            "app.endpoints.streaming_query.build_rag_context",
            new=mocker.AsyncMock(return_value=RAGContext()),
        )

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncOgxClientHolder",
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
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.recording.record_llm_call")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_agent_response_generator",
            new=mocker.AsyncMock(return_value=(mock_generator(), mock_turn_summary)),
        )

        async def mock_generate_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_agent_response",
            side_effect=mock_generate_agent_response,
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
            "app.endpoints.streaming_query.build_rag_context",
            new=mocker.AsyncMock(return_value=RAGContext()),
        )

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncOgxClientHolder",
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
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.recording.record_llm_call")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_agent_response_generator",
            new=mocker.AsyncMock(return_value=(mock_generator(), mock_turn_summary)),
        )

        async def mock_generate_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_agent_response",
            side_effect=mock_generate_agent_response,
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
            "app.endpoints.streaming_query.build_rag_context",
            new=mocker.AsyncMock(return_value=RAGContext()),
        )
        mocker.patch(
            "app.endpoints.streaming_query.normalize_conversation_id",
            return_value="normalized_123",
        )
        mock_validate_conv = mocker.patch(
            "app.endpoints.streaming_query.validate_and_retrieve_conversation",
            return_value=mock_conversation,
        )

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncOgxClientHolder",
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
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.recording.record_llm_call")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_agent_response_generator",
            new=mocker.AsyncMock(return_value=(mock_generator(), mock_turn_summary)),
        )

        async def mock_generate_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_agent_response",
            side_effect=mock_generate_agent_response,
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
            "app.endpoints.streaming_query.build_rag_context",
            new=mocker.AsyncMock(return_value=RAGContext()),
        )
        mock_validate = mocker.patch(
            "app.endpoints.streaming_query.validate_attachments_metadata"
        )

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mocker.patch(
            "app.endpoints.streaming_query.AsyncOgxClientHolder",
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
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
        )

        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch("app.endpoints.streaming_query.recording.record_llm_call")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_agent_response_generator",
            new=mocker.AsyncMock(return_value=(mock_generator(), mock_turn_summary)),
        )

        async def mock_generate_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_agent_response",
            side_effect=mock_generate_agent_response,
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
            "app.endpoints.streaming_query.build_rag_context",
            new=mocker.AsyncMock(return_value=RAGContext()),
        )

        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_updated_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_client_holder = mocker.Mock()
        mock_client_holder.get_client.return_value = mock_client
        mock_client_holder.update_azure_token = mocker.AsyncMock(
            return_value=mock_updated_client
        )
        mocker.patch(
            "app.endpoints.streaming_query.AsyncOgxClientHolder",
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

        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("azure", "model1"),
        )
        mocker.patch(
            "app.endpoints.streaming_query.run_shield_moderation",
            new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
        )
        mocker.patch("app.endpoints.streaming_query.recording.record_llm_call")

        async def mock_generator() -> AsyncIterator[str]:
            yield "data: test\n\n"

        mock_turn_summary = TurnSummary()
        mocker.patch(
            "app.endpoints.streaming_query.retrieve_agent_response_generator",
            new=mocker.AsyncMock(return_value=(mock_generator(), mock_turn_summary)),
        )

        async def mock_generate_agent_response(
            *_args: Any, **_kwargs: Any
        ) -> AsyncIterator[str]:
            async for item in mock_generator():
                yield item

        mocker.patch(
            "app.endpoints.streaming_query.generate_agent_response",
            side_effect=mock_generate_agent_response,
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

        mock_client_holder.update_azure_token.assert_called_once()
