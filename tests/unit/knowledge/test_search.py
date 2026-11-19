"""Unit tests for knowledge.search."""

import asyncio
from dataclasses import dataclass, field

import pytest
from pytest_mock import MockerFixture

from knowledge.search import search_sources
from knowledge.sources.base import KnowledgeSource
from knowledge.types import KnowledgeMatch, KnowledgeReadiness


def _match(
    content: str,
    score: float,
    *,
    match_id: str = "match-id",
    source: str | None = "source",
    metadata: dict[str, object] | None = None,
) -> KnowledgeMatch:
    """Build a knowledge match for search tests.

    Args:
        content: Match text.
        score: Similarity score.
        match_id: Stable identifier so tests can assert identity preservation.
        source: Optional citation identifier.
        metadata: Optional metadata carried alongside the match.

    Returns:
        A `KnowledgeMatch` with the given fields.

    """
    return KnowledgeMatch(
        content=content,
        score=score,
        id=match_id,
        source=source,
        metadata=metadata or {},
    )


def _sources(*items: KnowledgeSource) -> list[KnowledgeSource]:
    """Pack fake sources as `list[KnowledgeSource]`.

    `search_sources` takes a list, which is invariant, so a `list[_FakeSource]`
    cannot be passed directly.
    """
    return list(items)


@dataclass
class _FakeSource(KnowledgeSource):
    """Knowledge source that returns canned matches for tests."""

    matches: list[KnowledgeMatch] = field(default_factory=list)
    error: BaseException | None = None
    gate: asyncio.Event | None = None
    started: asyncio.Event | None = None
    received_prompts: list[str] = field(default_factory=list)

    async def search(self, prompt: str) -> list[KnowledgeMatch]:
        """Record `prompt` and return canned matches, optionally after a gate."""
        self.received_prompts.append(prompt)
        if self.started is not None:
            self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return list(self.matches)

    async def readiness(self) -> KnowledgeReadiness:
        """Report the fake source as ready."""
        return KnowledgeReadiness(status="ready")


