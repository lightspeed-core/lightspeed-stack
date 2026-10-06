"""Behave steps for A2A protocol e2e flows.

Drives LCS as an A2A server: fetch the agent card, send
``message/send``/``message/stream`` to ``/a2a``, and assert on the
client-visible task, context id, and artifact text.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from typing import Any, Optional

import requests
from behave import step, then, when  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import (
    normalize_endpoint,
    replace_placeholders,
    request_with_transient_retry,
)

DEFAULT_LLM_TIMEOUT = 180 if os.getenv("RUNNING_PROW") else 120
MAX_STREAM_BYTES = 10 * 1024 * 1024  
MAX_STREAM_EVENTS = 2000  
MAX_DIAGNOSTIC_EXCERPT_BYTES = 4096 

def _auth_headers(context: Context) -> dict[str, str]:
    """Return Authorization headers stored on the Behave context, if any."""
    headers = getattr(context, "auth_headers", None)
    return dict(headers) if headers else {}


def _service_url(context: Context, endpoint: str) -> str:
    """Build an absolute URL for an LCS path (not under /v1)."""
    path = normalize_endpoint(endpoint)
    return f"http://{context.hostname}:{context.port}{path}"


def _field(data: Mapping[str, Any], *names: str) -> Any:
    """Return the first present key from *names* (camelCase or snake_case)."""
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
    return None


def _consume_sse_jsonrpc_stream(
    response: requests.Response,
) -> tuple[list[dict[str, Any]], bytes, Optional[Any]]:
    """Incrementally read and decode an A2A JSON-RPC SSE stream.

    Lines are processed one at a time instead of being buffered into a full
    response body: each line is inspected for a ``data:`` payload, decoded,
    and either discarded or appended to the (bounded) results list. Only a
    small, bounded excerpt of the raw stream is retained, for use in failure
    messages, instead of a full copy of the body.

    A premature close after an error event is tolerated (the server may
    terminate the connection right after sending an error). To guard against
    an unexpectedly large or runaway stream, both the total bytes read and
    the number of parsed result events are capped; exceeding either limit
    fails the test instead of growing memory without bound.

    Returns:
        A tuple of (parsed JSON-RPC ``result`` objects, bounded diagnostic
        excerpt of the raw stream, first JSON-RPC ``error`` object seen, if
        any). The caller decides whether/when to raise on that error.
    """
    results: list[dict[str, Any]] = []
    excerpt = bytearray()
    first_error: Optional[Any] = None
    total_bytes = 0
    encoding = response.encoding or "utf-8"
    try:
        for line in response.iter_lines(decode_unicode=True):
            if line is None:
                continue
            line_bytes = line.encode(encoding)
            total_bytes += len(line_bytes) + 1
            assert total_bytes <= MAX_STREAM_BYTES, (
                f"A2A SSE stream exceeded {MAX_STREAM_BYTES} bytes "
                "without completing"
            )
            if len(excerpt) < MAX_DIAGNOSTIC_EXCERPT_BYTES:
                remaining = MAX_DIAGNOSTIC_EXCERPT_BYTES - len(excerpt)
                excerpt.extend(line_bytes[:remaining])
                excerpt.extend(b"\n")

            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            payload = stripped[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                envelope = json.loads(payload)
            except json.JSONDecodeError:
                continue
            error = envelope.get("error")
            if error and first_error is None:
                first_error = error
            result = envelope.get("result")
            if isinstance(result, dict):
                assert len(results) < MAX_STREAM_EVENTS, (
                    f"A2A SSE stream exceeded {MAX_STREAM_EVENTS} JSON-RPC "
                    "result events without completing"
                )
                results.append(result)
    except requests.exceptions.ChunkedEncodingError:
        pass
    return results, bytes(excerpt), first_error


def _parts_text(parts: Any) -> str:
    """Join text from A2A message/artifact parts."""
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return "".join(chunks)


def _artifacts_text(artifacts: Any) -> str:
    """Join all text parts from a list of A2A artifacts."""
    if not isinstance(artifacts, list):
        return ""
    chunks: list[str] = []
    for artifact in artifacts:
        if isinstance(artifact, dict):
            chunks.append(_parts_text(artifact.get("parts")))
    return "".join(chunks)


def _task_state(result: Mapping[str, Any]) -> str:
    """Return the A2A task status.state string, or empty if missing."""
    status = result.get("status")
    if isinstance(status, dict):
        state = status.get("state")
        return str(state) if state is not None else ""
    return ""


def _context_id(result: Mapping[str, Any]) -> str:
    """Return contextId / context_id from an A2A result object."""
    value = _field(result, "contextId", "context_id")
    return str(value) if value else ""


def _artifact_text_from_result(result: Mapping[str, Any]) -> str:
    """Extract assistant text from a completed task or a message result."""
    artifacts = result.get("artifacts")
    text = _artifacts_text(artifacts)
    if text:
        return text
    status = result.get("status")
    if isinstance(status, dict):
        message = status.get("message")
        if isinstance(message, dict):
            text = _parts_text(message.get("parts"))
            if text:
                return text
    parts = result.get("parts")
    return _parts_text(parts)


def _synthesize_result_from_stream(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a task-like dict from streamed A2A events for shared assertions."""
    context_id = ""
    artifacts: list[dict[str, Any]] = []
    state = ""
    for event in events:
        event_context = _context_id(event)
        if event_context:
            context_id = event_context
        kind = event.get("kind")
        if kind == "task":
            state = _task_state(event) or state
            nested = event.get("artifacts")
            if isinstance(nested, list):
                artifacts.extend(item for item in nested if isinstance(item, dict))
        elif kind == "status-update":
            state = _task_state(event) or state
        elif kind == "artifact-update":
            artifact = event.get("artifact")
            if isinstance(artifact, dict):
                artifacts.append(artifact)
    return {
        "contextId": context_id,
        "kind": "task",
        "status": {"state": state},
        "artifacts": artifacts,
    }


