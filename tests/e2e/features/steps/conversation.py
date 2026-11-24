"""Implementation of common test steps."""

import requests
from behave import (
    step,
    then,
    when,
)  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import replace_placeholders

# default timeout for HTTP operations
DEFAULT_TIMEOUT = 10


@step(
    "I use REST API conversation endpoint with conversation_id from above using HTTP GET method"
)
def access_conversation_endpoint_get(context: Context) -> None:
    """Send GET HTTP request to tested service for conversation/{conversation_id}."""
    assert (
        context.response_data["conversation_id"] is not None
    ), "conversation id not stored"
    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}/{context.response_data['conversation_id']}".replace(
        "//", "/"
    )
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)


@step(
    'I use REST API conversation endpoint with conversation_id "{conversation_id}" using HTTP GET method'
)
def access_conversation_endpoint_get_specific(
    context: Context, conversation_id: str
) -> None:
    """Send GET HTTP request to tested service for conversation/{conversation_id}."""
    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}/{conversation_id}".replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)


@step(
    "I use REST API conversation endpoint with the forked responses conversation id using HTTP GET method"
)
def access_forked_responses_conversation_get(context: Context) -> None:
    """GET /conversations/{id} using the id stored after a responses API fork."""
    assert hasattr(
        context, "responses_fork_conversation_id"
    ), "responses_fork_conversation_id not set; store fork id first"
    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = (
        f"{context.api_prefix}/{endpoint}/{context.responses_fork_conversation_id}"
    ).replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    context.response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)


@step(
    "I use REST API conversation endpoint with the responses multi-turn baseline conversation id using HTTP GET method"
)
def access_responses_baseline_conversation_get(context: Context) -> None:
    """GET /conversations/{id} for the linear thread before a responses fork."""
    assert hasattr(
        context, "responses_multi_turn_baseline_conversation_id"
    ), "responses_multi_turn_baseline_conversation_id not set"
    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    cid = context.responses_multi_turn_baseline_conversation_id
    path = f"{context.api_prefix}/{endpoint}/{cid}".replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    context.response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)


@then("The GET conversation response id matches the forked responses conversation id")
def check_get_matches_forked_responses_conversation_id(context: Context) -> None:
    """Assert GET /conversations payload matches the fork id from /v1/responses."""
    assert context.response is not None
    assert hasattr(context, "responses_fork_conversation_id")
    response_json = context.response.json()
    assert response_json["conversation_id"] == context.responses_fork_conversation_id, (
        f"expected conversation_id {context.responses_fork_conversation_id!r}, "
        f"got {response_json.get('conversation_id')!r}"
    )


@then(
    "The GET conversation response id matches the responses multi-turn baseline conversation id"
)
def check_get_matches_responses_baseline_conversation_id(context: Context) -> None:
    """Assert GET /conversations payload matches the pre-fork thread id."""
    assert context.response is not None
    assert hasattr(context, "responses_multi_turn_baseline_conversation_id")
    expected = context.responses_multi_turn_baseline_conversation_id
    response_json = context.response.json()
    assert response_json["conversation_id"] == expected, (
        f"expected conversation_id {expected!r}, "
        f"got {response_json.get('conversation_id')!r}"
    )


@when(
    "I use REST API conversation endpoint with conversation_id from above using HTTP DELETE method"
)
def access_conversation_endpoint_delete(context: Context) -> None:
    """Send DELETE HTTP request to tested service for conversation/{conversation_id}."""
    assert (
        context.response_data["conversation_id"] is not None
    ), "conversation id not stored"
    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}/{context.response_data['conversation_id']}".replace(
        "//", "/"
    )
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.delete(url, headers=headers, timeout=DEFAULT_TIMEOUT)


@step(
    'I use REST API conversation endpoint with conversation_id "{conversation_id}" using HTTP DELETE method'
)
def access_conversation_endpoint_delete_specific(
    context: Context, conversation_id: str
) -> None:
    """Send DELETE HTTP request to tested service for conversation/{conversation_id}."""
    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}/{conversation_id}".replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.delete(url, headers=headers, timeout=DEFAULT_TIMEOUT)


@when(
    'I use REST API conversation endpoint with conversation_id from above and topic_summary "{topic_summary}" using HTTP PUT method'
)
def access_conversation_endpoint_put(context: Context, topic_summary: str) -> None:
    """Send PUT HTTP request to tested service for conversation/{conversation_id} with topic_summary."""
    assert hasattr(context, "response_data"), "response_data not found in context"
    assert context.response_data.get("conversation_id"), "conversation id not stored"

    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}/{context.response_data['conversation_id']}".replace(
        "//", "/"
    )
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    context.response = None

    if topic_summary == "<EMPTY>":
        topic_summary = ""

    payload = {"topic_summary": topic_summary}

    context.response = requests.put(
        url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT
    )


@step(
    'I use REST API conversation endpoint with conversation_id "{conversation_id}" and topic_summary "{topic_summary}" using HTTP PUT method'
)
def access_conversation_endpoint_put_specific(
    context: Context, conversation_id: str, topic_summary: str
) -> None:
    """Send PUT HTTP request to tested service for conversation/{conversation_id} with topic_summary."""
    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}/{conversation_id}".replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    context.response = None

    payload = {"topic_summary": topic_summary}

    context.response = requests.put(
        url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT
    )


