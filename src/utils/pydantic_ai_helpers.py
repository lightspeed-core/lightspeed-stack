"""Helpers for running Pydantic AI agents against OGX (Responses API compatibility)."""

from __future__ import annotations

import re
from typing import Any, Final, Optional

from ogx.core.library_client import AsyncOGXAsLibraryClient
from ogx_client import AsyncOgxClient
from pydantic_ai.agent import Agent
from pydantic_ai.capabilities import AbstractCapability, AgentCapability
from pydantic_ai_skills import SkillsCapability

from configuration import AppConfig
from log import get_logger
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.skills import SkillMetadata
from models.common.tools import CatalogTool, CatalogToolParameter
from models.config import (
    QuestionValidityConfig,
    RedactionConfig,
    ShieldConfiguration,
    SkillsConfiguration,
)
from pydantic_ai_lightspeed.capabilities import QuestionValidity
from pydantic_ai_lightspeed.capabilities.redaction import PiiRedactionCapability
from pydantic_ai_lightspeed.ogx import OgxResponsesModel
from utils.shields import get_shields_for_request

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


def get_skills_metadata(
    skills: Optional[SkillsConfiguration],
) -> list[SkillMetadata]:
    """Return metadata for all loaded skills.

    Parameters:
        skills: Agent skills configuration from LCS, or None when skills are disabled.

    Returns:
        List of ``SkillMetadata`` with ``name`` and ``description`` for each loaded skill.
    """
    capability = _skills_capability(skills)
    if capability is None:
        return []
    return [
        SkillMetadata(name=skill.name, description=skill.description)
        for skill in capability.toolset.skills.values()
    ]


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


def _shield_capability(shield: ShieldConfiguration) -> AgentCapability[object]:
    """Build the pydantic-ai capability instance for a single configured shield.

    Parameters:
        shield: A single guardrail shield configuration entry.

    Returns:
        A ``QuestionValidity`` capability when ``shield.provider_id`` is
        ``"question_validity"``, or a ``PiiRedactionCapability`` when it is
        ``"redaction"``.

    Raises:
        ValueError: If ``shield.config`` doesn't match a known shield config type.
    """
    match shield.config:
        case QuestionValidityConfig():
            return QuestionValidity(config=shield.config)
        case RedactionConfig():
            return PiiRedactionCapability(config=shield.config)
        case _:
            raise ValueError(
                f"Unsupported shield config type for shield '{shield.name}': "
                f"{type(shield.config).__name__}"
            )


def _agent_capabilities(
    skills: Optional[SkillsConfiguration],
    shields: Optional[list[ShieldConfiguration]] = None,
    no_tools: bool = False,
) -> Optional[list[AgentCapability[object]]]:
    """Assemble pydantic-ai capabilities for an LCS agent.

    Args:
        skills: Agent skills configuration from LCS, or None when skills are disabled.
        shields: Configured guardrail shields (question validity, redaction), or
            None/empty when no shields are enabled.
        no_tools: When True, omit capabilities that expose a toolset via ``get_toolset()``.

    Returns:
        Configured capabilities, or None when no capabilities are enabled.
    """
    capabilities: list[AgentCapability[object]] = []
    for shield in shields or []:
        capabilities.append(_shield_capability(shield))
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


logger = get_logger(__name__)


def captured_output_items(agent: Any) -> list[Any]:
    """Return the structured output items captured from the last OGX call.

    In compacted mode the ``conversation`` parameter is not sent, so OGX does
    not persist the turn and lightspeed-stack must append it itself. The items
    are captured verbatim from the OGX response by
    :class:`OgxResponsesModel`, so the stored turn matches what OGX would have
    stored (LCORE-3883).

    Parameters:
        agent: The pydantic-ai agent whose model performed the call.

    Returns:
        The captured output items, or an empty list when the model did not
        capture any (for example a non-OGX model in a test double).
    """
    model = getattr(agent, "model", None)
    items = getattr(model, "last_output_items", None)
    if not isinstance(items, list):
        # Either the model captured nothing yet, or it is not an
        # OgxResponsesModel (a test double, or a future backend). Persisting an
        # empty output is preferable to raising on an otherwise good turn.
        logger.debug(
            "No captured output items available from model %s", type(model).__name__
        )
        return []
    return list(items)


def build_agent(
    client: AsyncOgxClient | AsyncOGXAsLibraryClient,
    responses_params: ResponsesApiParams,
    config: AppConfig,
    shields: Optional[list[str]] = None,
    no_tools: bool = False,
) -> Agent[None, str]:
    """Build a Pydantic AI agent that mirrors ``responses_params`` on the OGX backend.

    Uses ``OgxProvider`` with the same ``AsyncOgxClient`` (or library client)
    as the query endpoint, and ``OpenAIResponsesModel`` so requests follow the Responses API.
    OGX-specific fields (conversation, tools, MCP headers, etc.) are passed via
    ``model_settings['extra_body']`` so they merge into the OpenAI client request body.

    Parameters:
        client: Initialized OGX client from ``AsyncOgxClientHolder().get_client()``.
        responses_params: Parameters produced by ``prepare_responses_params`` for this turn.
        config: Application configuration. Agent skills (``config.skills``) and the
            configured guardrail shields (``config.shields``) are extracted from it.
        shields: Optional list of shield names to run for this turn, matching each
            shield's configured ``name``. Mirrors ``QueryRequest.shield_ids``: if
            ``None``, all shields configured in ``config.shields`` run; an empty
            list disables all shields.
        no_tools: When True, omit capabilities that expose a toolset via ``get_toolset()``.

    Returns:
        ``Agent`` configured for ``await agent.run(...)`` (or streaming) against the same
        stack configuration as ``client.responses.create(**responses_params.model_dump())``.
    """
    shield_configs = get_shields_for_request(config.shields, shields)
    capabilities = _agent_capabilities(config.skills, shield_configs, no_tools=no_tools)

    model = OgxResponsesModel.from_ogx_client(
        responses_params.model, client, responses_params=responses_params
    )

    return Agent(
        model,
        instructions=responses_params.instructions,
        capabilities=capabilities,
        defer_model_check=True,
    )