class TestSearchSources:
    """Tests for the `search_sources` function."""

    @pytest.mark.asyncio
    async def test_empty_sources_returns_empty_list(self) -> None:
        """No sources produces an empty result list."""
        result = await search_sources([], "prompt")

        assert result == []

    @pytest.mark.asyncio
    async def test_forwards_prompt_to_each_source(self) -> None:
        """Every source is searched with the same prompt."""
        source_a = _FakeSource(name="a")
        source_b = _FakeSource(name="b")

        await search_sources(_sources(source_a, source_b), "how do I restart?")

        assert source_a.received_prompts == ["how do I restart?"]
        assert source_b.received_prompts == ["how do I restart?"]

    @pytest.mark.asyncio
    async def test_tags_matches_with_source_name(self) -> None:
        """Each match is tagged with `metadata['knowledge_source']`."""
        sources = _sources(
            _FakeSource(
                name="docs",
                matches=[_match("alpha", 0.8, match_id="1", metadata={"k": "v"})],
            ),
            _FakeSource(
                name="wiki",
                matches=[_match("beta", 0.4, match_id="2")],
            ),
        )

        result = await search_sources(sources, "prompt")

        by_id = {match.id: match for match in result}
        assert by_id["1"].metadata == {"k": "v", "knowledge_source": "docs"}
        assert by_id["2"].metadata == {"knowledge_source": "wiki"}

    @pytest.mark.asyncio
    async def test_overwrites_existing_knowledge_source_metadata(self) -> None:
        """The searching source's name wins over a pre-existing tag."""
        sources = _sources(
            _FakeSource(
                name="docs",
                matches=[
                    _match(
                        "alpha",
                        0.5,
                        metadata={"knowledge_source": "stale"},
                    )
                ],
            )
        )

        result = await search_sources(sources, "prompt")

        assert result[0].metadata == {"knowledge_source": "docs"}

    @pytest.mark.asyncio
    async def test_does_not_mutate_input_matches(self) -> None:
        """Original matches and their metadata are left unchanged."""
        original = _match("alpha", 0.5, metadata={"k": "v"})
        sources = _sources(_FakeSource(name="docs", matches=[original]))

        result = await search_sources(sources, "prompt")

        assert original.metadata == {"k": "v"}
        assert original.score == 0.5
        assert result[0] is not original

    @pytest.mark.asyncio
    async def test_merges_matches_from_multiple_sources(self) -> None:
        """Matches from every source are included in the merged result."""
        sources = _sources(
            _FakeSource(
                name="docs",
                matches=[
                    _match("a1", 0.2, match_id="a1"),
                    _match("a2", 0.4, match_id="a2"),
                ],
            ),
            _FakeSource(name="wiki", matches=[_match("b1", 0.3, match_id="b1")]),
        )

        result = await search_sources(sources, "prompt")

        assert {match.id for match in result} == {"a1", "a2", "b1"}

    @pytest.mark.asyncio
    async def test_skips_empty_source_results(self) -> None:
        """A source that returns nothing does not contribute matches."""
        sources = _sources(
            _FakeSource(name="empty"),
            _FakeSource(name="docs", matches=[_match("only", 0.9, match_id="1")]),
        )

        result = await search_sources(sources, "prompt")

        assert [match.id for match in result] == ["1"]
        assert result[0].metadata == {"knowledge_source": "docs"}

    @pytest.mark.asyncio
    async def test_sorts_by_score_descending_without_reranker(self) -> None:
        """Without a reranker, merged matches are ranked highest-score-first."""
        sources = _sources(
            _FakeSource(
                name="docs",
                matches=[
                    _match("low", 0.1, match_id="low"),
                    _match("mid", 0.5, match_id="mid"),
                ],
            ),
            _FakeSource(
                name="wiki",
                matches=[_match("high", 0.9, match_id="high")],
            ),
        )

        result = await search_sources(sources, "prompt")

        assert [match.id for match in result] == ["high", "mid", "low"]
        assert [match.score for match in result] == [0.9, 0.5, 0.1]

    @pytest.mark.asyncio
    async def test_equal_scores_preserve_merge_order(self) -> None:
        """Tied scores keep source-then-match order via a stable sort."""
        sources = _sources(
            _FakeSource(
                name="docs",
                matches=[
                    _match("first", 0.5, match_id="first"),
                    _match("second", 0.5, match_id="second"),
                ],
            ),
            _FakeSource(
                name="wiki",
                matches=[_match("third", 0.5, match_id="third")],
            ),
        )

        result = await search_sources(sources, "prompt")

        assert [match.id for match in result] == ["first", "second", "third"]

    @pytest.mark.asyncio
    async def test_limit_keeps_the_highest_ranked_matches(self) -> None:
        """The cap keeps the highest scores the sources already returned."""
        sources = _sources(
            _FakeSource(
                name="docs",
                matches=[
                    _match("low", 0.2, match_id="low"),
                    _match("high", 0.8, match_id="high"),
                ],
            )
        )

        result = await search_sources(sources, "prompt", limit=1)

        assert [match.id for match in result] == ["high"]
        assert result[0].score == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_multiplies_scores_after_ranking(self) -> None:
        """Source weights scale the ranked scores and leave search hits unchanged."""
        original = _match("boosted", 0.4, match_id="boosted")
        sources = _sources(
            _FakeSource(
                name="docs",
                score_multiplier=3.0,
                matches=[original],
            ),
            _FakeSource(
                name="wiki",
                matches=[_match("plain", 0.9, match_id="plain")],
            ),
        )

        result = await search_sources(sources, "prompt")

        assert original.score == 0.4
        assert [match.id for match in result] == ["plain", "boosted"]
        assert result[0].score == pytest.approx(0.9)
        assert result[1].score == pytest.approx(1.2)

    @pytest.mark.asyncio
    async def test_multiplies_reranked_scores_without_changing_order(
        self, mocker: MockerFixture
    ) -> None:
        """Rerank order is kept; each returned score is then weighted."""
        reranked = [
            _match(
                "wiki",
                0.2,
                match_id="wiki",
                metadata={"knowledge_source": "wiki"},
            ),
            _match(
                "docs",
                0.8,
                match_id="docs",
                metadata={"knowledge_source": "docs"},
            ),
        ]
        mocker.patch(
            "knowledge.search.rerank",
            new_callable=mocker.AsyncMock,
            return_value=reranked,
        )
        sources = _sources(
            _FakeSource(
                name="docs",
                score_multiplier=3.0,
                matches=[_match("docs", 0.1, match_id="docs")],
            ),
            _FakeSource(
                name="wiki",
                matches=[_match("wiki", 0.9, match_id="wiki")],
            ),
        )

        result = await search_sources(sources, "prompt", reranker=mocker.Mock())

        assert [match.id for match in result] == ["wiki", "docs"]
        assert result[0] is reranked[0]
        assert result[1].score == pytest.approx(2.4)

    @pytest.mark.asyncio
    async def test_does_not_call_rerank_when_reranker_is_none(
        self, mocker: MockerFixture
    ) -> None:
        """The similarity-score sort path does not invoke the reranker."""
        mock_rerank = mocker.patch(
            "knowledge.search.rerank",
            new_callable=mocker.AsyncMock,
        )
        sources = _sources(_FakeSource(name="docs", matches=[_match("alpha", 0.2)]))

        await search_sources(sources, "prompt")

        mock_rerank.assert_not_called()

    @pytest.mark.asyncio
    async def test_reranker_receives_tagged_matches_in_source_order(
        self, mocker: MockerFixture
    ) -> None:
        """Rerank is called with source-order matches, not a pre-sorted list."""
        reranked = [_match("reranked", 0.99, match_id="reranked")]
        mock_rerank = mocker.patch(
            "knowledge.search.rerank",
            new_callable=mocker.AsyncMock,
            return_value=reranked,
        )
        reranker = mocker.Mock()
        sources = _sources(
            _FakeSource(
                name="docs",
                matches=[
                    _match("low", 0.1, match_id="low"),
                    _match("mid", 0.5, match_id="mid"),
                ],
            ),
            _FakeSource(
                name="wiki",
                matches=[_match("high", 0.9, match_id="high")],
            ),
        )

        result = await search_sources(sources, "prompt", reranker=reranker)

        assert result is reranked
        mock_rerank.assert_awaited_once()
        assert mock_rerank.await_args is not None
        call_prompt, call_matches, call_reranker = mock_rerank.await_args.args
        assert call_prompt == "prompt"
        assert call_reranker is reranker
        assert [match.id for match in call_matches] == ["low", "mid", "high"]
        assert [match.metadata["knowledge_source"] for match in call_matches] == [
            "docs",
            "docs",
            "wiki",
        ]

    @pytest.mark.asyncio
    async def test_searches_sources_concurrently(self) -> None:
        """Sources are searched in parallel, not one after another."""
        gate = asyncio.Event()
        started_a = asyncio.Event()
        started_b = asyncio.Event()
        sources = _sources(
            _FakeSource(name="a", gate=gate, started=started_a),
            _FakeSource(name="b", gate=gate, started=started_b),
        )

        task = asyncio.create_task(search_sources(sources, "prompt"))
        await asyncio.wait_for(
            asyncio.gather(started_a.wait(), started_b.wait()),
            timeout=1,
        )
        gate.set()

        result = await task

        assert result == []

    @pytest.mark.asyncio
    async def test_propagates_source_search_error(self) -> None:
        """A failing source search is not swallowed."""
        sources = _sources(
            _FakeSource(name="ok", matches=[_match("alpha", 0.5)]),
            _FakeSource(name="bad", error=RuntimeError("search failed")),
        )

        with pytest.raises(RuntimeError, match="search failed"):
            await search_sources(sources, "prompt")
