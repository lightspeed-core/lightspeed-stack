"""Unit tests for the KnowledgeSourceRegistry singleton."""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from knowledge.errors import (
    DuplicateKnowledgeSourceError,
    KnowledgeSourceNotFoundError,
)
from knowledge.registry import KnowledgeSourceRegistry
from knowledge.sources.faiss import FaissKnowledgeSource
from knowledge.sources.okp import OkpKnowledgeSource
from knowledge.sources.pgvector import PgVectorKnowledgeSource
from models.config import (
    ByokConfiguration,
    OkpConfiguration,
    RagConfiguration,
    RagStore,
    RetrievalConfiguration,
    RetrievalStrategyConfiguration,
)
from utils.types import Singleton


def _pg_store(rag_id: str, **overrides: object) -> RagStore:
    """Build a pgvector store that does not open a connection.

    Args:
        rag_id: Store name.
        overrides: Fields that replace the connection defaults.

    Returns:
        A validated pgvector ``RagStore``.

    """
    values: dict[str, object] = {
        "rag_id": rag_id,
        "backend": "pgvector",
        "vector_db_id": f"vs_{rag_id}",
        "host": "db.example",
        "port": 5432,
        "db": "knowledge",
        "user": "reader",
    }
    values.update(overrides)
    return RagStore(**values)  # pyright: ignore[reportArgumentType]


def _faiss_store(rag_id: str) -> RagStore:
    """Build a FAISS store entry. The index file is not opened in registry tests.

    Args:
        rag_id: Store name.

    Returns:
        A validated FAISS ``RagStore``.

    """
    return RagStore(
        rag_id=rag_id,
        backend="faiss",
        vector_db_id=f"vs_{rag_id}",
        db_path=f"/tmp/{rag_id}.db",
    )


def _rag(
    *stores: RagStore,
    inline: list[str] | None = None,
    tool: list[str] | None = None,
) -> RagConfiguration:
    """Build a RAG configuration around the given stores.

    Args:
        stores: BYOK stores, in registration order.
        inline: Retrieval source names exposed automatically.
        tool: Retrieval source names exposed as a tool.

    Returns:
        A validated ``RagConfiguration``.

    """
    return RagConfiguration(
        byok=ByokConfiguration(stores=list(stores)),
        okp=OkpConfiguration(),
        retrieval=RetrievalConfiguration(
            inline=RetrievalStrategyConfiguration(sources=inline or []),
            tool=RetrievalStrategyConfiguration(sources=tool or []),
        ),
    )


@pytest.fixture(autouse=True)
def _reset_registry() -> Generator[None, None, None]:
    """Isolate the knowledge source registry per test."""
    # pylint: disable=protected-access
    Singleton._instances.pop(KnowledgeSourceRegistry, None)
    yield
    Singleton._instances.pop(KnowledgeSourceRegistry, None)
    # pylint: enable=protected-access


@pytest.fixture(name="faiss_store")
def faiss_store_fixture(mocker: MockerFixture) -> None:
    """Stop FAISS construction from opening a database file."""
    mocker.patch("knowledge.sources.faiss.FaissVectorStore")


class TestKnowledgeSourceRegistry:
    """Tests for initializing and looking up configured knowledge sources."""

    def test_registry_is_a_process_singleton(self) -> None:
        """Every construction returns the same registry."""
        assert KnowledgeSourceRegistry() is KnowledgeSourceRegistry()

    @pytest.mark.asyncio
    async def test_initialize_registers_sources_from_configuration(
        self, faiss_store: None
    ) -> None:
        """BYOK stores keep configuration order and OKP is appended."""
        del faiss_store
        registry = KnowledgeSourceRegistry()

        await registry.initialize(
            _rag(
                _faiss_store("ocp-docs"),
                _pg_store("rh-docs"),
                inline=["ocp-docs", "okp"],
                tool=["rh-docs", "okp"],
            )
        )

        sources = registry.list_sources()
        assert [source.name for source in sources] == ["ocp-docs", "rh-docs", "okp"]
        assert isinstance(sources[0], FaissKnowledgeSource)
        assert isinstance(sources[1], PgVectorKnowledgeSource)
        assert isinstance(sources[2], OkpKnowledgeSource)
        assert sources[0].mode == {"auto"}
        assert sources[1].mode == {"tool"}
        assert sources[2].mode == {"auto", "tool"}

    @pytest.mark.asyncio
    async def test_initialize_omits_okp_when_it_is_not_retrieved(self) -> None:
        """A store that is not a retrieval source is kept with no exposure."""
        registry = KnowledgeSourceRegistry()

        await registry.initialize(_rag(_pg_store("rh-docs")))

        sources = registry.list_sources()
        assert [source.name for source in sources] == ["rh-docs"]
        assert sources[0].mode == set()
        assert registry.find_source("okp") is None

    @pytest.mark.asyncio
    async def test_initialize_appends_on_a_second_call(self) -> None:
        """A later initialize adds sources without dropping earlier ones."""
        registry = KnowledgeSourceRegistry()

        await registry.initialize(_rag(_pg_store("rh-docs"), tool=["rh-docs"]))
        await registry.initialize(_rag(_pg_store("extra"), inline=["extra"]))

        assert [source.name for source in registry.list_sources()] == [
            "rh-docs",
            "extra",
        ]

    @pytest.mark.asyncio
    async def test_registered_source_is_shared_across_lookups(self) -> None:
        """A source initialized on one reference is visible on another."""
        await KnowledgeSourceRegistry().initialize(
            _rag(_pg_store("rh-docs"), tool=["rh-docs"])
        )

        assert (
            KnowledgeSourceRegistry().get_source("rh-docs")
            is KnowledgeSourceRegistry().list_sources()[0]
        )

    def test_missing_source_is_absent(self) -> None:
        """Unknown names are not found."""
        registry = KnowledgeSourceRegistry()

        assert registry.find_source("missing") is None
        assert registry.list_sources() == []
        with pytest.raises(KnowledgeSourceNotFoundError, match="missing") as error:
            registry.get_source("missing")
        assert error.value.name == "missing"

    @pytest.mark.asyncio
    async def test_duplicate_name_in_one_initialize_is_rejected(self) -> None:
        """A pgvector store named okp plus the OKP source registers nothing."""
        registry = KnowledgeSourceRegistry()

        with pytest.raises(DuplicateKnowledgeSourceError, match="okp") as error:
            await registry.initialize(_rag(_pg_store("okp"), inline=["okp"]))

        assert error.value.name == "okp"
        assert registry.list_sources() == []

    @pytest.mark.asyncio
    async def test_duplicate_name_against_existing_source_is_rejected(self) -> None:
        """A name that is already registered is not replaced, and the new batch is dropped."""
        original = KnowledgeSourceRegistry()
        await original.initialize(_rag(_pg_store("rh-docs"), tool=["rh-docs"]))

        with pytest.raises(DuplicateKnowledgeSourceError, match="rh-docs") as error:
            await original.initialize(
                _rag(_pg_store("wiki"), _pg_store("rh-docs"), tool=["wiki", "rh-docs"])
            )

        assert error.value.name == "rh-docs"
        assert [source.name for source in original.list_sources()] == ["rh-docs"]

    @pytest.mark.asyncio
    async def test_empty_configuration_registers_nothing(self) -> None:
        """No BYOK stores and no OKP retrieval source leaves the registry empty."""
        registry = KnowledgeSourceRegistry()

        await registry.initialize(RagConfiguration())

        assert registry.list_sources() == []