def _require_a2a_result(context: Context) -> dict[str, Any]:
    """Return the last parsed A2A result, failing if none is stored."""
    result = getattr(context, "a2a_result", None)
    assert result is not None, "Send an A2A request before asserting on the result"
    assert isinstance(result, dict), f"A2A result is not an object: {result!r}"
    return result


def _require_a2a_events(context: Context) -> list[dict[str, Any]]:
    """Return parsed stream events, failing if the last call was not a stream."""
    events = getattr(context, "a2a_events", None)
    assert events is not None, "Send an A2A message/stream request first"
    assert events, f"A2A stream had no JSON-RPC result events: {context.response.text}"
    return events


def _build_jsonrpc_payload(
    context: Context,
    method: str,
    user_text: str,
    context_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a message/send or message/stream JSON-RPC body with model metadata."""
    message: dict[str, Any] = {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": user_text.strip()}],
        "metadata": {
            "model": "{MODEL}",
            "provider": "{PROVIDER}",
        },
    }
    if context_id:
        message["contextId"] = context_id
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": {"message": message},
    }
    return json.loads(replace_placeholders(context, json.dumps(payload)))


def _store_jsonrpc_response(context: Context, body: Mapping[str, Any]) -> None:
    """Parse a non-streaming JSON-RPC response into context.a2a_result."""
    error = body.get("error")
    assert not error, f"A2A JSON-RPC error: {error}"
    result = body.get("result")
    assert isinstance(result, dict), f"A2A result missing or not an object: {body}"
    context.a2a_result = result
    context.a2a_events = None


def _should_parse_response(response: requests.Response) -> bool:
    """Return False for HTTP error responses, which aren't JSON-RPC envelopes."""
    return response.status_code < 400


def _post_a2a(
    context: Context,
    method: str,
    user_text: str,
    *,
    stream: bool,
    context_id: Optional[str] = None,
) -> None:
    """POST /a2a and store the parsed A2A result on the Behave context."""
    url = _service_url(context, "/a2a")
    context.a2a_result = None
    context.a2a_events = None
    payload = _build_jsonrpc_payload(context, method, user_text, context_id)
    headers = _auth_headers(context)
    headers["Content-Type"] = "application/json"
    if stream:
        headers["Accept"] = "text/event-stream"
        resp = request_with_transient_retry(
            method="POST",
            url=url,
            json=payload,
            headers=headers,
            timeout=DEFAULT_LLM_TIMEOUT,
            stream=True,
        )
        events, excerpt, error = _consume_sse_jsonrpc_stream(resp)
        resp._content = excerpt
        context.response = resp
        if not _should_parse_response(resp):
            return
        assert not error, f"A2A JSON-RPC stream error: {error}"
        context.a2a_events = events
        context.a2a_result = _synthesize_result_from_stream(events)
        return

    context.response = request_with_transient_retry(
        method="POST",
        url=url,
        json=payload,
        headers=headers,
        timeout=DEFAULT_LLM_TIMEOUT,
    )
    if not _should_parse_response(context.response):
        return

    try:
        body = context.response.json()
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"A2A response is not JSON: {context.response.text}"
        ) from exc
    assert isinstance(body, dict), f"A2A JSON-RPC envelope is not an object: {body}"
    _store_jsonrpc_response(context, body)


@when('I fetch the A2A agent card from "{endpoint}"')
def fetch_a2a_agent_card(context: Context, endpoint: str) -> None:
    """GET the well-known A2A agent card, sending the scenario Authorization header."""
    url = _service_url(context, endpoint)
    context.response = request_with_transient_retry(
        method="GET",
        url=url,
        headers=_auth_headers(context),
        timeout=10,
    )


@when('I send an A2A "{method}" request')
def send_a2a_message(context: Context, method: str) -> None:
    """Send a new A2A message (no previous contextId) using the docstring text."""
    assert context.text is not None, "A2A user message text is required"
    stream = method == "message/stream"
    _post_a2a(context, method, context.text, stream=stream)


