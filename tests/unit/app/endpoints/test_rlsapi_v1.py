"""Unit tests for the rlsapi v1 /infer REST API endpoint."""

# pylint: disable=protected-access
# pylint: disable=unused-argument
# pylint: disable=too-many-lines
# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

import re
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import HTTPException, status
from llama_stack_client import APIConnectionError
from pydantic import ValidationError
from pytest_mock import MockerFixture

import constants
from app.endpoints.rlsapi_v1 import (
    AUTH_DISABLED,
    TemplateRenderError,
    _build_instructions,
    _compile_prompt_template,
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
from models.responses import ServiceUnavailableResponse
from models.rlsapi.responses import RlsapiV1InferResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers
from utils.suid import check_suid

MOCK_AUTH: AuthTuple = ("mock_user_id", "mock_username", False, "mock_token")


@pytest.fixture(autouse=True)
def _clear_prompt_template_cache() -> None:
    """Clear the lru_cache on _compile_prompt_template between tests."""
    _compile_prompt_template.cache_clear()


@pytest.fixture(name="mock_custom_prompt")
def mock_custom_prompt_fixture(mocker: MockerFixture) -> Callable[[str], None]:
    """Factory fixture that patches configuration with a custom system prompt."""

    def _set(prompt: str) -> None:
        mock_customization = mocker.Mock()
        mock_customization.system_prompt = prompt
        mock_config = mocker.Mock()
        mock_config.customization = mock_customization
        mocker.patch("app.endpoints.rlsapi_v1.configuration", mock_config)

    return _set


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


@pytest.fixture(name="mock_generic_runtime_error")
def mock_generic_runtime_error_fixture(mocker: MockerFixture) -> None:
    """Mock responses.create() to raise a non-context-length RuntimeError."""
    _setup_responses_mock(
        mocker,
        mocker.AsyncMock(side_effect=RuntimeError("something went wrong")),
    )


# --- Test _build_instructions ---


def test_build_instructions_default_prompt_passes_through() -> None:
    """Test _build_instructions returns default prompt unchanged when no template vars."""
    systeminfo = RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64")
    result = _build_instructions(systeminfo)

    assert result == constants.DEFAULT_SYSTEM_PROMPT


def test_build_instructions_with_customization(mocker: MockerFixture) -> None:
    """Test _build_instructions uses customization.system_prompt with template vars."""
    template = "Expert assistant.\n\nDate: {{ date }}\nOS: {{ os }}"
    mock_customization = mocker.Mock()
    mock_customization.system_prompt = template
    mock_config = mocker.Mock()
    mock_config.customization = mock_customization
    mocker.patch("app.endpoints.rlsapi_v1.configuration", mock_config)

    systeminfo = RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64")
    result = _build_instructions(systeminfo)

    assert "Expert assistant." in result
    assert "OS: RHEL" in result
    assert re.search(r"Date: \w+ \d{2}, \d{4}", result)


def test_build_instructions_no_customization(mocker: MockerFixture) -> None:
    """Test _build_instructions falls back to DEFAULT_SYSTEM_PROMPT."""
    mock_config = mocker.Mock()
    mock_config.customization = None
    mocker.patch("app.endpoints.rlsapi_v1.configuration", mock_config)

    systeminfo = RlsapiV1SystemInfo()
    result = _build_instructions(systeminfo)

    assert result == constants.DEFAULT_SYSTEM_PROMPT


# --- Test Jinja2 template rendering ---


def test_build_instructions_renders_jinja2_template(
    mock_custom_prompt: Callable[[str], None],
) -> None:
    """Test _build_instructions renders Jinja2 template variables instead of appending."""
    mock_custom_prompt(
        "You are an assistant.\n\nDate: {{ date }}\nOS: {{ os }} {{ version }} ({{ arch }})"
    )

    systeminfo = RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64")
    result = _build_instructions(systeminfo)

    assert "OS: RHEL 9.3 (x86_64)" in result
    assert re.search(r"Date: \w+ \d{2}, \d{4}", result)
    assert "Today's date:" not in result
    assert "User's system:" not in result


def test_build_instructions_jinja2_none_values_render_empty(
    mock_custom_prompt: Callable[[str], None],
) -> None:
    """Test that None system info values render as empty strings, not 'None'."""
    mock_custom_prompt("Assistant.\nOS={{ os }} VER={{ version }} ARCH={{ arch }}")

    systeminfo = RlsapiV1SystemInfo()
    result = _build_instructions(systeminfo)

    assert "None" not in result
    assert "OS= VER= ARCH=" in result


def test_build_instructions_jinja2_conditionals(
    mock_custom_prompt: Callable[[str], None],
) -> None:
    """Test that Jinja2 conditionals work in system prompt templates."""
    mock_custom_prompt(
        "Assistant.{% if os %} OS: {{ os }}{% endif %}"
        "{% if version %} VER: {{ version }}{% endif %}"
    )

    systeminfo = RlsapiV1SystemInfo(os="RHEL")
    result = _build_instructions(systeminfo)

    assert "OS: RHEL" in result
    assert "VER:" not in result


def test_build_instructions_plain_prompt_passes_through(
    mock_custom_prompt: Callable[[str], None],
) -> None:
    """Test that prompts without Jinja2 syntax pass through unchanged."""
    plain_prompt = "You are an expert RHEL assistant."
    mock_custom_prompt(plain_prompt)

    systeminfo = RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64")
    result = _build_instructions(systeminfo)

    assert result == plain_prompt


@pytest.mark.parametrize(
    "bad_template",
    [
        pytest.param("Hello {{ unclosed", id="unclosed_variable"),
        pytest.param("{% if %}", id="if_without_condition"),
        pytest.param("{% endfor %}", id="endfor_without_for"),
    ],
)
def test_build_instructions_malformed_template_raises_template_render_error(
    mock_custom_prompt: Callable[[str], None],
    bad_template: str,
) -> None:
    """Test that invalid Jinja2 syntax in system prompt raises TemplateRenderError."""
    mock_custom_prompt(bad_template)

    systeminfo = RlsapiV1SystemInfo(os="RHEL", version="9.3", arch="x86_64")

    with pytest.raises(TemplateRenderError, match="invalid Jinja2 syntax"):
        _build_instructions(systeminfo)


# --- Test _get_default_model_id ---


@pytest.mark.asyncio
async def test_get_default_model_id_success(mock_configuration: AppConfig) -> None:
    """Test _get_default_model_id returns properly formatted model ID."""
    model_id = await _get_default_model_id()
    assert model_id == "openai/gpt-4-turbo"


@pytest.mark.parametrize(
    "failure_mode",
    [
        pytest.param("no_llm_models", id="no_llm_models_found"),
        pytest.param("connection_error", id="connection_error"),
    ],
)
@pytest.mark.asyncio
async def test_get_default_model_id_errors(
    mocker: MockerFixture,
    minimal_config: AppConfig,
    failure_mode: str,
) -> None:
    """Test _get_default_model_id fallback failures raise 503 responses."""
    mocker.patch("app.endpoints.rlsapi_v1.configuration", minimal_config)

    mock_embedding_model = mocker.Mock()
    mock_embedding_model.custom_metadata = {"model_type": "embedding"}
    mock_embedding_model.id = "sentence-transformers/all-mpnet-base-v2"

    mock_client = mocker.Mock()
    mock_client.models = mocker.Mock()

    if failure_mode == "no_llm_models":
        mock_client.models.list = mocker.AsyncMock(return_value=[mock_embedding_model])
    else:
        mock_client.models.list = mocker.AsyncMock(
            side_effect=APIConnectionError(request=mocker.Mock())
        )

    mock_client_holder = mocker.Mock()
    mock_client_holder.get_client.return_value = mock_client
    mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder",
        return_value=mock_client_holder,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _get_default_model_id()

    assert exc_info.value.status_code == 503
    detail: dict[str, str] = exc_info.value.detail  # type: ignore[assignment]
    assert set(detail.keys()) == {"response", "cause"}


@pytest.mark.asyncio
async def test_config_error_503_matches_llm_error_503_shape(
    mocker: MockerFixture,
    minimal_config: AppConfig,
) -> None:
    """Test that auto-discovery 503s have the same shape as LLM error 503s.

    Both _get_default_model_id() no-LLM auto-discovery errors and APIConnectionError
    handlers use ServiceUnavailableResponse, producing identical detail shapes
    with 'response' and 'cause' keys.
    """
    mocker.patch("app.endpoints.rlsapi_v1.configuration", minimal_config)

    mock_embedding_model = mocker.Mock()
    mock_embedding_model.custom_metadata = {"model_type": "embedding"}
    mock_embedding_model.id = "sentence-transformers/all-mpnet-base-v2"

    mock_client = mocker.Mock()
    mock_client.models = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(return_value=[mock_embedding_model])

    mock_client_holder = mocker.Mock()
    mock_client_holder.get_client.return_value = mock_client
    mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder",
        return_value=mock_client_holder,
    )

    with pytest.raises(HTTPException) as config_exc:
        await _get_default_model_id()

    # Build an LLM connection error 503 using the same response model
    llm_response = ServiceUnavailableResponse(
        backend_name="Llama Stack",
        cause="Unable to connect to the inference backend",
    )
    llm_detail = llm_response.model_dump()["detail"]

    config_detail: dict[str, str] = config_exc.value.detail  # type: ignore[assignment]

    # Both must have identical key sets: {"response", "cause"}
    assert set(config_detail.keys()) == set(llm_detail.keys()) == {"response", "cause"}


