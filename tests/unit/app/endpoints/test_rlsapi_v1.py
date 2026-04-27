"""Unit tests for the rlsapi v1 /infer REST API endpoint."""

# pylint: disable=protected-access
# pylint: disable=unused-argument
# pylint: disable=too-many-lines
# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

import re
from collections.abc import Callable
from typing import Any, Optional

import pytest
from fastapi import HTTPException, status
from llama_stack_api import OpenAIResponseMessage
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
    _resolve_quota_subject,
    infer_endpoint,
    retrieve_simple_response,
)
from authentication.interface import AuthTuple
from authentication.rh_identity import RHIdentityData
from configuration import AppConfig
from models.responses import ServiceUnavailableResponse
from models.rlsapi.requests import (
    RlsapiV1Attachment,
    RlsapiV1Context,
    RlsapiV1InferRequest,
    RlsapiV1SystemInfo,
    RlsapiV1Terminal,
)
from models.rlsapi.responses import RlsapiV1InferResponse
from tests.unit.utils.auth_helpers import mock_authorization_resolvers
from utils.rh_identity import get_rh_identity_context
from utils.suid import check_suid
from utils.types import ShieldModerationBlocked, ShieldModerationPassed

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
        mock_rlsapi_v1 = mocker.Mock()
        mock_rlsapi_v1.allow_verbose_infer = False
        mock_rlsapi_v1.quota_subject = None
        mock_config = mocker.Mock()
        mock_config.customization = mock_customization
        mock_config.rlsapi_v1 = mock_rlsapi_v1
        mock_config.quota_limiters = []
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
    mock_usage = mocker.Mock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage
    _setup_responses_mock(mocker, mocker.AsyncMock(return_value=mock_response))


@pytest.fixture(name="mock_empty_llm_response")
def mock_empty_llm_response_fixture(mocker: MockerFixture) -> None:
    """Mock responses.create to return empty output list."""
    mock_response = mocker.Mock()
    mock_response.output = []
    mock_usage = mocker.Mock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_response.usage = mock_usage
    _setup_responses_mock(mocker, mocker.AsyncMock(return_value=mock_response))


@pytest.fixture(name="mock_auth_resolvers")
def mock_auth_resolvers_fixture(mocker: MockerFixture) -> None:
    """Mock authorization resolvers for endpoint tests."""
    mock_authorization_resolvers(mocker)


@pytest.fixture(autouse=True, name="mock_shield_passed")
def mock_shield_passed_fixture(mocker: MockerFixture) -> None:
    """Mock shield moderation to pass for all endpoint tests by default.

    Individual tests can override this by patching run_shield_moderation
    with a different return value.
    """
    mocker.patch(
        "app.endpoints.rlsapi_v1.run_shield_moderation",
        new=mocker.AsyncMock(return_value=ShieldModerationPassed()),
    )


@pytest.fixture(autouse=True, name="mock_model_configured")
def mock_model_configured_fixture(mocker: MockerFixture) -> None:
    """Mock model existence check to pass for all endpoint tests by default.

    Individual tests can override this by patching check_model_configured
    with a different return value.
    """
    mocker.patch(
        "app.endpoints.rlsapi_v1.check_model_configured",
        new=mocker.AsyncMock(return_value=True),
    )


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


# --- Test get_rh_identity_context ---


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
    rh_identity_setup: Optional[dict[str, str]],
    expected_org_id: str,
    expected_system_id: str,
) -> None:
    """Test get_rh_identity_context extracts or defaults org/system IDs."""
    if rh_identity_setup is not None:
        mock_rh_identity = mocker.Mock(spec=RHIdentityData)
        mock_rh_identity.get_org_id.return_value = rh_identity_setup["org_id"]
        mock_rh_identity.get_user_id.return_value = rh_identity_setup["user_id"]
        mock_request = mock_request_factory(rh_identity=mock_rh_identity)
    else:
        mock_request = mock_request_factory()

    org_id, system_id = get_rh_identity_context(mock_request)

    assert org_id == expected_org_id
    assert system_id == expected_system_id


# --- Test infer_endpoint ---


