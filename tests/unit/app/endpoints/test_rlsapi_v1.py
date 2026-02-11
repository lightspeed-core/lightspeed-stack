"""Unit tests for the rlsapi v1 /infer REST API endpoint."""

# pylint: disable=protected-access
# pylint: disable=unused-argument

from typing import Any

import pytest
from fastapi import HTTPException, status
from llama_stack_client import APIConnectionError
from pydantic import ValidationError
from pytest_mock import MockerFixture

import constants
from app.endpoints.rlsapi_v1 import (
    AUTH_DISABLED,
    _build_instructions,
    _get_default_model_id,
    _get_rh_identity_context,
    infer_endpoint,
    retrieve_simple_response,
)
from authentication.interface import AuthTuple
from authentication.rh_identity import RHIdentityData
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

MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


def _create_mock_request(mocker: MockerFixture, rh_identity: Any = None) -> Any:
    """Create a mock FastAPI Request with optional RH Identity data."""
    mock_request = mocker.Mock()
    mock_request.headers = {"User-Agent": "CLA/0.4.1"}

    if rh_identity is not None:
        mock_request.state = mocker.Mock()
        mock_request.state.rh_identity_data = rh_identity
    else:
        # Use spec=[] to create a Mock with no attributes, simulating absent rh_identity_data
        mock_request.state = mocker.Mock(spec=[])

    return mock_request


def _create_mock_background_tasks(mocker: MockerFixture) -> Any:
    """Create a mock BackgroundTasks object."""
    return mocker.Mock()


def _setup_responses_mock(mocker: MockerFixture, create_behavior: Any) -> None:
    """Set up responses.create mock with custom behavior."""
    mock_responses = mocker.Mock()
    mock_responses.create = create_behavior

    mock_client = mocker.Mock()
    mock_client.responses = mock_responses

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


def _create_mock_response_output(mocker: MockerFixture, text: str) -> Any:
    """Create a mock Responses API output item with assistant message."""
    mock_output_item = mocker.Mock()
    mock_output_item.type = "message"
    mock_output_item.role = "assistant"
    mock_output_item.content = text
    return mock_output_item


@pytest.fixture(name="mock_llm_response")
def mock_llm_response_fixture(mocker: MockerFixture) -> None:
    """Mock the LLM integration for successful responses via Responses API."""
    mock_response = mocker.Mock()
    mock_response.output = [
        _create_mock_response_output(mocker, "This is a test LLM response.")
    ]
    _setup_responses_mock(mocker, mocker.AsyncMock(return_value=mock_response))


@pytest.fixture(name="mock_empty_llm_response")
def mock_empty_llm_response_fixture(mocker: MockerFixture) -> None:
    """Mock responses.create to return empty output list."""
    mock_response = mocker.Mock()
    mock_response.output = []
    _setup_responses_mock(mocker, mocker.AsyncMock(return_value=mock_response))


@pytest.fixture(name="mock_auth_resolvers")
def mock_auth_resolvers_fixture(mocker: MockerFixture) -> None:
    """Mock authorization resolvers for endpoint tests."""
    mock_authorization_resolvers(mocker)


@pytest.fixture(name="mock_api_connection_error")
def mock_api_connection_error_fixture(mocker: MockerFixture) -> None:
    """Mock responses.create() to raise APIConnectionError."""
    _setup_responses_mock(
        mocker,
        mocker.AsyncMock(side_effect=APIConnectionError(request=mocker.Mock())),
    )


# --- Test _build_instructions ---


@pytest.mark.parametrize(
    ("systeminfo_kwargs", "expected_contains", "expected_not_contains"),
    [
        pytest.param(
            {"os": "RHEL", "version": "9.3", "arch": "x86_64"},
            ["OS: RHEL", "Version: 9.3", "Architecture: x86_64"],
            [],
            id="full_systeminfo",
        ),
        pytest.param(
            {"os": "RHEL", "version": "", "arch": ""},
            ["OS: RHEL"],
            ["Version:", "Architecture:"],
            id="partial_systeminfo",
        ),
        pytest.param(
            {},
            [constants.DEFAULT_SYSTEM_PROMPT],
            ["OS:", "Version:", "Architecture:"],
            id="empty_systeminfo",
        ),
    ],
)
def test_build_instructions(
    systeminfo_kwargs: dict[str, str],
    expected_contains: list[str],
    expected_not_contains: list[str],
) -> None:
    """Test _build_instructions with various system info combinations."""
    systeminfo = RlsapiV1SystemInfo(**systeminfo_kwargs)
    result = _build_instructions(systeminfo)

    for expected in expected_contains:
        assert expected in result
    for not_expected in expected_not_contains:
        assert not_expected not in result


# --- Test _build_instructions with customization.system_prompt ---


