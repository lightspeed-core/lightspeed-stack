"""Agent settings assembled from a query request."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.types.settings.compaction import CompactionSettings
from agent.types.settings.knowledge import KnowledgeSourceSettings
from agent.types.settings.mcp import MCPSettings
from agent.types.settings.shield import ShieldSettings
from agent.types.settings.skill import SkillSettings
from configuration import configuration
from models.api.requests import QueryRequest
from utils.prompts import get_system_prompt


@dataclass
class AgentSettings:  # pylint: disable=too-many-instance-attributes
    """Settings for an agent."""

    provider: str | None = None
    model: str | None = None
    instructions: str | None = None

    compaction: CompactionSettings = field(default_factory=CompactionSettings)

    skills: list[SkillSettings] = field(default_factory=list)
    shields: list[ShieldSettings] = field(default_factory=list)
    knowledge_sources: list[KnowledgeSourceSettings] = field(default_factory=list)
    mcp_servers: list[MCPSettings] = field(default_factory=list)

    @classmethod
    def from_query_request(cls, request: QueryRequest) -> AgentSettings:
        """Create agent settings from a query request and loaded configuration.

        Request values select the provider, model, and instructions. Omitted
        provider and model fall back to the configured inference defaults.
        Shields, knowledge sources, and MCP servers always include every
        configured entry. Omitted shield and knowledge-source ids leave them
        enabled; a provided list disables the rest. ``no_tools`` disables
        every MCP server. Skills and compaction come from configuration.

        Parameters:
            request: Incoming query whose agent-related fields are mapped.

        Returns:
            Settings for the agent that should handle the query.

        """
        provider = request.provider or configuration.inference.default_provider
        model = request.model or configuration.inference.default_model
        return cls(
            provider=provider,
            model=model,
            instructions=get_system_prompt(request.system_prompt),
            compaction=CompactionSettings.from_query_request(request),
            skills=SkillSettings.from_query_request(request),
            shields=ShieldSettings.from_query_request(request),
            knowledge_sources=KnowledgeSourceSettings.from_query_request(request),
            mcp_servers=MCPSettings.from_query_request(request),
        )
