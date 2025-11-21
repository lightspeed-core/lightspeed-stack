"""Unit tests for the RHEL Lightspeed rlsapi v1 /infer REST API endpoint."""

# pylint: disable=redefined-outer-name

from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError
from pytest_mock import MockerFixture

from app.endpoints.rlsapi_v1_infer import (
    format_v1_prompt,
    rlsapi_v1_infer_endpoint_handler,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.requests import RlsapiV1InferRequest
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.fixture
def app_config() -> AppConfig:
    """Fixture providing initialized AppConfig."""
    cfg = AppConfig()
    cfg.init_from_dict(
        {
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
            "user_data_collection": {"transcripts_enabled": False},
            "mcp_servers": [],
            "customization": None,
            "authorization": {"access_rules": []},
            "authentication": {"module": "noop"},
        }
    )
    return cfg


@pytest.fixture
def mock_llama_client(mocker: MockerFixture) -> Any:
    """Fixture providing a mock Llama Stack client with successful response."""
    mock_model = mocker.Mock()
    mock_model.model_type = "llm"
    mock_model.identifier = "test-model"
    mock_model.provider_id = "test-provider"

    mock_output = mocker.Mock()
    mock_output.type = "message"
    mock_output.role = "assistant"
    mock_output.content = "Test response from LLM."

    mock_response = mocker.Mock()
    mock_response.output = [mock_output]
    mock_response.usage = mocker.Mock(input_tokens=10, output_tokens=20)

    mock_client = mocker.AsyncMock()
    mock_client.models.list.return_value = [mock_model]
    mock_client.responses.create.return_value = mock_response

    mock_holder = mocker.patch(
        "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
    )
    mock_holder.return_value.get_client.return_value = mock_client
    return mock_client


@pytest.fixture
def endpoint_mocks(mocker: MockerFixture, app_config: AppConfig) -> None:
    """Fixture providing common mocks for endpoint tests."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.rlsapi_v1_infer.check_tokens_available")
    mocker.patch("app.endpoints.rlsapi_v1_infer.consume_tokens")
    mocker.patch("app.endpoints.rlsapi_v1_infer.configuration", app_config)


@pytest.fixture
def mock_request() -> Request:
    """Fixture providing mock FastAPI Request."""
    return Request(scope={"type": "http", "headers": []})


@pytest.fixture
def mock_auth() -> AuthTuple:
    """Fixture providing mock authentication tuple."""
    return ("test_user_id", "test_user", False, "test_token")


class TestFormatV1Prompt:
    """Tests for format_v1_prompt function."""

    def test_minimal_question_only(self) -> None:
        """Test prompt with just a question."""
        request = RlsapiV1InferRequest(question="How do I list files?")
        assert format_v1_prompt(request) == "Question: How do I list files?"

    def test_with_context(self) -> None:
        """Test prompt with context fields."""
        request = RlsapiV1InferRequest(
            question="What does this error mean?",
            context={
                "system_info": "RHEL 9.3",
                "terminal_output": "bash: command not found",
            },
        )
        prompt = format_v1_prompt(request)

        assert "System: RHEL 9.3" in prompt
        assert "Terminal:\nbash: command not found" in prompt
        assert prompt.endswith("Question: What does this error mean?")

    def test_with_attachment(self) -> None:
        """Test prompt with file attachment."""
        request = RlsapiV1InferRequest(
            question="Analyze this",
            context={"attachments": {"mimetype": "text/plain", "contents": "data"}},
        )
        prompt = format_v1_prompt(request)

        assert "File (text/plain):\ndata" in prompt


class TestRlsapiV1InferEndpoint:
    """Tests for rlsapi_v1_infer_endpoint_handler."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("endpoint_mocks", "mock_llama_client")
    async def test_success(self, mock_request: Request, mock_auth: AuthTuple) -> None:
        """Test successful inference returns response with text and request_id."""
        request = RlsapiV1InferRequest(question="How do I list files?")

        response = await rlsapi_v1_infer_endpoint_handler(
            request=mock_request, infer_request=request, auth=mock_auth
        )

        assert response.data["text"] == "Test response from LLM."
        assert "request_id" in response.data

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("endpoint_mocks")
    async def test_no_models_returns_404(
        self, mocker: MockerFixture, mock_request: Request, mock_auth: AuthTuple
    ) -> None:
        """Test 404 when no LLM models available."""
        mock_client = mocker.AsyncMock()
        mock_client.models.list.return_value = []
        mock_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await rlsapi_v1_infer_endpoint_handler(
                request=mock_request,
                infer_request=RlsapiV1InferRequest(question="test"),
                auth=mock_auth,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("endpoint_mocks")
    async def test_empty_response_returns_fallback(
        self, mocker: MockerFixture, mock_request: Request, mock_auth: AuthTuple
    ) -> None:
        """Test fallback message when LLM returns empty response."""
        mock_model = mocker.Mock(model_type="llm", identifier="m", provider_id="p")
        mock_response = mocker.Mock(output=[], usage=None)

        mock_client = mocker.AsyncMock()
        mock_client.models.list.return_value = [mock_model]
        mock_client.responses.create.return_value = mock_response

        mock_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_holder.return_value.get_client.return_value = mock_client

        response = await rlsapi_v1_infer_endpoint_handler(
            request=mock_request,
            infer_request=RlsapiV1InferRequest(question="test"),
            auth=mock_auth,
        )

        assert "unable to generate a response" in response.data["text"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("endpoint_mocks")
    async def test_connection_error_returns_500(
        self, mocker: MockerFixture, mock_request: Request, mock_auth: AuthTuple
    ) -> None:
        """Test 500 when Llama Stack connection fails."""
        mock_client = mocker.AsyncMock()
        mock_client.models.list.side_effect = APIConnectionError(request=None)  # type: ignore

        mock_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_holder.return_value.get_client.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await rlsapi_v1_infer_endpoint_handler(
                request=mock_request,
                infer_request=RlsapiV1InferRequest(question="test"),
                auth=mock_auth,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("endpoint_mocks")
    async def test_client_not_initialized_returns_500(
        self, mocker: MockerFixture, mock_request: Request, mock_auth: AuthTuple
    ) -> None:
        """Test 500 when Llama Stack client not initialized."""
        mock_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_holder.return_value.get_client.side_effect = RuntimeError(
            "Client not initialized"
        )

        with pytest.raises(HTTPException) as exc_info:
            await rlsapi_v1_infer_endpoint_handler(
                request=mock_request,
                infer_request=RlsapiV1InferRequest(question="test"),
                auth=mock_auth,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert (
            "Unable to initialize Llama Stack client"
            in exc_info.value.detail["response"]
        )

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("mock_llama_client")
    async def test_skip_userid_check_skips_quota(
        self, mocker: MockerFixture, mock_request: Request, app_config: AppConfig
    ) -> None:
        """Test that skip_userid_check=True skips quota operations."""
        mock_authorization_resolvers(mocker)
        mock_check_tokens = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.check_tokens_available"
        )
        mock_consume_tokens = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.consume_tokens"
        )
        mocker.patch("app.endpoints.rlsapi_v1_infer.configuration", app_config)

        # Auth tuple with skip_userid_check=True (noop auth behavior)
        auth_skip_quota: AuthTuple = ("test_user_id", "test_user", True, "test_token")

        await rlsapi_v1_infer_endpoint_handler(
            request=mock_request,
            infer_request=RlsapiV1InferRequest(question="test"),
            auth=auth_skip_quota,
        )

        # Quota functions should NOT be called when skip_userid_check=True
        mock_check_tokens.assert_not_called()
        mock_consume_tokens.assert_not_called()
