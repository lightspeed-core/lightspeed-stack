"""Build pydantic-ai agents from the process-wide :class:`ProviderRegistry`.

Providers and their available models are resolved once at startup by
:meth:`~lightspeed.core.providers.registry.ProviderRegistry.load`. Building an
``Agent`` here is just a lookup: no provider/model construction happens per
request.
"""

from __future__ import annotations

from pydantic_ai import Agent

from agent.capabilities.compaction.factory import CompactionFactory
from agent.capabilities.knowledge.factory import KnowledgeFactory
from agent.capabilities.mcp.factory import MCPFactory
from agent.capabilities.shields.factory import ShieldFactory
from agent.capabilities.skills.factory import SkillFactory
from agent.capabilities.step_persistence.factory import StepPersistenceFactory
from agent.types.settings import AgentSettings
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)
from providers.inference.registry import ProviderRegistry


class AgentFactory:  # pylint: disable=too-few-public-methods
    """Builds pydantic-ai :class:`~pydantic_ai.agent.Agent` instances on demand."""

    @staticmethod
    async def create_agent(
        settings: AgentSettings,
    ) -> Agent[None, str]:
        """Build an agent from the given settings.

        The model is resolved from the process-wide provider registry using
        ``settings.provider`` and ``settings.model``. MCP servers, shields,
        skills, knowledge sources, compaction, and step persistence are
        attached as capabilities from the same settings. A factory result of
        ``None`` is omitted. Configuration must already be loaded.

        Parameters:
            settings: Provider, model, instructions, and capability settings
                for the agent.

        Returns:
            An agent bound to the resolved model and assembled capabilities.

        Raises:
            RuntimeError: If the provider or model cannot be resolved.

        """
        try:
            model = ProviderRegistry().resolve_model_instance(
                "llm",
                settings.provider,
                settings.model,
            )
        except (
            ProviderNotFoundError,
            ModelNotAvailableError,
            ModelTypeNotSupportedError,
        ) as exc:
            raise RuntimeError(
                "Could not resolve model for agent "
                f"(provider={settings.provider} model={settings.model})"
            ) from exc

        raw_capabilities = (
            *(await MCPFactory.build_capabilities(settings.mcp_servers)),
            *ShieldFactory.build_capabilities(settings.shields),
            SkillFactory.build_capabilities(settings.skills),
            KnowledgeFactory.build_capabilities(settings.knowledge_sources),
            CompactionFactory.build_capability(settings.compaction),
            StepPersistenceFactory.build_capability(settings.step_persistence),
        )
        capabilities = [
            capability for capability in raw_capabilities if capability is not None
        ]

        return Agent(
            model=model, instructions=settings.instructions, capabilities=capabilities
        )
