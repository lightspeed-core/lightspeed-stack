# pylint: disable=redefined-outer-name, too-many-locals, too-many-lines
"""Unit tests for the /responses REST API endpoint (LCORE Responses API)."""

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api import OpenAIResponseObject
from llama_stack_api.openai_responses import OpenAIResponseMessage
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient
from pytest_mock import MockerFixture

from app.endpoints.responses import (
    handle_non_streaming_response,
    handle_streaming_response,
    responses_endpoint_handler,
)
from configuration import AppConfig
from models.config import Action
from models.database.conversations import UserConversation
from models.requests import ResponsesRequest
from models.responses import ResponsesResponse
from utils.types import TurnSummary

MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)
VALID_CONV_ID = "conv_e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
VALID_CONV_ID_NORMALIZED = "e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
MODULE = "app.endpoints.responses"


def _patch_base(mocker: MockerFixture, config: AppConfig) -> None:
    """Patch configuration and mandatory checks for responses endpoint."""
    mocker.patch(f"{MODULE}.configuration", config)
    mocker.patch(f"{MODULE}.check_configuration_loaded")
    mocker.patch(f"{MODULE}.check_tokens_available")
    mocker.patch(f"{MODULE}.validate_model_provider_override")
    mocker.patch(f"{MODULE}.prepare_tools", new=mocker.AsyncMock(return_value=None))


def _patch_client(mocker: MockerFixture) -> Any:
    """Patch AsyncLlamaStackClientHolder; return (mock_client, mock_holder)."""
    mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
    mock_vector_stores = mocker.Mock()
    mock_vector_stores.list = mocker.AsyncMock(return_value=mocker.Mock(data=[]))
    mock_client.vector_stores = mock_vector_stores
    mock_holder = mocker.Mock()
    mock_holder.get_client.return_value = mock_client
    mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)
    return mock_client, mock_holder


def _patch_rag(
    mocker: MockerFixture,
    *,
    raw_chunks: list[Any] | None = None,
    scores: list[float] | None = None,
    doc_ids: list[Any] | None = None,
    pre_rag_chunks: list[Any] | None = None,
    rag_context: str = "",
) -> None:
    """Patch vector search and RAG formatting for responses endpoint."""
    # pylint: disable=too-many-arguments
    if raw_chunks is None:
        raw_chunks = []
    if scores is None:
        scores = []
    if doc_ids is None:
        doc_ids = []
    if pre_rag_chunks is None:
        pre_rag_chunks = []
    mocker.patch(
        f"{MODULE}.perform_vector_search",
        new=mocker.AsyncMock(
            return_value=(raw_chunks, scores, doc_ids, pre_rag_chunks),
        ),
    )
    mocker.patch(
        f"{MODULE}.format_rag_context_for_injection",
        return_value=rag_context,
    )
    mocker.patch(f"{MODULE}.build_message_from_static_rag")


def _patch_moderation(mocker: MockerFixture, decision: str = "passed") -> Any:
    """Patch run_shield_moderation; return mock moderation result."""
    mock_moderation = mocker.Mock()
    mock_moderation.decision = decision
    mocker.patch(
        f"{MODULE}.run_shield_moderation",
        new=mocker.AsyncMock(return_value=mock_moderation),
    )
    return mock_moderation


def _make_responses_response(
    *,
    output_text: str = "",
    conversation: str = "",
    model: str = "provider/model1",
    **kwargs: Any,
) -> ResponsesResponse:
    """Build a minimal valid ResponsesResponse for tests."""
    defaults = {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": model,
        "output": [],
        "conversation": conversation,
        "completed_at": 0,
        "output_text": output_text,
        "available_quotas": {},
    }
    defaults.update(kwargs)
    return ResponsesResponse(**defaults)


def _patch_handle_non_streaming_common(
    mocker: MockerFixture, config: AppConfig
) -> None:
    """Patch deps used by handle_non_streaming_response (blocked and success)."""
    mocker.patch(f"{MODULE}.configuration", config)
    mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
    mocker.patch(
        f"{MODULE}.get_topic_summary",
        new=mocker.AsyncMock(return_value=None),
    )
    mocker.patch(f"{MODULE}.store_query_results")


