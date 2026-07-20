# pylint: disable=redefined-outer-name, import-error, too-many-locals
# pyright: reportCallIssue=false
"""Unit tests for the /streaming_query (v2) endpoint handler."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from ogx_client import AsyncOgxClient
from pytest_mock import MockerFixture

from app.endpoints.streaming_query import streaming_query_endpoint_handler
from configuration import AppConfig
from constants import MEDIA_TYPE_TEXT
from models.api.requests import QueryRequest
from models.common.query import Attachment
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import (
    RAGContext,
    ReferencedDocument,
    TurnSummary,
)
from models.config import Action
from models.database.conversations import UserConversation

MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)


@pytest.fixture(name="setup_configuration")
def setup_configuration_fixture() -> AppConfig:
    """Set up configuration for tests.

    Returns:
        AppConfig: Test configuration with noop conversation cache.
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


@pytest.fixture(name="dummy_request")
def create_dummy_request() -> Request:
    """Create a minimal FastAPI Request for unit tests.

    Returns:
        Request: Request with all actions authorized.
    """
    req = Request(scope={"type": "http", "headers": []})
    req.state.authorized_actions = set(Action)
    return req


async def _mock_sse_generator() -> AsyncIterator[str]:
    """Yield a single SSE event for mocked agent streaming."""
    yield "data: test\n\n"


def _patch_streaming_handler_deps(  # pylint: disable=too-many-arguments
    mocker: MockerFixture,
    setup_configuration: AppConfig,
    *,
    responses_params: Any | None = None,
    turn_summary: TurnSummary | None = None,
    inline_rag_context: RAGContext | None = None,
    azure_manager: Any | None = None,
    client_holder: Any | None = None,
) -> tuple[Any, Any]:
    """Patch common streaming_query handler dependencies for the non-compaction path.

    Returns:
        tuple: ``(mock_generate_agent_response, mock_client_holder)``.
    """
    mocker.patch("app.endpoints.streaming_query.configuration", setup_configuration)
    mocker.patch("app.endpoints.streaming_query.check_configuration_loaded")
    mocker.patch(
        "app.endpoints.streaming_query.check_mcp_auth",
        new=mocker.AsyncMock(),
    )
    mocker.patch("app.endpoints.streaming_query.check_tokens_available")
    mocker.patch("app.endpoints.streaming_query.validate_model_provider_override")
    mocker.patch(
        "app.endpoints.streaming_query.needs_compaction_path",
        new=mocker.AsyncMock(return_value=False),
    )
    mocker.patch(
        "app.endpoints.streaming_query.build_rag_context",
        new=mocker.AsyncMock(return_value=inline_rag_context or RAGContext()),
    )
    mocker.patch(
        "app.endpoints.streaming_query.normalize_conversation_id",
        return_value="123",
    )
    mocker.patch(
        "app.endpoints.streaming_query.get_suid",
        return_value="req-test-id",
    )
    mocker.patch(
        "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
        return_value=("provider1", "model1"),
    )
    mocker.patch("app.endpoints.streaming_query.recording.record_llm_call")

    if client_holder is None:
        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        client_holder = mocker.Mock()
        client_holder.get_client.return_value = mock_client
    mocker.patch(
        "app.endpoints.streaming_query.AsyncOgxClientHolder",
        return_value=client_holder,
    )

    if responses_params is None:
        responses_params = mocker.Mock(spec=ResponsesApiParams)
        responses_params.model = "provider1/model1"
        responses_params.conversation = "conv_123"
        responses_params.tools = None
        responses_params.model_dump.return_value = {
            "input": "test",
            "model": "provider1/model1",
        }
    mocker.patch(
        "app.endpoints.streaming_query.prepare_responses_params",
        new=mocker.AsyncMock(return_value=responses_params),
    )

    if azure_manager is None:
        mocker.patch("app.endpoints.streaming_query.AzureEntraIDManager")
    else:
        mocker.patch(
            "app.endpoints.streaming_query.AzureEntraIDManager",
            return_value=azure_manager,
        )

    summary = turn_summary if turn_summary is not None else TurnSummary()
    mocker.patch(
        "app.endpoints.streaming_query.retrieve_agent_response_generator",
        new=mocker.AsyncMock(return_value=(_mock_sse_generator(), summary)),
    )

    mock_generate = mocker.patch(
        "app.endpoints.streaming_query.generate_agent_response",
        side_effect=lambda **_kwargs: _mock_sse_generator(),
    )
    return mock_generate, client_holder


class TestOLSCompatibilityIntegration:  # pylint: disable=too-few-public-methods
    """OLS-compatible request field validation."""

    def test_media_type_validation(self) -> None:
        """Test that media type validation works correctly."""
        valid_request = QueryRequest(query="test", media_type="application/json")
        assert valid_request.media_type == "application/json"

        valid_request = QueryRequest(query="test", media_type="text/plain")
        assert valid_request.media_type == "text/plain"

        with pytest.raises(ValueError, match="media_type must be either"):
            QueryRequest(query="test", media_type="invalid/type")


