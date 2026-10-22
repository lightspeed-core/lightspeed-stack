"""Unit tests for knowledge.toolset."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pytest
from pydantic_ai.tools import RunContext
from pydantic_ai.toolsets import FunctionToolset
from pytest_mock import MockerFixture, MockType

from knowledge.sources.base import KnowledgeSource
from knowledge.toolset import KnowledgeToolset
from knowledge.types import KnowledgeMatch, KnowledgeReadiness


def _match(
    content: str,
    score: float,
    *,
    match_id: str = "match-id",
) -> KnowledgeMatch:
    """Build a knowledge match for toolset tests.

    Args:
        content: Match text.
        score: Similarity score.
        match_id: Stable identifier so tests can assert identity.

    Returns:
        A `KnowledgeMatch` with the given fields.

    """
    return KnowledgeMatch(content=content, score=score, id=match_id)


def _run_context(mocker: MockerFixture) -> RunContext[object]:
    """Return a dummy run context; search does not read it.

    Args:
        mocker: Pytest-mock fixture.

    Returns:
        A typed stand-in for `RunContext`.

    """
    return cast(RunContext[object], mocker.Mock())


@dataclass
class FakeKnowledgeSource(KnowledgeSource):
    """Knowledge source that records prompts and returns canned matches."""

    matches: list[KnowledgeMatch] = field(default_factory=list)
    received_prompts: list[str] = field(default_factory=list)

    async def search(self, prompt: str) -> list[KnowledgeMatch]:
        """Record `prompt` and return canned matches."""
        self.received_prompts.append(prompt)
        return list(self.matches)

    async def readiness(self) -> KnowledgeReadiness:
        """Report the fake source as ready."""
        return KnowledgeReadiness(status="ready")


class TestKnowledgeToolset:
    """Tests for the `KnowledgeToolset` function toolset."""

    def test_is_function_toolset(self) -> None:
        """KnowledgeToolset is a pydantic-ai FunctionToolset."""
        assert issubclass(KnowledgeToolset, FunctionToolset)

    def test_id_uses_single_source_name(self) -> None:
        """Toolset id is `knowledge:` plus the source name."""
        toolset = KnowledgeToolset([FakeKnowledgeSource(name="docs")])

        assert toolset.id == "knowledge:docs"

    def test_id_joins_source_names(self) -> None:
        """Multiple sources are joined with `+` in declaration order."""
        toolset = KnowledgeToolset(
            [
                FakeKnowledgeSource(name="docs"),
                FakeKnowledgeSource(name="wiki"),
            ]
        )

        assert toolset.id == "knowledge:docs+wiki"

    def test_registers_search_knowledge_tool(self) -> None:
        """The toolset exposes exactly one `search_knowledge` tool."""
        toolset = KnowledgeToolset([FakeKnowledgeSource(name="docs")])

        assert list(toolset.tools) == ["search_knowledge"]
        assert toolset.tools["search_knowledge"].name == "search_knowledge"

    def test_tool_description_lists_source_names(self) -> None:
        """The model-facing description names every searched source."""
        toolset = KnowledgeToolset(
            [
                FakeKnowledgeSource(name="docs"),
                FakeKnowledgeSource(name="wiki"),
            ]
        )

        assert toolset.tools["search_knowledge"].description == (
            "Search the knowledge base for information relevant to a query. "
            "Searches across: docs, wiki."
        )

    def test_search_knowledge_schema_exposes_only_query(self) -> None:
        """The model sees a `query` argument; run context is not a tool parameter."""
        toolset = KnowledgeToolset([FakeKnowledgeSource(name="docs")])
        schema = toolset.tools["search_knowledge"].function_schema.json_schema

        assert schema.get("properties", {}).keys() == {"query"}
        assert schema.get("required") == ["query"]
        assert toolset.tools["search_knowledge"].function_schema.takes_ctx is True

    @pytest.mark.asyncio
    async def test_search_forwards_query_sources_and_reranker(
        self, mocker: MockerFixture
    ) -> None:
        """`search_knowledge` passes the query, sources, and reranker through."""
        source = FakeKnowledgeSource(name="docs")
        reranker: MockType = mocker.Mock()
        matches = [_match("hit", 0.9)]
        mock_search = mocker.patch(
            "knowledge.toolset.search_sources",
            new_callable=mocker.AsyncMock,
            return_value=matches,
        )
        toolset = KnowledgeToolset([source], reranker=reranker)

        result = await toolset._search(  # pylint: disable=protected-access
            _run_context(mocker), "how do I restart?"
        )

        assert result is matches
        mock_search.assert_awaited_once()
        assert mock_search.await_args is not None
        called_sources, called_query, called_reranker = mock_search.await_args.args
        assert list(called_sources) == [source]
        assert called_query == "how do I restart?"
        assert called_reranker is reranker

    @pytest.mark.asyncio
    async def test_search_defaults_reranker_to_none(
        self, mocker: MockerFixture
    ) -> None:
        """Without a reranker, search_sources is called with `None`."""
        mock_search = mocker.patch(
            "knowledge.toolset.search_sources",
            new_callable=mocker.AsyncMock,
            return_value=[],
        )
        toolset = KnowledgeToolset([FakeKnowledgeSource(name="docs")])

        await toolset._search(  # pylint: disable=protected-access
            _run_context(mocker), "query"
        )

        mock_search.assert_awaited_once()
        assert mock_search.await_args is not None
        assert mock_search.await_args.args[2] is None

    @pytest.mark.asyncio
    async def test_search_uses_a_copy_of_the_sources_sequence(
        self, mocker: MockerFixture
    ) -> None:
        """Mutating the constructor sequence after init does not change searches."""
        source_a = FakeKnowledgeSource(name="docs")
        source_b = FakeKnowledgeSource(name="wiki")
        sources: list[KnowledgeSource] = [source_a]
        mock_search = mocker.patch(
            "knowledge.toolset.search_sources",
            new_callable=mocker.AsyncMock,
            return_value=[],
        )
        toolset = KnowledgeToolset(sources)
        sources.append(source_b)

        await toolset._search(  # pylint: disable=protected-access
            _run_context(mocker), "query"
        )

        mock_search.assert_awaited_once()
        assert mock_search.await_args is not None
        assert list(mock_search.await_args.args[0]) == [source_a]
        assert mock_search.await_args.args[0] is not sources

    @pytest.mark.asyncio
    async def test_search_queries_sources_and_returns_tagged_matches(
        self, mocker: MockerFixture
    ) -> None:
        """The tool searches attached sources and tags matches with the source name."""
        source = FakeKnowledgeSource(
            name="docs",
            matches=[_match("alpha", 0.8, match_id="1")],
        )
        toolset = KnowledgeToolset([source])

        result = await toolset._search(  # pylint: disable=protected-access
            _run_context(mocker), "how do I restart?"
        )

        assert source.received_prompts == ["how do I restart?"]
        assert [match.id for match in result] == ["1"]
        assert result[0].content == "alpha"
        assert result[0].metadata == {"knowledge_source": "docs"}

    @pytest.mark.asyncio
    async def test_search_merges_matches_from_every_source(
        self, mocker: MockerFixture
    ) -> None:
        """One `search_knowledge` call covers every tool-mode source at once."""
        docs = FakeKnowledgeSource(
            name="docs",
            matches=[_match("from-docs", 0.2, match_id="docs-1")],
        )
        wiki = FakeKnowledgeSource(
            name="wiki",
            matches=[_match("from-wiki", 0.9, match_id="wiki-1")],
        )
        toolset = KnowledgeToolset([docs, wiki])

        result = await toolset._search(  # pylint: disable=protected-access
            _run_context(mocker), "query"
        )

        assert docs.received_prompts == ["query"]
        assert wiki.received_prompts == ["query"]
        assert [match.id for match in result] == ["wiki-1", "docs-1"]
        assert [match.metadata["knowledge_source"] for match in result] == [
            "wiki",
            "docs",
        ]
