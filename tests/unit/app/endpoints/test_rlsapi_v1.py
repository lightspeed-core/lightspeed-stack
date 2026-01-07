"""Unit tests for the rlsapi v1 /infer REST API endpoint."""

# pylint: disable=protected-access
# pylint: disable=unused-argument

from typing import Any

import pytest
from fastapi import HTTPException, status
from llama_stack_client import APIConnectionError
from llama_stack_client.types.chat.completion_create_response import (
    OpenAIChatCompletion,
    OpenAIChatCompletionChoice,
)
from pydantic import ValidationError
from pytest_mock import MockerFixture

import constants
from app.endpoints.rlsapi_v1 import (
    _get_default_model_id,
    infer_endpoint,
    retrieve_simple_response,
)
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.rlsapi.requests import (
    RlsapiV1Attachment,
    RlsapiV1Context,
    RlsapiV1InferRequest,
    RlsapiV1SystemInfo,
    RlsapiV1Terminal,
)
from models.rlsapi.responses import RlsapiV1InferResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers
from utils.suid import check_suid

MOCK_AUTH: AuthTuple = ("test_user_id", "test_user", True, "test_token")


def _setup_chat_completions_mock(mocker: MockerFixture, create_behavior: Any) -> None:
    """Set up chat.completions mock with custom create() behavior.

    Args:
        mocker: The pytest-mock fixture for creating mocks.
        create_behavior: The AsyncMock or side_effect for completions.create().
    """
    mock_completions = mocker.Mock()
    mock_completions.create = create_behavior

    mock_chat = mocker.Mock()
    mock_chat.completions = mock_completions

    mock_client = mocker.Mock()
    mock_client.chat = mock_chat

    mock_client_holder = mocker.Mock()
    mock_client_holder.get_client.return_value = mock_client
    mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder",
        return_value=mock_client_holder,
    )


@pytest.fixture(name="mock_configuration")
def mock_configuration_fixture(
    mocker: MockerFixture, minimal_config: AppConfig
) -> AppConfig:
    """Extend minimal_config with inference defaults and patch it."""
    minimal_config.inference.default_model = "gpt-4-turbo"
    minimal_config.inference.default_provider = "openai"
    mocker.patch("app.endpoints.rlsapi_v1.configuration", minimal_config)
    return minimal_config


@pytest.fixture(name="mock_llm_response")
def mock_llm_response_fixture(mocker: MockerFixture) -> None:
    """Mock the LLM integration for successful responses via chat.completions."""
    mock_message = mocker.Mock()
    mock_message.content = "This is a test LLM response."

    mock_choice = mocker.Mock(spec=OpenAIChatCompletionChoice)
    mock_choice.message = mock_message

    mock_response = mocker.Mock(spec=OpenAIChatCompletion)
    mock_response.choices = [mock_choice]

    _setup_chat_completions_mock(mocker, mocker.AsyncMock(return_value=mock_response))


@pytest.fixture(name="mock_empty_llm_response")
def mock_empty_llm_response_fixture(mocker: MockerFixture) -> None:
    """Mock chat.completions to return empty choices list."""
    mock_response = mocker.Mock(spec=OpenAIChatCompletion)
    mock_response.choices = []

    _setup_chat_completions_mock(mocker, mocker.AsyncMock(return_value=mock_response))


@pytest.fixture(name="mock_api_connection_error")
def mock_api_connection_error_fixture(mocker: MockerFixture) -> None:
    """Mock chat.completions.create() to raise APIConnectionError."""
    _setup_chat_completions_mock(
        mocker,
        mocker.AsyncMock(side_effect=APIConnectionError(request=mocker.Mock())),
    )


# --- Test _get_default_model_id ---


def test_get_default_model_id_success(mock_configuration: AppConfig) -> None:
    """Test _get_default_model_id returns properly formatted model ID."""
    model_id = _get_default_model_id()
    assert model_id == "openai/gpt-4-turbo"


