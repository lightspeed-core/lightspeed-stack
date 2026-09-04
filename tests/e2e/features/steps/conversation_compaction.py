"""Step definitions for the conversation-compaction e2e feature (LCORE-2230).

Everything here observes compaction from outside the deployed stack — the
``context_status`` field on responses, the ``compaction`` event on the native
stream, and the conversation history the Conversations API serves. Steps
never import from or execute anything under ``src/``
(``docs/testing/e2e_testing.md``, "Choosing the Test Layer"); the internals
(buffer, additive summaries, blocking) are integration tests (LCORE-1574).
"""

import json
from typing import Any, Optional

from behave import then  # pyright: ignore
from behave.runner import Context


def _sse_events(response_text: str) -> list[dict[str, Any]]:
    """Return the decoded SSE ``data:`` payloads of a streamed response, in order."""
    events: list[dict[str, Any]] = []
    for line in response_text.strip().split("\n"):
        if not line.startswith("data: "):
            continue
        try:
            events.append(json.loads(line[6:]))
        except json.JSONDecodeError:
            continue  # Skip malformed lines
    return events


def _first_index(events: list[dict[str, Any]], name: str) -> Optional[int]:
    """Return the position of the first event called ``name``, or None."""
    return next((i for i, e in enumerate(events) if e.get("event") == name), None)


@then('The response context_status is "{status}"')
def check_context_status(context: Context, status: str) -> None:
    """Assert the non-streaming response reports the expected ``context_status`` (R7)."""
    assert context.response is not None, "Request needs to be performed first"
    response_json = context.response.json()
    assert (
        "context_status" in response_json
    ), f"context_status missing from response; keys: {list(response_json)}"
    actual = response_json["context_status"]
    assert actual == status, f"context_status is {actual!r}, expected {status!r}"


@then("The conversation history includes the following user queries")
def check_history_includes_user_queries(context: Context) -> None:
    """Assert every listed query is still a user message in the conversation (R6).

    Reads ``chat_history`` from the GET conversation response and collects the
    content of every ``user``-typed message across all turns; each row of the
    scenario's "User query" table must appear among them verbatim.
    """
    assert context.response is not None, "Request needs to be performed first"
    assert context.table is not None, "Table with column 'User query' is required"
    response_json = context.response.json()
    assert "chat_history" in response_json, "chat_history not found in response"
    user_queries = [
        message["content"].strip()
        for turn in response_json["chat_history"]
        for message in turn.get("messages", [])
        if message.get("type") == "user"
    ]
    for row in context.table:
        expected = row["User query"].strip()
        assert expected in user_queries, (
            f"user query {expected!r} not found in conversation history; "
            f"user queries present: {user_queries!r}"
        )


@then("The streamed response contains a compaction event before the first token")
def check_compaction_event_precedes_tokens(context: Context) -> None:
    """Assert the stream announced compaction before any answer token (R12)."""
    assert context.response is not None, "Request needs to be performed first"
    events = _sse_events(context.response.text)
    names = [e.get("event") for e in events]
    compaction_at = _first_index(events, "compaction")
    assert compaction_at is not None, f"no compaction event in stream; events: {names}"
    token_at = _first_index(events, "token")
    assert token_at is None or compaction_at < token_at, (
        f"compaction event at position {compaction_at} came after the first "
        f"token at {token_at}; events: {names}"
    )


@then('The streamed response end event has context_status "{status}"')
def check_end_event_context_status(context: Context, status: str) -> None:
    """Assert the stream's ``end`` event payload carries the expected ``context_status`` (R7)."""
    assert context.response is not None, "Request needs to be performed first"
    events = _sse_events(context.response.text)
    end_at = _first_index(events, "end")
    assert (
        end_at is not None
    ), f"no end event in stream; events: {[e.get('event') for e in events]}"
    data = events[end_at].get("data") or {}
    assert "context_status" in data, f"end event carries no context_status: {data!r}"
    actual = data["context_status"]
    assert (
        actual == status
    ), f"end event context_status is {actual!r}, expected {status!r}"
