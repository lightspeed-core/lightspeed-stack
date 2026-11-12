"""Unit tests for knowledge.capability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pytest
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextContent,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext
from pytest_mock import AsyncMockType, MockerFixture, MockType

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


def _source(name: str, *modes: Literal["tool", "auto"]) -> FakeKnowledgeSource:
    """Build a fake knowledge source with the given exposure modes."""
    mode: set[Literal["tool", "auto"]] = set(modes) if modes else {"tool"}
    return FakeKnowledgeSource(name=name, mode=mode)


def _match(
    content: str,
    score: float,
    *,
    match_id: str = "match-id",
    source: str | None = "doc://source",
    metadata: dict[str, object] | None = None,
) -> KnowledgeMatch:
    """Build a knowledge match for auto-mode injection tests."""
    return KnowledgeMatch(
        content=content,
        score=score,
        id=match_id,
        source=source,
        metadata=metadata or {},
    )


def _user_request(text: str = "how do I restart?") -> ModelRequest:
    """Build a model request whose latest part is a user prompt."""
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _request_context(
    mocker: MockerFixture,
    messages: list[ModelRequest | ModelResponse] | None = None,
) -> ModelRequestContext:
    """Build a `ModelRequestContext` wrapping `messages`."""
    return ModelRequestContext(
        model=mocker.Mock(),
        messages=list(messages or [_user_request()]),
        model_settings=None,
        model_request_parameters=mocker.Mock(),
    )


def _injected_knowledge(request: ModelRequest) -> TextContent:
    """Return the knowledge `TextContent` appended to `request`."""
    added = request.parts[-1]
    assert isinstance(added, UserPromptPart)
    content = added.content
    assert isinstance(content, list)
    text = content[0]
    assert isinstance(text, TextContent)
    return text


class TestKnowledgeBeforeModelRequestAutoMode:
    """Tests for `Knowledge.before_model_request` auto-mode injection."""

    @pytest.fixture(name="search_sources")
    def search_sources_fixture(self, mocker: MockerFixture) -> AsyncMockType:
        """Patch `search_sources` where the capability looks it up."""
        return mocker.patch(
            "knowledge.capability.search_sources",
            new_callable=mocker.AsyncMock,
            return_value=[],
        )

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_no_auto_sources(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """Tool-only sources are not searched and the request is left untouched."""
        request = _user_request()
        request_context = _request_context(mocker, [request])
        capability = Knowledge(sources=[_source("tools")])

        result = await capability.before_model_request(mocker.Mock(), request_context)

        assert result is request_context
        assert len(request.parts) == 1
        search_sources.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_sources_are_empty(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """An empty source list skips auto injection."""
        request = _user_request()
        request_context = _request_context(mocker, [request])
        capability = Knowledge(sources=[])

        result = await capability.before_model_request(mocker.Mock(), request_context)

        assert result is request_context
        assert len(request.parts) == 1
        search_sources.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_prompt_is_missing(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """Auto sources are not searched when history has no user prompt."""
        request = ModelRequest(parts=[SystemPromptPart(content="system")])
        request_context = _request_context(mocker, [request])
        capability = Knowledge(sources=[_source("docs", "auto")])

        result = await capability.before_model_request(mocker.Mock(), request_context)

        assert result is request_context
        assert len(request.parts) == 1
        search_sources.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_prompt_is_empty(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """An empty user prompt is treated as missing and skips search."""
        request = _user_request("")
        request_context = _request_context(mocker, [request])
        capability = Knowledge(sources=[_source("docs", "auto")])

        result = await capability.before_model_request(mocker.Mock(), request_context)

        assert result is request_context
        assert len(request.parts) == 1
        search_sources.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_search_finds_no_matches(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """An empty search result does not append a knowledge part."""
        request = _user_request()
        request_context = _request_context(mocker, [request])
        capability = Knowledge(sources=[_source("docs", "auto")])

        result = await capability.before_model_request(mocker.Mock(), request_context)

        assert result is request_context
        assert len(request.parts) == 1
        search_sources.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_searches_only_auto_mode_sources_with_latest_prompt(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """Tool-only sources are skipped; auto sources keep declaration order."""
        tool = _source("tools")
        auto_docs = _source("docs", "auto")
        auto_wiki = _source("wiki", "auto")
        earlier = _user_request("older question")
        latest = _user_request("how do I restart?")
        request_context = _request_context(
            mocker,
            [
                earlier,
                ModelResponse(parts=[TextPart(content="reply")]),
                latest,
            ],
        )
        capability = Knowledge(sources=[tool, auto_docs, auto_wiki])

        await capability.before_model_request(mocker.Mock(), request_context)

        search_sources.assert_awaited_once_with(
            [auto_docs, auto_wiki],
            "how do I restart?",
            None,
        )
        assert len(earlier.parts) == 1

    @pytest.mark.asyncio
    async def test_includes_source_with_both_auto_and_tool_modes(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """A source exposing both modes is still searched automatically."""
        both = _source("docs", "auto", "tool")
        request_context = _request_context(mocker)
        capability = Knowledge(sources=[both])

        await capability.before_model_request(mocker.Mock(), request_context)

        search_sources.assert_awaited_once_with([both], "how do I restart?", None)

    @pytest.mark.asyncio
    async def test_forwards_reranker_to_search_sources(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """The capability's cross-encoder is passed through to search."""
        auto = _source("docs", "auto")
        reranker: MockType = mocker.Mock()
        request_context = _request_context(mocker)
        capability = Knowledge(sources=[auto], reranker=reranker)

        await capability.before_model_request(mocker.Mock(), request_context)

        search_sources.assert_awaited_once_with([auto], "how do I restart?", reranker)

    @pytest.mark.asyncio
    async def test_appends_formatted_knowledge_to_latest_request(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """Matches are injected as delimited XML on the latest user request."""
        original = UserPromptPart(content="how do I restart?")
        request = ModelRequest(parts=[original])
        earlier = _user_request("older question")
        request_context = _request_context(
            mocker,
            [earlier, ModelResponse(parts=[TextPart(content="reply")]), request],
        )
        search_sources.return_value = [
            _match(
                "  Restart systemd  ",
                0.9,
                match_id="m1",
                source="doc://restart",
                metadata={"knowledge_source": "docs", "page": 1},
            )
        ]
        capability = Knowledge(sources=[_source("docs", "auto")])

        result = await capability.before_model_request(mocker.Mock(), request_context)

        assert result is request_context
        assert request.parts[0] is original
        assert len(earlier.parts) == 1
        text = _injected_knowledge(request)
        assert text.content == (
            "<knowledge>\n"
            '<match id="m1" source="doc://restart" knowledge_source="docs">\n'
            "Restart systemd\n"
            "</match>\n"
            "</knowledge>"
        )
        assert text.metadata == {
            "kind": "knowledge",
            "knowledge_scores": {"m1": 0.9},
            "knowledge_metadata": {
                "m1": {"knowledge_source": "docs", "page": 1},
            },
            "knowledge_sources": {"m1": "docs"},
        }

    @pytest.mark.asyncio
    async def test_formats_multiple_matches_and_missing_source_fields(
        self,
        mocker: MockerFixture,
        search_sources: AsyncMockType,
    ) -> None:
        """Matches are joined with a blank line; missing fields get safe defaults."""
        request = _user_request()
        request_context = _request_context(mocker, [request])
        search_sources.return_value = [
            _match(
                "alpha",
                0.8,
                match_id="m1",
                source="doc://a",
                metadata={"knowledge_source": "docs"},
            ),
            _match(
                "beta",
                0.2,
                match_id="m2",
                source=None,
                metadata={},
            ),
        ]
        capability = Knowledge(sources=[_source("docs", "auto")])

        await capability.before_model_request(mocker.Mock(), request_context)

        text = _injected_knowledge(request)
        assert text.content == (
            "<knowledge>\n"
            '<match id="m1" source="doc://a" knowledge_source="docs">\n'
            "alpha\n"
            "</match>\n"
            "\n"
            '<match id="m2" source="None" knowledge_source="">\n'
            "beta\n"
            "</match>\n"
            "</knowledge>"
        )
        assert text.metadata == {
            "kind": "knowledge",
            "knowledge_scores": {"m1": 0.8, "m2": 0.2},
            "knowledge_metadata": {
                "m1": {"knowledge_source": "docs"},
                "m2": {},
            },
            "knowledge_sources": {"m1": "docs", "m2": None},
        }


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
