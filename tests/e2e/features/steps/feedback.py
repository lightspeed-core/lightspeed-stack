"""Implementation of common test steps for the feedback API."""

import json
import os
from typing import Optional

import requests
from behave import (  # pyright: ignore[reportAttributeAccessIssue]  # pyright: ignore[reportAttributeAccessIssue]  # pyright: ignore[reportAttributeAccessIssue]
    given,
    step,
    when,
)
from behave.runner import Context

from tests.e2e.features.steps.common_http import access_rest_api_endpoint
from tests.e2e.utils.utils import (
    absolute_repo_path,
    is_prow_environment,
    restart_container,
    switch_config,
)

# default timeout for HTTP operations
DEFAULT_TIMEOUT = 10


def _register_feedback_conversation_cleanup(context: Context) -> None:
    """Mark that ``after_feature`` should DELETE tracked conversations (see ``environment``)."""
    context.feedback_e2e_conversation_cleanup = True
    if not hasattr(context, "feedback_conversations"):
        context.feedback_conversations = []


@step("The feedback is enabled")  # type: ignore[reportCallIssue]
def enable_feedback(context: Context) -> None:
    """Enable the feedback endpoint and assert success."""
    assert context is not None
    _register_feedback_conversation_cleanup(context)
    payload = {"status": True}
    access_feedback_put_endpoint(context, payload)


@step("The feedback is disabled")  # type: ignore[reportCallIssue]
def disable_feedback(context: Context) -> None:
    """Disable the feedback endpoint and assert success."""
    assert context is not None
    _register_feedback_conversation_cleanup(context)
    payload = {"status": False}
    access_feedback_put_endpoint(context, payload)


@when("I update feedback status with")  # type: ignore[reportCallIssue]
def set_feedback(context: Context) -> None:
    """Enable or disable feedback via PUT request."""
    assert context.text is not None, "Payload needs to be specified"
    payload = json.loads(context.text or "{}")
    access_feedback_put_endpoint(context, payload)


def access_feedback_put_endpoint(context: Context, payload: dict) -> None:
    """Update feedback using a JSON payload."""
    assert context is not None
    endpoint = "feedback/status"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    response = requests.put(url, headers=headers, json=payload)
    context.response = response


@when("I submit the following feedback for the conversation created before")  # type: ignore
def submit_feedback_valid_conversation(context: Context) -> None:
    """Submit feedback for previousl created conversation."""
    assert (
        hasattr(context, "conversation_id") and context.conversation_id is not None
    ), "Conversation for feedback submission is not created"
    access_feedback_post_endpoint(context, context.conversation_id)


@when('I submit the following feedback for nonexisting conversation "{conversation_id}"')  # type: ignore
def submit_feedback_nonexisting_conversation(
    context: Context, conversation_id: str
) -> None:
    """Submit feedback for a non-existing conversation ID."""
    access_feedback_post_endpoint(context, conversation_id)


@when("I submit the following feedback without specifying conversation ID")  # type: ignore
def submit_feedback_without_conversation(context: Context) -> None:
    """Submit feedback with no conversation ID."""
    access_feedback_post_endpoint(context, None)


def access_feedback_post_endpoint(
    context: Context, conversation_id: Optional[str]
) -> None:
    """Send POST HTTP request with JSON payload to tested service."""
    endpoint = "feedback"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path
    payload = json.loads(context.text or "{}")
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    context.response = requests.post(url, headers=headers, json=payload)


@when("I retreive the current feedback status")  # type: ignore[reportCallIssue]
def access_feedback_get_endpoint(context: Context) -> None:
    """Retrieve the current feedback status via GET request."""
    access_rest_api_endpoint(context, "feedback/status", "GET")


@given("A new conversation is initialized")  # type: ignore[reportCallIssue]
def initialize_conversation(context: Context) -> None:
    """Create a conversation for submitting feedback."""
    create_conversation_with_user_id(context, user_id=None)


@given('A new conversation is initialized with user_id "{user_id}"')  # type: ignore
def initialize_conversation_with_user_id(context: Context, user_id: str) -> None:
    """Create a conversation for submitting feedback with a specific user_id."""
    create_conversation_with_user_id(context, user_id=user_id)


def create_conversation_with_user_id(
    context: Context, user_id: Optional[str] = None
) -> None:
    """Create a conversation, optionally with a specific user_id query parameter."""
    endpoint = "query"
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path
    if user_id is not None:
        url = f"{url}?user_id={user_id}"
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    payload = {
        "query": "Say Hello.",
        "system_prompt": "You are a helpful assistant",
        "model": context.default_model,
        "provider": context.default_provider,
    }

    response = requests.post(url, headers=headers, json=payload)
    assert (
        response.status_code == 200
    ), f"Failed to create conversation: {response.text}"

    body = response.json()
    context.conversation_id = body["conversation_id"]
    assert context.conversation_id, "Conversation was not created."
    _register_feedback_conversation_cleanup(context)
    context.feedback_conversations.append(context.conversation_id)
    context.response = response


def _lightspeed_yaml_path(context: Context, filename: str) -> str:
    """Repo-relative path to a mode-specific Lightspeed YAML (absolute on Prow)."""
    mode = "library-mode" if context.is_library_mode else "server-mode"
    rel = os.path.join("tests/e2e/configuration", mode, filename)
    if is_prow_environment():
        return absolute_repo_path(rel)
    return rel


@given("An invalid feedback storage path is configured")  # type: ignore[reportCallIssue]
def configure_invalid_feedback_storage_path(context: Context) -> None:
    """Set an invalid feedback storage path and restart the container."""
    switch_config(
        _lightspeed_yaml_path(context, "lightspeed-stack-invalid-feedback-storage.yaml")
    )
    restart_container("lightspeed-stack")