class TestStreamingQueryEndpointHandler:
    """High-level tests for streaming_query_endpoint_handler."""

    @pytest.mark.asyncio
    async def test_successful_streaming_query(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful streaming query returns an SSE StreamingResponse."""
        _patch_streaming_handler_deps(mocker, setup_configuration)

        response = await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(query="What is Kubernetes?"),
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_streaming_query_text_media_type_header(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query uses plain text media type when requested."""
        _patch_streaming_handler_deps(mocker, setup_configuration)

        response = await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(
                query="What is Kubernetes?", media_type=MEDIA_TYPE_TEXT
            ),
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == MEDIA_TYPE_TEXT

    @pytest.mark.asyncio
    async def test_streaming_query_merges_inline_and_tool_referenced_documents(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test handler merges inline and tool RAG documents before streaming."""
        inline_doc = ReferencedDocument(
            doc_title="Inline Doc", document_id="inline_doc_1"
        )
        tool_doc = ReferencedDocument(doc_title="Tool Doc", document_id="tool_doc_1")
        turn_summary = TurnSummary(referenced_documents=[tool_doc])

        mock_generate, _ = _patch_streaming_handler_deps(
            mocker,
            setup_configuration,
            turn_summary=turn_summary,
            inline_rag_context=RAGContext(
                context_text="",
                referenced_documents=[inline_doc],
            ),
        )

        await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(query="What is Kubernetes?"),
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_generate.assert_called_once()
        passed_summary: TurnSummary = mock_generate.call_args.kwargs["turn_summary"]
        assert [doc.document_id for doc in passed_summary.referenced_documents] == [
            "inline_doc_1",
            "tool_doc_1",
        ]

    @pytest.mark.asyncio
    async def test_streaming_query_with_conversation(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query retrieves an existing conversation."""
        _patch_streaming_handler_deps(mocker, setup_configuration)
        mock_validate_conv = mocker.patch(
            "app.endpoints.streaming_query.validate_and_retrieve_conversation",
            return_value=mocker.Mock(spec=UserConversation),
        )

        await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(
                query="What is Kubernetes?",
                conversation_id="123e4567-e89b-12d3-a456-426614174000",
            ),
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_validate_conv.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_query_with_attachments(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query validates attachments metadata."""
        _patch_streaming_handler_deps(mocker, setup_configuration)
        mock_validate = mocker.patch(
            "app.endpoints.streaming_query.validate_attachments_metadata"
        )
        attachments = [
            Attachment(
                attachment_type="log",
                content_type="text/plain",
                content="log content",
            )
        ]

        await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(
                query="What is Kubernetes?",
                attachments=attachments,
            ),
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        mock_validate.assert_called_once_with(attachments)

    @pytest.mark.asyncio
    async def test_streaming_query_azure_token_refresh(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming query refreshes Azure token when needed."""
        mock_client = mocker.AsyncMock(spec=AsyncOgxClient)
        mock_updated_client = mocker.AsyncMock(spec=AsyncOgxClient)
        client_holder = mocker.Mock()
        client_holder.get_client.return_value = mock_client
        client_holder.update_azure_token = mocker.AsyncMock(
            return_value=mock_updated_client
        )

        responses_params = mocker.Mock(spec=ResponsesApiParams)
        responses_params.model = "azure/model1"
        responses_params.conversation = "conv_123"
        responses_params.tools = None
        responses_params.model_dump.return_value = {
            "input": "test",
            "model": "azure/model1",
        }

        azure_manager = mocker.Mock()
        azure_manager.is_entra_id_configured = True
        azure_manager.is_token_expired = True
        azure_manager.refresh_token.return_value = True

        _patch_streaming_handler_deps(
            mocker,
            setup_configuration,
            responses_params=responses_params,
            azure_manager=azure_manager,
            client_holder=client_holder,
        )
        mocker.patch(
            "app.endpoints.streaming_query.extract_provider_and_model_from_model_id",
            return_value=("azure", "model1"),
        )

        await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(query="What is Kubernetes?"),
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        client_holder.update_azure_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_query_uses_compaction_path_when_needed(
        self,
        dummy_request: Request,
        setup_configuration: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test handler uses compaction streaming path when compaction is needed."""
        mock_generate, _ = _patch_streaming_handler_deps(mocker, setup_configuration)
        mock_retrieve = mocker.patch(
            "app.endpoints.streaming_query.retrieve_agent_response_generator",
            new=mocker.AsyncMock(),
        )
        mocker.patch(
            "app.endpoints.streaming_query.needs_compaction_path",
            new=mocker.AsyncMock(return_value=True),
        )
        mock_compaction = mocker.patch(
            "app.endpoints.streaming_query.generate_response_with_compaction",
            return_value=_mock_sse_generator(),
        )

        response = await streaming_query_endpoint_handler(
            request=dummy_request,
            query_request=QueryRequest(query="What is Kubernetes?"),
            auth=MOCK_AUTH,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)
        mock_compaction.assert_called_once()
        mock_retrieve.assert_not_called()
        mock_generate.assert_not_called()
