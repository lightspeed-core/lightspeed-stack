"""Step definitions for OKP(Solr) RAG retrieval tests."""

import os
import subprocess
import time
from typing import Any

import requests
from behave import given, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

# OKP/Solr Docker container name
OKP_CONTAINER_NAME = os.getenv("E2E_OKP_CONTAINER", "okp-solr")

# Default OKP health check URL
OKP_DEFAULT_URL = os.getenv("E2E_OKP_URL", "http://localhost:8081")

# Output item types that represent tool invocations
_TOOL_OUTPUT_TYPES = frozenset(
    {
        "file_search_call",
        "function_call",
        "mcp_call",
        "web_search_call",
        "mcp_list_tools",
    }
)


def _get_response_body(context: Context) -> dict[str, Any]:
    """Return the response body dict, handling both JSON and streaming formats."""
    if getattr(context, "use_streaming_response_data", False):
        return context.response_data
    return context.response.json()


def _get_rag_chunks(context: Context) -> list[dict[str, Any]]:
    """Extract rag_chunks from query response or results from Responses API output."""
    body = _get_response_body(context)
    if "rag_chunks" in body:
        return body["rag_chunks"]
    # Responses API: collect results from file_search_call output items
    results: list[dict[str, Any]] = []
    for item in body.get("output", []):
        if item.get("type") == "file_search_call":
            results.extend(item.get("results") or [])
    return results


def _get_referenced_documents(context: Context) -> list[dict[str, Any]]:
    """Extract referenced_documents from response body."""
    body = _get_response_body(context)
    return body.get("referenced_documents", [])


def _get_tool_calls(context: Context) -> list[dict[str, Any]]:
    """Extract tool calls from query response or output items from Responses API."""
    body = _get_response_body(context)
    if "tool_calls" in body:
        return body["tool_calls"]
    # Responses API: extract tool-type items from output
    return [
        item
        for item in body.get("output", [])
        if item.get("type") in _TOOL_OUTPUT_TYPES
    ]


def _get_file_search_results(context: Context) -> list[dict[str, Any]]:
    """Extract file_search results from Responses API output items."""
    body = _get_response_body(context)
    results: list[dict[str, Any]] = []
    for item in body.get("output", []):
        if item.get("type") == "file_search_call":
            results.extend(item.get("results") or [])
    return results


# ── Given steps ──


@given("OKP(Solr) server is running")
def okp_server_is_running(context: Context) -> None:
    """Verify that the OKP(Solr) server is reachable."""
    url = OKP_DEFAULT_URL
    try:
        resp = requests.get(url, timeout=10)
        assert (
            resp.status_code < 500
        ), f"OKP server at {url} returned status {resp.status_code}"
    except requests.ConnectionError as exc:
        assert False, f"OKP(Solr) server is not reachable at {url}: {exc}"


@given("The OKP(Solr) server is stopped")
def okp_server_is_stopped(context: Context) -> None:
    """Stop the OKP(Solr) Docker container to simulate unavailability."""
    context.okp_was_running = False
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", OKP_CONTAINER_NAME],
            capture_output=True,
            text=True,
            check=True,
        )
        if "true" in result.stdout.lower():
            context.okp_was_running = True
            subprocess.run(
                ["docker", "stop", OKP_CONTAINER_NAME],
                capture_output=True,
                text=True,
                check=True,
            )
            time.sleep(2)
    except subprocess.CalledProcessError as exc:
        print(f"Warning: could not stop OKP container: {exc}")


# ── Then steps: rag_chunk assertions ──


@then("The number of rag_chunk returned is {count:d}")
def check_rag_chunk_count(context: Context, count: int) -> None:
    """Assert the number of rag_chunks matches the expected count."""
    chunks = _get_rag_chunks(context)
    assert len(chunks) == count, f"Expected {count} rag_chunks, got {len(chunks)}"


@then("Each rag_chunk has a non-empty score")
def check_rag_chunk_scores(context: Context) -> None:
    """Assert every rag_chunk has a non-empty score."""
    chunks = _get_rag_chunks(context)
    assert chunks, "No rag_chunks to check"
    for i, chunk in enumerate(chunks):
        score = chunk.get("score")
        assert score is not None, f"rag_chunk[{i}] has no score"


@then('Each rag_chunk source is "{source}"')
def check_rag_chunk_source(context: Context, source: str) -> None:
    """Assert every rag_chunk has the expected source."""
    chunks = _get_rag_chunks(context)
    assert chunks, "No rag_chunks to check"
    for i, chunk in enumerate(chunks):
        actual = chunk.get("source")
        if actual is None:
            attrs = chunk.get("attributes") or {}
            actual = attrs.get("source")
        assert (
            actual == source
        ), f"rag_chunk[{i}] source is {actual!r}, expected {source!r}"


@then('Each rag_chunk reference_url contains "{domain}"')
def check_rag_chunk_reference_url(context: Context, domain: str) -> None:
    """Assert every rag_chunk's reference_url contains the expected domain."""
    chunks = _get_rag_chunks(context)
    assert chunks, "No rag_chunks to check"
    for i, chunk in enumerate(chunks):
        attrs = chunk.get("attributes") or {}
        ref_url = attrs.get("reference_url") or attrs.get("doc_url") or ""
        assert domain in str(
            ref_url
        ), f"rag_chunk[{i}] reference_url {ref_url!r} does not contain {domain!r}"


