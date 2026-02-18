# pylint: disable=too-many-lines,too-many-arguments,too-many-positional-arguments
"""Unit tests for the /responses REST API endpoint."""

from typing import Any, AsyncIterator

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from llama_stack_api.openai_responses import OpenAIResponseMessage
from llama_stack_client import (
    APIConnectionError,
    APIStatusError as LLSApiStatusError,
    AsyncLlamaStackClient,
)
from llama_stack_client.types import ResponseObject, ResponseObjectStream
from llama_stack_client.types.response_object import Usage

from pytest_mock import MockerFixture

from app.endpoints.responses import (
    generate_response,
    handle_non_streaming_response,
    handle_streaming_response,
    responses_endpoint_handler,
    response_generator,
    shield_violation_generator,
)
from configuration import AppConfig
from models.config import Action
from models.database.conversations import UserConversation
from models.responses_api_types import ResponsesRequest, ResponsesResponse
from utils.types import ShieldModerationResult, TurnSummary

MOCK_AUTH = (
    "00000001-0001-0001-0001-000000000001",
    "mock_username",
    False,
    "mock_token",
)

VALID_CONV_ID = "conv_0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e"


@pytest.fixture(name="dummy_request")
def dummy_request_fixture() -> Request:
    """Create dummy request fixture."""
    req = Request(scope={"type": "http"})
    req.state.authorized_actions = set()
    return req


@pytest.fixture(name="test_config")
def test_config_fixture() -> AppConfig:
    """Create test configuration."""
    config = AppConfig()
    config.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080, "auth_enabled": False},
            "llama_stack": {"api_key": "test-key", "url": "http://test.com"},
            "user_data_collection": {"transcripts_enabled": False},
            "mcp_servers": [],
            "conversation_cache": {"type": "noop"},
        }
    )
    return config


@pytest.fixture(name="mock_client")
def mock_client_fixture(mocker: MockerFixture) -> Any:
    """Create mock Llama Stack client."""
    client = mocker.AsyncMock(spec=AsyncLlamaStackClient)
    mock_response = mocker.Mock(spec=ResponsesResponse)
    mock_response.id = "resp-123"
    mock_response.status = "completed"
    mock_response.usage = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
    mock_response.output = []
    client.responses.create = mocker.AsyncMock(return_value=mock_response)
    return client


@pytest.fixture(name="mock_client_holder")
def mock_client_holder_fixture(mocker: MockerFixture, mock_client: Any) -> Any:
    """Create mock client holder."""
    holder = mocker.Mock()
    holder.get_client.return_value = mock_client
    return holder


def _setup_base_patches(mocker: MockerFixture, test_config: AppConfig) -> None:
    """Set up common patches for endpoint handler tests."""
    mocker.patch("app.endpoints.responses.configuration", test_config)
    mocker.patch("app.endpoints.responses.check_configuration_loaded")
    mocker.patch("app.endpoints.responses.check_tokens_available")


def _create_moderation_result(
    blocked: bool, refusal_response: Any = None
) -> ShieldModerationResult:
    """Create moderation result."""
    return ShieldModerationResult(
        blocked=blocked,
        refusal_response=refusal_response,
        moderation_id="mod-123" if blocked else None,
        message="Blocked" if blocked else None,
    )