@pytest.fixture(name="dummy_request")
def dummy_request_fixture() -> Request:
    """Minimal FastAPI Request with authorized_actions for responses endpoint."""
    req = Request(scope={"type": "http", "headers": []})
    req.state.authorized_actions = {Action.QUERY, Action.READ_OTHERS_CONVERSATIONS}
    return req


@pytest.fixture(name="minimal_config")
def minimal_config_fixture() -> AppConfig:
    """Minimal AppConfig for responses endpoint tests."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "test-key",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "authorization": {"access_rules": []},
        }
    )
    return cfg


def _request_with_model_and_conv(
    input_text: str = "Hello", model: str = "provider/model1"
) -> ResponsesRequest:
    """Build request with model and conversation set (as handler does)."""
    return ResponsesRequest(
        input=input_text,
        model=model,
        conversation=VALID_CONV_ID,
    )


class TestResponsesEndpointHandler:
    """Unit tests for responses_endpoint_handler."""

    @pytest.mark.asyncio
    async def test_successful_responses_string_input_non_streaming(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful responses request with string input returns ResponsesResponse."""
        responses_request = ResponsesRequest(input="What is Kubernetes?")
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        mocker.patch(
            f"{MODULE}.create_new_conversation",
            new=mocker.AsyncMock(return_value="conv_new_123"),
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")

        mock_response = _make_responses_response(
            output_text="Kubernetes is a container orchestration platform.",
            conversation="conv_new_123",
        )
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(return_value=mock_response),
        )

        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )
        assert isinstance(response, ResponsesResponse)
        assert (
            response.output_text == "Kubernetes is a container orchestration platform."
        )
        assert response.conversation == "conv_new_123"

    @pytest.mark.asyncio
    async def test_responses_with_conversation_validates_and_retrieves(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that providing conversation ID calls validate_and_retrieve_conversation."""
        responses_request = ResponsesRequest(
            input="Follow-up question",
            conversation=VALID_CONV_ID,
        )
        _patch_base(mocker, minimal_config)
        mock_user_conv = mocker.Mock(spec=UserConversation)
        mock_user_conv.id = VALID_CONV_ID_NORMALIZED
        mock_validate = mocker.patch(
            f"{MODULE}.validate_and_retrieve_conversation",
            return_value=mock_user_conv,
        )
        _patch_client(mocker)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{MODULE}.to_llama_stack_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(
                return_value=_make_responses_response(
                    output_text="Answer",
                    conversation=VALID_CONV_ID_NORMALIZED,
                )
            ),
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_responses_model_not_configured_raises_404(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that unconfigured model leads to 404 HTTPException."""
        responses_request = ResponsesRequest(input="Hello", model="provider/unknown")
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        mocker.patch(
            f"{MODULE}.create_new_conversation",
            new=mocker.AsyncMock(return_value="conv_new"),
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/unknown"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=False),
        )
        mocker.patch(
            f"{MODULE}.extract_provider_and_model_from_model_id",
            return_value=("provider", "unknown"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await responses_endpoint_handler(
                request=dummy_request,
                responses_request=responses_request,
                auth=MOCK_AUTH,
                _mcp_headers={},
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_responses_streaming_returns_streaming_response(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that stream=True delegates to handle_streaming_response."""
        responses_request = ResponsesRequest(input="Stream this", stream=True)
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        mocker.patch(
            f"{MODULE}.create_new_conversation",
            new=mocker.AsyncMock(return_value="conv_new"),
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")
        mock_streaming = mocker.Mock(spec=StreamingResponse)
        mocker.patch(
            f"{MODULE}.handle_streaming_response",
            new=mocker.AsyncMock(return_value=mock_streaming),
        )

        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )
        assert response is mock_streaming

    @pytest.mark.asyncio
    async def test_responses_azure_token_refresh(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that Azure token refresh is called when model starts with azure."""
        responses_request = ResponsesRequest(input="Hi", model="azure/some-model")
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        mocker.patch(
            f"{MODULE}.create_new_conversation",
            new=mocker.AsyncMock(return_value="conv_new"),
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="azure/some-model"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        mock_azure = mocker.Mock()
        mock_azure.is_entra_id_configured = True
        mock_azure.is_token_expired = True
        mock_azure.refresh_token.return_value = True
        mocker.patch(f"{MODULE}.AzureEntraIDManager", return_value=mock_azure)
        updated_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_update_token = mocker.patch(
            f"{MODULE}.update_azure_token",
            new=mocker.AsyncMock(return_value=updated_client),
        )
        _patch_rag(mocker)
        _patch_moderation(mocker, decision="passed")
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(
                return_value=_make_responses_response(
                    output_text="Ok",
                    conversation="conv_new",
                    model="azure/some-model",
                )
            ),
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )
        mock_update_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_responses_structured_input_appends_rag_message(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that non-string input uses extract_text and appends RAG message."""
        structured_input: list[Any] = [
            OpenAIResponseMessage(role="user", content="What is K8s?"),
        ]
        responses_request = ResponsesRequest(
            input=cast(Any, structured_input),
        )
        _patch_base(mocker, minimal_config)
        _patch_client(mocker)
        mocker.patch(
            f"{MODULE}.create_new_conversation",
            new=mocker.AsyncMock(return_value="conv_new"),
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker, rag_context="\n\nRelevant documentation:\nDoc1")
        mock_build_message = mocker.patch(f"{MODULE}.build_message_from_static_rag")
        _patch_moderation(mocker, decision="passed")
        mocker.patch(
            f"{MODULE}.handle_non_streaming_response",
            new=mocker.AsyncMock(
                return_value=_make_responses_response(
                    output_text="K8s is Kubernetes.",
                    conversation="conv_new",
                )
            ),
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        mock_build_message.assert_called_once_with("\n\nRelevant documentation:\nDoc1")

    @pytest.mark.asyncio
    async def test_responses_blocked_with_conversation_appends_refusal(
        self,
        dummy_request: Request,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Blocked moderation with conversation calls append_turn_items_to_conversation."""
        responses_request = ResponsesRequest(
            input="Bad",
            conversation=VALID_CONV_ID,
            stream=False,
            model="provider/model1",
        )
        _patch_base(mocker, minimal_config)
        mock_user_conv = mocker.Mock(spec=UserConversation)
        mock_user_conv.id = VALID_CONV_ID_NORMALIZED
        mocker.patch(
            f"{MODULE}.validate_and_retrieve_conversation",
            return_value=mock_user_conv,
        )
        _patch_client(mocker)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{MODULE}.to_llama_stack_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            f"{MODULE}.select_model_for_responses",
            new=mocker.AsyncMock(return_value="provider/model1"),
        )
        mocker.patch(
            f"{MODULE}.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )
        _patch_rag(mocker)
        mock_moderation = _patch_moderation(mocker, decision="blocked")
        mock_moderation.message = "Blocked"
        mock_moderation.moderation_id = "resp_blocked_123"
        mock_moderation.refusal_response = OpenAIResponseMessage(
            type="message", role="assistant", content="Blocked"
        )
        mock_append = mocker.patch(
            f"{MODULE}.append_turn_items_to_conversation",
            new=mocker.AsyncMock(),
        )
        # Let real handle_non_streaming_response run (stream=False) so it calls
        # append_turn_items_to_conversation
        mocker.patch(f"{MODULE}.store_query_results")
        # Response build may omit model from model_dump(); ensure it is present for validation
        real_validate = ResponsesResponse.model_validate

        def _validate_with_model(data: dict) -> Any:
            if "model" not in data:
                data = {**data, "model": "provider/model1"}
            return real_validate(data)

        mocker.patch.object(
            ResponsesResponse,
            "model_validate",
            side_effect=_validate_with_model,
        )

        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=responses_request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        mock_append.assert_called_once()


class TestHandleNonStreamingResponse:
    """Unit tests for handle_non_streaming_response."""

    @pytest.mark.asyncio
    async def test_handle_non_streaming_blocked_returns_refusal(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that blocked moderation returns response with refusal message."""
        request = _request_with_model_and_conv("Bad input")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "blocked"
        mock_moderation.message = "Content blocked"
        mock_refusal = mocker.Mock(spec=OpenAIResponseMessage)
        mock_refusal.type = "message"
        mock_refusal.role = "assistant"
        mock_refusal.content = "Content blocked"
        mock_moderation.refusal_response = mock_refusal

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mock_client.conversations.items.create = mocker.AsyncMock()
        mock_api_response = mocker.Mock()
        mock_api_response.output = [mock_refusal]
        mock_api_response.model_dump.return_value = {
            "id": "resp_blocked",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": "provider/model1",
            "output": [mock_refusal],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
        mocker.patch(
            f"{MODULE}.OpenAIResponseObject.model_construct",
            return_value=mock_api_response,
        )

        response = await handle_non_streaming_response(
            client=mock_client,
            request=request,
            auth=MOCK_AUTH,
            input_text="Bad input",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            static_rag_docs=[],
        )
        assert isinstance(response, ResponsesResponse)
        assert response.output_text == "Content blocked"
        mock_client.responses.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_non_streaming_success_returns_response(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test successful handle_non_streaming_response returns ResponsesResponse."""
        request = _request_with_model_and_conv("Hello")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mock_api_response = mocker.Mock(spec=OpenAIResponseObject)
        mock_api_response.output = []
        mock_api_response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        mock_api_response.model_dump.return_value = {
            "id": "resp_1",
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": "provider/model1",
            "output": [],
            "usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "total_tokens": 3,
            },
        }
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_api_response)

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.extract_token_usage",
            return_value=mocker.Mock(input_tokens=1, output_tokens=2),
        )
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=mocker.Mock(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.extract_text_from_response_items",
            return_value="Model reply",
        )
        mocker.patch(
            f"{MODULE}.extract_vector_store_ids_from_tools",
            return_value=[],
        )
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        response = await handle_non_streaming_response(
            client=mock_client,
            request=request,
            auth=MOCK_AUTH,
            input_text="Hello",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            static_rag_docs=[],
        )

        assert isinstance(response, ResponsesResponse)
        assert response.output_text == "Model reply"
        mock_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_non_streaming_context_length_raises_413(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that RuntimeError with context_length raises 413."""
        request = _request_with_model_and_conv("Long input")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        with pytest.raises(HTTPException) as exc_info:
            await handle_non_streaming_response(
                client=mock_client,
                request=request,
                auth=MOCK_AUTH,
                input_text="Long input",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                static_rag_docs=[],
            )

        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_handle_non_streaming_connection_error_raises_503(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that APIConnectionError raises 503."""
        request = _request_with_model_and_conv("Hi")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed",
                request=mocker.Mock(),
            )
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        with pytest.raises(HTTPException) as exc_info:
            await handle_non_streaming_response(
                client=mock_client,
                request=request,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                static_rag_docs=[],
            )

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_handle_non_streaming_api_status_error_raises_http(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that APIStatusError is handled and re-raised as HTTPException."""
        request = _request_with_model_and_conv("Hi")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="API error",
                response=mocker.Mock(request=None),
                body=None,
            )
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{MODULE}.handle_known_apistatus_errors",
            return_value=mocker.Mock(
                model_dump=lambda: {
                    "status_code": 500,
                    "detail": {"response": "Error", "cause": "API error"},
                }
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await handle_non_streaming_response(
                client=mock_client,
                request=request,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                static_rag_docs=[],
            )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_handle_non_streaming_runtime_error_without_context_reraises(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test that RuntimeError without context_length is re-raised."""
        request = _request_with_model_and_conv("Hi")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("Some other error")
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        _patch_handle_non_streaming_common(mocker, minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )

        with pytest.raises(RuntimeError, match="Some other error"):
            await handle_non_streaming_response(
                client=mock_client,
                request=request,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                static_rag_docs=[],
            )


class TestHandleStreamingResponse:
    """Unit tests for handle_streaming_response and streaming generators."""

    @pytest.mark.asyncio
    async def test_handle_streaming_blocked_returns_sse_consumes_shield_generator(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming with blocked moderation yields SSE from shield_violation_generator."""
        request = _request_with_model_and_conv("Bad", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "blocked"
        mock_moderation.message = "Blocked"
        mock_moderation.moderation_id = "mod_123"
        mock_refusal = OpenAIResponseMessage(
            role="assistant", content="Blocked", type="message"
        )
        mock_moderation.refusal_response = mock_refusal

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")

        mock_client.conversations.items.create = mocker.AsyncMock()
        response = await handle_streaming_response(
            client=mock_client,
            request=request,
            auth=MOCK_AUTH,
            input_text="Bad",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            static_rag_docs=[],
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        collected: list[str] = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)
        assert "event: response.created" in body
        assert "event: response.output_item.added" in body
        assert "event: response.output_item.done" in body
        assert "event: response.completed" in body
        assert "[DONE]" in body
        mock_client.responses.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_streaming_success_returns_sse_consumes_response_generator(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming with passed moderation yields SSE from response_generator."""
        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mock_chunk = mocker.Mock()
        mock_chunk.type = "response.completed"
        mock_chunk.response = mocker.Mock()
        mock_chunk.response.usage = mocker.Mock(
            input_tokens=1, output_tokens=2, total_tokens=3
        )
        mock_chunk.model_dump.return_value = {
            "type": "response.completed",
            "response": {"id": "r1", "usage": {"input_tokens": 1}},
        }

        async def mock_stream() -> Any:
            yield mock_chunk

        mock_client.responses.create = mocker.AsyncMock(return_value=mock_stream())

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(f"{MODULE}.get_available_quotas", return_value={})
        mocker.patch(f"{MODULE}.extract_token_usage", return_value=mocker.Mock())
        mocker.patch(f"{MODULE}.consume_query_tokens")
        mocker.patch(f"{MODULE}.extract_vector_store_ids_from_tools", return_value=[])
        mocker.patch(
            f"{MODULE}.build_turn_summary",
            return_value=TurnSummary(referenced_documents=[]),
        )
        mocker.patch(
            f"{MODULE}.get_topic_summary",
            new=mocker.AsyncMock(return_value=None),
        )
        mocker.patch(f"{MODULE}.store_query_results")
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        mock_holder = mocker.Mock()
        mock_holder.get_client.return_value = mock_client
        mocker.patch(f"{MODULE}.AsyncLlamaStackClientHolder", return_value=mock_holder)
        response = await handle_streaming_response(
            client=mock_client,
            request=request,
            auth=MOCK_AUTH,
            input_text="Hi",
            started_at=datetime.now(UTC),
            moderation_result=mock_moderation,
            static_rag_docs=[],
        )
        assert isinstance(response, StreamingResponse)
        collected = []
        async for part in response.body_iterator:
            chunk_str = (
                part.decode("utf-8")
                if isinstance(part, bytes)
                else (part if isinstance(part, str) else bytes(part).decode("utf-8"))
            )
            collected.append(chunk_str)
        body = "".join(collected)
        assert "response.completed" in body or "event:" in body
        assert "[DONE]" in body
        mock_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_streaming_context_length_raises_413(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming raises 413 when create raises RuntimeError context_length."""
        request = _request_with_model_and_conv("Long", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        with pytest.raises(HTTPException) as exc_info:
            await handle_streaming_response(
                client=mock_client,
                request=request,
                auth=MOCK_AUTH,
                input_text="Long",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                static_rag_docs=[],
            )
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_handle_streaming_connection_error_raises_503(
        self,
        minimal_config: AppConfig,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming raises 503 when create raises APIConnectionError."""
        request = _request_with_model_and_conv("Hi", model="provider/model1")
        mock_client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(
                message="Connection failed",
                request=mocker.Mock(),
            )
        )
        mock_moderation = mocker.Mock()
        mock_moderation.decision = "passed"

        mocker.patch(f"{MODULE}.configuration", minimal_config)
        mocker.patch(
            f"{MODULE}.normalize_conversation_id",
            return_value=VALID_CONV_ID_NORMALIZED,
        )
        with pytest.raises(HTTPException) as exc_info:
            await handle_streaming_response(
                client=mock_client,
                request=request,
                auth=MOCK_AUTH,
                input_text="Hi",
                started_at=datetime.now(UTC),
                moderation_result=mock_moderation,
                static_rag_docs=[],
            )

        assert exc_info.value.status_code == 503
