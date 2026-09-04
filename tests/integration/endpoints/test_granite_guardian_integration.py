"""Integration tests for Granite Guardian input guardrail across endpoints.

Tests exercise the shield moderation pipeline with a real
``run_shield_moderation_v2`` / ``build_shield`` → ``GraniteGuardian.run()``
path for ``/responses`` and ``/rlsapi``, and the pydantic-ai capability
path via ``build_agent`` → ``GraniteGuardian.wrap_run()`` for ``/query``
and ``/streaming_query``.

The Guardian's LLM call (``model_request``) is mocked so no real
inference server is needed.
"""

# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from ogx_client.models.open_ai_response_object import OpenAIResponseObject
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import ModelRequestParameters, StreamedResponse
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from app.endpoints.query import query_endpoint_handler
from app.endpoints.responses import responses_endpoint_handler
from app.endpoints.rlsapi_v1 import infer_endpoint
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest, ResponsesRequest
from models.api.requests.rlsapi import RlsapiV1InferRequest
from models.api.responses.successful import ResponsesResponse
from models.api.responses.successful.rlsapi import RlsapiV1InferResponse
from models.common.responses.contexts import ResponsesContext
from models.config import (
    GraniteGuardianConfig,
    GraniteGuardianShieldConfiguration,
    RiskDefinition,
)
from models.database.conversations import UserConversation, UserTurn
from tests.integration.conftest import (
    make_openai_model,
    make_openai_models_list_response,
)
from version import __version__

_GUARDIAN_MODULE = "pydantic_ai_lightspeed.capabilities.granite_guardian._capability"

MOCK_CONV_ID = "conv_" + "a" * 48
NORMALIZED_CONV_ID = "a" * 48

VIOLATION_MESSAGE = "Content blocked by Granite Guardian."

_RESPONSE_DUMP: dict[str, Any] = {
    "id": "resp_guardian_test",
    "object": "response",
    "created_at": 1700000000,
    "status": "completed",
    "model": "test-provider/test-model",
    "store": False,
    "output": [
        {
            "type": "message",
            "id": "msg-1",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": "Ansible is an automation tool.",
                    "annotations": [],
                }
            ],
        }
    ],
    "usage": {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "input_tokens_details": {"cached_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 0},
    },
}


def _guardian_shield_config() -> GraniteGuardianShieldConfiguration:
    """Build a GraniteGuardianShieldConfiguration for testing."""
    return GraniteGuardianShieldConfiguration(
        name="granite-guardian",
        provider_id="granite_guardian",
        config=GraniteGuardianConfig(
            url="http://localhost:8080/v1",
            risks=[
                RiskDefinition(
                    name="harmful_content",
                    description="Content that is harmful",
                    threshold=0.5,
                    points=["input"],
                    violation_message=VIOLATION_MESSAGE,
                )
            ],
        ),
    )


def _mock_guardian_model_request(mocker: MockerFixture) -> Any:
    """Mock the Guardian's model_request to return valid logprobs.

    Returns the mock so callers can inspect call args.
    """
    mock_response = mocker.Mock()
    mock_response.usage = RequestUsage(input_tokens=5, output_tokens=1)
    mock_response.provider_details = {"logprobs": [{"token": "no"}]}
    return mocker.patch(
        f"{_GUARDIAN_MODULE}.model_request",
        new=mocker.AsyncMock(return_value=mock_response),
    )


def _mock_guardian_init(mocker: MockerFixture) -> None:
    """Mock GraniteGuardian's external dependencies so __post_init__ succeeds."""
    mocker.patch(f"{_GUARDIAN_MODULE}.httpx.AsyncClient")
    mocker.patch(f"{_GUARDIAN_MODULE}.AsyncOpenAI")
    mocker.patch(f"{_GUARDIAN_MODULE}.OpenAIProvider")
    mocker.patch(f"{_GUARDIAN_MODULE}.OpenAIChatModel")