# ── Then steps: referenced_document assertions ──


@then("Each referenced_document has fields doc_url, doc_title, source, and document_id")
def check_referenced_document_fields(context: Context) -> None:
    """Assert every referenced_document has the required fields."""
    docs = _get_referenced_documents(context)
    assert docs, "No referenced_documents to check"
    required = {"doc_url", "doc_title", "source", "document_id"}
    for i, doc in enumerate(docs):
        missing = required - set(doc.keys())
        assert not missing, (
            f"referenced_document[{i}] missing fields: {missing}. "
            f"Available: {list(doc.keys())}"
        )


@then('Each referenced_document doc_url contains "{domain}"')
def check_referenced_document_doc_url(context: Context, domain: str) -> None:
    """Assert every referenced_document doc_url contains the expected domain."""
    docs = _get_referenced_documents(context)
    assert docs, "No referenced_documents to check"
    for i, doc in enumerate(docs):
        doc_url = str(doc.get("doc_url", ""))
        assert (
            domain in doc_url
        ), f"referenced_document[{i}] doc_url {doc_url!r} does not contain {domain!r}"


@then("Each referenced_document doc_title is not empty")
def check_referenced_document_doc_title(context: Context) -> None:
    """Assert every referenced_document has a non-empty doc_title."""
    docs = _get_referenced_documents(context)
    assert docs, "No referenced_documents to check"
    for i, doc in enumerate(docs):
        title = doc.get("doc_title")
        assert title, f"referenced_document[{i}] has empty or missing doc_title"


@then('Each referenced_document source is "{source}"')
def check_referenced_document_source(context: Context, source: str) -> None:
    """Assert every referenced_document has the expected source."""
    docs = _get_referenced_documents(context)
    assert docs, "No referenced_documents to check"
    for i, doc in enumerate(docs):
        actual = doc.get("source")
        assert (
            actual == source
        ), f"referenced_document[{i}] source is {actual!r}, expected {source!r}"


@then("Each referenced_document has a non-empty document_id")
def check_referenced_document_id(context: Context) -> None:
    """Assert every referenced_document has a non-empty document_id."""
    docs = _get_referenced_documents(context)
    assert docs, "No referenced_documents to check"
    for i, doc in enumerate(docs):
        doc_id = doc.get("document_id")
        assert doc_id, f"referenced_document[{i}] has empty or missing document_id"


# ── Then steps: tool_calls assertions ──


@then("The response contains non-empty tool_calls")
def check_tool_calls_present(context: Context) -> None:
    """Assert the response contains at least one tool call."""
    tool_calls = _get_tool_calls(context)
    assert len(tool_calls) > 0, "tool_calls is empty — no tool calls were made"


@then('A tool_call has name "{name}"')
def check_tool_call_name(context: Context, name: str) -> None:
    """Assert at least one tool call has the expected name."""
    tool_calls = _get_tool_calls(context)
    assert tool_calls, "No tool_calls to check"
    names = [tc.get("name") for tc in tool_calls]
    assert (
        name in names
    ), f"No tool_call with name {name!r} found. Available names: {names!r}"


@then('A tool_call has type "{type_name}"')
def check_tool_call_type(context: Context, type_name: str) -> None:
    """Assert at least one tool call has the expected type."""
    tool_calls = _get_tool_calls(context)
    assert tool_calls, "No tool_calls to check"
    types = [tc.get("type") for tc in tool_calls]
    matched = any(t in {type_name, f"{type_name}_call"} for t in types)
    assert (
        matched
    ), f"No tool_call with type {type_name!r} found. Available types: {types!r}"


# ── Then steps: content and results assertions ──


@then("The response contains non-empty content")
def check_response_content_present(context: Context) -> None:
    """Assert the response contains non-empty content text."""
    body = _get_response_body(context)
    if "response" in body:
        content = body["response"]
    elif "output_text" in body:
        content = body["output_text"]
    else:
        content = body.get("response_complete", "")
    assert content, "Response content is empty"


@then("The response contains non-empty results")
def check_results_present(context: Context) -> None:
    """Assert the Responses API output contains non-empty file_search results."""
    results = _get_file_search_results(context)
    assert len(results) > 0, "No file_search results found in response output"


@then("The number of results returned is {count:d}")
def check_results_count(context: Context, count: int) -> None:
    """Assert the number of file_search results matches the expected count."""
    results = _get_file_search_results(context)
    assert len(results) == count, f"Expected {count} results, got {len(results)}"


# ── Then steps: empty response assertions ──


@then("The response contains no rag_chunks")
def check_no_rag_chunks(context: Context) -> None:
    """Assert the response has no rag_chunks (empty or absent)."""
    body = _get_response_body(context)
    chunks = body.get("rag_chunks", [])
    assert len(chunks) == 0, f"Expected no rag_chunks, got {len(chunks)}"


@then("The response contains no referenced_documents")
def check_no_referenced_documents(context: Context) -> None:
    """Assert the response has no referenced_documents (empty or absent)."""
    body = _get_response_body(context)
    docs = body.get("referenced_documents", [])
    assert len(docs) == 0, f"Expected no referenced_documents, got {len(docs)}"
