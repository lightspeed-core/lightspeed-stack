"""Unit tests for utils/pydantic_ai module."""

# pylint: disable=protected-access

import httpx
from ogx.core.library_client import AsyncOGXAsLibraryClient
from ogx_client import AsyncOgxClient
from pydantic_ai_skills import SkillsCapability
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from models.config import ShieldConfiguration, SkillsConfiguration
from pydantic_ai_lightspeed.capabilities import (
    PiiRedactionCapability,
    QuestionValidity,
)
from utils.pydantic_ai_helpers import (
    _agent_capabilities,
    _skills_capability,
    build_agent,
    get_agent_capability_tools,
)


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
        assert _agent_capabilities(None, shields=[]) is None

    def test_returns_skills_capability_when_configured(
        self, mock_skills_configuration: SkillsConfiguration
    ) -> None:
        """Test that configured skills are included in the capability list."""
        capabilities = _agent_capabilities(mock_skills_configuration) or []

        assert len(capabilities) == 1
        assert isinstance(capabilities[0], SkillsCapability)

    def test_returns_shield_capabilities_when_configured(
        self, mocker: MockerFixture
    ) -> None:
        """Instantiate QuestionValidity and PII redaction from shield config."""
        _module = "pydantic_ai_lightspeed.capabilities.question_validity._capability"
        mocker.patch(f"{_module}.AsyncOgxClientHolder")
        mocker.patch(f"{_module}.OgxResponsesModel.from_ogx_client")

        shields = [
            ShieldConfiguration(
                shield_id="lightspeed_question_validity",
                provider_id="lightspeed_question_validity",
                provider_shield_id="gpt-4o-mini",
            ),
            ShieldConfiguration(
                shield_id="lightspeed_pii_redaction",
                provider_id="lightspeed_pii_redaction",
                provider_shield_id="lightspeed_pii_redaction",
                params={
                    "rules": [
                        {"pattern": r"secret", "replacement": "[REDACTED]"},
                    ]
                },
            ),
        ]

        capabilities = _agent_capabilities(None, shields) or []

        assert len(capabilities) == 2
        assert isinstance(capabilities[0], QuestionValidity)
        assert capabilities[0].config.model_id == "gpt-4o-mini"
        assert isinstance(capabilities[1], PiiRedactionCapability)
        assert len(capabilities[1].config.compiled_patterns) == 1

    def test_combines_skills_and_shield_capabilities(
        self,
        mocker: MockerFixture,
        mock_skills_configuration: SkillsConfiguration,
    ) -> None:
        """Include both skills and shield capabilities when both are configured."""
        _module = "pydantic_ai_lightspeed.capabilities.question_validity._capability"
        mocker.patch(f"{_module}.AsyncOgxClientHolder")
        mocker.patch(f"{_module}.OgxResponsesModel.from_ogx_client")

        shields = [
            ShieldConfiguration(
                shield_id="lightspeed_question_validity",
                provider_id="lightspeed_question_validity",
                provider_shield_id="gpt-4o-mini",
            ),
        ]

        capabilities = _agent_capabilities(mock_skills_configuration, shields) or []

        assert len(capabilities) == 2
        assert isinstance(capabilities[0], SkillsCapability)
        assert isinstance(capabilities[1], QuestionValidity)


class TestBuildAgent:
    """Tests for the build_agent factory function."""

    def test_returns_agent_with_correct_model(self, mocker: MockerFixture) -> None:
        """Test that build_agent returns an Agent with the specified model name."""
        mock_client = mocker.Mock()
        mock_client.base_url = "http://localhost:8321"
        mock_client.api_key = "test-key"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)
        mock_client.default_headers = {}

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
        mock_client.default_headers = {}

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
        mock_lib_client = mocker.Mock(spec=AsyncOGXAsLibraryClient)
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
        mock_client: AsyncOgxClient,
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
        mock_client: AsyncOgxClient,
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
        mock_client: AsyncOgxClient,
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

    def test_agent_includes_shield_capabilities_when_configured(
        self,
        mocker: MockerFixture,
        mock_client: AsyncOgxClient,
        mock_params: ResponsesApiParams,
    ) -> None:
        """Attach shield capabilities from LCORE shields configuration."""
        _module = "pydantic_ai_lightspeed.capabilities.question_validity._capability"
        mocker.patch(f"{_module}.AsyncOgxClientHolder")
        mocker.patch(f"{_module}.OgxResponsesModel.from_ogx_client")

        shields = [
            ShieldConfiguration(
                shield_id="lightspeed_question_validity",
                provider_id="lightspeed_question_validity",
                provider_shield_id="gpt-4o-mini",
            ),
            ShieldConfiguration(
                shield_id="lightspeed_pii_redaction",
                provider_id="lightspeed_pii_redaction",
                provider_shield_id="lightspeed_pii_redaction",
                params={
                    "rules": [
                        {"pattern": r"secret", "replacement": "[REDACTED]"},
                    ]
                },
            ),
        ]

        agent = build_agent(mock_client, mock_params, None, shields)

        capability_types = {
            type(capability) for capability in agent._root_capability.capabilities
        }
        assert QuestionValidity in capability_types
        assert PiiRedactionCapability in capability_types


class TestGetAgentCapabilityTools:
    """Tests for get_agent_capability_tools."""

    def test_returns_empty_list_when_skills_not_configured(self) -> None:
        """Test that missing skills configuration yields no capability tools."""
        assert not get_agent_capability_tools(None)
        assert not get_agent_capability_tools(SkillsConfiguration(paths=[]))

    def test_returns_skills_tools_when_configured(
        self, mock_skills_configuration: SkillsConfiguration
    ) -> None:
        """Test that configured skills expose pydantic-ai skill tools."""
        tools = get_agent_capability_tools(mock_skills_configuration)

        assert [tool.identifier for tool in tools] == [
            "list_skills",
            "load_skill",
            "read_skill_resource",
            "run_skill_script",
        ]
        assert all(
            tool.provider_id == "agent-skills"
            and tool.toolgroup_id == "builtin::agent-skills"
            and tool.server_source == "builtin"
            and tool.type == "tool"
            for tool in tools
        )

        load_skill = next(tool for tool in tools if tool.identifier == "load_skill")
        assert [parameter.model_dump() for parameter in load_skill.parameters] == [
            {
                "name": "skill_name",
                "description": (
                    "Exact name from your available skills list.\n"
                    'Must match exactly (e.g., "data-analysis" not "data analysis").'
                ),
                "parameter_type": "string",
                "required": True,
                "default": None,
            }
        ]