# ============================================================================
# /responses endpoint helpers
# ============================================================================


def _build_responses_mock_client(mocker: MockerFixture) -> Any:
    """Build a mock OGX client for responses integration tests."""
    mock_client = mocker.AsyncMock()
    mock_client.responses.create = mocker.AsyncMock(
        return_value=OpenAIResponseObject.from_dict(_RESPONSE_DUMP)
    )
    mock_client.openai.list.return_value = make_openai_models_list_response(
        make_openai_model()
    )
    mock_client.shields.list.return_value = []
    mock_client.vector_stores.list.return_value = []
    mock_conv = mocker.MagicMock()
    mock_conv.id = MOCK_CONV_ID
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conv)
    return mock_client


def _patch_responses_client_holders(mocker: MockerFixture, mock_client: Any) -> None:
    """Patch AsyncOgxClientHolder for the responses endpoint."""
    for module in ("app.endpoints.responses", "utils.endpoints"):
        holder = mocker.patch(f"{module}.AsyncOgxClientHolder")
        holder.return_value.get_client.return_value = mock_client

    original_cls = ResponsesContext

    def _skip_validation(**kwargs: Any) -> ResponsesContext:
        return original_cls.model_construct(**kwargs)

    mocker.patch(
        "app.endpoints.responses.ResponsesContext", side_effect=_skip_validation
    )


def _setup_responses_test(mocker: MockerFixture) -> Any:
    """Set up mock client and patches for a responses integration test."""
    mock_client = _build_responses_mock_client(mocker)
    _patch_responses_client_holders(mocker, mock_client)
    mocker.patch(
        "app.endpoints.responses.maybe_get_topic_summary",
        new=mocker.AsyncMock(return_value=None),
    )
    return mock_client


def _inject_guardian_shield(test_config: AppConfig) -> None:
    """Add the Granite Guardian shield to the test configuration."""
    test_config.configuration.shields = [_guardian_shield_config()]


# ============================================================================
# /responses endpoint tests
# ============================================================================