class TestResponsesEndpointHandler:
    """Tests for responses_endpoint_handler."""

    @pytest.mark.asyncio
    async def test_non_streaming_without_conversation(
        self,
        dummy_request: Request,
        test_config: AppConfig,
        mock_client_holder: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test non-streaming response without conversation."""
        _setup_base_patches(mocker, test_config)
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.responses.select_model_for_responses",
            return_value="test-model",
        )
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation",
            return_value=_create_moderation_result(blocked=False),
        )
        mocker.patch(
            "app.endpoints.responses.handle_non_streaming_response",
            return_value=mocker.Mock(spec=ResponsesResponse),
        )

        request = ResponsesRequest(input="Test", stream=False)
        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        assert isinstance(response, ResponsesResponse)

    @pytest.mark.asyncio
    async def test_non_streaming_with_conversation(
        self,
        dummy_request: Request,
        test_config: AppConfig,
        mock_client_holder: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test non-streaming response with conversation."""
        _setup_base_patches(mocker, test_config)
        mock_conv = mocker.Mock(spec=UserConversation)
        mock_conv.id = "conv-123"
        mocker.patch(
            "app.endpoints.responses.validate_and_retrieve_conversation",
            return_value=mock_conv,
        )
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            "app.endpoints.responses.to_llama_stack_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.responses.select_model_for_responses",
            return_value="test-model",
        )
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation",
            return_value=_create_moderation_result(blocked=False),
        )
        mocker.patch(
            "app.endpoints.responses.handle_non_streaming_response",
            return_value=mocker.Mock(spec=ResponsesResponse),
        )

        request = ResponsesRequest(
            input="Test", conversation=VALID_CONV_ID, stream=False
        )
        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        assert isinstance(response, ResponsesResponse)

    @pytest.mark.asyncio
    async def test_streaming_without_conversation(
        self,
        dummy_request: Request,
        test_config: AppConfig,
        mock_client_holder: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test streaming response without conversation."""
        _setup_base_patches(mocker, test_config)
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.responses.select_model_for_responses",
            return_value="test-model",
        )
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation",
            return_value=_create_moderation_result(blocked=False),
        )
        mocker.patch(
            "app.endpoints.responses.handle_streaming_response",
            return_value=mocker.Mock(spec=StreamingResponse),
        )

        request = ResponsesRequest(input="Test", stream=True)
        response = await responses_endpoint_handler(
            request=dummy_request,
            responses_request=request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)

    @pytest.mark.asyncio
    async def test_with_model_override(
        self,
        dummy_request: Request,
        test_config: AppConfig,
        mock_client_holder: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test handler with model override permission."""
        dummy_request.state.authorized_actions = {Action.MODEL_OVERRIDE}
        _setup_base_patches(mocker, test_config)
        mock_validate = mocker.patch(
            "app.endpoints.responses.validate_model_override_permissions"
        )
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation",
            return_value=_create_moderation_result(blocked=False),
        )
        mocker.patch(
            "app.endpoints.responses.handle_non_streaming_response",
            return_value=mocker.Mock(spec=ResponsesResponse),
        )

        request = ResponsesRequest(input="Test", model="custom-model", stream=False)
        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_select_model(
        self,
        dummy_request: Request,
        test_config: AppConfig,
        mock_client_holder: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test handler auto-selects model when not provided."""
        _setup_base_patches(mocker, test_config)
        mock_select = mocker.patch(
            "app.endpoints.responses.select_model_for_responses",
            return_value="auto-model",
        )
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation",
            return_value=_create_moderation_result(blocked=False),
        )
        mocker.patch(
            "app.endpoints.responses.handle_non_streaming_response",
            return_value=mocker.Mock(spec=ResponsesResponse),
        )

        request = ResponsesRequest(input="Test", stream=False)
        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        mock_select.assert_called_once()

    @pytest.mark.asyncio
    async def test_azure_token_refresh(
        self,
        dummy_request: Request,
        test_config: AppConfig,
        mock_client_holder: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test Azure token refresh when needed."""
        _setup_base_patches(mocker, test_config)
        mock_azure = mocker.patch("app.endpoints.responses.AzureEntraIDManager")
        mock_instance = mock_azure.return_value
        mock_instance.is_entra_id_configured = True
        mock_instance.is_token_expired = True
        mock_instance.refresh_token.return_value = True
        mock_update = mocker.patch(
            "app.endpoints.responses.update_azure_token",
            return_value=mock_client_holder.get_client(),
        )
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation",
            return_value=_create_moderation_result(blocked=False),
        )
        mocker.patch(
            "app.endpoints.responses.handle_non_streaming_response",
            return_value=mocker.Mock(spec=ResponsesResponse),
        )

        request = ResponsesRequest(input="Test", model="azure/test-model", stream=False)
        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_shield_blocked_with_conversation(
        self,
        dummy_request: Request,
        test_config: AppConfig,
        mock_client_holder: Any,
        mocker: MockerFixture,
    ) -> None:
        """Test shield blocked with conversation persists refusal."""
        _setup_base_patches(mocker, test_config)
        mock_conv = mocker.Mock(spec=UserConversation)
        mock_conv.id = "conv-123"
        mocker.patch(
            "app.endpoints.responses.validate_and_retrieve_conversation",
            return_value=mock_conv,
        )
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            "app.endpoints.responses.to_llama_stack_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            "app.endpoints.responses.AsyncLlamaStackClientHolder",
            return_value=mock_client_holder,
        )
        mocker.patch(
            "app.endpoints.responses.select_model_for_responses",
            return_value="test-model",
        )
        refusal = OpenAIResponseMessage(
            type="message", role="assistant", content="Cannot help"
        )
        mocker.patch(
            "app.endpoints.responses.run_shield_moderation",
            return_value=_create_moderation_result(
                blocked=True, refusal_response=refusal
            ),
        )
        mock_append = mocker.patch(
            "app.endpoints.responses.append_refused_turn_to_conversation"
        )
        mocker.patch(
            "app.endpoints.responses.handle_non_streaming_response",
            return_value=mocker.Mock(spec=ResponsesResponse),
        )

        request = ResponsesRequest(
            input="Bad input", conversation=VALID_CONV_ID, stream=False
        )
        await responses_endpoint_handler(
            request=dummy_request,
            responses_request=request,
            auth=MOCK_AUTH,
            _mcp_headers={},
        )

        mock_append.assert_called_once()


