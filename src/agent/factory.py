"""Build pydantic-ai agents from the process-wide :class:`ProviderRegistry`.

Providers and their available models are resolved once at startup by
:meth:`~lightspeed.core.providers.registry.ProviderRegistry.load`. Building an
``Agent`` here is just a lookup: no provider/model construction happens per
request.
"""

from __future__ import annotations

from pydantic_ai import Agent

from agent.capabilities.knowledge.factory import KnowledgeFactory
from agent.capabilities.mcp.factory import MCPFactory
from agent.capabilities.shields.factory import ShieldFactory
from agent.capabilities.skills.factory import SkillFactory
from agent.types.settings import AgentSettings


class AgentFactory:
    """Builds pydantic-ai :class:`~pydantic_ai.agent.Agent` instances on demand."""

    @staticmethod
    def create_agent(
        settings: AgentSettings,
    ) -> Agent[None, str]:
        """Build an ``Agent``, bound to a real provider/model or (when both
        are omitted) a throwaway agent for introspection only.

        The ``/tools`` endpoint calls this with no ``provider``/``model`` to
        get an agent with the same toolsets a real request agent would have,
        purely to list them -- it never calls the model or runs a tool.

        Every configured MCP server is attached as an ``MCP`` capability (see
        :class:`~lightspeed.core.agent.tools.mcp.factory.MCPCapabilityFactory`),
        configured skill paths as a ``Skills`` capability (see
        :class:`~lightspeed.core.agent.tools.skills.factory.SkillsCapabilityFactory`),
        and configured knowledge sources as ``Knowledge`` capabilities (see
        :class:`~lightspeed.core.agent.knowledge.factory.KnowledgeCapabilityFactory`),
        so ``Configuration`` must already be loaded (the ``/tools`` and
        ``/query`` endpoints both check this before calling here).

        Parameters:
            provider: Name of the configured provider to use (e.g. from
                ``QueryRequest.provider``). Omit together with ``model`` to
                get a harmless placeholder model instead of a real one.
            model: Upstream model identifier (e.g. from ``QueryRequest.model``).
            instructions: Optional system instructions for the agent (e.g.
                from ``QueryRequest.system_prompt``).

        Returns:
            An ``Agent`` bound to the resolved provider and model, or to a
            placeholder model if both ``provider`` and ``model`` are omitted.

        Raises:
            RuntimeError: If ``Configuration`` hasn't been loaded yet.
            KeyError: If ``provider`` is not registered, or ``model`` is not
                available for ``provider``.

        """
        capabilities = []

        capabilities.append(MCPFactory.build_capabilities(settings.mcp_servers))
        capabilities.append(ShieldFactory.build_capabilities(settings.shields))
        capabilities.append(SkillFactory.build_capabilities(settings.skills))
        capabilities.append(
            KnowledgeFactory.build_capabilities(settings.knowledge_sources)
        )

        return Agent(instructions=settings.instructions, capabilities=capabilities)