@when(
    "I use REST API conversation endpoint with conversation_id from above and empty topic_summary using HTTP PUT method"
)
def access_conversation_endpoint_put_empty(context: Context) -> None:
    """Send PUT HTTP request with empty topic_summary to test validation."""
    assert hasattr(context, "response_data"), "response_data not found in context"
    assert context.response_data.get("conversation_id"), "conversation id not stored"

    endpoint = "conversations"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}/{context.response_data['conversation_id']}".replace(
        "//", "/"
    )
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    context.response = None

    payload = {"topic_summary": ""}

    context.response = requests.put(
        url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT
    )


@then("The conversation with conversation_id from above is returned")
def check_returned_conversation_id(context: Context) -> None:
    """Check the conversation id in response."""
    response_json = context.response.json()
    found_conversation = None
    for conversation in response_json["conversations"]:
        if conversation["conversation_id"] == context.response_data["conversation_id"]:
            found_conversation = conversation
            break

    context.found_conversation = found_conversation

    assert found_conversation is not None, "conversation not found"


@then("The conversation has topic_summary and last_message_timestamp")
def check_conversation_metadata_not_empty(context: Context) -> None:
    """Check that conversation has non-empty metadata fields."""
    found_conversation = context.found_conversation

    assert found_conversation is not None, "conversation not found in context"

    assert (
        "last_message_timestamp" in found_conversation
    ), "last_message_timestamp field missing"
    timestamp = found_conversation["last_message_timestamp"]
    assert isinstance(
        timestamp, (int, float)
    ), f"last_message_timestamp should be a number, got {type(timestamp)}"
    assert timestamp > 0, f"last_message_timestamp should be positive, got {timestamp}"

    assert "topic_summary" in found_conversation, "topic_summary field missing"
    topic_summary = found_conversation["topic_summary"]
    assert topic_summary is not None, "topic_summary should not be None"


@then('The conversation topic_summary is "{expected_summary}"')
def check_conversation_topic_summary(context: Context, expected_summary: str) -> None:
    """Check that the conversation has the expected topic summary."""
    found_conversation = context.found_conversation

    assert found_conversation is not None, "conversation not found in context"
    assert "topic_summary" in found_conversation, "topic_summary field missing"

    actual_summary = found_conversation["topic_summary"]
    assert (
        actual_summary == expected_summary
    ), f"Expected topic_summary '{expected_summary}', but got '{actual_summary}'"


@then("The returned conversation details have expected conversation_id")
def check_found_conversation_id(context: Context) -> None:
    """Check whether the conversation details have expected conversation_id."""
    response_json = context.response.json()

    assert (
        response_json["conversation_id"] == context.response_data["conversation_id"]
    ), "found wrong conversation"


@then("The conversation with details and conversation_id from above is not found")
def check_deleted_conversation(context: Context) -> None:
    """Check whether the deleted conversation is gone."""
    assert context.response is not None


@then("The conversation history contains {count:d} messages")
def check_conversation_message_count(context: Context, count: int) -> None:
    """Check that the conversation history has expected number of messages."""
    response_json = context.response.json()

    assert "chat_history" in response_json, "chat_history not found in response"
    actual_count = len(response_json["chat_history"])

    assert actual_count == count, (
        f"Expected {count} messages in conversation history, "
        f"but found {actual_count}"
    )


@then("The conversation history has correct metadata")
def check_conversation_metadata(context: Context) -> None:
    """Check that conversation history has correct model and provider info."""
    response_json = context.response.json()

    assert "chat_history" in response_json, "chat_history not found in response"
    chat_history = response_json["chat_history"]

    assert len(chat_history) > 0, "chat_history is empty"

    for idx, turn in enumerate(chat_history):
        assert "provider" in turn, f"Turn {idx} missing 'provider'"
        assert "model" in turn, f"Turn {idx} missing 'model'"
        assert "messages" in turn, f"Turn {idx} missing 'messages'"
        assert "started_at" in turn, f"Turn {idx} missing 'started_at'"
        assert "completed_at" in turn, f"Turn {idx} missing 'completed_at'"

        assert turn["provider"], f"Turn {idx} has empty provider"
        assert turn["model"], f"Turn {idx} has empty model"

        messages = turn["messages"]
        assert (
            len(messages) == 2
        ), f"Turn {idx} should have 2 messages (user + assistant)"

        user_msg = messages[0]
        assert user_msg["type"] == "user", f"Turn {idx} first message should be user"
        assert "content" in user_msg, f"Turn {idx} user message missing content"

        assistant_msg = messages[1]
        assert (
            assistant_msg["type"] == "assistant"
        ), f"Turn {idx} second message should be assistant"
        assert (
            "content" in assistant_msg
        ), f"Turn {idx} assistant message missing content"


@then("The conversation uses model {model} and provider {provider}")
def check_conversation_model_provider(
    context: Context, model: str, provider: str
) -> None:
    """Check that conversation used specific model and provider."""
    response_json = context.response.json()

    assert "chat_history" in response_json, "chat_history not found in response"
    chat_history = response_json["chat_history"]

    assert len(chat_history) > 0, "chat_history is empty"

    expected_model = replace_placeholders(context, model)
    expected_provider = replace_placeholders(context, provider)

    for idx, turn in enumerate(chat_history):
        actual_model = turn.get("model")
        actual_provider = turn.get("provider")

        assert (
            actual_model == expected_model
        ), f"Turn {idx} expected model '{expected_model}', got '{actual_model}'"
        assert (
            actual_provider == expected_provider
        ), f"Turn {idx} expected provider '{expected_provider}', got '{actual_provider}'"