class TestHandleStreamingResponse:
    """Tests for handle_streaming_response."""

    @pytest.mark.asyncio
    async def test_shield_blocked(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test streaming response when shield blocks."""
        refusal = OpenAIResponseMessage(
            type="message", role="assistant", content="Cannot help"
        )
        moderation_result = _create_moderation_result(
            blocked=True, refusal_response=refusal
        )
        request = ResponsesRequest(
            input="Test", conversation=VALID_CONV_ID, stream=True
        )

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )

        response = await handle_streaming_response(
            client=mocker.AsyncMock(),
            request=request,
            user_id="user-123",
            moderation_result=moderation_result,
            started_at="2024-01-01T00:00:00Z",
            user_conversation=None,
            input_text="Test",
            _skip_userid_check=False,
        )

        assert isinstance(response, StreamingResponse)

    @pytest.mark.asyncio
    async def test_successful_streaming(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test successful streaming response."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(
            input="Test", conversation=VALID_CONV_ID, model="test-model", stream=True
        )

        async def mock_stream() -> AsyncIterator[ResponseObjectStream]:
            mock_chunk = mocker.Mock(spec=ResponseObjectStream)
            mock_chunk.type = "response.completed"
            mock_response_obj = mocker.Mock(spec=ResponseObject)
            mock_response_obj.usage = Usage(
                input_tokens=10, output_tokens=5, total_tokens=15
            )
            mock_response_obj.model_dump = mocker.Mock(
                return_value={
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                    }
                }
            )

            def model_dump_side_effect(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {
                    "type": "response.completed",
                    "response": {
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "total_tokens": 15,
                        },
                    },
                }

            mock_chunk.model_dump = mocker.Mock(side_effect=model_dump_side_effect)
            mock_chunk.response = mock_response_obj
            yield mock_chunk

        mock_client = mocker.AsyncMock()
        mock_client.responses.create.return_value = mock_stream()

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch("app.endpoints.responses.consume_query_tokens", return_value=None)

        response = await handle_streaming_response(
            client=mock_client,
            request=request,
            user_id="user-123",
            moderation_result=moderation_result,
            started_at="2024-01-01T00:00:00Z",
            user_conversation=None,
            input_text="Test",
            _skip_userid_check=False,
        )

        assert isinstance(response, StreamingResponse)

    @pytest.mark.asyncio
    async def test_prompt_too_long_error(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test streaming response handles prompt too long error."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(
            input="x" * 100000,
            conversation=VALID_CONV_ID,
            model="test-model",
            stream=True,
        )

        mock_client = mocker.AsyncMock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )

        mocker.patch("app.endpoints.responses.configuration", test_config)

        with pytest.raises(HTTPException) as exc_info:
            await handle_streaming_response(
                client=mock_client,
                request=request,
                user_id="user-123",
                moderation_result=moderation_result,
                started_at="2024-01-01T00:00:00Z",
                user_conversation=None,
                input_text="x" * 100000,
                _skip_userid_check=False,
            )
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_connection_error(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test streaming response handles connection error."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(
            input="Test", conversation=VALID_CONV_ID, model="test-model", stream=True
        )

        mock_client = mocker.AsyncMock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(request=mocker.Mock())
        )

        mocker.patch("app.endpoints.responses.configuration", test_config)

        with pytest.raises(HTTPException) as exc_info:
            await handle_streaming_response(
                client=mock_client,
                request=request,
                user_id="user-123",
                moderation_result=moderation_result,
                started_at="2024-01-01T00:00:00Z",
                user_conversation=None,
                input_text="Test",
                _skip_userid_check=False,
            )
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_api_status_error(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test streaming response handles API status error."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(
            input="Test", conversation=VALID_CONV_ID, model="test-model", stream=True
        )

        mock_client = mocker.AsyncMock()
        error = LLSApiStatusError(
            message="API Error", response=mocker.Mock(request=None), body=None
        )
        error.status_code = 429
        mock_client.responses.create = mocker.AsyncMock(side_effect=error)

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mock_error_response = mocker.Mock()
        mock_error_response.status_code = 429
        mock_error_response.model_dump = mocker.Mock(
            return_value={"status_code": 429, "detail": "Quota exceeded"}
        )
        mocker.patch(
            "app.endpoints.responses.handle_known_apistatus_errors",
            return_value=mock_error_response,
        )

        with pytest.raises(HTTPException) as exc_info:
            await handle_streaming_response(
                client=mock_client,
                request=request,
                user_id="user-123",
                moderation_result=moderation_result,
                started_at="2024-01-01T00:00:00Z",
                user_conversation=None,
                input_text="Test",
                _skip_userid_check=False,
            )
        assert exc_info.value.status_code == 429


class TestShieldViolationGenerator:
    """Tests for shield_violation_generator."""

    @pytest.mark.asyncio
    async def test_generates_all_events(self, mocker: MockerFixture) -> None:
        """Test shield violation generator yields all required events."""
        refusal = OpenAIResponseMessage(
            type="message", role="assistant", content="Cannot help"
        )

        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            "app.endpoints.responses.extract_text_from_response_output_item",
            return_value="Cannot help",
        )

        events = []
        async for event in shield_violation_generator(
            refusal_response=refusal,
            conversation_id=VALID_CONV_ID,
            response_id="resp-123",
            created_at=1234567890,
            mirrored_params={"model": "test-model"},
            available_quotas={"tokens": 100},
        ):
            events.append(event)

        assert len(events) == 5
        assert "event: response.created" in events[0]
        assert "event: response.output_item.added" in events[1]
        assert "event: response.output_item.done" in events[2]
        assert "event: response.completed" in events[3]
        assert "data: [DONE]" in events[4]

    @pytest.mark.asyncio
    async def test_generates_events_with_empty_refusal(
        self, mocker: MockerFixture
    ) -> None:
        """Test shield violation generator handles empty refusal content."""
        refusal = OpenAIResponseMessage(type="message", role="assistant", content="")

        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            "app.endpoints.responses.extract_text_from_response_output_item",
            return_value="",
        )

        events = []
        async for event in shield_violation_generator(
            refusal_response=refusal,
            conversation_id=VALID_CONV_ID,
            response_id="resp-456",
            created_at=1234567890,
            mirrored_params={"model": "test-model"},
            available_quotas={"tokens": 50},
        ):
            events.append(event)

        assert len(events) == 5
        assert "event: response.created" in events[0]


class TestResponseGenerator:
    """Tests for response_generator."""

    @pytest.mark.asyncio
    async def test_in_progress_event(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test response generator handles in_progress event."""

        async def mock_stream() -> AsyncIterator[ResponseObjectStream]:
            mock_chunk = mocker.Mock(spec=ResponseObjectStream)
            mock_chunk.type = "response.in_progress"
            mock_chunk.model_dump = mocker.Mock(
                return_value={
                    "type": "response.in_progress",
                    "response": {"id": "resp-123", "status": "in_progress"},
                }
            )
            yield mock_chunk

            mock_chunk2 = mocker.Mock(spec=ResponseObjectStream)
            mock_chunk2.type = "response.completed"
            mock_response_obj = mocker.Mock(spec=ResponseObject)
            mock_response_obj.usage = Usage(
                input_tokens=10, output_tokens=5, total_tokens=15
            )
            mock_response_obj.output = []

            def model_dump_side_effect(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {
                    "type": "response.completed",
                    "response": {
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "total_tokens": 15,
                        },
                        "output": [],
                    },
                }

            mock_chunk2.model_dump = mocker.Mock(side_effect=model_dump_side_effect)
            mock_chunk2.response = mock_response_obj
            yield mock_chunk2

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch("app.endpoints.responses.consume_query_tokens")
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )
        mocker.patch(
            "app.endpoints.responses.extract_response_metadata",
            return_value=("text", [], [], []),
        )

        generator = response_generator(
            stream=mock_stream(),
            conversation_id=VALID_CONV_ID,
            user_id="user-123",
            model_id="test-model",
            turn_summary=TurnSummary(),
        )

        events = []
        async for event in generator:
            events.append(event)

        assert len(events) == 3
        assert "response.in_progress" in events[0]
        assert "response.completed" in events[1]
        assert "[DONE]" in events[2]

    @pytest.mark.asyncio
    async def test_incomplete_event(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test response generator handles incomplete event."""

        async def mock_stream() -> AsyncIterator[ResponseObjectStream]:
            mock_chunk = mocker.Mock(spec=ResponseObjectStream)
            mock_chunk.type = "response.incomplete"
            mock_response_obj = mocker.Mock(spec=ResponseObject)
            mock_response_obj.usage = Usage(
                input_tokens=10, output_tokens=5, total_tokens=15
            )
            mock_response_obj.model_dump = mocker.Mock(
                return_value={
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                    }
                }
            )

            def model_dump_side_effect(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {
                    "type": "response.incomplete",
                    "response": {
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "total_tokens": 15,
                        },
                    },
                }

            mock_chunk.model_dump = mocker.Mock(side_effect=model_dump_side_effect)
            mock_chunk.response = mock_response_obj
            yield mock_chunk

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch("app.endpoints.responses.consume_query_tokens")
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )
        mocker.patch(
            "app.endpoints.responses.extract_response_metadata",
            return_value=("text", [], [], []),
        )

        generator = response_generator(
            stream=mock_stream(),
            conversation_id=VALID_CONV_ID,
            user_id="user-123",
            model_id="test-model",
            turn_summary=TurnSummary(),
        )

        events = []
        async for event in generator:
            events.append(event)

        assert len(events) == 2
        assert "response.incomplete" in events[0]
        assert "[DONE]" in events[1]

    @pytest.mark.asyncio
    async def test_failed_event(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test response generator handles failed event."""

        async def mock_stream() -> AsyncIterator[ResponseObjectStream]:
            mock_chunk = mocker.Mock(spec=ResponseObjectStream)
            mock_chunk.type = "response.failed"
            mock_response_obj = mocker.Mock(spec=ResponseObject)
            mock_response_obj.usage = Usage(
                input_tokens=10, output_tokens=5, total_tokens=15
            )
            mock_response_obj.model_dump = mocker.Mock(
                return_value={
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                    }
                }
            )

            def model_dump_side_effect(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {
                    "type": "response.failed",
                    "response": {
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "total_tokens": 15,
                        },
                    },
                }

            mock_chunk.model_dump = mocker.Mock(side_effect=model_dump_side_effect)
            mock_chunk.response = mock_response_obj
            yield mock_chunk

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch("app.endpoints.responses.consume_query_tokens")
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )
        mocker.patch(
            "app.endpoints.responses.extract_response_metadata",
            return_value=("text", [], [], []),
        )

        generator = response_generator(
            stream=mock_stream(),
            conversation_id=VALID_CONV_ID,
            user_id="user-123",
            model_id="test-model",
            turn_summary=TurnSummary(),
        )

        events = []
        async for event in generator:
            events.append(event)

        assert len(events) == 2
        assert "response.failed" in events[0]
        assert "[DONE]" in events[1]