@pytest.mark.parametrize(
    ("config_setup", "expected_message"),
    [
        pytest.param(
            "missing_model",
            "No default model configured",
            id="missing_model_config",
        ),
        pytest.param(
            "none_inference",
            "No inference configuration available",
            id="none_inference_config",
        ),
    ],
)
def test_get_default_model_id_errors(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    config_setup: str,
    expected_message: str,
) -> None:
    """Test _get_default_model_id raises HTTPException for invalid configs."""
    if config_setup == "missing_model":
        # Config exists but no model/provider defaults
        mocker.patch("app.endpoints.rlsapi_v1.configuration", minimal_config)
    else:
        # inference is None
        mock_config = mocker.Mock()
        mock_config.inference = None
        mocker.patch("app.endpoints.rlsapi_v1.configuration", mock_config)

    with pytest.raises(HTTPException) as exc_info:
        _get_default_model_id()

    assert exc_info.value.status_code == 503
    assert expected_message in str(exc_info.value.detail)


# --- Test retrieve_simple_response ---


@pytest.mark.asyncio
async def test_retrieve_simple_response_success(
    mock_configuration: AppConfig, mock_llm_response: None
) -> None:
    """Test retrieve_simple_response returns LLM response text."""
    response = await retrieve_simple_response("How do I list files?")
    assert response == "This is a test LLM response."


@pytest.mark.asyncio
async def test_retrieve_simple_response_empty_output(
    mock_configuration: AppConfig, mock_empty_llm_response: None
) -> None:
    """Test retrieve_simple_response handles empty LLM output."""
    response = await retrieve_simple_response("Test question")
    assert response == ""


@pytest.mark.asyncio
async def test_retrieve_simple_response_api_connection_error(
    mock_configuration: AppConfig, mock_api_connection_error: None
) -> None:
    """Test retrieve_simple_response propagates APIConnectionError."""
    with pytest.raises(APIConnectionError):
        await retrieve_simple_response("Test question")


# --- Test infer_endpoint ---


@pytest.mark.asyncio
async def test_infer_minimal_request(
    mocker: MockerFixture, mock_configuration: AppConfig, mock_llm_response: None
) -> None:
    """Test /infer endpoint returns valid response with LLM text."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(question="How do I list files?")

    response = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text == "This is a test LLM response."
    assert response.data.request_id is not None
    assert check_suid(response.data.request_id)


@pytest.mark.asyncio
async def test_infer_full_context_request(
    mocker: MockerFixture, mock_configuration: AppConfig, mock_llm_response: None
) -> None:
    """Test /infer endpoint handles full context (stdin, attachments, terminal)."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(
        question="Why did this command fail?",
        context=RlsapiV1Context(
            stdin="some piped input",
            attachments=RlsapiV1Attachment(contents="key=value", mimetype="text/plain"),
            terminal=RlsapiV1Terminal(output="bash: command not found"),
            systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64"),
        ),
    )

    response = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text
    assert response.data.request_id


@pytest.mark.asyncio
async def test_infer_generates_unique_request_ids(
    mocker: MockerFixture, mock_configuration: AppConfig, mock_llm_response: None
) -> None:
    """Test that each /infer call generates a unique request_id."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(question="How do I list files?")

    response1 = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)
    response2 = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert response1.data.request_id != response2.data.request_id


@pytest.mark.asyncio
async def test_infer_api_connection_error_returns_503(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_api_connection_error: None,
) -> None:
    """Test /infer endpoint returns 503 when LLM service is unavailable."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(question="Test question")

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_infer_empty_llm_response_returns_fallback(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_empty_llm_response: None,
) -> None:
    """Test /infer endpoint returns fallback text when LLM returns empty response."""
    mock_authorization_resolvers(mocker)
    request = RlsapiV1InferRequest(question="Test question")

    response = await infer_endpoint(infer_request=request, auth=MOCK_AUTH)

    assert response.data.text == constants.UNABLE_TO_PROCESS_RESPONSE


# --- Test request validation ---


@pytest.mark.parametrize("invalid_question", ["", "   ", "\t\n"])
def test_infer_rejects_invalid_question(invalid_question: str) -> None:
    """Test that empty or whitespace-only questions are rejected."""
    with pytest.raises(ValidationError):
        RlsapiV1InferRequest(question=invalid_question)


def test_infer_request_question_is_stripped() -> None:
    """Test that question whitespace is stripped during validation."""
    request = RlsapiV1InferRequest(question="  How do I list files?  ")
    assert request.question == "How do I list files?"
