"""Step definitions for OKP(Solr) RAG retrieval tests."""

from typing import Any

from behave import given, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import (
    RESPONSE_TOOL_OUTPUT_ITEM_TYPES,
    is_konflux_environment,
)

# ── Response Body Extraction ──


def _get_response_body(context: Context) -> dict[str, Any]:
    """Return the response body dict, handling both JSON and streaming formats."""
    if getattr(context, "use_streaming_response_data", False):
        return context.response_data
    return context.response.json()


# ── Data Extractors ──


def _get_file_search_results(context: Context) -> list[dict[str, Any]]:
    """Extract file_search results from Responses API ``output`` items.

    Query API bodies have no ``output`` array, so this returns an empty list
    there. Use ``_get_rag_chunks`` when either endpoint is possible.
    """
    body = _get_response_body(context)
    results: list[dict[str, Any]] = []
    for item in body.get("output", []):
        if item.get("type") == "file_search_call":
            results.extend(item.get("results") or [])
    return results


def _get_rag_chunks(context: Context) -> list[dict[str, Any]]:
    """Extract RAG chunks from a query or Responses API body.

    Query and streaming_query put chunks on ``rag_chunks``. The Responses API
    has no such field; tool RAG chunks are ``file_search_call.results`` in
    ``output``, so this falls through to ``_get_file_search_results``.
    """
    body = _get_response_body(context)
    if "rag_chunks" in body:
        return body["rag_chunks"]
    return _get_file_search_results(context)


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
        if item.get("type") in RESPONSE_TOOL_OUTPUT_ITEM_TYPES
    ]


# ── Generic Field Accessors ──


def _get_nested_field(item: dict[str, Any], field_path: str) -> Any:
    """Get a field from item, supporting nested access via dot notation.

    Examples:
        _get_nested_field(chunk, "score") -> chunk.get("score")
        _get_nested_field(chunk, "attributes.reference_url")
            -> chunk.get("attributes", {}).get("reference_url")

    Parameters:
        item: Dictionary to extract field from.
        field_path: Field path, using dots for nested access.

    Returns:
        Field value or None if not found.
    """
    keys = field_path.split(".")
    value: Any = item
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


# ── Generic Assertion Helpers ──


def _assert_count_matches(items: list, expected_count: int, item_type: str) -> None:
    """Assert the number of items matches the expected count.

    Parameters:
        items: List of items to check.
        expected_count: Expected number of items.
        item_type: Human-readable item type for error messages.

    Raises:
        AssertionError: If count doesn't match.
    """
    actual_count = len(items)
    assert (
        actual_count == expected_count
    ), f"Expected {expected_count} {item_type}, but found {actual_count}"


def _assert_not_empty(items: list, item_type: str) -> None:
    """Assert the collection is not empty.

    Parameters:
        items: List of items to check.
        item_type: Human-readable item type for error messages.

    Raises:
        AssertionError: If collection is empty.
    """
    assert len(items) > 0, f"{item_type} is empty — no items were found"


def _assert_empty(items: list, item_type: str) -> None:
    """Assert the collection is empty.

    Parameters:
        items: List of items to check.
        item_type: Human-readable item type for error messages.

    Raises:
        AssertionError: If collection is not empty.
    """
    assert len(items) == 0, f"Expected no {item_type}, but found {len(items)}"


def _assert_field_not_empty(
    items: list[dict[str, Any]], field_path: str, item_type: str
) -> None:
    """Assert every item has a non-empty value for the specified field.

    Parameters:
        items: List of items to check.
        field_path: Field path to check (supports dot notation).
        item_type: Human-readable item type for error messages.

    Raises:
        AssertionError: If any item has empty or missing field.
    """
    assert items, f"No {item_type} to check"
    for i, item in enumerate(items):
        value = _get_nested_field(item, field_path)
        assert value is not None and value != "", (
            f"Expected non-empty {field_path} in {item_type}[{i}], "
            f"but found {value!r}"
        )


def _assert_field_contains(
    items: list[dict[str, Any]], field_path: str, substring: str, item_type: str
) -> None:
    """Assert every item's field contains the expected substring (case-insensitive).

    Parameters:
        items: List of items to check.
        field_path: Field path to check (supports dot notation).
        substring: Expected substring.
        item_type: Human-readable item type for error messages.

    Raises:
        AssertionError: If any item's field doesn't contain substring.
    """
    assert items, f"No {item_type} to check"
    for i, item in enumerate(items):
        value = _get_nested_field(item, field_path)
        assert substring.lower() in str(value).lower(), (
            f"Expected {substring!r} in {item_type}[{i}].{field_path}, "
            f"but found {value!r}"
        )


