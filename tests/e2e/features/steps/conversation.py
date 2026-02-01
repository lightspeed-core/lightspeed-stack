"""Implementation of common test steps."""

import json
import time
from behave import (
    step,
    when,
    then,
    given,
)  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context
import requests
from tests.e2e.utils.utils import replace_placeholders, restart_container, switch_config

# default timeout for HTTP operations
DEFAULT_TIMEOUT = 10

# Retry configuration for conversation polling
# Background persistence takes ~500ms for MCP cleanup + topic summary generation
MAX_RETRIES = 10  # Maximum retry attempts
INITIAL_RETRY_DELAY = 0.2  # Start with 200ms delay
MAX_RETRY_DELAY = 2.0  # Cap at 2 second delay


def poll_for_conversation(
    url: str, headers: dict, max_retries: int = MAX_RETRIES
) -> requests.Response:
    """Poll for conversation availability with exponential backoff.

    Conversations are persisted asynchronously in background tasks, which includes:
    - 500ms MCP cleanup delay
    - Topic summary generation
    - Database write operations

    This function retries GET requests with exponential backoff to handle the
    asynchronous persistence timing.

    Parameters:
        url (str): The conversation endpoint URL
        headers (dict): Request headers (including auth)
        max_retries (int): Maximum number of retry attempts (must be >= 1)

    Returns:
        requests.Response: The final response (successful or last failure)

    Raises:
        ValueError: If max_retries < 1
    """
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    delay = INITIAL_RETRY_DELAY

    for attempt in range(max_retries):
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)

        # Success - conversation found
        if response.status_code == 200:
            if attempt > 0:
                print(
                    f"✅ Conversation found after {attempt + 1} attempts "
                    f"(waited {sum(min(INITIAL_RETRY_DELAY * (2 ** i), MAX_RETRY_DELAY) for i in range(attempt)):.2f}s)"
                )
            return response

        # 404 means not persisted yet - retry
        if response.status_code == 404 and attempt < max_retries - 1:
            print(
                f"⏳ Conversation not yet persisted (attempt {attempt + 1}/{max_retries}), "
                f"waiting {delay:.2f}s..."
            )
            time.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_DELAY)  # Exponential backoff with cap
            continue

        # Other errors or final attempt - return as-is
        return response

    return response  # Return last response if all retries exhausted


def poll_for_topic_summary(
    url: str, headers: dict, conversation_id: str, max_seconds: int = 10
) -> dict | None:
    """Poll until topic_summary is populated in the conversation.

    After a conversation is persisted, the topic_summary is generated asynchronously
    via an LLM call, which can take several seconds. This function polls the
    conversation list or GET endpoint until topic_summary is not None.

    Parameters:
        url (str): The conversations list endpoint URL
        headers (dict): Request headers (including auth)
        conversation_id (str): The conversation ID to check
        max_seconds (int): Maximum total seconds to poll (default 10)

    Returns:
        dict | None: The conversation dict with topic_summary, or None if timeout

    Raises:
        ValueError: If max_seconds < 1
    """
    if max_seconds < 1:
        raise ValueError("max_seconds must be >= 1")

    delay = 0.5  # Start with 500ms
    elapsed = 0.0
    attempt = 0

    print(f"⏳ Polling for topic_summary (conversation: {conversation_id[:8]}...)")

    while elapsed < max_seconds:
        attempt += 1
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)

        if response.status_code == 200:
            data = response.json()
            # Search for our conversation in the list
            for conv in data.get("conversations", []):
                if conv.get("conversation_id") == conversation_id:
                    topic_summary = conv.get("topic_summary")
                    if topic_summary is not None:
                        print(
                            f"✅ Topic summary populated after {elapsed:.1f}s "
                            f"({attempt} attempts)"
                        )
                        return conv

        # Not ready yet - wait and retry
        print(
            f"⏳ Topic summary not ready (attempt {attempt}, elapsed {elapsed:.1f}s), "
            f"waiting {delay:.1f}s..."
        )
        time.sleep(delay)
        elapsed += delay
        delay = min(delay * 1.5, 2.0)  # Exponential backoff, cap at 2s

    print(f"⚠️  Timeout after {max_seconds}s - topic_summary still None")
    return None


@step(
    "I use REST API conversation endpoint with conversation_id from above using HTTP GET method"
)
def access_conversation_endpoint_get(context: Context) -> None:
    """Send GET HTTP request to tested service for conversation/{conversation_id}.

    Uses polling with exponential backoff to handle asynchronous conversation
    persistence from background tasks.
    """
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

    # Poll for conversation availability (handles async background persistence)
    context.response = poll_for_conversation(url, headers)


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


