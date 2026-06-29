"""Unit tests for utils/pydantic_ai module."""

# pylint: disable=protected-access

import httpx
import pytest
from llama_stack.core.library_client import AsyncLlamaStackAsLibraryClient
from llama_stack_client import AsyncLlamaStackClient
from pydantic_ai_skills import SkillsCapability
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from models.config import SkillsConfiguration
from utils.pydantic_ai import (
    _LLS_RESPONSES_EXTRA_FIELDS,
    _agent_capabilities,
    _model_settings_from_responses_params,
    _skills_capability,
    build_agent,
    llama_stack_provider_from_client,
)


class TestLlamaStackProviderFromClient:
    """Tests for llama_stack_provider_from_client factory."""

    def test_library_client(self, mocker: MockerFixture) -> None:
        """Test that a library client creates a provider with library_client kwarg."""
        mock_lib_client = mocker.Mock(spec=AsyncLlamaStackAsLibraryClient)
        mock_lib_client.provider_data = None

        provider = llama_stack_provider_from_client(mock_lib_client)

        assert provider._library_client is mock_lib_client

    def test_remote_client_with_api_key(self, mocker: MockerFixture) -> None:
        """Test that a remote client uses its api_key."""
        mock_client = mocker.Mock()
        mock_client.base_url = "http://my-server:8321"
        mock_client.api_key = "my-secret"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)

        provider = llama_stack_provider_from_client(mock_client)

        assert provider.client.api_key == "my-secret"
        assert "my-server:8321" in provider.base_url

    def test_remote_client_without_api_key(self, mocker: MockerFixture) -> None:
        """Test that a remote client without api_key defaults to 'not-needed'."""
        mock_client = mocker.Mock()
        mock_client.base_url = "http://my-server:8321"
        mock_client.api_key = None
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)

        provider = llama_stack_provider_from_client(mock_client)

        assert provider.client.api_key == "not-needed"

    def test_remote_client_passes_http_client(self, mocker: MockerFixture) -> None:
        """Test that a remote client's internal http_client is forwarded."""
        mock_http_client = mocker.Mock(spec=httpx.AsyncClient)
        mock_client = mocker.Mock()
        mock_client.base_url = "http://my-server:8321"
        mock_client.api_key = "key"
        mock_client._client = mock_http_client

        provider = llama_stack_provider_from_client(mock_client)

        assert provider._client._client is mock_http_client


