"""Unit tests for the OKP MCP retriever."""

from typing import Any
from urllib.parse import urljoin

import pytest
from pydantic import AnyUrl
from pytest_mock import MockerFixture

import constants
from models.common.query import OkpFilter
from pydantic_ai_lightspeed.retrieval.okp_mcp import _provider
from pydantic_ai_lightspeed.retrieval.okp_mcp._client import OkpMcpUnavailableError
from pydantic_ai_lightspeed.retrieval.okp_mcp._provider import OkpMcpRetriever

SAMPLE_RESULT: dict[str, Any] = {
    "response": {
        "numFound": 2,
        "docs": [
            {
                "chunk": "content A",
                "score": 74.0,
                "title": "Title A",
                "doc_id": "doc-a",
                "product": ["rhel"],
                "product_version": "9",
                "online_source_url": "https://docs.redhat.com/a",
                "source_path": "/en/a",
            },
            {
                "chunk": "content B",
                "score": 73.0,
                "title": "Title B",
                "doc_id": "doc-b",
                "online_source_url": "https://docs.redhat.com/b",
                "source_path": "/en/b",
            },
        ],
    }
}


def _retriever(offline: bool = False, max_chunks: int = 5) -> OkpMcpRetriever:
    """Build a retriever with an explicit, test-friendly configuration."""
    return OkpMcpRetriever(
        url="http://okp:8080/mcp",
        tool_name="search",
        max_chunks=max_chunks,
        offline=offline,
        doc_base_url="http://okp:8081",
    )


@pytest.mark.asyncio
async def test_fetch_maps_online_urls(mocker: MockerFixture) -> None:
    """Online mode uses online_source_url and maps chunks + documents."""
    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(return_value=SAMPLE_RESULT)
    )

    chunks, documents = await _retriever(offline=False).fetch("q")

    assert [c.content for c in chunks] == ["content A", "content B"]
    assert all(c.source == constants.OKP_RAG_ID for c in chunks)
    assert chunks[0].score == 74.0
    assert chunks[0].attributes["doc_url"] == "https://docs.redhat.com/a"
    assert chunks[0].attributes["document_id"] == "doc-a"
    assert chunks[0].attributes["product"] == ["rhel"]

    assert [str(d.doc_url) for d in documents] == [
        "https://docs.redhat.com/a",
        "https://docs.redhat.com/b",
    ]
    assert documents[0].doc_title == "Title A"
    assert documents[0].source == constants.OKP_RAG_ID


@pytest.mark.asyncio
async def test_fetch_maps_offline_urls(mocker: MockerFixture) -> None:
    """Offline mode joins source_path onto the document base URL."""
    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(return_value=SAMPLE_RESULT)
    )

    chunks, documents = await _retriever(offline=True).fetch("q")

    assert chunks[0].attributes["doc_url"] == "http://okp:8081/en/a"
    assert documents[0].doc_url == AnyUrl("http://okp:8081/en/a")


@pytest.mark.asyncio
async def test_fetch_caps_at_max_chunks(mocker: MockerFixture) -> None:
    """Only max_chunks documents are kept."""
    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(return_value=SAMPLE_RESULT)
    )

    chunks, _ = await _retriever(max_chunks=1).fetch("q")

    assert len(chunks) == 1
    assert chunks[0].content == "content A"


@pytest.mark.asyncio
async def test_fetch_requests_clamped_rows(mocker: MockerFixture) -> None:
    """rows requested from the server never exceed OKP_MCP_MAX_ROWS."""
    call = mocker.AsyncMock(return_value={"response": {"docs": []}})
    mocker.patch.object(_provider, "call_okp_search", call)

    await _retriever(max_chunks=100).fetch("q")

    assert call.await_args.kwargs["rows"] == constants.OKP_MCP_MAX_ROWS


@pytest.mark.asyncio
async def test_fetch_skips_chunks_without_content(mocker: MockerFixture) -> None:
    """Documents lacking chunk text produce no RAGChunk."""
    result = {"response": {"docs": [{"doc_id": "d1", "title": "t"}, {"chunk": "keep"}]}}
    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(return_value=result)
    )

    chunks, _ = await _retriever().fetch("q")

    assert [c.content for c in chunks] == ["keep"]


@pytest.mark.asyncio
async def test_fetch_dedups_documents(mocker: MockerFixture) -> None:
    """Documents with the same URL are deduplicated."""
    result = {
        "response": {
            "docs": [
                {"chunk": "a", "doc_id": "d", "online_source_url": "https://x/1"},
                {"chunk": "b", "doc_id": "d", "online_source_url": "https://x/1"},
            ]
        }
    }
    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(return_value=result)
    )

    chunks, documents = await _retriever().fetch("q")

    assert len(chunks) == 2
    assert len(documents) == 1


@pytest.mark.asyncio
async def test_fetch_raises_when_every_search_fails(mocker: MockerFixture) -> None:
    """When all searches fail, OkpMcpUnavailableError signals Solr fallback."""
    mocker.patch.object(
        _provider,
        "call_okp_search",
        mocker.AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(OkpMcpUnavailableError):
        await _retriever().fetch("q")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"response": None},
        {"response": {"docs": None}},
        {"response": {}},
    ],
)
async def test_fetch_handles_malformed_payload(
    mocker: MockerFixture, payload: dict[str, Any]
) -> None:
    """Missing/malformed response shapes yield empty results."""
    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(return_value=payload)
    )

    chunks, documents = await _retriever().fetch("q")

    assert chunks == []
    assert documents == []