@when('I send an A2A "{method}" follow-up request')
def send_a2a_follow_up(context: Context, method: str) -> None:
    """Send an A2A message using the stored contextId inside the message object."""
    assert context.text is not None, "A2A user message text is required"
    context_id = getattr(context, "a2a_context_id", None)
    assert context_id, "Store the A2A context id before sending a follow-up"
    stream = method == "message/stream"
    _post_a2a(context, method, context.text, stream=stream, context_id=context_id)


@then('The A2A agent card name is "{name}"')
def assert_agent_card_name(context: Context, name: str) -> None:
    """Assert the agent card ``name`` matches the configured value."""
    assert context.response is not None, "Fetch the agent card first"
    card = context.response.json()
    actual = _field(card, "name")
    assert actual == name, f"Agent card name is {actual!r}, expected {name!r}"


@then('The A2A agent card url ends with "{suffix}"')
def assert_agent_card_url_suffix(context: Context, suffix: str) -> None:
    """Assert the advertised JSON-RPC URL ends with the A2A path."""
    assert context.response is not None, "Fetch the agent card first"
    card = context.response.json()
    url = str(_field(card, "url") or "")
    assert url.endswith(suffix), f"Agent card url {url!r} does not end with {suffix!r}"


@then("The A2A agent card advertises streaming")
def assert_agent_card_streaming(context: Context) -> None:
    """Assert capabilities.streaming is true on the agent card."""
    assert context.response is not None, "Fetch the agent card first"
    card = context.response.json()
    capabilities = card.get("capabilities") or {}
    streaming = capabilities.get("streaming")
    assert streaming is True, f"Agent card streaming is {streaming!r}, expected true"


@then('The A2A agent card lists skill "{skill_id}"')
def assert_agent_card_skill(context: Context, skill_id: str) -> None:
    """Assert the agent card skills list includes the given skill id."""
    assert context.response is not None, "Fetch the agent card first"
    card = context.response.json()
    skills = card.get("skills") or []
    ids = [_field(skill, "id") for skill in skills if isinstance(skill, dict)]
    assert skill_id in ids, f"Skill {skill_id!r} not in agent card skills {ids!r}"


@then('The A2A task state is "{state}"')
def assert_a2a_task_state(context: Context, state: str) -> None:
    """Assert the completed A2A task (or synthesized stream result) is in *state*."""
    result = _require_a2a_result(context)
    actual = _task_state(result)
    assert (
        actual == state
    ), f"A2A task state is {actual!r}, expected {state!r}. Result: {result}"


@then('The A2A artifact text contains "{fragment}"')
def assert_a2a_artifact_contains(context: Context, fragment: str) -> None:
    """Assert the A2A artifact/message text contains *fragment* (case-insensitive)."""
    result = _require_a2a_result(context)
    text = _artifact_text_from_result(result)
    assert text, f"A2A artifact text is empty. Result: {result}"
    assert (
        fragment.lower() in text.lower()
    ), f"A2A artifact text {text!r} does not contain {fragment!r}"


@step("I store the A2A context id")
def store_a2a_context_id(context: Context) -> None:
    """Save contextId from the last A2A result for a follow-up turn."""
    result = _require_a2a_result(context)
    context_id = _context_id(result)
    assert context_id, f"A2A result has no contextId: {result}"
    context.a2a_context_id = context_id


@then("The A2A context id is unchanged")
def assert_a2a_context_id_unchanged(context: Context) -> None:
    """Assert the latest result reuses the stored multi-turn contextId."""
    expected = getattr(context, "a2a_context_id", None)
    assert expected, "Store the A2A context id before asserting it is unchanged"
    actual = _context_id(_require_a2a_result(context))
    assert (
        actual == expected
    ), f"A2A contextId changed: stored {expected!r}, got {actual!r}"


@then("The A2A stream contains a submitted task")
def assert_a2a_stream_submitted(context: Context) -> None:
    """Assert the SSE stream included a task in submitted state (or kind=task)."""
    events = _require_a2a_events(context)
    for event in events:
        if event.get("kind") == "task":
            state = _task_state(event)
            if state in ("", "submitted", "working"):
                return
        if event.get("kind") == "status-update" and _task_state(event) == "submitted":
            return
    raise AssertionError(f"A2A stream has no submitted task event: {events}")


@then("The A2A stream contains working status updates")
def assert_a2a_stream_working(context: Context) -> None:
    """Assert at least one status-update event is in working state."""
    events = _require_a2a_events(context)
    for event in events:
        if event.get("kind") == "status-update" and _task_state(event) == "working":
            return
    raise AssertionError(f"A2A stream has no working status-update: {events}")


@then("The A2A stream ends with a completed task")
def assert_a2a_stream_completed(context: Context) -> None:
    """Assert a final completed status-update appears on the stream."""
    events = _require_a2a_events(context)
    completed = False
    for event in events:
        if _task_state(event) != "completed":
            continue
        final = event.get("final")
        if event.get("kind") == "status-update" and final is True:
            completed = True
        if event.get("kind") == "task":
            completed = True
    assert completed, f"A2A stream did not complete: {events}"
    actual = _task_state(_require_a2a_result(context))
    assert actual == "completed", f"Synthesized stream state is {actual!r}"