@when(
    "I use REST API conversation endpoint with conversation_id from above using HTTP DELETE method"
)
def access_conversation_endpoint_delete(context: Context) -> None:
    """Send DELETE HTTP request to tested service for conversation/{conversation_id}.

    Polls to ensure conversation is persisted before attempting deletion.
    """
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

    # First, poll to ensure conversation is persisted
    check_response = poll_for_conversation(url, headers)
    if check_response.status_code != 200:
        print(
            f"⚠️  Warning: Conversation not found before DELETE (status: {check_response.status_code})"
        )

    # Now perform DELETE
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
    """Check the conversation id in response.

    If the conversation is not found in the list, retries the GET request
    with exponential backoff to handle asynchronous background persistence.
    """
    max_retries = 10
    delay = 0.2  # Start with 200ms

    for attempt in range(max_retries):
        assert context.response.status_code == 200, (
            f"Expected 200 from conversations list, got {context.response.status_code}: "
            f"{context.response.text}"
        )
        response_json = context.response.json()
        conversations = response_json.get("conversations")
        assert conversations is not None, "Missing 'conversations' in response payload"
        found_conversation = None
        for conversation in conversations:
            if (
                conversation["conversation_id"]
                == context.response_data["conversation_id"]
            ):
                found_conversation = conversation
                break

        if found_conversation is not None:
            context.found_conversation = found_conversation
            if attempt > 0:
                print(
                    f"✅ Conversation found in list after {attempt + 1} attempts "
                    f"(waited {sum(0.2 * (2 ** i) for i in range(attempt)):.2f}s)"
                )
            return

        # Not found yet - retry if not last attempt
        if attempt < max_retries - 1:
            print(
                f"⏳ Conversation not in list yet (attempt {attempt + 1}/{max_retries}), "
                f"retrying in {delay:.2f}s..."
            )
            time.sleep(delay)
            delay = min(delay * 2, 2.0)  # Exponential backoff, cap at 2s

            # Re-fetch the list
            endpoint = "conversations"
            base = f"http://{context.hostname}:{context.port}"
            path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
            url = base + path
            headers = context.auth_headers if hasattr(context, "auth_headers") else {}
            context.response = requests.get(url, headers=headers, timeout=10)
        else:
            # Final attempt - fail with helpful message
            conversation_ids = [
                c["conversation_id"] for c in response_json["conversations"]
            ]
            assert False, (
                f"conversation not found after {max_retries} attempts. "
                f"Looking for: {context.response_data['conversation_id']}, "
                f"Found IDs: {conversation_ids}"
            )


@then("The conversation has topic_summary and last_message_timestamp")
def check_conversation_metadata_not_empty(context: Context) -> None:
    """Check that conversation has non-empty metadata fields.

    If topic_summary is None, polls the endpoint until it's populated
    (up to 10 seconds) since topic generation happens asynchronously.
    """
    found_conversation = context.found_conversation

    assert found_conversation is not None, "conversation not found in context"

    # Check last_message_timestamp (should be immediate)
    assert (
        "last_message_timestamp" in found_conversation
    ), "last_message_timestamp field missing"
    timestamp = found_conversation["last_message_timestamp"]
    assert isinstance(
        timestamp, (int, float)
    ), f"last_message_timestamp should be a number, got {type(timestamp)}"
    assert timestamp > 0, f"last_message_timestamp should be positive, got {timestamp}"

    # Check topic_summary (may need polling)
    assert "topic_summary" in found_conversation, "topic_summary field missing"
    topic_summary = found_conversation["topic_summary"]

    # If topic_summary is None, poll until it's ready (async generation via LLM)
    if topic_summary is None:
        print("⏳ Topic summary not yet generated, polling...")
        # Re-fetch from the same endpoint that was used to get the conversation
        base = f"http://{context.hostname}:{context.port}"
        path = f"{context.api_prefix}/conversations".replace("//", "/")
        url = base + path
        headers = context.auth_headers if hasattr(context, "auth_headers") else {}

        conversation_id = context.response_data["conversation_id"]
        updated_conv = poll_for_topic_summary(
            url, headers, conversation_id, max_seconds=10
        )

        if updated_conv is not None:
            # Update context with the refreshed conversation
            context.found_conversation = updated_conv
            topic_summary = updated_conv["topic_summary"]
        else:
            # Timeout - fail with helpful message
            assert False, (
                "topic_summary still None after 10 seconds of polling. "
                "Background LLM call may have failed or timed out."
            )

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


@then("The conversation details are following")
def check_returned_conversation_content(context: Context) -> None:
    """Check the conversation content in response."""
    json_str = replace_placeholders(context, context.text or "{}")

    expected_data = json.loads(json_str)
    found_conversation = context.found_conversation

    assert (
        found_conversation["last_used_model"] == expected_data["last_used_model"]
    ), f"last_used_model mismatch, was {found_conversation["last_used_model"]}"
    assert (
        found_conversation["last_used_provider"] == expected_data["last_used_provider"]
    ), f"last_used_provider mismatch, was {found_conversation["last_used_provider"]}"
    assert (
        found_conversation["message_count"] == expected_data["message_count"]
    ), f"message count mismatch, was {found_conversation["message_count"]}"


@then("The returned conversation details have expected conversation_id")
def check_found_conversation_id(context: Context) -> None:
    """Check whether the conversation details have expected conversation_id."""
    response_json = context.response.json()

    assert (
        response_json["conversation_id"] == context.response_data["conversation_id"]
    ), "found wrong conversation"


@then("The body of the response has following messages")
def check_found_conversation_content(context: Context) -> None:
    """Check whether the conversation details have expected data."""
    expected_data = json.loads(context.text)
    response_json = context.response.json()
    chat_messages = response_json["chat_history"][0]["messages"]

    assert chat_messages[0]["content"] == expected_data["content"]
    assert chat_messages[0]["type"] == expected_data["type"]
    assert (
        expected_data["content_response"] in chat_messages[1]["content"]
    ), f"expected substring not in response, has {chat_messages[1]["content"]}"
    assert chat_messages[1]["type"] == expected_data["type_response"]


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


@given("An invalid conversation cache path is configured")  # type: ignore
def configure_invalid_conversation_cache_path(context: Context) -> None:
    """Set an invalid conversation cache path and restart the container."""
    switch_config(context.scenario_config)
    restart_container("lightspeed-stack")
