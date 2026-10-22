"""Unit tests for knowledge.capability."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai.capabilities import AbstractCapability
from pytest_mock import MockerFixture, MockType

from knowledge.capability import Knowledge
from knowledge.sources.base import KnowledgeSource
from knowledge.toolset import KnowledgeToolset
from knowledge.types import KnowledgeMatch, KnowledgeReadiness


@dataclass
class FakeKnowledgeSource(KnowledgeSource):
    """Minimal knowledge source double for constructing `Knowledge`."""

    async def search(self, prompt: str) -> list[KnowledgeMatch]:
        """Unused; required by `KnowledgeSource`."""
        return []

    async def readiness(self) -> KnowledgeReadiness:
        """Report the source as ready."""
        return KnowledgeReadiness(status="ready")


class TestKnowledge:
    """Tests for the `Knowledge` capability dataclass."""

    def test_is_abstract_capability(self) -> None:
        """Knowledge is a pydantic-ai capability."""
        assert issubclass(Knowledge, AbstractCapability)

    def test_stores_sources_and_defaults_reranker_to_none(self) -> None:
        """Sources are retained and the cross-encoder is optional."""
        source = FakeKnowledgeSource(name="kb")

        capability = Knowledge(sources=[source])

        assert list(capability.sources) == [source]
        assert capability.reranker is None

    def test_stores_optional_reranker(self, mocker: MockerFixture) -> None:
        """An explicit reranker is retained on the capability."""
        source = FakeKnowledgeSource(name="kb")
        reranker: MockType = mocker.Mock()

        capability = Knowledge(sources=[source], reranker=reranker)

        assert capability.reranker is reranker


class TestGetToolset:
    """Tests for `Knowledge.get_toolset` tool-mode exposure."""

    def test_returns_none_when_there_are_no_sources(self) -> None:
        """An empty source list does not register a search tool."""
        assert Knowledge(sources=[]).get_toolset() is None

    def test_returns_none_for_auto_only_sources(self) -> None:
        """Sources that only inject context do not register a search tool."""
        source = FakeKnowledgeSource(name="kb", mode={"auto"})

        assert Knowledge(sources=[source]).get_toolset() is None

    def test_returns_none_when_every_source_is_auto_only(self) -> None:
        """Mixed auto-only sources still produce no toolset."""
        sources = [
            FakeKnowledgeSource(name="docs", mode={"auto"}),
            FakeKnowledgeSource(name="wiki", mode={"auto"}),
        ]

        assert Knowledge(sources=sources).get_toolset() is None

    def test_returns_toolset_for_default_tool_mode(self) -> None:
        """The default source mode is `'tool'` and yields a knowledge toolset."""
        source = FakeKnowledgeSource(name="kb")

        toolset = Knowledge(sources=[source]).get_toolset()

        assert isinstance(toolset, KnowledgeToolset)
        assert toolset.id == "knowledge:kb"
        assert list(toolset.tools) == ["search_knowledge"]

    def test_includes_sources_with_both_tool_and_auto_modes(self) -> None:
        """A source that is both `'tool'` and `'auto'` still gets a search tool."""
        source = FakeKnowledgeSource(name="kb", mode={"tool", "auto"})

        toolset = Knowledge(sources=[source]).get_toolset()

        assert isinstance(toolset, KnowledgeToolset)
        assert toolset.id == "knowledge:kb"

    def test_filters_to_tool_mode_sources_in_declaration_order(self) -> None:
        """Auto-only sources are omitted; remaining sources keep their order."""
        docs = FakeKnowledgeSource(name="docs")
        wiki = FakeKnowledgeSource(name="wiki", mode={"auto"})
        runbooks = FakeKnowledgeSource(name="runbooks", mode={"tool", "auto"})

        toolset = Knowledge(sources=[docs, wiki, runbooks]).get_toolset()

        assert isinstance(toolset, KnowledgeToolset)
        assert toolset.id == "knowledge:docs+runbooks"
        description = toolset.tools["search_knowledge"].description
        assert description is not None
        assert "docs, runbooks" in description
        assert "wiki" not in description

    def test_does_not_mutate_capability_sources(self) -> None:
        """Filtering tool-mode sources leaves the capability's source list intact."""
        docs = FakeKnowledgeSource(name="docs")
        wiki = FakeKnowledgeSource(name="wiki", mode={"auto"})
        sources = [docs, wiki]
        capability = Knowledge(sources=sources)

        capability.get_toolset()

        assert list(capability.sources) == [docs, wiki]

    def test_passes_reranker_to_toolset(self, mocker: MockerFixture) -> None:
        """The capability reranker is forwarded into `KnowledgeToolset`."""
        source = FakeKnowledgeSource(name="kb")
        reranker: MockType = mocker.Mock()
        mock_toolset_cls = mocker.patch(
            "knowledge.capability.KnowledgeToolset",
            return_value=mocker.Mock(spec=KnowledgeToolset),
        )

        result = Knowledge(sources=[source], reranker=reranker).get_toolset()

        mock_toolset_cls.assert_called_once_with([source], reranker=reranker)
        assert result is mock_toolset_cls.return_value

    def test_passes_none_reranker_by_default(self, mocker: MockerFixture) -> None:
        """When no reranker is configured, the toolset is built with `None`."""
        source = FakeKnowledgeSource(name="kb")
        mock_toolset_cls = mocker.patch(
            "knowledge.capability.KnowledgeToolset",
            return_value=mocker.Mock(spec=KnowledgeToolset),
        )

        Knowledge(sources=[source]).get_toolset()

        mock_toolset_cls.assert_called_once_with([source], reranker=None)
