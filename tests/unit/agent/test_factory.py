"""Unit tests for assembling a pydantic-ai agent from request settings."""

import pytest
from pytest_mock import MockerFixture, MockType

from agent.factory import AgentFactory
from agent.types.settings import AgentSettings
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)


def _patch_factories(  # pylint: disable=too-many-arguments
    mocker: MockerFixture,
    *,
    mcp: list[object] | None = None,
    shields: list[object] | None = None,
    skills: object | None = None,
    knowledge: object | None = None,
    compaction: object | None = None,
    persistence: object | None = None,
) -> dict[str, MockType]:
    """Replace every capability factory with a stub."""
    return {
        "mcp": mocker.patch(
            "agent.factory.MCPFactory.build_capabilities",
            new_callable=mocker.AsyncMock,
            return_value=[] if mcp is None else mcp,
        ),
        "shields": mocker.patch(
            "agent.factory.ShieldFactory.build_capabilities",
            return_value=[] if shields is None else shields,
        ),
        "skills": mocker.patch(
            "agent.factory.SkillFactory.build_capabilities",
            return_value=skills,
        ),
        "knowledge": mocker.patch(
            "agent.factory.KnowledgeFactory.build_capabilities",
            return_value=knowledge,
        ),
        "compaction": mocker.patch(
            "agent.factory.CompactionFactory.build_capability",
            return_value=compaction,
        ),
        "persistence": mocker.patch(
            "agent.factory.StepPersistenceFactory.build_capability",
            return_value=persistence,
        ),
    }


@pytest.mark.asyncio
async def test_create_agent_assembles_resolved_capabilities(
    mocker: MockerFixture,
) -> None:
    """The agent receives the resolved model and every capability that was built."""
    model = mocker.Mock()
    registry = mocker.Mock()
    registry.resolve_model_instance.return_value = model
    mocker.patch("agent.factory.ProviderRegistry", return_value=registry)
    agent_cls = mocker.patch("agent.factory.Agent")
    mcp_capability = mocker.Mock()
    shield_capability = mocker.Mock()
    skill_capability = mocker.Mock()
    knowledge_capability = mocker.Mock()
    compaction_capability = mocker.Mock()
    persistence_capability = mocker.Mock()
    factories = _patch_factories(
        mocker,
        mcp=[mcp_capability],
        shields=[shield_capability],
        skills=skill_capability,
        knowledge=knowledge_capability,
        compaction=compaction_capability,
        persistence=persistence_capability,
    )
    settings = AgentSettings(
        provider="openai",
        model="gpt",
        instructions="Be helpful",
    )

    result = await AgentFactory.create_agent(settings)

    assert result is agent_cls.return_value
    registry.resolve_model_instance.assert_called_once_with("llm", "openai", "gpt")
    factories["mcp"].assert_awaited_once_with(settings.mcp_servers)
    factories["shields"].assert_called_once_with(settings.shields)
    factories["skills"].assert_called_once_with(settings.skills)
    factories["knowledge"].assert_called_once_with(settings.knowledge_sources)
    factories["compaction"].assert_called_once_with(settings.compaction)
    factories["persistence"].assert_called_once_with(settings.step_persistence)
    agent_cls.assert_called_once_with(
        model=model,
        instructions="Be helpful",
        capabilities=[
            mcp_capability,
            shield_capability,
            skill_capability,
            knowledge_capability,
            compaction_capability,
            persistence_capability,
        ],
    )


@pytest.mark.asyncio
async def test_create_agent_omits_capabilities_that_were_not_built(
    mocker: MockerFixture,
) -> None:
    """Empty factory lists and ``None`` results are not passed to the agent."""
    registry = mocker.Mock()
    mocker.patch("agent.factory.ProviderRegistry", return_value=registry)
    agent_cls = mocker.patch("agent.factory.Agent")
    _patch_factories(mocker)

    result = await AgentFactory.create_agent(AgentSettings())

    assert result is agent_cls.return_value
    registry.resolve_model_instance.assert_called_once_with("llm", None, None)
    agent_cls.assert_called_once_with(
        model=registry.resolve_model_instance.return_value,
        instructions=None,
        capabilities=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ProviderNotFoundError("openai"),
        ModelNotAvailableError("granite", "llm", "openai"),
        ModelTypeNotSupportedError("llm", "openai"),
    ],
)
async def test_unresolved_model_raises_runtime_error(
    mocker: MockerFixture, error: Exception
) -> None:
    """Provider and model lookup failures become a RuntimeError and stop assembly."""
    registry = mocker.Mock()
    registry.resolve_model_instance.side_effect = error
    mocker.patch("agent.factory.ProviderRegistry", return_value=registry)
    factories = _patch_factories(mocker)
    settings = AgentSettings(provider="openai", model="granite")

    with pytest.raises(RuntimeError, match=r"provider=openai model=granite") as raised:
        await AgentFactory.create_agent(settings)

    assert raised.value.__cause__ is error
    for factory in factories.values():
        factory.assert_not_called()
