"""Helpers for running Pydantic AI agents against Llama Stack (Responses API compatibility)."""

from __future__ import annotations

import re
from typing import Any, Final, Optional

from ogx.core.library_client import AsyncOGXAsLibraryClient
from ogx_client import AsyncOgxClient
from pydantic_ai.agent import Agent
from pydantic_ai.capabilities import AbstractCapability, AgentCapability
from pydantic_ai_skills import SkillsCapability

from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.tools import CatalogTool, CatalogToolParameter
from models.config import SkillsConfiguration
from pydantic_ai_lightspeed.llamastack import (
    OgxResponsesModel,
)

_AGENT_SKILLS_PROVIDER_ID: Final[str] = "agent-skills"
_AGENT_SKILLS_TOOLGROUP_ID: Final[str] = "builtin::agent-skills"
_BUILTIN_CAPABILITY_SERVER_SOURCE: Final[str] = "builtin"
_CAPABILITY_TOOL_TYPE: Final[str] = "tool"


def _skills_capability(
    skills_config: Optional[SkillsConfiguration],
) -> Optional[SkillsCapability]:
    """Return a skills capability when skill paths are configured.

    Args:
        skills_config: Agent skills configuration from LCS, or None when skills are disabled.

    Returns:
        SkillsCapability when skill paths are configured, or None when skills are disabled.
    """
    if skills_config is None or not skills_config.paths:
        return None
    return SkillsCapability(
        directories=[str(path) for path in skills_config.paths],
        validate=False,
    )


def _json_schema_to_parameters(
    schema: Optional[dict[str, Any]],
) -> list[CatalogToolParameter]:
    """Convert a JSON Schema object to the flat parameter list used by ``/tools``."""
    if not schema or "properties" not in schema:
        return []

    required_params = set(schema.get("required", []))
    parameters: list[CatalogToolParameter] = []
    for name, prop in schema["properties"].items():
        parameter_type = prop.get("type")
        if parameter_type is None and "anyOf" in prop:
            for option in prop["anyOf"]:
                if isinstance(option, dict) and option.get("type") not in (
                    None,
                    "null",
                ):
                    parameter_type = option["type"]
                    break
        parameters.append(
            CatalogToolParameter(
                name=name,
                description=prop.get("description", ""),
                parameter_type=parameter_type or "string",
                required=name in required_params,
                default=prop.get("default"),
            )
        )
    return parameters


def _capability_tool_description(description: str) -> str:
    """Extract a user-facing description from pydantic-ai tool docstrings."""
    if match := re.search(r"<summary>(.*?)</summary>", description, re.DOTALL):
        return match.group(1).strip()
    return description.strip()


def _capability_tools_from_toolset(toolset: Any) -> list[CatalogTool]:
    """Serialize tools registered on a pydantic-ai capability toolset."""
    raw_tools = getattr(toolset, "tools", None)
    if not raw_tools:
        return []

    tools: list[CatalogTool] = []
    for tool in raw_tools.values():
        tools.append(
            CatalogTool(
                identifier=tool.name,
                description=_capability_tool_description(tool.description or ""),
                parameters=_json_schema_to_parameters(tool.function_schema.json_schema),
                provider_id=_AGENT_SKILLS_PROVIDER_ID,
                toolgroup_id=_AGENT_SKILLS_TOOLGROUP_ID,
                server_source=_BUILTIN_CAPABILITY_SERVER_SOURCE,
                type=_CAPABILITY_TOOL_TYPE,
            )
        )
    return tools


def get_agent_capability_tools(
    skills: Optional[SkillsConfiguration],
) -> list[CatalogTool]:
    """Return tool metadata for pydantic-ai capabilities configured for LCS agents.

    Parameters:
        skills: Agent skills configuration from LCS, or None when skills are disabled.

    Returns:
        Catalog tools for the ``/tools`` endpoint response format.
    """
    capabilities = _agent_capabilities(skills) or []

    tools: list[CatalogTool] = []
    for capability in capabilities:
        if not isinstance(capability, AbstractCapability):
            continue
        toolset = capability.get_toolset()
        if toolset is None:
            continue
        tools.extend(_capability_tools_from_toolset(toolset))
    return tools


def _agent_capabilities(
    skills: Optional[SkillsConfiguration],
    no_tools: bool = False,
) -> Optional[list[AgentCapability[object]]]:
    """Assemble pydantic-ai capabilities for an LCS agent.

    Args:
        skills: Agent skills configuration from LCS, or None when skills are disabled.
        no_tools: When True, omit capabilities that expose a toolset via ``get_toolset()``.

    Returns:
        Configured capabilities, or None when no capabilities are enabled.
    """
    capabilities: list[AgentCapability[object]] = []
    if skills_capability := _skills_capability(skills):
        capabilities.append(skills_capability)
    if no_tools:
        capabilities = [
            capability
            for capability in capabilities
            if not (
                isinstance(capability, AbstractCapability)
                and capability.get_toolset() is not None
            )
        ]
    return capabilities or None


def build_agent(
    client: AsyncOgxClient | AsyncOGXAsLibraryClient,
    responses_params: ResponsesApiParams,
    skills: Optional[SkillsConfiguration],
    no_tools: bool = False,
) -> Agent[None, str]:
    """Build a Pydantic AI agent that mirrors ``responses_params`` on the Llama Stack backend.

    Uses ``OgxProvider`` with the same ``AsyncOgxClient`` (or library client)
    as the query endpoint, and ``OpenAIResponsesModel`` so requests follow the Responses API.
    Llama-Stack-specific fields (conversation, tools, MCP headers, etc.) are passed via
    ``model_settings['extra_body']`` so they merge into the OpenAI client request body.

    Parameters:
        client: Initialized Llama Stack client from ``AsyncOgxClientHolder().get_client()``.
        responses_params: Parameters produced by ``prepare_responses_params`` for this turn.
        skills: Agent skills configuration from LCS, or None when skills are disabled.
        no_tools: When True, omit capabilities that expose a toolset via ``get_toolset()``.

    Returns:
        ``Agent`` configured for ``await agent.run(...)`` (or streaming) against the same
        stack configuration as ``client.responses.create(**responses_params.model_dump())``.
    """
    capabilities = _agent_capabilities(skills, no_tools=no_tools)

    model = OgxResponsesModel.from_ogx_client(
        responses_params.model, client, responses_params=responses_params
    )

    return Agent(
        model,
        instructions=responses_params.instructions,
        capabilities=capabilities,
        defer_model_check=True,
    )