@pytest.mark.asyncio
async def test_get_default_model_id_auto_discovery_success(
    mocker: MockerFixture, minimal_config: AppConfig
) -> None:
    """Test _get_default_model_id returns first discovered LLM model ID."""
    mocker.patch("app.endpoints.rlsapi_v1.configuration", minimal_config)

    mock_llm_model = mocker.Mock()
    mock_llm_model.custom_metadata = {"model_type": "llm"}
    mock_llm_model.id = "openai/gpt-4o-mini"

    mock_embedding_model = mocker.Mock()
    mock_embedding_model.custom_metadata = {"model_type": "embedding"}
    mock_embedding_model.id = "sentence-transformers/all-mpnet-base-v2"

    mock_client = mocker.Mock()
    mock_client.models = mocker.Mock()
    mock_client.models.list = mocker.AsyncMock(
        return_value=[mock_embedding_model, mock_llm_model]
    )

    mock_client_holder = mocker.Mock()
    mock_client_holder.get_client.return_value = mock_client
    mocker.patch(
        "app.endpoints.rlsapi_v1.AsyncLlamaStackClientHolder",
        return_value=mock_client_holder,
    )

    model_id = await _get_default_model_id()

    assert model_id == "openai/gpt-4o-mini"


# --- Test retrieve_simple_response ---