class TestResponsesGraniteGuardian:
    """Integration tests for Granite Guardian on the /responses endpoint."""

    @pytest.mark.asyncio
    async def test_blocks_unsafe_input(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_db_session: Session,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Granite Guardian blocks unsafe input in non-streaming mode."""
        _, _ = test_config, test_db_session
        _inject_guardian_shield(test_config)
        mock_client = _setup_responses_test(mocker)
        _mock_guardian_init(mocker)
        _mock_guardian_model_request(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=False)

        request = ResponsesRequest(
            input="Some harmful content",
            model="test-provider/test-model",
            stream=False,
            store=True,
            generate_topic_summary=False,
        )

        response = await responses_endpoint_handler(
            request=test_request,
            responses_request=request,
            auth=test_auth,
            mcp_headers={},
        )

        assert isinstance(response, ResponsesResponse)
        assert VIOLATION_MESSAGE in (response.output_text or "")
        mock_client.responses.create.assert_not_called()

        # Check the block message shows up in the conversation turn
        mock_client.items.create.assert_called_once()
        items = mock_client.items.create.call_args[1]["add_items_request"].items
        assert len(items) == 2

        user_msg = items[0].actual_instance
        assert user_msg.role == "user"
        assert user_msg.content == "Some harmful content"

        assistant_msg = items[1].actual_instance
        assert assistant_msg.role == "assistant"
        assert assistant_msg.content == VIOLATION_MESSAGE

    @pytest.mark.asyncio
    async def test_passes_safe_input(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_db_session: Session,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Granite Guardian allows safe input through."""
        _, _ = test_config, test_db_session
        _inject_guardian_shield(test_config)
        mock_client = _setup_responses_test(mocker)
        _mock_guardian_init(mocker)
        _mock_guardian_model_request(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=True)

        request = ResponsesRequest(
            input="What is Ansible?",
            model="test-provider/test-model",
            stream=False,
            store=True,
            generate_topic_summary=False,
        )

        response = await responses_endpoint_handler(
            request=test_request,
            responses_request=request,
            auth=test_auth,
            mcp_headers={},
        )

        assert isinstance(response, ResponsesResponse)
        assert response.id == "resp_guardian_test"
        assert response.output_text == "Ansible is an automation tool."
        mock_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_streaming_blocks_unsafe_input(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_db_session: Session,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Granite Guardian blocks unsafe input in streaming mode."""
        _, _ = test_config, test_db_session
        _inject_guardian_shield(test_config)
        mock_client = _setup_responses_test(mocker)
        _mock_guardian_init(mocker)
        _mock_guardian_model_request(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=False)

        request = ResponsesRequest(
            input="Some harmful content",
            model="test-provider/test-model",
            stream=True,
            store=True,
            generate_topic_summary=False,
        )

        response = await responses_endpoint_handler(
            request=test_request,
            responses_request=request,
            auth=test_auth,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"

        body = b""
        async for part in response.body_iterator:
            if isinstance(part, str):
                body += part.encode()
            else:
                body += bytes(part)
        body_str = body.decode()

        assert "event: response.created" in body_str
        assert "event: response.completed" in body_str
        assert VIOLATION_MESSAGE in body_str
        mock_client.responses.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_persists_turn(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_db_session: Session,
        test_auth: AuthTuple,
    ) -> None:
        """Test that a blocked response persists the moderation turn to the DB."""
        _ = test_config
        _inject_guardian_shield(test_config)
        _setup_responses_test(mocker)
        _mock_guardian_init(mocker)
        _mock_guardian_model_request(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=False)

        request = ResponsesRequest(
            input="Blocked content",
            model="test-provider/test-model",
            stream=False,
            store=True,
            generate_topic_summary=False,
        )

        await responses_endpoint_handler(
            request=test_request,
            responses_request=request,
            auth=test_auth,
            mcp_headers={},
        )

        conversation = (
            test_db_session.query(UserConversation)
            .filter_by(id=NORMALIZED_CONV_ID)
            .first()
        )
        assert conversation is not None
        assert conversation.last_response_id is None

        turns = (
            test_db_session.query(UserTurn)
            .filter_by(conversation_id=NORMALIZED_CONV_ID)
            .all()
        )
        assert len(turns) == 1
        assert turns[0].response_id.startswith("modr-")


# ============================================================================
# /rlsapi endpoint helpers
# ============================================================================


def _create_rlsapi_mock_request(mocker: MockerFixture) -> Any:
    """Create a mock FastAPI Request for rlsapi tests."""
    mock_request = mocker.Mock()
    mock_request.state = mocker.Mock(spec=[])
    mock_request.headers = {"User-Agent": f"CLA/{__version__}"}
    return mock_request


def _setup_rlsapi_responses_mock(mocker: MockerFixture) -> Any:
    """Set up responses.create mock for rlsapi tests."""
    mock_response = mocker.Mock()
    mock_output = mocker.Mock()
    mock_output.type = "message"
    mock_output.role = "assistant"
    mock_output.content = "Use the `ls` command to list files."
    mock_response.output = [mock_output]
    mock_usage = mocker.Mock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage

    mock_responses = mocker.Mock()
    mock_responses.create = mocker.AsyncMock(return_value=mock_response)
    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

    mock_holder_class = mocker.patch("app.endpoints.rlsapi_v1.AsyncOgxClientHolder")
    mock_holder_class.return_value.get_client.return_value = mock_client
    return mock_client


# ============================================================================
# /rlsapi endpoint tests
# ============================================================================


class TestRlsapiGraniteGuardian:
    """Integration tests for Granite Guardian on the /rlsapi v1 /infer endpoint."""

    @pytest.fixture(name="rlsapi_config")
    def rlsapi_config_fixture(
        self, test_config: AppConfig, mocker: MockerFixture
    ) -> AppConfig:
        """Extend test_config with rlsapi defaults and Granite Guardian shield."""
        test_config.inference.default_model = "test-model"
        test_config.inference.default_provider = "test-provider"
        test_config.configuration.shields = [_guardian_shield_config()]
        mocker.patch("app.endpoints.rlsapi_v1.configuration", test_config)
        return test_config

    @pytest.fixture(name="mock_model_configured")
    def mock_model_configured_fixture(self, mocker: MockerFixture) -> None:
        """Mock model existence check to pass."""
        mocker.patch(
            "app.endpoints.rlsapi_v1.check_model_configured",
            new=mocker.AsyncMock(return_value=True),
        )

    @pytest.mark.asyncio
    async def test_blocks_unsafe_input(
        self,
        rlsapi_config: AppConfig,
        mock_model_configured: None,
        mocker: MockerFixture,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Granite Guardian blocks unsafe input on /infer."""
        _, _ = rlsapi_config, mock_model_configured
        mock_client = _setup_rlsapi_responses_mock(mocker)
        _mock_guardian_init(mocker)
        _mock_guardian_model_request(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=False)

        response = await infer_endpoint(
            infer_request=RlsapiV1InferRequest(question="Harmful question"),
            request=_create_rlsapi_mock_request(mocker),
            background_tasks=mocker.Mock(),
            auth=test_auth,
        )

        assert isinstance(response, RlsapiV1InferResponse)
        assert response.data.text == VIOLATION_MESSAGE
        mock_client.responses.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_safe_input(
        self,
        rlsapi_config: AppConfig,
        mock_model_configured: None,
        mocker: MockerFixture,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Granite Guardian allows safe input on /infer."""
        _, _ = rlsapi_config, mock_model_configured
        mock_client = _setup_rlsapi_responses_mock(mocker)
        _mock_guardian_init(mocker)
        _mock_guardian_model_request(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=True)

        response = await infer_endpoint(
            infer_request=RlsapiV1InferRequest(question="How do I list files?"),
            request=_create_rlsapi_mock_request(mocker),
            background_tasks=mocker.Mock(),
            auth=test_auth,
        )

        assert isinstance(response, RlsapiV1InferResponse)
        assert response.data.text == "Use the `ls` command to list files."
        mock_client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_blocked_response_has_no_token_counts(
        self,
        rlsapi_config: AppConfig,
        mock_model_configured: None,
        mocker: MockerFixture,
        test_auth: AuthTuple,
    ) -> None:
        """Test that a blocked rlsapi response has no token usage counts."""
        _, _ = rlsapi_config, mock_model_configured
        _setup_rlsapi_responses_mock(mocker)
        _mock_guardian_init(mocker)
        _mock_guardian_model_request(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=False)

        response = await infer_endpoint(
            infer_request=RlsapiV1InferRequest(question="Bad input"),
            request=_create_rlsapi_mock_request(mocker),
            background_tasks=mocker.Mock(),
            auth=test_auth,
        )

        assert response.data.input_tokens is None
        assert response.data.output_tokens is None


# ============================================================================
# /query and /streaming_query shared helpers
# ============================================================================


# Signature required by pydantic-ai FunctionModel handler interface.
async def _mock_llm(messages: list[Any], info: Any) -> ModelResponse:
    """FunctionModel handler returning a simple assistant response."""
    _, _ = messages, info
    return ModelResponse(
        parts=[TextPart("This is a test response about Ansible.")],
        finish_reason="stop",
        provider_response_id="response-123",
    )


# Signature required by pydantic-ai FunctionModel stream handler interface.
async def _mock_llm_stream(messages: list[Any], info: Any) -> AsyncIterator[str]:
    """FunctionModel stream handler yielding a simple assistant response."""
    _, _ = messages, info
    yield "This is a test response about Ansible."


class _TestLLMModel(FunctionModel):
    """FunctionModel subclass that sets finish_reason on streamed responses."""

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: Any = None,
    ) -> AsyncIterator[StreamedResponse]:
        """Delegate to parent and patch finish_reason on the streamed response."""
        async with super().request_stream(
            messages, model_settings, model_request_parameters, run_context
        ) as response:
            response.finish_reason = "stop"
            response.provider_response_id = "response-123"
            yield response


def _mock_ogx_for_query(mocker: MockerFixture, module: str) -> Any:
    """Patch AsyncOgxClientHolder in the given endpoint module and return the mock client."""
    mock_holder_class = mocker.patch(f"{module}.AsyncOgxClientHolder")
    mock_client = mocker.AsyncMock()

    mock_client.openai.list.return_value = make_openai_models_list_response(
        make_openai_model()
    )
    mock_client.vector_stores.list.return_value = []
    mock_client.shields.list.return_value = []
    mock_client.items.create = mocker.AsyncMock()

    mock_conv = mocker.MagicMock()
    mock_conv.id = MOCK_CONV_ID
    mock_client.conversations.create = mocker.AsyncMock(return_value=mock_conv)

    mock_holder_class.return_value.get_client.return_value = mock_client
    return mock_client


def _mock_build_agent_model(mocker: MockerFixture) -> None:
    """Replace OgxResponsesModel.from_ogx_client with a test model."""
    mocker.patch(
        "utils.pydantic_ai_helpers.OgxResponsesModel.from_ogx_client",
        return_value=_TestLLMModel(
            _mock_llm,
            stream_function=_mock_llm_stream,
            settings={"extra_body": {"conversation": MOCK_CONV_ID}},
        ),
    )


def _mock_guardian_for_capability(mocker: MockerFixture) -> Any:
    """Mock all Guardian external dependencies for the capability path.

    Includes AsyncOgxClientHolder in the Guardian module so
    ``wrap_run`` can call ``append_turn_to_conversation``.

    Returns:
        The mock OGX client used by the Guardian capability.
    """
    _mock_guardian_init(mocker)
    _mock_guardian_model_request(mocker)
    mock_holder = mocker.patch(f"{_GUARDIAN_MODULE}.AsyncOgxClientHolder")
    mock_client = mocker.AsyncMock()
    mock_holder.return_value.get_client.return_value = mock_client
    return mock_client


# ============================================================================
# /query endpoint tests
# ============================================================================


class TestQueryGraniteGuardian:
    """Integration tests for Granite Guardian on the /query endpoint.

    These tests let ``build_agent`` run for real so ``GraniteGuardian``
    is wired as a pydantic-ai capability and ``wrap_run`` fires during
    ``agent.run()``.  The main LLM model is replaced by a
    ``FunctionModel`` and the Guardian's ``model_request`` is mocked.
    """

    @pytest.mark.asyncio
    async def test_blocks_unsafe_input(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Guardian capability blocks unsafe input on /query."""
        _inject_guardian_shield(test_config)
        _mock_ogx_for_query(mocker, "app.endpoints.query")
        _mock_build_agent_model(mocker)
        guardian_client = _mock_guardian_for_capability(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=False)

        response = await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(query="Some harmful content"),
            auth=test_auth,
            mcp_headers={},
        )

        assert VIOLATION_MESSAGE in response.response

        guardian_client.items.create.assert_called_once()
        items = guardian_client.items.create.call_args[1]["add_items_request"].items
        assert len(items) == 2

        user_msg = items[0].actual_instance
        assert user_msg.role == "user"
        assert user_msg.content == "Some harmful content"

        assistant_msg = items[1].actual_instance
        assert assistant_msg.role == "assistant"
        assert assistant_msg.content == VIOLATION_MESSAGE

    @pytest.mark.asyncio
    async def test_passes_safe_input(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Guardian capability allows safe input on /query."""
        _inject_guardian_shield(test_config)
        _mock_ogx_for_query(mocker, "app.endpoints.query")
        _mock_build_agent_model(mocker)
        _mock_guardian_for_capability(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=True)

        response = await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(query="What is Ansible?"),
            auth=test_auth,
            mcp_headers={},
        )

        assert "Ansible" in response.response
        assert VIOLATION_MESSAGE not in response.response

    @pytest.mark.asyncio
    async def test_guardian_token_usage_is_not_included_in_user_token_usage(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_auth: AuthTuple,
    ) -> None:
        """Test that a blocked /query response reports only Guardian token usage."""
        _inject_guardian_shield(test_config)
        _mock_ogx_for_query(mocker, "app.endpoints.query")
        _mock_build_agent_model(mocker)
        _mock_guardian_for_capability(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", side_effect=[False, True])

        response = await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(query="Bad content"),
            auth=test_auth,
            mcp_headers={},
        )

        assert VIOLATION_MESSAGE in response.response
        assert response.input_tokens == 0
        assert response.output_tokens == 0

        response = await query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(query="Bad content"),
            auth=test_auth,
            mcp_headers={},
        )

        assert VIOLATION_MESSAGE not in response.response
        # Both token counts are rough estimates produced by FunctionModel's
        # _estimate_usage: input = 50-token base + prompt tokens, output = response text tokens.
        assert response.input_tokens == 52
        assert response.output_tokens == 8


# ============================================================================
# /streaming_query endpoint tests
# ============================================================================


class TestStreamingQueryGraniteGuardian:
    """Integration tests for Granite Guardian on the /streaming_query endpoint.

    Uses the same capability path as ``/query`` but exercises
    ``agent.run_stream_events()`` instead of ``agent.run()``.
    """

    @pytest.mark.asyncio
    async def test_blocks_unsafe_input(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Guardian capability blocks unsafe input on /streaming_query."""
        _inject_guardian_shield(test_config)
        _mock_ogx_for_query(mocker, "app.endpoints.streaming_query")
        _mock_build_agent_model(mocker)
        guardian_client = _mock_guardian_for_capability(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=False)

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(query="Some harmful content"),
            auth=test_auth,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)

        body = b""
        async for part in response.body_iterator:
            if isinstance(part, str):
                body += part.encode()
            else:
                body += bytes(part)
        body_str = body.decode()

        assert VIOLATION_MESSAGE in body_str

        guardian_client.items.create.assert_called_once()
        items = guardian_client.items.create.call_args[1]["add_items_request"].items
        assert len(items) == 2

        user_msg = items[0].actual_instance
        assert user_msg.role == "user"
        assert user_msg.content == "Some harmful content"

        assistant_msg = items[1].actual_instance
        assert assistant_msg.role == "assistant"
        assert assistant_msg.content == VIOLATION_MESSAGE

    @pytest.mark.asyncio
    async def test_passes_safe_input(
        self,
        test_config: AppConfig,
        mocker: MockerFixture,
        test_request: Request,
        test_auth: AuthTuple,
    ) -> None:
        """Test that Guardian capability allows safe input on /streaming_query."""
        _inject_guardian_shield(test_config)
        _mock_ogx_for_query(mocker, "app.endpoints.streaming_query")
        _mock_build_agent_model(mocker)
        _mock_guardian_for_capability(mocker)
        mocker.patch(f"{_GUARDIAN_MODULE}.is_safe", return_value=True)

        response = await streaming_query_endpoint_handler(
            request=test_request,
            query_request=QueryRequest(query="What is Ansible?"),
            auth=test_auth,
            mcp_headers={},
        )

        assert isinstance(response, StreamingResponse)

        body = b""
        async for part in response.body_iterator:
            if isinstance(part, str):
                body += part.encode()
            else:
                body += bytes(part)
        body_str = body.decode()

        assert "Ansible" in body_str
        assert VIOLATION_MESSAGE not in body_str