class TestModelSettingsFromResponsesParams:
    """Tests for _model_settings_from_responses_params mapping."""

    @pytest.fixture(name="minimal_params")
    def minimal_params_fixture(self, mocker: MockerFixture) -> object:
        """Create minimal ResponsesApiParams mock with required fields only."""
        params = mocker.Mock()
        params.model_dump.return_value = {"model": "test/model", "input": "hello"}
        params.max_output_tokens = None
        params.temperature = None
        params.parallel_tool_calls = None
        params.extra_headers = None
        params.store = False
        params.tools = None
        params.previous_response_id = None
        return params

    def test_minimal_params_returns_store_false(self, minimal_params: object) -> None:
        """Test that minimal params produce settings with openai_store=False."""
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert settings["openai_store"] is False

    def test_minimal_params_no_extra_body(self, minimal_params: object) -> None:
        """Test that minimal params without extra fields omit extra_body."""
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert "extra_body" not in settings

    def test_max_output_tokens_mapped(self, minimal_params: object) -> None:
        """Test that max_output_tokens is mapped to max_tokens."""
        minimal_params.max_output_tokens = 1024  # type: ignore[attr-defined]
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert settings["max_tokens"] == 1024

    def test_temperature_mapped(self, minimal_params: object) -> None:
        """Test that temperature is passed through."""
        minimal_params.temperature = 0.7  # type: ignore[attr-defined]
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert settings["temperature"] == 0.7

    def test_parallel_tool_calls_mapped(self, minimal_params: object) -> None:
        """Test that parallel_tool_calls is passed through."""
        minimal_params.parallel_tool_calls = True  # type: ignore[attr-defined]
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert settings["parallel_tool_calls"] is True

    def test_extra_headers_mapped(self, minimal_params: object) -> None:
        """Test that extra_headers are converted to a dict."""
        minimal_params.extra_headers = {"x-custom": "value"}  # type: ignore[attr-defined]
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert settings["extra_headers"] == {"x-custom": "value"}

    def test_store_true_mapped(self, minimal_params: object) -> None:
        """Test that store=True is passed as openai_store."""
        minimal_params.store = True  # type: ignore[attr-defined]
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert settings["openai_store"] is True

    def test_previous_response_id_mapped(self, minimal_params: object) -> None:
        """Test that previous_response_id is passed as openai_previous_response_id."""
        minimal_params.previous_response_id = "resp_abc123"  # type: ignore[attr-defined]
        settings = _model_settings_from_responses_params(minimal_params)  # type: ignore[arg-type]
        assert settings["openai_previous_response_id"] == "resp_abc123"

    def test_extra_body_from_lls_fields(self, mocker: MockerFixture) -> None:
        """Test that LLS-specific fields are placed into extra_body."""
        params = mocker.Mock()
        params.model_dump.return_value = {
            "model": "test/model",
            "conversation": "conv-123",
            "max_infer_iters": 5,
            "tool_choice": "auto",
        }
        params.max_output_tokens = None
        params.temperature = None
        params.parallel_tool_calls = None
        params.extra_headers = None
        params.store = False
        params.previous_response_id = None
        params.tools = [{"type": "function"}]

        settings = _model_settings_from_responses_params(params)

        assert "extra_body" in settings
        assert settings["extra_body"]["conversation"] == "conv-123"
        assert settings["extra_body"]["max_infer_iters"] == 5
        assert settings["extra_body"]["tool_choice"] == "auto"
        assert settings["openai_native_tools"] == [{"type": "function"}]

    def test_extra_body_only_includes_known_fields(self, mocker: MockerFixture) -> None:
        """Test that extra_body only includes fields in _LLS_RESPONSES_EXTRA_FIELDS."""
        params = mocker.Mock()
        params.model_dump.return_value = {
            "model": "test/model",
            "conversation": "conv-1",
            "unknown_field": "should-not-appear",
        }
        params.max_output_tokens = None
        params.temperature = None
        params.parallel_tool_calls = None
        params.extra_headers = None
        params.store = False
        params.previous_response_id = None

        settings = _model_settings_from_responses_params(params)

        assert "unknown_field" not in settings.get("extra_body", {})
        assert settings["extra_body"]["conversation"] == "conv-1"


class TestLlsResponsesExtraFields:
    """Tests for the _LLS_RESPONSES_EXTRA_FIELDS constant."""

    def test_is_frozenset(self) -> None:
        """Test that _LLS_RESPONSES_EXTRA_FIELDS is a frozenset."""
        assert isinstance(_LLS_RESPONSES_EXTRA_FIELDS, frozenset)

    def test_contains_expected_fields(self) -> None:
        """Test that key fields are present."""
        expected = {
            "conversation",
            "max_infer_iters",
            "tool_choice",
            "include",
            "text",
            "reasoning",
            "prompt",
            "metadata",
            "max_tool_calls",
            "safety_identifier",
        }
        assert expected == _LLS_RESPONSES_EXTRA_FIELDS


class TestSkillsCapability:
    """Tests for _skills_capability."""

    def test_returns_none_when_skills_not_configured(self) -> None:
        """Test that missing skills configuration returns None."""
        assert _skills_capability(None) is None

    def test_returns_none_when_paths_empty(self) -> None:
        """Test that an empty paths list returns None."""
        assert _skills_capability(SkillsConfiguration(paths=[])) is None

    def test_returns_capability_for_configured_paths(
        self, mock_skills_configuration: SkillsConfiguration
    ) -> None:
        """Test that configured paths produce a SkillsCapability."""
        capability = _skills_capability(mock_skills_configuration)

        assert isinstance(capability, SkillsCapability)
        assert list(capability.toolset.skills) == ["test-skill"]


class TestAgentCapabilities:
    """Tests for _agent_capabilities."""

    def test_returns_none_when_no_capabilities_configured(self) -> None:
        """Test that missing configuration yields None for Agent construction."""
        assert _agent_capabilities(None) is None
        assert _agent_capabilities(SkillsConfiguration(paths=[])) is None

    def test_returns_skills_capability_when_configured(
        self, mock_skills_configuration: SkillsConfiguration
    ) -> None:
        """Test that configured skills are included in the capability list."""
        capabilities = _agent_capabilities(mock_skills_configuration) or []

        assert len(capabilities) == 1
        assert isinstance(capabilities[0], SkillsCapability)