class TestGenerateResponse:
    """Tests for generate_response."""

    @pytest.mark.asyncio
    async def test_new_conversation_with_topic_summary(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test generate_response creates topic summary for new conversation."""

        async def mock_generator() -> AsyncIterator[str]:
            yield "event: response.created\ndata: {}\n\n"
            yield "data: [DONE]\n\n"

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mock_get_topic = mocker.patch(
            "app.endpoints.responses.get_topic_summary",
            return_value="Topic summary",
        )
        mocker.patch("app.endpoints.responses.persist_response_metadata")
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )

        generator = generate_response(
            generator=mock_generator(),
            turn_summary=TurnSummary(),
            client=mocker.AsyncMock(),
            user_id="user-123",
            input_text="Test input",
            started_at="2024-01-01T00:00:00Z",
            user_conversation=None,
            generate_topic_summary=True,
            model_id="test-model",
            conversation_id=VALID_CONV_ID,
            _skip_userid_check=False,
        )

        events = []
        async for event in generator:
            events.append(event)

        mock_get_topic.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_conversation_skips_topic_summary(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test generate_response skips topic summary for existing conversation."""

        async def mock_generator() -> AsyncIterator[str]:
            yield "event: response.created\ndata: {}\n\n"
            yield "data: [DONE]\n\n"

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mock_get_topic = mocker.patch(
            "app.endpoints.responses.get_topic_summary",
            return_value="Topic summary",
        )
        mocker.patch("app.endpoints.responses.persist_response_metadata")
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )

        mock_conv = mocker.Mock(spec=UserConversation)
        generator = generate_response(
            generator=mock_generator(),
            turn_summary=TurnSummary(),
            client=mocker.AsyncMock(),
            user_id="user-123",
            input_text="Test input",
            started_at="2024-01-01T00:00:00Z",
            user_conversation=mock_conv,
            generate_topic_summary=True,
            model_id="test-model",
            conversation_id=VALID_CONV_ID,
            _skip_userid_check=False,
        )

        events = []
        async for event in generator:
            events.append(event)

        mock_get_topic.assert_not_called()


