"""Step definitions for the conversation-compaction e2e feature (LCORE-2230).

Everything here observes compaction from outside the deployed stack — the
``context_status`` field on responses, the ``compaction`` event on the native
stream, and the conversation history the Conversations API serves. Steps
never import from or execute anything under ``src/``
(``docs/testing/e2e_testing.md``, "Choosing the Test Layer"); the internals
(buffer, additive summaries, blocking) are integration tests (LCORE-1574).
"""

import json
import os
from typing import Any, Optional

import yaml
from behave import given, then  # pyright: ignore
from behave.runner import Context

from tests.e2e.utils.utils import absolute_repo_path, is_prow_environment


def _active_fixture_path(context: Context) -> str:
    """Resolve the fixture file the last ``The service uses ...`` step applied.

    Mirrors the lookup in ``common.configure_service``: the configuration
    directory from the Background, the deployment-mode subdirectory when it
    exists, and the basename recorded on the context. The repo-root
    ``lightspeed-stack.yaml`` copy is not used because on Prow the config is
    pushed into a ConfigMap and that file is never written.
    """
    config_name = context.active_lightspeed_stack_config_basename
    mode_dir = "library-mode" if context.is_library_mode else "server-mode"
    raw_base = getattr(context, "lightspeed_stack_config_directory", None)
    base = str(raw_base).strip().rstrip("/") if raw_base else "tests/e2e/configuration"
    mode_base = os.path.join(base, mode_dir)
    if is_prow_environment():
        mode_base = absolute_repo_path(mode_base)
        base = absolute_repo_path(base)
    if os.path.isdir(mode_base):
        return os.path.join(mode_base, config_name)
    return os.path.join(base, config_name)


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


@given("the active model has a registered context window")
def require_context_window_for_active_model(context: Context) -> None:
    """Skip the scenario when the active model has no ``context_windows`` entry.

    The compaction trigger only runs for models listed under
    ``inference.context_windows`` in the active lightspeed-stack.yaml. The
    fixtures list every fixed provider/model pair the e2e workflows use, but
    the vLLM-backed runs (rhaiis, rhelai) take their model id from an env var
    and mapping keys are not env-substituted, so those runs have no entry and
    ``context_status`` can never become ``summarized``. Rather than fail there,
    the scenario is skipped, the same way shield scenarios skip in library mode.

    Reads the fixture source file, never anything under ``src/``. The
    provider/model pair comes from the context, which already reflects the
    ``E2E_DEFAULT_*_OVERRIDE`` values on every path.
    """
    fixture_path = _active_fixture_path(context)
    with open(fixture_path, encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file) or {}
    windows = (config.get("inference") or {}).get("context_windows") or {}
    model_key = f"{context.default_provider}/{context.default_model}"
    if model_key not in windows:
        context.scenario.skip(
            f"no context window registered for {model_key} in {fixture_path}; "
            f"compaction cannot trigger (registered: {sorted(windows)})"
        )


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
