"""Unit tests for knowledge source settings built from a query."""

from types import SimpleNamespace

from pytest_mock import MockerFixture

from agent.types.settings.knowledge import (
    KnowledgeSettings,
    KnowledgeSourceSettings,
    OKPKnowledgeSourceSettings,
)
from constants import OKP_RAG_ID
from knowledge.sources.okp import OkpProductFilter
from models.api.requests import QueryRequest
from models.config import (
    ByokConfiguration,
    RagConfiguration,
    RagStore,
    RetrievalConfiguration,
    RetrievalStrategyConfiguration,
)


def _store(rag_id: str) -> RagStore:
    """Build a FAISS store entry. The index file is not opened."""
    return RagStore(
        rag_id=rag_id,
        backend="faiss",
        vector_db_id=f"vs_{rag_id}",
        db_path=f"/tmp/{rag_id}.db",
    )


def _install(mocker: MockerFixture, rag: RagConfiguration) -> None:
    """Point knowledge settings at the given RAG configuration."""
    mocker.patch(
        "agent.types.settings.knowledge.configuration",
        SimpleNamespace(rag=rag),
    )


def _rag() -> RagConfiguration:
    """Return stores plus an OKP retrieval source that is not itself a store."""
    return RagConfiguration(
        byok=ByokConfiguration(stores=[_store("alpha"), _store("beta")]),
        retrieval=RetrievalConfiguration(
            inline=RetrievalStrategyConfiguration(sources=["alpha", OKP_RAG_ID]),
            tool=RetrievalStrategyConfiguration(sources=["beta", OKP_RAG_ID]),
        ),
    )


def _query(
    vector_store_ids: list[str] | None,
    okp_products: list[OkpProductFilter] | None = None,
) -> QueryRequest:
    """Build a query that selects the given knowledge sources."""
    return QueryRequest(
        query="What is Kubernetes?",
        vector_store_ids=vector_store_ids,
        okp_products=okp_products,
    )


def test_configured_sources_stay_enabled_when_the_query_omits_ids(
    mocker: MockerFixture,
) -> None:
    """Omitted vector store ids leave every configured source enabled."""
    _install(mocker, _rag())

    settings = KnowledgeSettings.from_query_request(_query(None))

    assert settings.sources == [
        KnowledgeSourceSettings(id="alpha", enabled=True),
        KnowledgeSourceSettings(id="beta", enabled=True),
        OKPKnowledgeSourceSettings(id=OKP_RAG_ID, enabled=True),
    ]


def test_query_ids_enable_only_the_named_sources(mocker: MockerFixture) -> None:
    """A provided id list disables every configured source that is absent."""
    _install(mocker, _rag())

    settings = KnowledgeSettings.from_query_request(_query(["beta", "unknown"]))

    assert settings.sources == [
        KnowledgeSourceSettings(id="alpha", enabled=False),
        KnowledgeSourceSettings(id="beta", enabled=True),
        OKPKnowledgeSourceSettings(id=OKP_RAG_ID, enabled=False),
    ]


def test_empty_id_list_disables_every_source(mocker: MockerFixture) -> None:
    """An empty vector store id list disables every configured source."""
    _install(mocker, _rag())

    settings = KnowledgeSettings.from_query_request(_query([]))

    assert settings.sources == [
        KnowledgeSourceSettings(id="alpha", enabled=False),
        KnowledgeSourceSettings(id="beta", enabled=False),
        OKPKnowledgeSourceSettings(id=OKP_RAG_ID, enabled=False),
    ]


def test_no_configured_sources_produce_no_settings(mocker: MockerFixture) -> None:
    """An empty RAG configuration yields no knowledge source settings."""
    _install(mocker, RagConfiguration())

    assert KnowledgeSettings.from_query_request(_query(None)).sources == []


def test_okp_products_are_kept_on_the_okp_source(mocker: MockerFixture) -> None:
    """Product filters from the query are stored only on the OKP setting."""
    _install(mocker, _rag())
    products = [
        OkpProductFilter("openshift_container_platform", ("4.19", "4.20")),
        OkpProductFilter("rhel"),
    ]

    settings = KnowledgeSettings.from_query_request(_query(None, products))

    assert settings.sources[-1] == OKPKnowledgeSourceSettings(
        id=OKP_RAG_ID,
        enabled=True,
        products=products,
    )
    assert all(
        not isinstance(source, OKPKnowledgeSourceSettings)
        for source in settings.sources[:-1]
    )