def _assert_field_matches(
    items: list[dict[str, Any]], field_path: str, expected: Any, item_type: str
) -> None:
    """Assert every item's field matches the expected value.

    For fields that might be nested (e.g., source in attributes), checks both
    the direct field and the attributes.field path.

    Parameters:
        items: List of items to check.
        field_path: Field path to check (supports dot notation).
        expected: Expected value.
        item_type: Human-readable item type for error messages.

    Raises:
        AssertionError: If any item's field doesn't match expected value.
    """
    assert items, f"No {item_type} to check"
    for i, item in enumerate(items):
        actual = _get_nested_field(item, field_path)
        # Fallback: check if field exists in attributes
        if actual is None and "." not in field_path:
            actual = _get_nested_field(item, f"attributes.{field_path}")
        assert actual == expected, (
            f"Expected {field_path}={expected!r} in {item_type}[{i}], "
            f"but found {actual!r}"
        )


def _assert_has_fields(
    items: list[dict[str, Any]], required_fields: set[str], item_type: str
) -> None:
    """Assert every item has all required fields.

    Parameters:
        items: List of items to check.
        required_fields: Set of required field names.
        item_type: Human-readable item type for error messages.

    Raises:
        AssertionError: If any item is missing required fields.
    """
    assert items, f"No {item_type} to check"
    for i, item in enumerate(items):
        missing = required_fields - set(item.keys())
        assert not missing, (
            f"Expected fields {required_fields} in {item_type}[{i}], "
            f"but missing {missing}. Available fields: {list(item.keys())}"
        )


# ── Given steps ──


@given("OKP(Solr) server is running")
def okp_server_is_running(context: Context) -> None:
    """Verify Solr is reachable from the OGX pod (Konflux in-cluster Service)."""
    if not is_konflux_environment():
        raise RuntimeError(
            "OKP Solr health check is only supported in Konflux "
            "(in-cluster GET via e2e-ops check-okp-solr-from-llama)."
        )

    from tests.e2e.utils.prow_utils import assert_okp_reachable_from_ogx

    assert_okp_reachable_from_ogx()


@given("The OKP(Solr) server is stopped")
def okp_server_is_stopped(context: Context) -> None:
    """Stop the OKP Solr pod to simulate unavailability (Konflux only)."""
    context.okp_was_running = False

    if not is_konflux_environment():
        raise RuntimeError(
            "Stopping OKP Solr is only supported in Konflux "
            "(pod disruption via e2e-ops disrupt-okp-solr)."
        )

    from tests.e2e.utils.prow_utils import disrupt_okp_solr_pod

    was_running = disrupt_okp_solr_pod()
    if was_running:
        context.okp_was_running = True
        print("✓ OKP Solr pod disrupted in Konflux environment")
    else:
        print("✓ OKP Solr pod was not running")


# ── Then Steps: rag_chunks Assertions ──


@then("The number of rag_chunk returned is {count:d}")
def check_rag_chunk_count(context: Context, count: int) -> None:
    """Assert the number of rag_chunks matches the expected count."""
    chunks = _get_rag_chunks(context)
    _assert_count_matches(chunks, count, "rag_chunks")


@then("Each rag_chunk has a non-empty score")
def check_rag_chunk_scores(context: Context) -> None:
    """Assert every rag_chunk has a non-empty score."""
    chunks = _get_rag_chunks(context)
    _assert_field_not_empty(chunks, "score", "rag_chunks")


@then('Each rag_chunk source is "{source}"')
def check_rag_chunk_source(context: Context, source: str) -> None:
    """Assert every rag_chunk has the expected source."""
    chunks = _get_rag_chunks(context)
    _assert_field_matches(chunks, "source", source, "rag_chunks")


@then('Each rag_chunk reference_url contains "{domain}"')
def check_rag_chunk_reference_url(context: Context, domain: str) -> None:
    """Assert every rag_chunk's reference_url contains the expected domain."""
    chunks = _get_rag_chunks(context)
    # Check both possible field paths for reference_url
    assert chunks, "No rag_chunks to check"
    for i, chunk in enumerate(chunks):
        attrs = chunk.get("attributes") or {}
        ref_url = attrs.get("reference_url") or attrs.get("doc_url") or ""
        assert domain in str(ref_url), (
            f"Expected {domain!r} in rag_chunks[{i}].attributes.reference_url, "
            f"but found {ref_url!r}"
        )