@pytest.mark.parametrize(
    ("custom_prompt", "expected_prompt"),
    [
        pytest.param(
            "You are a RHEL expert.",
            "You are a RHEL expert.",
            id="customization_system_prompt_set",
        ),
        pytest.param(
            None,
            constants.DEFAULT_SYSTEM_PROMPT,
            id="customization_system_prompt_none",
        ),
    ],
)
def test_build_instructions_with_customization(
    mocker: MockerFixture,
    custom_prompt: str | None,
    expected_prompt: str,
) -> None:
    """Test _build_instructions uses customization.system_prompt when set."""
    mock_customization = mocker.Mock()
    mock_customization.system_prompt = custom_prompt
    mock_config = mocker.Mock()
    mock_config.customization = mock_customization
    mocker.patch("app.endpoints.rlsapi_v1.configuration", mock_config)

    systeminfo = RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64")
    result = _build_instructions(systeminfo)

    assert expected_prompt in result
    assert "OS: RHEL" in result


def test_build_instructions_no_customization(mocker: MockerFixture) -> None:
    """Test _build_instructions falls back when customization is None."""
    mock_config = mocker.Mock()
    mock_config.customization = None
    mocker.patch("app.endpoints.rlsapi_v1.configuration", mock_config)

    systeminfo = RlsapiV1SystemInfo()
    result = _build_instructions(systeminfo)

    assert result == constants.DEFAULT_SYSTEM_PROMPT


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
    response = await retrieve_simple_response(
        "How do I list files?", constants.DEFAULT_SYSTEM_PROMPT
    )
    assert response == "This is a test LLM response."


@pytest.mark.asyncio
async def test_retrieve_simple_response_empty_output(
    mock_configuration: AppConfig, mock_empty_llm_response: None
) -> None:
    """Test retrieve_simple_response handles empty LLM output."""
    response = await retrieve_simple_response(
        "Test question", constants.DEFAULT_SYSTEM_PROMPT
    )
    assert response == ""


@pytest.mark.asyncio
async def test_retrieve_simple_response_api_connection_error(
    mock_configuration: AppConfig, mock_api_connection_error: None
) -> None:
    """Test retrieve_simple_response propagates APIConnectionError."""
    with pytest.raises(APIConnectionError):
        await retrieve_simple_response("Test question", constants.DEFAULT_SYSTEM_PROMPT)


# --- Test _get_rh_identity_context ---


def test_get_rh_identity_context_with_rh_identity(mocker: MockerFixture) -> None:
    """Test extraction of org_id and system_id from RH Identity data."""
    mock_rh_identity = mocker.Mock(spec=RHIdentityData)
    mock_rh_identity.get_org_id.return_value = "12345678"
    mock_rh_identity.get_user_id.return_value = "system-cn-abc123"

    mock_request = _create_mock_request(mocker, rh_identity=mock_rh_identity)

    org_id, system_id = _get_rh_identity_context(mock_request)

    assert org_id == "12345678"
    assert system_id == "system-cn-abc123"


def test_get_rh_identity_context_without_rh_identity(mocker: MockerFixture) -> None:
    """Test auth_disabled defaults when RH Identity is not configured."""
    mock_request = _create_mock_request(mocker, rh_identity=None)

    org_id, system_id = _get_rh_identity_context(mock_request)

    assert org_id == AUTH_DISABLED
    assert system_id == AUTH_DISABLED


def test_get_rh_identity_context_with_empty_values(mocker: MockerFixture) -> None:
    """Test auth_disabled fallback when RH Identity returns empty strings."""
    mock_rh_identity = mocker.Mock(spec=RHIdentityData)
    mock_rh_identity.get_org_id.return_value = ""
    mock_rh_identity.get_user_id.return_value = ""

    mock_request = _create_mock_request(mocker, rh_identity=mock_rh_identity)

    org_id, system_id = _get_rh_identity_context(mock_request)

    assert org_id == AUTH_DISABLED
    assert system_id == AUTH_DISABLED


# --- Test infer_endpoint ---


@pytest.mark.asyncio
async def test_infer_minimal_request(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
) -> None:
    """Test /infer endpoint returns valid response with LLM text."""
    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text == "This is a test LLM response."
    assert response.data.request_id is not None
    assert check_suid(response.data.request_id)


@pytest.mark.asyncio
async def test_infer_full_context_request(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
) -> None:
    """Test /infer endpoint handles full context (stdin, attachments, terminal)."""
    infer_request = RlsapiV1InferRequest(
        question="Why did this command fail?",
        context=RlsapiV1Context(
            stdin="some piped input",
            attachments=RlsapiV1Attachment(contents="key=value", mimetype="text/plain"),
            terminal=RlsapiV1Terminal(output="bash: command not found"),
            systeminfo=RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64"),
        ),
    )
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text
    assert response.data.request_id