async def test_retrieve_simple_response_success(
    mock_configuration: AppConfig, mock_llm_response: None
) -> None:
    """Test retrieve_simple_response returns LLM response text."""
    response = await retrieve_simple_response(
        "How do I list files?", constants.DEFAULT_SYSTEM_PROMPT
    )
    assert response == "This is a test LLM response."


async def test_retrieve_simple_response_empty_output(
    mock_configuration: AppConfig, mock_empty_llm_response: None
) -> None:
    """Test retrieve_simple_response handles empty LLM output."""
    response = await retrieve_simple_response(
        "Test question", constants.DEFAULT_SYSTEM_PROMPT
    )
    assert response == ""


async def test_retrieve_simple_response_api_connection_error(
    mock_configuration: AppConfig, mock_api_connection_error: None
) -> None:
    """Test retrieve_simple_response propagates APIConnectionError."""
    with pytest.raises(APIConnectionError):
        await retrieve_simple_response("Test question", constants.DEFAULT_SYSTEM_PROMPT)


# --- Test _get_rh_identity_context ---


@pytest.mark.parametrize(
    ("rh_identity_setup", "expected_org_id", "expected_system_id"),
    [
        pytest.param(
            {"org_id": "12345678", "user_id": "system-cn-abc123"},
            "12345678",
            "system-cn-abc123",
            id="with_identity",
        ),
        pytest.param(None, AUTH_DISABLED, AUTH_DISABLED, id="without_identity"),
        pytest.param(
            {"org_id": "", "user_id": ""},
            AUTH_DISABLED,
            AUTH_DISABLED,
            id="empty_values",
        ),
    ],
)
def test_get_rh_identity_context(
    mocker: MockerFixture,
    mock_request_factory: Callable[..., Any],
    rh_identity_setup: dict[str, str] | None,
    expected_org_id: str,
    expected_system_id: str,
) -> None:
    """Test _get_rh_identity_context extracts or defaults org/system IDs."""
    if rh_identity_setup is not None:
        mock_rh_identity = mocker.Mock(spec=RHIdentityData)
        mock_rh_identity.get_org_id.return_value = rh_identity_setup["org_id"]
        mock_rh_identity.get_user_id.return_value = rh_identity_setup["user_id"]
        mock_request = mock_request_factory(rh_identity=mock_rh_identity)
    else:
        mock_request = mock_request_factory()

    org_id, system_id = _get_rh_identity_context(mock_request)

    assert org_id == expected_org_id
    assert system_id == expected_system_id