class TestHandleNonStreamingResponse:
    """Tests for handle_non_streaming_response."""

    @pytest.mark.asyncio
    async def test_shield_blocked(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test non-streaming response when shield blocks."""
        refusal = OpenAIResponseMessage(
            type="message", role="assistant", content="Cannot help"
        )
        moderation_result = _create_moderation_result(
            blocked=True, refusal_response=refusal
        )
        request = ResponsesRequest(input="Test", stream=False)

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch(
            "app.endpoints.responses.extract_text_from_response_output_item",
            return_value="Cannot help",
        )
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )
        mocker.patch("app.endpoints.responses.persist_response_metadata")

        response = await handle_non_streaming_response(
            client=mocker.AsyncMock(),
            request=request,
            user_id="user-123",
            moderation_result=moderation_result,
            started_at="2024-01-01T00:00:00Z",
            user_conversation=None,
            input_text="Test",
            _skip_userid_check=False,
        )

        assert isinstance(response, ResponsesResponse)
        assert response.status == "completed"
        assert len(response.output) == 1

    @pytest.mark.asyncio
    async def test_successful_response(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test successful non-streaming response."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(input="Test", model="test-model", stream=False)

        mock_response = mocker.Mock(spec=ResponseObject)
        mock_response.usage = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        mock_response.output = []
        mock_response.status = "completed"
        mock_response.id = "resp-123"
        mock_response.model_dump = mocker.Mock(
            return_value={
                "id": "resp-123",
                "object": "response",
                "created_at": 1704067200,
                "status": "completed",
                "model": "test-model",
                "output": [],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
        )

        mock_client = mocker.AsyncMock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch("app.endpoints.responses.consume_query_tokens")
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )
        mocker.patch(
            "app.endpoints.responses.extract_response_metadata",
            return_value=("text", [], [], []),
        )
        mocker.patch("app.endpoints.responses.persist_response_metadata")

        response = await handle_non_streaming_response(
            client=mock_client,
            request=request,
            user_id="user-123",
            moderation_result=moderation_result,
            started_at="2024-01-01T00:00:00Z",
            user_conversation=None,
            input_text="Test",
            _skip_userid_check=False,
        )

        assert isinstance(response, ResponsesResponse)

    @pytest.mark.asyncio
    async def test_prompt_too_long_error(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test non-streaming response handles prompt too long error."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(input="x" * 100000, model="test-model", stream=False)

        mock_client = mocker.AsyncMock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=RuntimeError("context_length exceeded")
        )

        mocker.patch("app.endpoints.responses.configuration", test_config)

        with pytest.raises(HTTPException) as exc_info:
            await handle_non_streaming_response(
                client=mock_client,
                request=request,
                user_id="user-123",
                moderation_result=moderation_result,
                started_at="2024-01-01T00:00:00Z",
                user_conversation=None,
                input_text="x" * 100000,
                _skip_userid_check=False,
            )
        assert exc_info.value.status_code == 413

    @pytest.mark.asyncio
    async def test_connection_error(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test non-streaming response handles connection error."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(input="Test", model="test-model", stream=False)

        mock_client = mocker.AsyncMock()
        mock_client.responses.create = mocker.AsyncMock(
            side_effect=APIConnectionError(request=mocker.Mock())
        )

        mocker.patch("app.endpoints.responses.configuration", test_config)

        with pytest.raises(HTTPException) as exc_info:
            await handle_non_streaming_response(
                client=mock_client,
                request=request,
                user_id="user-123",
                moderation_result=moderation_result,
                started_at="2024-01-01T00:00:00Z",
                user_conversation=None,
                input_text="Test",
                _skip_userid_check=False,
            )
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_api_status_error(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test non-streaming response handles API status error."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(input="Test", model="test-model", stream=False)

        mock_client = mocker.AsyncMock()
        error = LLSApiStatusError(
            message="API Error", response=mocker.Mock(request=None), body=None
        )
        error.status_code = 429
        mock_client.responses.create = mocker.AsyncMock(side_effect=error)

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mock_error_response = mocker.Mock()
        mock_error_response.status_code = 429
        mock_error_response.model_dump = mocker.Mock(
            return_value={"status_code": 429, "detail": "Quota exceeded"}
        )
        mocker.patch(
            "app.endpoints.responses.handle_known_apistatus_errors",
            return_value=mock_error_response,
        )

        with pytest.raises(HTTPException) as exc_info:
            await handle_non_streaming_response(
                client=mock_client,
                request=request,
                user_id="user-123",
                moderation_result=moderation_result,
                started_at="2024-01-01T00:00:00Z",
                user_conversation=None,
                input_text="Test",
                _skip_userid_check=False,
            )
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_with_topic_summary(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> None:
        """Test non-streaming response generates topic summary."""
        moderation_result = _create_moderation_result(blocked=False)
        request = ResponsesRequest(
            input="Test", model="test-model", stream=False, generate_topic_summary=True
        )

        mock_response = mocker.Mock(spec=ResponseObject)
        mock_response.usage = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        mock_response.output = []
        mock_response.status = "completed"
        mock_response.id = "resp-123"
        type(mock_response).output_text = mocker.PropertyMock(return_value="")
        mock_response.model_dump = mocker.Mock(
            return_value={
                "id": "resp-123",
                "object": "response",
                "created_at": 1704067200,
                "status": "completed",
                "model": "test-model",
                "output": [],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
        )

        mock_client = mocker.AsyncMock()
        mock_client.responses.create = mocker.AsyncMock(return_value=mock_response)

        mocker.patch("app.endpoints.responses.configuration", test_config)
        mocker.patch(
            "app.endpoints.responses.normalize_conversation_id",
            return_value=VALID_CONV_ID,
        )
        mocker.patch("app.endpoints.responses.consume_query_tokens")
        mocker.patch(
            "app.endpoints.responses.get_available_quotas", return_value={"tokens": 100}
        )
        mocker.patch(
            "app.endpoints.responses.extract_response_metadata",
            return_value=("text", [], [], []),
        )
        mock_get_topic = mocker.patch(
            "app.endpoints.responses.get_topic_summary",
            return_value="Topic summary",
        )
        mocker.patch("app.endpoints.responses.persist_response_metadata")

        await handle_non_streaming_response(
            client=mock_client,
            request=request,
            user_id="user-123",
            moderation_result=moderation_result,
            started_at="2024-01-01T00:00:00Z",
            user_conversation=None,
            input_text="Test",
            _skip_userid_check=False,
        )

        mock_get_topic.assert_called_once()