@pytest.mark.asyncio
async def test_infer_endpoint_configuration_not_loaded(
    mocker: MockerFixture,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer returns HTTP 500 when configuration is not loaded."""
    mocker.patch.object(AppConfig(), "_configuration", None)

    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = mock_request_factory()

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.asyncio
async def test_infer_model_not_found_returns_404(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer returns HTTP 404 when configured model does not exist in Llama Stack."""
    mocker.patch(
        "app.endpoints.rlsapi_v1.check_model_configured",
        new=mocker.AsyncMock(return_value=False),
    )

    infer_request = RlsapiV1InferRequest(question="How do I list files?")
    mock_request = mock_request_factory()

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=infer_request,
            request=mock_request,
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail["response"] == "Model not found"  # type: ignore[index]
    assert "gpt-4-turbo" in exc_info.value.detail["cause"]  # type: ignore[index]


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
@pytest.mark.asyncio
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
    rlsapi_v1_mock = mocker.Mock()
    rlsapi_v1_mock.allow_verbose_infer = verbose_enabled
    rlsapi_v1_mock.quota_subject = None
    config_mock = mocker.Mock()
    config_mock.inference = mock_configuration.inference
    config_mock.customization = mock_configuration.customization
    config_mock.rlsapi_v1 = rlsapi_v1_mock
    config_mock.quota_limiters = []
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
    rlsapi_v1_mock = mocker.Mock()
    rlsapi_v1_mock.allow_verbose_infer = verbose_enabled
    rlsapi_v1_mock.quota_subject = None
    config_mock = mocker.Mock()
    config_mock.inference = mock_configuration.inference
    config_mock.customization = mock_configuration.customization
    config_mock.rlsapi_v1 = rlsapi_v1_mock
    config_mock.quota_limiters = []
    mocker.patch("app.endpoints.rlsapi_v1.configuration", config_mock)


@pytest.mark.parametrize(
    ("verbose_enabled", "expect_extract_called"),
    [
        pytest.param(True, True, id="verbose_calls_extract"),
        pytest.param(False, False, id="non_verbose_skips_extract"),
    ],
)
@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


# --- Test _resolve_quota_subject ---


@pytest.mark.parametrize(
    ("quota_subject", "rh_identity_setup", "expected"),
    [
        pytest.param(None, None, None, id="disabled_no_identity"),
        pytest.param(
            None,
            {"org_id": "org1", "user_id": "sys1"},
            None,
            id="disabled_with_identity",
        ),
        pytest.param("user_id", None, "mock_user_id", id="user_id_no_identity"),
        pytest.param(
            "org_id",
            {"org_id": "org123", "user_id": "sys456"},
            "org123",
            id="org_id_with_identity",
        ),
        pytest.param(
            "system_id",
            {"org_id": "org123", "user_id": "sys456"},
            "sys456",
            id="system_id_with_identity",
        ),
        pytest.param(
            "org_id",
            None,
            "mock_user_id",
            id="org_id_fallback_no_identity",
        ),
        pytest.param(
            "system_id",
            None,
            "mock_user_id",
            id="system_id_fallback_no_identity",
        ),
        pytest.param(
            "org_id",
            {"org_id": "", "user_id": "sys1"},
            "mock_user_id",
            id="org_id_fallback_empty_org",
        ),
        pytest.param(
            "system_id",
            {"org_id": "org1", "user_id": ""},
            "mock_user_id",
            id="system_id_fallback_empty_system",
        ),
    ],
)
def test_resolve_quota_subject(
    mocker: MockerFixture,
    mock_request_factory: Callable[..., Any],
    quota_subject: Optional[str],
    rh_identity_setup: Optional[dict[str, str]],
    expected: Optional[str],
) -> None:
    """Test _resolve_quota_subject resolves correct ID based on config and identity."""
    rlsapi_v1_mock = mocker.Mock()
    rlsapi_v1_mock.quota_subject = quota_subject
    config_mock = mocker.Mock()
    config_mock.rlsapi_v1 = rlsapi_v1_mock
    mocker.patch("app.endpoints.rlsapi_v1.configuration", config_mock)

    if rh_identity_setup is not None:
        mock_rh_identity = mocker.Mock(spec=RHIdentityData)
        mock_rh_identity.get_org_id.return_value = rh_identity_setup["org_id"]
        mock_rh_identity.get_user_id.return_value = rh_identity_setup["user_id"]
        mock_request = mock_request_factory(rh_identity=mock_rh_identity)
    else:
        mock_request = mock_request_factory()

    result = _resolve_quota_subject(mock_request, MOCK_AUTH)
    assert result == expected


# --- Test quota enforcement in infer_endpoint ---


@pytest.fixture(name="mock_quota_config")
def mock_quota_config_fixture(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
) -> Callable[[str], None]:
    """Factory fixture that patches configuration with quota_subject enabled.

    Args:
        mocker: The pytest mocker fixture.
        mock_configuration: Base AppConfig to extend.

    Returns:
        Callable that accepts a quota_subject value and patches configuration.
    """

    def _set(quota_subject: str) -> None:
        rlsapi_v1_mock = mocker.Mock()
        rlsapi_v1_mock.quota_subject = quota_subject
        rlsapi_v1_mock.allow_verbose_infer = False
        config_mock = mocker.Mock()
        config_mock.inference = mock_configuration.inference
        config_mock.customization = mock_configuration.customization
        config_mock.rlsapi_v1 = rlsapi_v1_mock
        config_mock.quota_limiters = []
        mocker.patch("app.endpoints.rlsapi_v1.configuration", config_mock)

    return _set


@pytest.mark.asyncio
async def test_infer_quota_check_called_when_configured(
    mocker: MockerFixture,
    mock_quota_config: Callable[[str], None],
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer calls check_tokens_available when quota_subject is set."""
    mock_quota_config("user_id")
    mock_check = mocker.patch("app.endpoints.rlsapi_v1.check_tokens_available")
    mock_consume = mocker.patch("app.endpoints.rlsapi_v1.consume_query_tokens")

    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="How do I list files?"),
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    mock_check.assert_called_once_with([], "mock_user_id")
    mock_consume.assert_called_once()


@pytest.mark.asyncio
async def test_infer_quota_skipped_when_not_configured(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer skips quota calls when quota_subject is None (default)."""
    mock_check = mocker.patch("app.endpoints.rlsapi_v1.check_tokens_available")
    mock_consume = mocker.patch("app.endpoints.rlsapi_v1.consume_query_tokens")

    await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="How do I list files?"),
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_check.assert_not_called()
    mock_consume.assert_not_called()


@pytest.mark.asyncio
async def test_infer_quota_exceeded_returns_429(
    mocker: MockerFixture,
    mock_quota_config: Callable[[str], None],
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test /infer returns HTTP 429 when quota is exceeded."""
    mock_quota_config("user_id")
    mocker.patch(
        "app.endpoints.rlsapi_v1.check_tokens_available",
        side_effect=HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS),
    )

    with pytest.raises(HTTPException) as exc_info:
        await infer_endpoint(
            infer_request=RlsapiV1InferRequest(question="How do I list files?"),
            request=mock_request_factory(),
            background_tasks=mock_background_tasks,
            auth=MOCK_AUTH,
        )

    assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.parametrize(
    ("quota_subject", "rh_identity_setup", "expected_subject"),
    [
        pytest.param(
            "org_id",
            {"org_id": "org123", "user_id": "sys456"},
            "org123",
            id="org_id",
        ),
        pytest.param(
            "system_id",
            {"org_id": "org123", "user_id": "sys456"},
            "sys456",
            id="system_id",
        ),
    ],
)
@pytest.mark.asyncio
async def test_infer_quota_with_rh_identity_subject(
    mocker: MockerFixture,
    mock_quota_config: Callable[[str], None],
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
    quota_subject: str,
    rh_identity_setup: dict[str, str],
    expected_subject: str,
) -> None:
    """Test /infer propagates org_id/system_id to quota check and consumption."""
    mock_quota_config(quota_subject)

    mock_rh_identity = mocker.Mock(spec=RHIdentityData)
    mock_rh_identity.get_org_id.return_value = rh_identity_setup["org_id"]
    mock_rh_identity.get_user_id.return_value = rh_identity_setup["user_id"]

    mock_check = mocker.patch("app.endpoints.rlsapi_v1.check_tokens_available")
    mock_consume = mocker.patch("app.endpoints.rlsapi_v1.consume_query_tokens")

    await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="How do I list files?"),
        request=mock_request_factory(rh_identity=mock_rh_identity),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_check.assert_called_once_with([], expected_subject)
    mock_consume.assert_called_once()
    assert mock_consume.call_args.kwargs["user_id"] == expected_subject


@pytest.mark.asyncio
async def test_infer_quota_shield_blocked_does_not_consume_tokens(
    mocker: MockerFixture,
    mock_quota_config: Callable[[str], None],
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test quota pre-check runs but tokens are NOT consumed when shield blocks."""
    mock_quota_config("user_id")

    blocked = ShieldModerationBlocked(
        message="Blocked by moderation",
        moderation_id="modr-test",
        refusal_response=OpenAIResponseMessage(
            role="assistant",
            content="Blocked by moderation",
        ),
    )
    mocker.patch(
        "app.endpoints.rlsapi_v1.run_shield_moderation",
        new=mocker.AsyncMock(return_value=blocked),
    )

    mock_check = mocker.patch("app.endpoints.rlsapi_v1.check_tokens_available")
    mock_consume = mocker.patch("app.endpoints.rlsapi_v1.consume_query_tokens")

    response = await infer_endpoint(
        infer_request=RlsapiV1InferRequest(question="Bad question"),
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert response.data.text == "Blocked by moderation"
    mock_check.assert_called_once_with([], "mock_user_id")
    mock_consume.assert_not_called()


# --- Test shield moderation ---


def _create_blocked_moderation_result() -> ShieldModerationBlocked:
    """Create a ShieldModerationBlocked result for testing."""
    return ShieldModerationBlocked(
        message="I can't answer that. Can I help with something else?",
        moderation_id="modr-test-123",
        refusal_response=OpenAIResponseMessage(
            role="assistant",
            content="I can't answer that. Can I help with something else?",
        ),
    )


@pytest.mark.asyncio
async def test_infer_shield_blocked_returns_refusal(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that blocked shield moderation returns refusal text without calling LLM."""
    blocked = _create_blocked_moderation_result()
    mocker.patch(
        "app.endpoints.rlsapi_v1.run_shield_moderation",
        new=mocker.AsyncMock(return_value=blocked),
    )

    infer_request = RlsapiV1InferRequest(question="How do I hack a server?")
    mock_request = mock_request_factory()

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request,
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert isinstance(response, RlsapiV1InferResponse)
    assert response.data.text == blocked.message
    assert response.data.request_id is not None
    assert check_suid(response.data.request_id)
    # Blocked response must not include verbose metadata
    assert response.data.tool_calls is None
    assert response.data.tool_results is None
    assert response.data.rag_chunks is None
    assert response.data.referenced_documents is None
    assert response.data.input_tokens is None
    assert response.data.output_tokens is None


@pytest.mark.asyncio
async def test_infer_shield_blocked_skips_llm_call(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that blocked shield moderation prevents any LLM call."""
    blocked = _create_blocked_moderation_result()
    mocker.patch(
        "app.endpoints.rlsapi_v1.run_shield_moderation",
        new=mocker.AsyncMock(return_value=blocked),
    )
    mock_retrieve = mocker.patch(
        "app.endpoints.rlsapi_v1.retrieve_simple_response",
        new=mocker.AsyncMock(),
    )

    infer_request = RlsapiV1InferRequest(question="How do I hack a server?")

    await infer_endpoint(
        infer_request=infer_request,
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_infer_shield_blocked_queues_splunk_event(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that blocked shield moderation queues a Splunk event with correct sourcetype."""
    blocked = _create_blocked_moderation_result()
    mocker.patch(
        "app.endpoints.rlsapi_v1.run_shield_moderation",
        new=mocker.AsyncMock(return_value=blocked),
    )

    infer_request = RlsapiV1InferRequest(question="How do I hack a server?")

    await infer_endpoint(
        infer_request=infer_request,
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_background_tasks.add_task.assert_called_once()
    call_args = mock_background_tasks.add_task.call_args
    assert call_args[0][2] == "infer_shield_blocked"


@pytest.mark.asyncio
async def test_infer_shield_passed_proceeds_to_llm(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that passed shield moderation proceeds to normal LLM inference."""
    # autouse fixture already patches with ShieldModerationPassed
    infer_request = RlsapiV1InferRequest(question="How do I list files?")

    response = await infer_endpoint(
        infer_request=infer_request,
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    assert response.data.text == "This is a test LLM response."
    # Splunk event should use normal sourcetype
    call_args = mock_background_tasks.add_task.call_args
    assert call_args[0][2] == "infer_with_llm"


@pytest.mark.asyncio
async def test_infer_shield_moderation_receives_combined_input(
    mocker: MockerFixture,
    mock_configuration: AppConfig,
    mock_llm_response: None,
    mock_auth_resolvers: None,
    mock_request_factory: Callable[..., Any],
    mock_background_tasks: Any,
) -> None:
    """Test that shield moderation receives the full combined input source."""
    mock_moderation = mocker.AsyncMock(return_value=ShieldModerationPassed())
    mocker.patch(
        "app.endpoints.rlsapi_v1.run_shield_moderation",
        new=mock_moderation,
    )

    infer_request = RlsapiV1InferRequest(
        question="Why did this fail?",
        context=RlsapiV1Context(
            stdin="piped input",
            terminal=RlsapiV1Terminal(output="permission denied"),
        ),
    )

    await infer_endpoint(
        infer_request=infer_request,
        request=mock_request_factory(),
        background_tasks=mock_background_tasks,
        auth=MOCK_AUTH,
    )

    mock_moderation.assert_called_once()
    # The input_text argument should be the combined input source
    input_text = mock_moderation.call_args[0][1]
    assert "Why did this fail?" in input_text
    assert "piped input" in input_text
    assert "permission denied" in input_text


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