@pytest.mark.asyncio
async def test_infer_generates_unique_request_ids(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
) -> None:
    """Test that each /infer call generates a unique request_id."""
    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    response1 = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )
    response2 = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert response1.data.request_id != response2.data.request_id


@pytest.mark.asyncio
async def test_infer_api_connection_error_returns_503(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_api_connection_error: None,
    mock_auth_resolvers: None,
) -> None:
    """Test /infer endpoint returns 503 when LLM service is unavailable."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_infer_empty_llm_response_returns_fallback(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_empty_llm_response: None,
    mock_auth_resolvers: None,
) -> None:
    """Test /infer endpoint returns fallback text when LLM returns empty response."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert response.data.text == constants.UNABLE_TO_PROCESS_RESPONSE


# --- Test Splunk integration ---


@pytest.mark.asyncio
async def test_infer_queues_splunk_event_on_success(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
) -> None:
    """Test that successful inference queues a Splunk event via BackgroundTasks."""
    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_background_tasks.add_task.assert_called_once()
    call_args = mock_background_tasks.add_task.call_args
    assert call_args[0][1]["question"] == "How do I list files?"
    assert call_args[0][2] == "infer_with_llm"


@pytest.mark.asyncio
async def test_infer_queues_splunk_error_event_on_failure(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_api_connection_error: None,
    mock_auth_resolvers: None,
) -> None:
    """Test that failed inference queues a Splunk error event."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    with pytest.raises(HTTPException):
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )

    mock_background_tasks.add_task.assert_called_once()
    call_args = mock_background_tasks.add_task.call_args
    assert call_args[0][2] == "infer_error"


@pytest.mark.asyncio
async def test_infer_splunk_event_includes_rh_identity_context(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
) -> None:
    """Test that Splunk event includes org_id and system_id from RH Identity."""
    mock_rh_identity = mocker.Mock(spec=RHIdentityData)
    mock_rh_identity.get_org_id.return_value = "org123"
    mock_rh_identity.get_user_id.return_value = "system456"

    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = _create_mock_request(mocker, rh_identity=mock_rh_identity)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    call_args = mock_background_tasks.add_task.call_args
    event = call_args[0][1]
    assert event["org_id"] == "org123"
    assert event["system_id"] == "system456"


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


# --- Test MCP tools passthrough ---


def _setup_responses_mock_with_capture(
    mocker: MockerFixture, response_text: str = "Test response."
) -> Any:
    """Set up responses.create mock and return the create mock for assertion.

    Unlike _setup_responses_mock, this returns the mock_create object so
    callers can inspect call_args to verify tools were passed correctly.

    Args:
        mocker: The pytest mocker fixture.
        response_text: Text for the mock LLM response.

    Returns:
        The mock create coroutine, whose call_args can be inspected.
    """
    mock_response = mocker.Mock()
    mock_response.output = [_create_mock_response_output(mocker, response_text)]

    mock_create = mocker.AsyncMock(return_value=mock_response)
    _setup_responses_mock(mocker, mock_create)
    return mock_create


@pytest.mark.asyncio
async def test_retrieve_simple_response_passes_tools(
    mocker: MockerFixture, mock_configuration: AppConfig
) -> None:
    """Test that retrieve_simple_response forwards tools to responses.create()."""
    mock_create = _setup_responses_mock_with_capture(mocker)
    tools = [
        {
            "type": "mcp",
            "server_label": "test-mcp",
            "server_url": "http://localhost:9000/sse",
            "require_approval": "never",
        }
    ]

    await retrieve_simple_response("Test question", "Instructions", tools=tools)

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["tools"] == tools


@pytest.mark.asyncio
async def test_retrieve_simple_response_defaults_to_empty_tools(
    mocker: MockerFixture, mock_configuration: AppConfig
) -> None:
    """Test that retrieve_simple_response passes empty list when tools is None."""
    mock_create = _setup_responses_mock_with_capture(mocker)

    await retrieve_simple_response("Test question", "Instructions")

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["tools"] == []


@pytest.mark.asyncio
async def test_infer_endpoint_calls_get_mcp_tools(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
) -> None:
    """Test that infer_endpoint calls get_mcp_tools with configuration.mcp_servers."""
    mock_get_mcp_tools = mocker.patch(
        "app.endpoints.rlsapi_v1.get_mcp_tools",
        return_value=[{"type": "mcp", "server_label": "test"}],
    )

    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = _create_mock_request(mocker)
    mock_background_tasks = _create_mock_background_tasks(mocker)

    await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_get_mcp_tools.assert_called_once_with(mock_configuration.mcp_servers)
