"""Unit tests for the RHEL Lightspeed rlsapi v1 /infer REST API endpoint."""

# pylint: disable=redefined-outer-name

from typing import Any
import pytest

from fastapi import HTTPException, Request, status
from llama_stack_client import APIConnectionError
from pytest_mock import MockerFixture


from authentication.interface import AuthTuple
from app.endpoints.rlsapi_v1_infer import (
    format_v1_prompt,
    rlsapi_v1_infer_endpoint_handler,
)
from configuration import AppConfig
from models.requests import RlsapiV1InferRequest
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.fixture
def app_test_config() -> dict[str, Any]:
    """Fixture providing common test configuration."""
    return {
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
        "authorization": {"access_rules": []},
        "authentication": {"module": "noop"},
    }


@pytest.fixture
def configured_app(app_test_config: dict[str, Any]) -> AppConfig:
    """Fixture providing initialized AppConfig instance."""
    cfg = AppConfig()
    cfg.init_from_dict(app_test_config)
    return cfg


@pytest.fixture
def mock_request() -> Request:
    """Fixture providing mock FastAPI Request."""
    return Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer test-token")],
        }
    )


@pytest.fixture
def mock_auth() -> AuthTuple:
    """Fixture providing mock authentication tuple."""
    return ("test_user_id", "test_user", False, "test_token")