@pytest.mark.asyncio
async def test_fetch_defaults_product_filters_to_none(mocker: MockerFixture) -> None:
    """Without configured filters, None is forwarded (client then omits them)."""
    call = mocker.AsyncMock(return_value={"response": {"docs": []}})
    mocker.patch.object(_provider, "call_okp_search", call)

    await _retriever().fetch("q")

    assert call.await_args.kwargs["product"] is None
    assert call.await_args.kwargs["product_version"] is None


@pytest.mark.asyncio
async def test_fetch_fans_out_over_products_and_versions(
    mocker: MockerFixture,
) -> None:
    """A multi-version query-time filter issues one search per (product, version)."""
    call = mocker.AsyncMock(return_value={"response": {"docs": []}})
    mocker.patch.object(_provider, "call_okp_search", call)

    okp = OkpFilter.model_validate(
        {
            "products": [
                {
                    "product": "openshift_container_platform",
                    "versions": ["4.16", "4.17"],
                },
                {"product": "rhel"},
            ]
        }
    )
    await _retriever().fetch("q", okp=okp)

    combos = {
        (c.kwargs["product"], c.kwargs["product_version"]) for c in call.await_args_list
    }
    assert combos == {
        ("openshift_container_platform", "4.16"),
        ("openshift_container_platform", "4.17"),
        ("rhel", None),
    }


@pytest.mark.asyncio
async def test_fetch_okp_filter_selects_products(mocker: MockerFixture) -> None:
    """A query-time filter drives the searched product/version."""
    call = mocker.AsyncMock(return_value={"response": {"docs": []}})
    mocker.patch.object(_provider, "call_okp_search", call)

    okp = OkpFilter.model_validate({"products": [{"product": "rhel"}]})
    await _retriever().fetch("q", okp=okp)

    assert call.await_count == 1
    assert call.await_args.kwargs["product"] == "rhel"
    assert call.await_args.kwargs["product_version"] is None


@pytest.mark.asyncio
async def test_fetch_merges_and_dedups_across_calls(mocker: MockerFixture) -> None:
    """Docs from multiple searches are merged, sorted by score, and deduplicated."""

    async def _search(**kwargs: Any) -> dict[str, Any]:
        if kwargs["product_version"] == "4.16":
            return {
                "response": {
                    "docs": [
                        {"chunk": "shared", "doc_id": "d", "score": 60.0},
                        {"chunk": "low", "doc_id": "e", "score": 10.0},
                    ]
                }
            }
        return {
            "response": {
                "docs": [
                    {"chunk": "shared", "doc_id": "d", "score": 60.0},
                    {"chunk": "high", "doc_id": "f", "score": 90.0},
                ]
            }
        }

    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(side_effect=_search)
    )

    okp = OkpFilter.model_validate(
        {"products": [{"product": "ocp", "versions": ["4.16", "4.17"]}]}
    )
    chunks, _ = await _retriever(max_chunks=5).fetch("q", okp=okp)

    # "shared" appears in both searches but is deduplicated; results are score-sorted.
    assert [c.content for c in chunks] == ["high", "shared", "low"]


@pytest.mark.asyncio
async def test_fetch_degrades_on_partial_failure(mocker: MockerFixture) -> None:
    """A failing search is skipped while the others still contribute."""

    async def _search(**kwargs: Any) -> dict[str, Any]:
        if kwargs["product_version"] == "4.16":
            raise RuntimeError("boom")
        return {"response": {"docs": [{"chunk": "ok", "doc_id": "g", "score": 5.0}]}}

    mocker.patch.object(
        _provider, "call_okp_search", mocker.AsyncMock(side_effect=_search)
    )

    okp = OkpFilter.model_validate(
        {"products": [{"product": "ocp", "versions": ["4.16", "4.17"]}]}
    )
    chunks, _ = await _retriever().fetch("q", okp=okp)

    assert [c.content for c in chunks] == ["ok"]


def test_from_configuration_uses_defaults(mocker: MockerFixture) -> None:
    """from_configuration falls back to constant defaults when rhokp_url is unset."""
    okp = mocker.Mock()
    okp.rhokp_url = None
    okp.offline = True
    okp.max_chunks = 7
    config_mock = mocker.Mock()
    config_mock.okp = okp
    mocker.patch.object(_provider, "configuration", config_mock)
    mocker.patch.object(
        _provider,
        "okp_mcp_endpoint_url",
        return_value=urljoin(constants.RH_SERVER_OKP_DEFAULT_URL, "/mcp"),
    )

    retriever = OkpMcpRetriever.from_configuration()

    assert retriever.url == urljoin(constants.RH_SERVER_OKP_DEFAULT_URL, "/mcp")
    assert retriever.doc_base_url == constants.RH_SERVER_OKP_DEFAULT_URL
    assert retriever.tool_name == constants.OKP_MCP_DEFAULT_TOOL_NAME
    assert retriever.max_chunks == 7
    assert retriever.offline is True
    assert retriever.headers is None
    assert retriever.timeout is None


def test_from_configuration_derives_endpoint_from_rhokp_url(
    mocker: MockerFixture,
) -> None:
    """from_configuration derives the endpoint and doc base URL from rhokp_url."""
    okp = mocker.Mock()
    okp.rhokp_url = "http://rhokp:9000"
    okp.offline = False
    okp.max_chunks = 5
    config_mock = mocker.Mock()
    config_mock.okp = okp
    mocker.patch.object(_provider, "configuration", config_mock)
    mocker.patch.object(
        _provider, "okp_mcp_endpoint_url", return_value="http://rhokp:9000/mcp"
    )

    retriever = OkpMcpRetriever.from_configuration()

    assert retriever.url == "http://rhokp:9000/mcp"
    assert retriever.doc_base_url == "http://rhokp:9000"