# ── Then Steps: referenced_documents Assertions ──


@then("Each referenced_document has fields doc_url, doc_title, source, and document_id")
def check_referenced_document_fields(context: Context) -> None:
    """Assert every referenced_document has the required fields."""
    docs = _get_referenced_documents(context)
    required_fields = {"doc_url", "doc_title", "source", "document_id"}
    _assert_has_fields(docs, required_fields, "referenced_documents")


@then('Each referenced_document doc_url contains "{domain}"')
def check_referenced_document_doc_url(context: Context, domain: str) -> None:
    """Assert every referenced_document doc_url contains the expected domain."""
    docs = _get_referenced_documents(context)
    _assert_field_contains(docs, "doc_url", domain, "referenced_documents")


@then("Each referenced_document doc_title is not empty")
def check_referenced_document_doc_title(context: Context) -> None:
    """Assert every referenced_document has a non-empty doc_title."""
    docs = _get_referenced_documents(context)
    _assert_field_not_empty(docs, "doc_title", "referenced_documents")


@then('Each referenced_document doc_title contains "{substring}"')
def check_referenced_document_doc_title_contains(
    context: Context, substring: str
) -> None:
    """Assert every referenced_document doc_title contains the expected substring.

    Matching is case-insensitive.
    """
    docs = _get_referenced_documents(context)
    _assert_field_contains(docs, "doc_title", substring, "referenced_documents")


@then("The number of referenced_document returned is {count:d}")
def check_referenced_document_count(context: Context, count: int) -> None:
    """Assert the number of referenced_documents matches the expected count."""
    docs = _get_referenced_documents(context)
    _assert_count_matches(docs, count, "referenced_documents")


@then('Each referenced_document source is "{source}"')
def check_referenced_document_source(context: Context, source: str) -> None:
    """Assert every referenced_document has the expected source."""
    docs = _get_referenced_documents(context)
    _assert_field_matches(docs, "source", source, "referenced_documents")


@then("Each referenced_document has a non-empty document_id")
def check_referenced_document_id(context: Context) -> None:
    """Assert every referenced_document has a non-empty document_id."""
    docs = _get_referenced_documents(context)
    _assert_field_not_empty(docs, "document_id", "referenced_documents")


# ── Then Steps: tool_calls Assertions ──


@then("The response contains non-empty tool_calls")
def check_tool_calls_present(context: Context) -> None:
    """Assert the response contains at least one tool call."""
    tool_calls = _get_tool_calls(context)
    _assert_not_empty(tool_calls, "tool_calls")


@then('A tool_call has name "{name}"')
def check_tool_call_name(context: Context, name: str) -> None:
    """Assert at least one tool call has the expected name."""
    tool_calls = _get_tool_calls(context)
    assert tool_calls, "No tool_calls to check"
    names = [tc.get("name") for tc in tool_calls]
    assert name in names, (
        f"Expected tool_call with name {name!r}, " f"but found names {names!r}"
    )


# ── Then Steps: Content and Results Assertions ──


@then("The response contains non-empty results")
def check_results_present(context: Context) -> None:
    """Assert the Responses API output contains non-empty file_search results."""
    results = _get_file_search_results(context)
    _assert_not_empty(results, "file_search results")


@then("The number of results returned is {count:d}")
def check_results_count(context: Context, count: int) -> None:
    """Assert the number of file_search results matches the expected count."""
    results = _get_file_search_results(context)
    _assert_count_matches(results, count, "file_search results")


# ── Then Steps: Empty Response Assertions ──


@then("The response contains no rag_chunks")
def check_no_rag_chunks(context: Context) -> None:
    """Assert the response has no rag_chunks (empty or absent)."""
    body = _get_response_body(context)
    chunks = body.get("rag_chunks", [])
    _assert_empty(chunks, "rag_chunks")


@then("The response contains no referenced_documents")
def check_no_referenced_documents(context: Context) -> None:
    """Assert the response has no referenced_documents (empty or absent)."""
    body = _get_response_body(context)
    docs = body.get("referenced_documents", [])
    _assert_empty(docs, "referenced_documents")
