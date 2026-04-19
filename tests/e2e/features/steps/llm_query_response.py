"""LLM query and response steps."""

import json
import os
from typing import Any, cast

import requests
from behave import step, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import replace_placeholders

# Longer timeout for Prow/OpenShift with CPU-based vLLM
DEFAULT_LLM_TIMEOUT = 180 if os.getenv("RUNNING_PROW") else 120

# Responses API ``output`` item types that indicate tool listing or invocation.
_RESPONSE_TOOL_OUTPUT_ITEM_TYPES = frozenset(
    {
        "file_search_call",
        "mcp_call",
        "mcp_list_tools",
        "function_call",
        "web_search_call",
    }
)


def _response_contains_fragment(text: str, fragment: str) -> bool:
    """Return whether *fragment* occurs in *text* as a substring (case-insensitive)."""
    return fragment.lower() in text.lower()


def _collect_output_item_types(response_body: dict[str, Any]) -> list[str]:
    """Collect ``type`` from each top-level ``output`` item in a Responses API JSON body."""
    output = cast(list[dict[str, Any]], response_body["output"])
    return [item["type"] for item in output]


@then("The responses output should not include any tool invocation item types")
def responses_output_should_not_include_tool_items(context: Context) -> None:
    """Assert no tool-related items appear in the Responses JSON ``output`` array."""
    assert context.response is not None, "Request needs to be performed first"
    response_json = cast(dict[str, Any], context.response.json())
    types_found = _collect_output_item_types(response_json)
    bad = [t for t in types_found if t in _RESPONSE_TOOL_OUTPUT_ITEM_TYPES]
    assert not bad, (
        "Expected no tool-related output items, but found types "
        f"{bad!r} among all output types {types_found!r}"
    )


@then('The responses output should include an item with type "{item_type}"')
def responses_output_should_include_item_type(context: Context, item_type: str) -> None:
    """Assert at least one ``output`` item has the given ``type``."""
    assert context.response is not None, "Request needs to be performed first"
    response_json = cast(dict[str, Any], context.response.json())
    types_found = _collect_output_item_types(response_json)
    assert item_type in types_found, (
        f"Expected output item type {item_type!r} not found; "
        f"had types {types_found!r}"
    )


@then('The responses output should not include an item with type "{item_type}"')
def responses_output_should_not_include_item_type(
    context: Context, item_type: str
) -> None:
    """Assert no ``output`` item has the given ``type``."""
    assert context.response is not None, "Request needs to be performed first"
    response_json = cast(dict[str, Any], context.response.json())
    types_found = _collect_output_item_types(response_json)
    assert item_type not in types_found, (
        f"Expected output item type {item_type!r} to be absent; "
        f"but found types {types_found!r}"
    )


@then("The responses output should include an item with one of these types")
def responses_output_should_include_one_of_types(context: Context) -> None:
    """Assert at least one output item type matches a row in the scenario table."""
    assert context.response is not None, "Request needs to be performed first"
    assert context.table is not None, "Table with column 'item type' is required"
    allowed = [row["item type"].strip() for row in context.table]
    response_json = cast(dict[str, Any], context.response.json())
    types_found = _collect_output_item_types(response_json)
    assert any(
        a in types_found for a in allowed
    ), f"Expected at least one of {allowed!r} in output types {types_found!r}"


@step("I wait for the response to be completed")
def wait_for_complete_response(context: Context) -> None:
    """Wait for the response to be complete."""
    context.response_data = _parse_streaming_response(context.response.text)
    context.response.raise_for_status()
    assert context.response_data["finished"] is True


@step('I use "{endpoint}" to ask question')
def ask_question(context: Context, endpoint: str) -> None:
    """Call the service REST API endpoint with question."""
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path

    # Replace {MODEL} and {PROVIDER} placeholders with actual values
    json_str = replace_placeholders(context, context.text or "{}")

    data = json.loads(json_str)
    context.response = requests.post(url, json=data, timeout=DEFAULT_LLM_TIMEOUT)


def _read_streamed_response(response: requests.Response) -> str:
    """Read a streaming response body, tolerating premature close (e.g. after error event)."""
    chunks = []
    try:
        for line in response.iter_lines(decode_unicode=True):
            if line is not None:
                chunks.append(line + "\n")
    except requests.exceptions.ChunkedEncodingError:
        pass  # Server may close stream after sending an error event
    return "".join(chunks)