@pytest.fixture
def common_mocks(mocker: MockerFixture, configured_app: AppConfig) -> None:
    """Fixture providing common mocks used by most endpoint tests."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.rlsapi_v1_infer.check_tokens_available")
    mocker.patch("app.endpoints.rlsapi_v1_infer.consume_tokens")
    mocker.patch("app.endpoints.rlsapi_v1_infer.configuration", configured_app)


class TestFormatV1Prompt:
    """Tests for format_v1_prompt function."""

    def test_format_v1_prompt_minimal(self) -> None:
        """Test formatting prompt with just question (no context)."""
        request = RlsapiV1InferRequest(question="How do I list files?")

        prompt = format_v1_prompt(request)

        assert prompt == "Question: How do I list files?"

    def test_format_v1_prompt_with_context_dict(self) -> None:
        """Test formatting prompt with context dictionary."""
        request = RlsapiV1InferRequest(
            question="What does this error mean?",
            context={
                "system_info": "RHEL 9.3",
                "terminal_output": "bash: command not found",
                "stdin": "user input",
            },
        )

        prompt = format_v1_prompt(request)

        assert "System: RHEL 9.3" in prompt
        assert "Terminal:\nbash: command not found" in prompt
        assert "Input:\nuser input" in prompt
        assert "Question: What does this error mean?" in prompt

    def test_format_v1_prompt_with_attachments(self) -> None:
        """Test formatting prompt with attachments in context."""
        request = RlsapiV1InferRequest(
            question="Analyze this file",
            context={
                "attachments": {
                    "mimetype": "text/plain",
                    "contents": "file content here",
                }
            },
        )

        prompt = format_v1_prompt(request)

        assert "File (text/plain):\nfile content here" in prompt
        assert "Question: Analyze this file" in prompt

    def test_format_v1_prompt_question_is_last(self) -> None:
        """Test that question always appears last in prompt."""
        request = RlsapiV1InferRequest(
            question="Help me",
            context={
                "system_info": "RHEL 9.3",
                "terminal_output": "error output",
            },
        )

        prompt = format_v1_prompt(request)

        # Question should be at the end
        assert prompt.endswith("Question: Help me")

    @pytest.mark.parametrize(
        "attachment,expected_content",
        [
            ("simple string attachment", "simple string attachment"),
            (123, "123"),
            (["list", "data"], "['list', 'data']"),
        ],
    )
    def test_format_v1_prompt_with_non_dict_attachment(
        self, attachment: Any, expected_content: str
    ) -> None:
        """Test formatting prompt with non-dict attachment (string/int/list)."""
        request = RlsapiV1InferRequest(
            question="Analyze this", context={"attachments": attachment}
        )

        prompt = format_v1_prompt(request)

        assert f"File (text/plain):\n{expected_content}" in prompt
        assert "Question: Analyze this" in prompt


class TestRlsapiV1InferEndpoint:
    """Tests for rlsapi_v1_infer_endpoint_handler function."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("common_mocks")
    async def test_rlsapi_v1_infer_success(
        self,
        mocker: MockerFixture,
        mock_request: Request,
        mock_auth: AuthTuple,
    ) -> None:
        """Test successful inference with quota tracking."""
        # Mock LlamaStack client
        mock_model = mocker.Mock()
        mock_model.model_type = "llm"
        mock_model.identifier = "test-model"

        mock_output_item = mocker.Mock()
        mock_output_item.type = "message"
        mock_output_item.role = "assistant"
        mock_output_item.content = "To list files, use the ls command."

        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]
        mock_response.usage = mocker.Mock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20

        mock_client = mocker.AsyncMock()
        mock_client.models.list.return_value = [mock_model]
        mock_client.responses.create.return_value = mock_response

        mock_client_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        infer_request = RlsapiV1InferRequest(question="How do I list files?")

        response = await rlsapi_v1_infer_endpoint_handler(
            request=mock_request, infer_request=infer_request, auth=mock_auth
        )

        assert response.data["text"] == "To list files, use the ls command."
        assert "request_id" in response.data

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("common_mocks")
    async def test_rlsapi_v1_infer_no_models(
        self,
        mocker: MockerFixture,
        mock_request: Request,
        mock_auth: AuthTuple,
    ) -> None:
        """Test error when no LLM models are available."""
        # Mock client returns no LLM models
        mock_client = mocker.AsyncMock()
        mock_client.models.list.return_value = []

        mock_client_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        infer_request = RlsapiV1InferRequest(question="How do I list files?")

        with pytest.raises(HTTPException) as exc_info:
            await rlsapi_v1_infer_endpoint_handler(
                request=mock_request, infer_request=infer_request, auth=mock_auth
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "No LLM models available" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("common_mocks")
    async def test_rlsapi_v1_infer_empty_response(
        self,
        mocker: MockerFixture,
        mock_request: Request,
        mock_auth: AuthTuple,
    ) -> None:
        """Test handling of empty response from Llama Stack."""
        mock_model = mocker.Mock()
        mock_model.model_type = "llm"
        mock_model.identifier = "test-model"

        # Mock response with empty output
        mock_response = mocker.Mock()
        mock_response.output = []
        mock_response.usage = None

        mock_client = mocker.AsyncMock()
        mock_client.models.list.return_value = [mock_model]
        mock_client.responses.create.return_value = mock_response

        mock_client_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        infer_request = RlsapiV1InferRequest(question="How do I list files?")

        response = await rlsapi_v1_infer_endpoint_handler(
            request=mock_request, infer_request=infer_request, auth=mock_auth
        )

        # Should use fallback message
        assert "unable to generate a response" in response.data["text"]

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("common_mocks")
    async def test_rlsapi_v1_infer_with_context(
        self,
        mocker: MockerFixture,
        mock_request: Request,
        mock_auth: AuthTuple,
    ) -> None:
        """Test inference with full context integration."""
        mock_model = mocker.Mock()
        mock_model.model_type = "llm"
        mock_model.identifier = "test-model"

        mock_output_item = mocker.Mock()
        mock_output_item.type = "message"
        mock_output_item.role = "assistant"
        mock_output_item.content = "This error means the command was not found."

        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]
        mock_response.usage = {"input_tokens": 50, "output_tokens": 30}

        mock_client = mocker.AsyncMock()
        mock_client.models.list.return_value = [mock_model]
        mock_client.responses.create.return_value = mock_response

        mock_client_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        infer_request = RlsapiV1InferRequest(
            question="What does this error mean?",
            context={
                "system_info": "RHEL 9.3",
                "terminal_output": "bash: command not found",
            },
        )

        response = await rlsapi_v1_infer_endpoint_handler(
            request=mock_request, infer_request=infer_request, auth=mock_auth
        )

        assert response.data["text"] == "This error means the command was not found."
        assert "request_id" in response.data

        # Verify context was passed to format_v1_prompt (indirectly through client call)
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args
        prompt_input = call_args.kwargs["input"]
        assert "RHEL 9.3" in prompt_input
        assert "command not found" in prompt_input

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("common_mocks")
    async def test_rlsapi_v1_infer_connection_error(
        self,
        mocker: MockerFixture,
        mock_request: Request,
        mock_auth: AuthTuple,
    ) -> None:
        """Test handling of Llama Stack connection error."""
        # Mock client that raises APIConnectionError
        mock_client = mocker.AsyncMock()
        mock_client.models.list.side_effect = APIConnectionError(request=None)  # type: ignore

        mock_client_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        infer_request = RlsapiV1InferRequest(question="Test question")

        with pytest.raises(HTTPException) as exc_info:
            await rlsapi_v1_infer_endpoint_handler(
                request=mock_request, infer_request=infer_request, auth=mock_auth
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "Unable to connect to Llama Stack" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_rlsapi_v1_infer_custom_system_prompt(
        self,
        mocker: MockerFixture,
        app_test_config: dict[str, Any],
        mock_request: Request,
        mock_auth: AuthTuple,
    ) -> None:
        """Test that custom system prompt from configuration is used."""
        mock_authorization_resolvers(mocker)

        # Add custom system prompt to config
        custom_prompt = "You are a specialized RHEL 9 assistant."
        app_test_config["customization"] = {"system_prompt": custom_prompt}

        cfg = AppConfig()
        cfg.init_from_dict(app_test_config)

        mocker.patch("app.endpoints.rlsapi_v1_infer.check_tokens_available")
        mocker.patch("app.endpoints.rlsapi_v1_infer.consume_tokens")
        mocker.patch("app.endpoints.rlsapi_v1_infer.configuration", cfg)

        # Mock LlamaStack client
        mock_model = mocker.Mock()
        mock_model.model_type = "llm"
        mock_model.identifier = "test-model"

        mock_output_item = mocker.Mock()
        mock_output_item.type = "message"
        mock_output_item.role = "assistant"
        mock_output_item.content = "Test response"

        mock_response = mocker.Mock()
        mock_response.output = [mock_output_item]
        mock_response.usage = mocker.Mock()
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20

        mock_client = mocker.AsyncMock()
        mock_client.models.list.return_value = [mock_model]
        mock_client.responses.create.return_value = mock_response

        mock_client_holder = mocker.patch(
            "app.endpoints.rlsapi_v1_infer.AsyncLlamaStackClientHolder"
        )
        mock_client_holder.return_value.get_client.return_value = mock_client

        infer_request = RlsapiV1InferRequest(question="Help me with RHEL")

        response = await rlsapi_v1_infer_endpoint_handler(
            request=mock_request, infer_request=infer_request, auth=mock_auth
        )

        # Verify the custom system prompt was passed to Llama Stack
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args
        assert call_args.kwargs["instructions"] == custom_prompt
        assert response.data["text"] == "Test response"
