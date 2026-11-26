"""Unit tests for agent settings assembled from a query."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast

from fastapi import Request
from pytest_mock import MockerFixture, MockType

from agent.types.settings.agent import AgentSettings
from agent.types.settings.compaction import CompactionSettings
from agent.types.settings.knowledge import (
    KnowledgeSourceSettings,
    OKPKnowledgeSourceSettings,
)
from agent.types.settings.mcp import MCPSettings
from agent.types.settings.shield import ShieldSettings
from agent.types.settings.skill import SkillSettings
from agent.types.settings.step_persistence import StepPersistenceSettings
from constants import OKP_RAG_ID
from models.api.requests import QueryRequest
from models.config import (
    ByokConfiguration,
    CompactionConfiguration,
    InferenceConfiguration,
    ModelContextProtocolServer,
    RagConfiguration,
    RagStore,
    RetrievalConfiguration,
    RetrievalStrategyConfiguration,
    SkillsConfiguration,
)

_SETTINGS_MODULES = (
    "agent.types.settings.agent",
    "agent.types.settings.compaction",
    "agent.types.settings.knowledge",
    "agent.types.settings.mcp",
    "agent.types.settings.shield",
    "agent.types.settings.skill",
)


def _store(rag_id: str) -> RagStore:
    """Build a FAISS store entry. The index file is not opened."""
    return RagStore(
        rag_id=rag_id,
        backend="faiss",
        vector_db_id=f"vs_{rag_id}",
        db_path=f"/tmp/{rag_id}.db",
    )


def _configuration(
    *,
    skills: SkillsConfiguration | None,
    compaction_enabled: bool = True,
) -> SimpleNamespace:
    """Build the configuration object every settings module reads."""
    return SimpleNamespace(
        inference=InferenceConfiguration(
            default_provider="openai",
            default_model="default-model",
        ),
        compaction=CompactionConfiguration(enabled=compaction_enabled),
        skills=skills,
        shields=[SimpleNamespace(name="topic"), SimpleNamespace(name="pii")],
        rag=RagConfiguration(
            byok=ByokConfiguration(stores=[_store("alpha")]),
            retrieval=RetrievalConfiguration(
                inline=RetrievalStrategyConfiguration(sources=["alpha", OKP_RAG_ID]),
                tool=RetrievalStrategyConfiguration(sources=["alpha"]),
            ),
        ),
        mcp_servers=[
            ModelContextProtocolServer(name="docs", url="https://mcp.example/docs"),
        ],
    )


def _install(
    mocker: MockerFixture,
    config: SimpleNamespace,
    prompt: str = "resolved prompt",
) -> MockType:
    """Patch settings configuration and system-prompt resolution."""
    for module in _SETTINGS_MODULES:
        mocker.patch(f"{module}.configuration", config)
    return mocker.patch(
        "agent.types.settings.agent.get_system_prompt",
        return_value=prompt,
    )


def _request(mocker: MockerFixture) -> Request:
    """Build a request with no client MCP headers."""
    request = mocker.Mock(spec=Request)
    request.headers = {"MCP-HEADERS": "{}"}
    return cast(Request, request)


def test_query_fields_select_the_agent(mocker: MockerFixture) -> None:
    """Query values override defaults and select shields and knowledge sources."""
    prompt = _install(
        mocker,
        _configuration(skills=SkillsConfiguration(paths=[Path("skills/one")])),
    )
    query = QueryRequest(
        query="What is Kubernetes?",
        provider="watsonx",
        model="granite",
        system_prompt="Be brief",
        shield_ids=["pii"],
        vector_store_ids=[OKP_RAG_ID],
        no_tools=False,
    )

    settings = AgentSettings.from_query_request(_request(mocker), query, "token")

    prompt.assert_called_once_with("Be brief")
    assert settings.provider == "watsonx"
    assert settings.model == "granite"
    assert settings.instructions == "resolved prompt"
    assert settings.compaction == CompactionSettings(
        provider="watsonx",
        model="granite",
        enabled=True,
    )
    assert settings.step_persistence == StepPersistenceSettings(enabled=True)
    assert settings.skills == [SkillSettings(path="skills/one")]
    assert settings.shields == [
        ShieldSettings(id="topic", enabled=False),
        ShieldSettings(id="pii", enabled=True),
    ]
    assert settings.knowledge.sources == [
        KnowledgeSourceSettings(id="alpha", enabled=False),
        OKPKnowledgeSourceSettings(id=OKP_RAG_ID, enabled=True),
    ]
    assert settings.mcp_servers == [MCPSettings(id="docs", headers={}, enabled=True)]


def test_omitted_query_fields_use_configuration_defaults(
    mocker: MockerFixture,
) -> None:
    """Omitted provider, model, and id lists keep the configured defaults enabled."""
    prompt = _install(mocker, _configuration(skills=None))
    query = QueryRequest(query="What is Kubernetes?", provider="", model="")

    settings = AgentSettings.from_query_request(_request(mocker), query, "token")

    prompt.assert_called_once_with(None)
    assert settings.provider == "openai"
    assert settings.model == "default-model"
    assert settings.compaction == CompactionSettings(
        provider="openai",
        model="default-model",
        enabled=True,
    )
    assert settings.step_persistence == StepPersistenceSettings(enabled=True)
    assert settings.skills == []
    assert [shield.enabled for shield in settings.shields] == [True, True]
    assert [source.enabled for source in settings.knowledge.sources] == [True, True]


def test_empty_selections_disable_optional_capabilities(
    mocker: MockerFixture,
) -> None:
    """Empty id lists, disabled tools, and disabled compaction turn those features off."""
    _install(mocker, _configuration(skills=None, compaction_enabled=False))
    query = QueryRequest(
        query="What is Kubernetes?",
        shield_ids=[],
        vector_store_ids=[],
        no_tools=True,
    )

    settings = AgentSettings.from_query_request(_request(mocker), query, "token")

    assert settings.compaction.enabled is False
    assert settings.skills == []
    assert [shield.enabled for shield in settings.shields] == [False, False]
    assert [source.enabled for source in settings.knowledge.sources] == [False, False]
    assert settings.mcp_servers == [MCPSettings(id="docs", headers={}, enabled=False)]
