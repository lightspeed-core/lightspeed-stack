"""LLM query and response steps."""

import json
import os
import requests
from behave import then, step  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context
from tests.e2e.utils.utils import replace_placeholders

# Longer timeout for Prow/OpenShift with CPU-based vLLM
DEFAULT_LLM_TIMEOUT = 180 if os.getenv("RUNNING_PROW") else 60


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
    if endpoint == "streaming_query":
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


@then("The response should have proper LLM response format")
def check_llm_response_format(context: Context) -> None:
    """Check the format of response from the service with LLM-generated answer."""
    assert context.response is not None
    response_json = context.response.json()
    assert "conversation_id" in response_json
    assert "response" in response_json


@then("The response should not be truncated")
def check_llm_response_not_truncated(context: Context) -> None:
    """Check that the response from LLM is not truncated."""
    assert context.response is not None
    response_json = context.response.json()
    assert response_json["truncated"] is False


@then("The response should contain following fragments")
def check_fragments_in_response(context: Context) -> None:
    """Check that all specified fragments are present in the LLM response.

    First checks that the HTTP response exists and contains a
    "response" field. For each fragment listed in the scenario's
    table under "Fragments in LLM response", asserts that it
    appears as a substring in the LLM's response. Raises an
    assertion error if any fragment is missing or if the fragments
    table is not provided.
    """
    assert context.response is not None
    response_json = context.response.json()
    response = response_json["response"]

    assert context.table is not None, "Fragments are not specified in table"

    for fragment in context.table:
        expected = fragment["Fragments in LLM response"]
        assert (
            expected in response
        ), f"Fragment '{expected}' not found in LLM response: '{response}'"


@then("The streamed response should contain following fragments")
def check_streamed_fragments_in_response(context: Context) -> None:
    """Check that all specified fragments are present in the LLM response.

    First checks that the HTTP response exists and contains a
    "response" field. For each fragment listed in the scenario's
    table under "Fragments in LLM response", asserts that it
    appears as a substring in the LLM's response. Raises an
    assertion error if any fragment is missing or if the fragments
    table is not provided.
    """
    assert context.response_data["response_complete"] is not None
    response = context.response_data["response"]

    assert context.table is not None, "Fragments are not specified in table"

    for fragment in context.table:
        expected = fragment["Fragments in LLM response"]
        assert (
            expected in response
        ), f"Fragment '{expected}' not found in LLM response: '{response}'"


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