@step('I use "{endpoint}" to ask question with authorization header')
def ask_question_authorized(context: Context, endpoint: str) -> None:
    """Call the service REST API endpoint with question."""
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path

    # Replace {MODEL} and {PROVIDER} placeholders with actual values
    json_str = replace_placeholders(context, context.text or "{}")

    data = json.loads(json_str)
    use_sse = endpoint == "streaming_query" or (
        endpoint == "responses" and bool(data.get("stream"))
    )
    if use_sse:
        resp = requests.post(
            url,
            json=data,
            headers=context.auth_headers,
            timeout=DEFAULT_LLM_TIMEOUT,
            stream=True,
        )
        # Consume stream so server close after error event does not raise
        body = _read_streamed_response(resp)
        resp._content = body.encode(resp.encoding or "utf-8")
        context.response = resp
    else:
        context.response = requests.post(
            url, json=data, headers=context.auth_headers, timeout=DEFAULT_LLM_TIMEOUT
        )


# Query length chosen to exceed typical model context windows (e.g. 128k tokens)
_TOO_LONG_QUERY_LENGTH = 80_000


@step('I use "{endpoint}" to ask question with too-long query and authorization header')
def ask_question_too_long_authorized(context: Context, endpoint: str) -> None:
    """Call the query endpoint with a query string that exceeds model context (expect 413)."""
    long_query = "what is openshift?" * _TOO_LONG_QUERY_LENGTH
    payload = {
        "query": long_query,
        "model": context.default_model,
        "provider": context.default_provider,
    }
    context.text = json.dumps(payload)
    print(f"Request: query length={len(long_query)}, model={context.default_model}")
    ask_question_authorized(context, endpoint)


@step("I store conversation details")
def store_conversation_details(context: Context) -> None:
    """Store details about the conversation."""
    context.response_data = json.loads(context.response.text)


@step('I use "{endpoint}" to ask question with same conversation_id')
def ask_question_in_same_conversation(context: Context, endpoint: str) -> None:
    """Call the service REST API endpoint with question, but use the existing conversation id."""
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path

    # Replace {MODEL} and {PROVIDER} placeholders with actual values
    json_str = replace_placeholders(context, context.text or "{}")

    data = json.loads(json_str)
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    data["conversation_id"] = context.response_data["conversation_id"]

    context.response = requests.post(
        url, json=data, headers=headers, timeout=DEFAULT_LLM_TIMEOUT
    )


@then("The response should contain non-empty rag_chunks")
def check_rag_chunks_present(context: Context) -> None:
    """Check that the response contains non-empty rag_chunks from inline RAG."""
    assert context.response is not None
    response_json = context.response.json()
    assert "rag_chunks" in response_json, "rag_chunks field missing from response"
    assert (
        len(response_json["rag_chunks"]) > 0
    ), "rag_chunks is empty — inline RAG did not inject any chunks"


@then("The response should contain non-empty referenced_documents")
def check_referenced_documents_present(context: Context) -> None:
    """Check that the response contains non-empty referenced_documents."""
    assert context.response is not None
    response_json = context.response.json()
    assert (
        "referenced_documents" in response_json
    ), "referenced_documents field missing from response"
    assert (
        len(response_json["referenced_documents"]) > 0
    ), "referenced_documents is empty — no documents were referenced"


@then("The responses output_text should contain following fragments")
def check_fragments_in_responses_output_text(context: Context) -> None:
    """Check that fragments from the scenario table appear in JSON ``output_text``.

    Used for POST ``/v1/responses`` (query endpoint uses the ``response`` field).
    Matching is case-insensitive.
    """
    assert context.response is not None, "Request needs to be performed first"
    response_json = context.response.json()
    assert (
        "output_text" in response_json
    ), f"Expected 'output_text' in JSON body, got keys: {list(response_json.keys())}"
    output_text = response_json["output_text"]

    assert context.table is not None, "Fragments are not specified in table"

    for fragment in context.table:
        expected = fragment["Fragments in LLM response"]
        assert _response_contains_fragment(output_text, expected), (
            f"Fragment {expected!r} not found in output_text (case-insensitive): "
            f"{output_text!r}"
        )