# --- Test infer_endpoint ---


async def test_infer_minimal_request(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer endpoint returns valid response with LLM text."""
    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = mock_request_factory()

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
    # Standard response must not include verbose metadata (dual opt-in required)
    assert response.data.tool_calls is None
    assert response.data.tool_results is None
    assert response.data.rag_chunks is None
    assert response.data.referenced_documents is None
    assert response.data.input_tokens is None
    assert response.data.output_tokens is None
    # Minimal serialized data keys (matches response_model_exclude_none on /infer)
    data_keys = set(response.model_dump(exclude_none=True)["data"].keys())
    assert data_keys == {
        "text",
        "request_id",
    }, f"Expected only text and request_id, got {data_keys}"


async def test_infer_full_context_request(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
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
    mock_request = mock_request_factory()

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text
    assert response.data.request_id


async def test_infer_generates_unique_request_ids(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that each /infer call generates a unique request_id."""
    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = mock_request_factory()

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


async def test_infer_api_connection_error_returns_503(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_api_connection_error: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer endpoint returns 503 when LLM service is unavailable."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = mock_request_factory()

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


async def test_infer_malformed_template_returns_500(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_custom_prompt: Callable[[str], None],
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer endpoint returns 500 when system prompt has invalid Jinja2 syntax."""
    mock_custom_prompt("Hello {{ unclosed")

    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = mock_request_factory()

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


async def test_infer_empty_llm_response_returns_fallback(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_empty_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer endpoint returns fallback text when LLM returns empty response."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = mock_request_factory()

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert response.data.text == constants.UNABLE_TO_PROCESS_RESPONSE


@pytest.mark.parametrize(
    ("verbose_enabled", "expect_metadata"),
    [
        pytest.param(True, True, id="verbose_enabled"),
        pytest.param(False, False, id="verbose_disabled"),
    ],
)
async def test_infer_include_metadata_respects_verbose_config(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
    verbose_enabled: bool,
    expect_metadata: bool,
) -> None:
    """Test /infer metadata inclusion controlled by dual opt-in (config + request)."""
    custom_mock = mocker.Mock()
    custom_mock.allow_verbose_infer = verbose_enabled
    custom_mock.system_prompt = "You are a helpful assistant."
    config_mock = mocker.Mock()
    config_mock.inference = mock_configuration.inference
    config_mock.customization = custom_mock
    mocker.patch("app.endpoints.rlsapi_v1.configuration", config_mock)

    mock_response = mocker.Mock()
    mock_response.output = [
        _create_mock_response_output(mocker, "Metadata test response.")
    ]
    mock_usage = mocker.Mock()
    mock_usage.input_tokens = 42
    mock_usage.output_tokens = 18
    mock_response.usage = mock_usage
    _setup_responses_mock(mocker, mocker.AsyncMock(return_value=mock_response))

    infer_request = RlsapiV1InferRequest(
        question="How do I list files?", include_metadata=True
    )

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    if expect_metadata:
        assert isinstance(response, RlsapiV1InferResponse)
        assert response.data.text == "Metadata test response."
        assert response.data.request_id is not None
        assert response.data.tool_calls is not None
        assert response.data.tool_results is not None
        assert response.data.rag_chunks is not None
        assert response.data.referenced_documents is not None
        assert response.data.input_tokens == 42
        assert response.data.output_tokens == 18
    else:
        assert response.data.tool_calls is None
        assert response.data.tool_results is None
        assert response.data.rag_chunks is None
        assert response.data.referenced_documents is None
        assert response.data.input_tokens is None
        assert response.data.output_tokens is None


def _setup_config_mock(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    verbose_enabled: bool,
) -> None:
    """Helper to set up configuration mock with verbose setting."""
    custom_mock = mocker.Mock()
    custom_mock.allow_verbose_infer = verbose_enabled
    custom_mock.system_prompt = "You are a helpful assistant."
    config_mock = mocker.Mock()
    config_mock.inference = mock_configuration.inference
    config_mock.customization = custom_mock
    mocker.patch("app.endpoints.rlsapi_v1.configuration", config_mock)


@pytest.mark.parametrize(
    ("verbose_enabled", "expect_extract_called"),
    [
        pytest.param(True, True, id="verbose_calls_extract"),
        pytest.param(False, False, id="non_verbose_skips_extract"),
    ],
)
async def test_infer_extract_token_usage_on_failure_depends_on_verbose(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
    verbose_enabled: bool,
    expect_extract_called: bool,
) -> None:
    """Verify extract_token_usage is called on failure only when verbose is enabled."""
    _setup_config_mock(mocker, mock_configuration, verbose_enabled=verbose_enabled)

    mock_usage: Any = None
    if verbose_enabled:
        mock_response = mocker.Mock()
        mock_response.output = [_create_mock_response_output(mocker, "Response")]
        mock_usage = mocker.Mock()
        mock_usage.input_tokens = 50
        mock_usage.output_tokens = 25
        mock_response.usage = mock_usage
        _setup_responses_mock(mocker, mocker.AsyncMock(return_value=mock_response))
        mocker.patch(
            "app.endpoints.rlsapi_v1.extract_text_from_response_items",
            side_effect=RuntimeError("text extraction failed"),
        )
    else:
        mocker.patch(
            "app.endpoints.rlsapi_v1.retrieve_simple_response",
            side_effect=RuntimeError("retrieval failed"),
        )

    mock_extract = mocker.patch("app.endpoints.rlsapi_v1.extract_token_usage")

    with pytest.raises(RuntimeError):
        infer_request = RlsapiV1InferRequest(question="How do I list files?")
        if verbose_enabled:
            infer_request.include_metadata = True
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request_factory(),
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )

    if expect_extract_called:
        mock_extract.assert_called_once()
        call_args = mock_extract.call_args
        assert call_args[0][0] == mock_usage
        assert call_args[0][1] == "openai/gpt-4-turbo"
    else:
        mock_extract.assert_not_called()


# --- Test Splunk integration ---


async def test_infer_queues_splunk_event_on_success(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that successful inference queues a Splunk event via BackgroundTasks."""
    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = mock_request_factory()

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


async def test_infer_queues_splunk_error_event_on_failure(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_api_connection_error: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that failed inference queues a Splunk error event."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = mock_request_factory()

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


async def test_infer_splunk_event_includes_rh_identity_context(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that Splunk event includes org_id and system_id from RH Identity."""
    mock_rh_identity = mocker.Mock(spec=RHIdentityData)
    mock_rh_identity.get_org_id.return_value = "org123"
    mock_rh_identity.get_user_id.return_value = "system456"

    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = mock_request_factory(rh_identity=mock_rh_identity)

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


async def test_retrieve_simple_response_defaults_to_empty_tools(
    mocker: MockerFixture, mock_configuration: AppConfig
) -> None:
    """Test that retrieve_simple_response passes empty list when tools is None."""
    mock_create = _setup_responses_mock_with_capture(mocker)

    await retrieve_simple_response("Test question", "Instructions")

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["tools"] == []


async def test_infer_endpoint_calls_get_mcp_tools(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that infer_endpoint calls get_mcp_tools with configuration.mcp_servers."""
    mock_get_mcp_tools = mocker.patch(
        "app.endpoints.rlsapi_v1.get_mcp_tools",
        new_callable=mocker.AsyncMock,
        return_value=[{"type": "mcp", "server_label": "test"}],
    )

    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = mock_request_factory()

    await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_get_mcp_tools.assert_called_once_with(
        request_headers=mock_request.headers,
    )


async def test_infer_generic_runtime_error_reraises(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_generic_runtime_error: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer endpoint re-raises non-context-length RuntimeErrors."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = mock_request_factory()

    with pytest.raises(RuntimeError, match="something went wrong"):
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )


async def test_infer_generic_runtime_error_records_failure(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_generic_runtime_error: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that non-context-length RuntimeErrors record inference failure metrics."""
    infer_request = RlsapiV1InferRequest(question="Test question")
    mock_request = mock_request_factory()

    with pytest.raises(RuntimeError):
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )

    mock_background_tasks.add_task.assert_called_once()
    call_args = mock_background_tasks.add_task.call_args
    assert call_args[0][2] == "infer_error"