class TestBuildAgent:
    """Tests for the build_agent factory function."""

    def test_returns_agent_with_correct_model(self, mocker: MockerFixture) -> None:
        """Test that build_agent returns an Agent with the specified model name."""
        mock_client = mocker.Mock()
        mock_client.base_url = "http://localhost:8321"
        mock_client.api_key = "test-key"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)

        mock_params = mocker.Mock()
        mock_params.model = "provider/my-model"
        mock_params.instructions = "Be helpful."
        mock_params.model_dump.return_value = {
            "model": "provider/my-model",
            "conversation": "conv-1",
        }
        mock_params.max_output_tokens = None
        mock_params.temperature = None
        mock_params.parallel_tool_calls = None
        mock_params.extra_headers = None
        mock_params.store = False
        mock_params.previous_response_id = None

        agent = build_agent(mock_client, mock_params, None)

        assert agent is not None

    def test_agent_has_instructions(self, mocker: MockerFixture) -> None:
        """Test that build_agent passes instructions to the Agent."""
        mock_client = mocker.Mock()
        mock_client.base_url = "http://localhost:8321"
        mock_client.api_key = "test-key"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)

        mock_params = mocker.Mock()
        mock_params.model = "provider/my-model"
        mock_params.instructions = "You are a helpful assistant."
        mock_params.model_dump.return_value = {"model": "provider/my-model"}
        mock_params.max_output_tokens = None
        mock_params.temperature = None
        mock_params.parallel_tool_calls = None
        mock_params.extra_headers = None
        mock_params.store = False
        mock_params.previous_response_id = None

        agent = build_agent(mock_client, mock_params, None)

        assert "You are a helpful assistant." in agent._instructions

    def test_agent_with_library_client(self, mocker: MockerFixture) -> None:
        """Test that build_agent works with a library client."""
        mock_lib_client = mocker.Mock(spec=AsyncLlamaStackAsLibraryClient)
        mock_lib_client.provider_data = None

        mock_params = mocker.Mock()
        mock_params.model = "provider/my-model"
        mock_params.instructions = None
        mock_params.model_dump.return_value = {
            "model": "provider/my-model",
            "conversation": "conv-1",
        }
        mock_params.max_output_tokens = None
        mock_params.temperature = None
        mock_params.parallel_tool_calls = None
        mock_params.extra_headers = None
        mock_params.store = True
        mock_params.previous_response_id = None

        agent = build_agent(mock_lib_client, mock_params, None)

        assert agent is not None

    def test_agent_includes_skills_capability_when_configured(
        self,
        mock_client: AsyncLlamaStackClient,
        mock_params: ResponsesApiParams,
        mock_skills_configuration: SkillsConfiguration,
    ) -> None:
        """Test that build_agent attaches SkillsCapability when skills are passed."""
        agent = build_agent(
            mock_client,
            mock_params,
            mock_skills_configuration,
        )

        capability_types = {
            type(capability) for capability in agent._root_capability.capabilities
        }
        assert SkillsCapability in capability_types

    def test_agent_has_no_skills_capability_when_not_configured(
        self,
        mock_client: AsyncLlamaStackClient,
        mock_params: ResponsesApiParams,
    ) -> None:
        """Test that build_agent omits SkillsCapability when skills are not passed."""
        agent = build_agent(mock_client, mock_params, None)

        capability_types = {
            type(capability) for capability in agent._root_capability.capabilities
        }
        assert SkillsCapability not in capability_types

    def test_agent_excludes_tool_capabilities_when_no_tools(
        self,
        mock_client: AsyncLlamaStackClient,
        mock_params: ResponsesApiParams,
        mock_skills_configuration: SkillsConfiguration,
    ) -> None:
        """Test that build_agent omits tool-bearing capabilities when no_tools=True."""
        agent = build_agent(
            mock_client,
            mock_params,
            mock_skills_configuration,
            no_tools=True,
        )

        capability_types = {
            type(capability) for capability in agent._root_capability.capabilities
        }
        assert SkillsCapability not in capability_types