@then("The response should contain following fragments")
def check_fragments_in_response(context: Context) -> None:
    """Check that all specified fragments are present in the LLM response.

    First checks that the HTTP response exists and contains a
    "response" field. For each fragment listed in the scenario's
    table under "Fragments in LLM response", asserts that it
    appears as a substring in the LLM's response (case-insensitive). Raises an
    assertion error if any fragment is missing or if the fragments
    table is not provided.
    """
    assert context.response is not None
    response_json = context.response.json()

    # Support both query endpoint format (response field) and responses API format (output array)
    if "response" in response_json:
        response = response_json["response"]
    else:
        # Responses API format: extract text from output messages
        response = " ".join(
            part.get("text", "")
            for item in response_json.get("output", [])
            if item.get("type") == "message"
            for part in (
                item.get("content") if isinstance(item.get("content"), list) else []
            )
            if part.get("type") == "output_text"
        )

    assert context.table is not None, "Fragments are not specified in table"

    for fragment in context.table:
        expected = fragment["Fragments in LLM response"]
        assert _response_contains_fragment(response, expected), (
            f"Fragment {expected!r} not found in LLM response (case-insensitive): "
            f"{response!r}"
        )


@then("The streamed response should contain following fragments")
def check_streamed_fragments_in_response(context: Context) -> None:
    """Check that all specified fragments are present in the LLM response.

    First checks that the HTTP response exists and contains a
    "response" field. For each fragment listed in the scenario's
    table under "Fragments in LLM response", asserts that it
    appears as a substring in the LLM's response (case-insensitive). Raises an
    assertion error if any fragment is missing or if the fragments
    table is not provided.
    """
    assert context.response_data["response_complete"] is not None
    response = context.response_data["response"]

    assert context.table is not None, "Fragments are not specified in table"

    for fragment in context.table:
        expected = fragment["Fragments in LLM response"]
        assert _response_contains_fragment(response, expected), (
            f"Fragment {expected!r} not found in streamed LLM response "
            f"(case-insensitive): {response!r}"
        )


@then("The streamed response contains error message {message}")
def check_streamed_response_error_message(context: Context, message: str) -> None:
    """Check that the streamed SSE response contains an error event with the given message.

    Parses the response body as SSE, asserts that an event with event type 'error' is
    present, and that its 'response' or 'cause' field contains the given message.
    Use for streaming endpoints when the error is delivered in the stream (e.g. 200 + error event).
    """
    assert context.response is not None, "Request needs to be performed first"
    print(context.response.text)
    parsed = _parse_streaming_response(context.response.text)
    stream_error = parsed.get("stream_error")
    assert (
        stream_error is not None
    ), "No error event in stream. Expected an SSE event with event type 'error'."
    response_text = str(stream_error.get("response", ""))
    cause_text = str(stream_error.get("cause", ""))
    assert message in response_text or message in cause_text, (
        f"Expected error message '{message}' not found in stream error event: "
        f"response={response_text!r}, cause={cause_text!r}"
    )


@then("The streamed response is equal to the full response")
def compare_streamed_responses(context: Context) -> None:
    """Check that streamed response is equal to complete response.

    First checks that the HTTP response exists and contains a
    "response" field. Do this check also for the complete response
    Then assert that the response is not empty and that it is equal
    to complete response
    """
    assert context.response_data["response"] is not None
    assert context.response_data["response_complete"] is not None

    response = context.response_data["response"]
    complete_response = context.response_data["response_complete"]

    assert response != "", "response is empty"
    assert (
        response == complete_response
    ), f"{response} and {complete_response} do not match"


def _parse_streaming_response(response_text: str) -> dict:
    """Parse streaming SSE response and reconstruct the full message."""
    lines = response_text.strip().split("\n")
    conversation_id = None
    full_response = ""
    full_response_split = []
    finished = False
    first_token = True
    stream_error = (
        None  # {"status_code": int, "response": str, "cause": str} if event "error"
    )

    for line in lines:
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])  # Remove 'data: ' prefix
                event = data.get("event")

                if event == "start":
                    conversation_id = data["data"]["conversation_id"]
                elif event == "token":
                    # Skip the first token (shield status message)
                    if first_token:
                        first_token = False
                        continue
                    full_response_split.append(data["data"]["token"])
                elif event == "turn_complete":
                    full_response = data["data"]["token"]
                elif event == "end":
                    finished = True
                elif event == "error":
                    stream_error = data.get("data") or {}
            except json.JSONDecodeError:
                continue  # Skip malformed lines

    return {
        "conversation_id": conversation_id,
        "response": "".join(full_response_split),
        "response_complete": full_response,
        "finished": finished,
        "stream_error": stream_error,
    }
