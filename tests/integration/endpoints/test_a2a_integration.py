"""Integration tests for the A2A JSON-RPC endpoint."""

# pylint: disable=protected-access

import json
import uuid
from collections.abc import Generator
from typing import Any, Optional

import pytest
from fastapi import HTTPException, status
from ogx_client import ApiException
from pytest_mock import MockerFixture

import app.endpoints.a2a as a2a_endpoint
import constants
from a2a_storage.storage_factory import A2AStorageFactory
from authentication.interface import AuthTuple
from authorization.middleware import get_authorization_resolvers
from configuration import AppConfig
from models.config import (
    AccessRule,
    Action,
    AuthenticationConfiguration,
    AuthorizationConfiguration,
    Customization,
    RHIdentityConfiguration,
)
from tests.integration.conftest import (
    build_a2a_request,
    create_text_agent_stream_events,
    make_openai_model,
    make_openai_models_list_response,
    mock_agent_run_stream,
)

_AGENT_CARD_CONFIG: dict[str, Any] = {
    "name": "Integration A2A Assistant",
    "description": "Integration test agent",
    "protocolVersion": "0.3.0",
    "provider": {
        "organization": "Red Hat",
        "url": "https://redhat.com",
    },
    "skills": [
        {
            "id": "general-qa",
            "name": "General Q&A",
            "description": "Answer general questions",
            "tags": ["qa"],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain"],
        }
    ],
    "capabilities": {
        "streaming": True,
        "pushNotifications": False,
        "stateTransitionHistory": False,
    },
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
}


def _clear_a2a_storage() -> None:
    """Clear A2A storage singletons."""
    a2a_endpoint._TASK_STORE = None
    a2a_endpoint._CONTEXT_STORE = None
    A2AStorageFactory.reset()


@pytest.fixture(autouse=True)
def reset_a2a_storage() -> Generator[None, None, None]:
    """Reset A2A storage singletons before and after each test."""
    _clear_a2a_storage()
    yield
    _clear_a2a_storage()


@pytest.fixture(autouse=True)
def reset_authorization_cache() -> Generator[None, None, None]:
    """Clear cached auth resolvers before and after each test."""
    get_authorization_resolvers.cache_clear()
    yield
    get_authorization_resolvers.cache_clear()


@pytest.fixture(autouse=True)
def configure_a2a_agent_card(test_config: AppConfig) -> None:
    """Attach an agent card to the integration config.

    Autouse because most tests in this module go through
    ``_create_a2a_app``/``get_lightspeed_agent_card``, which require one.
    It's a harmless no-op for the handful of tests (e.g.
    ``test_a2a_jsonrpc_forbidden_without_action``) that are rejected by the
    ``@authorize`` decorator before the real endpoint body ever runs, and so
    never read ``configuration.customization``.
    """
    assert test_config._configuration is not None
    test_config._configuration.customization = Customization(
        agent_card_config=_AGENT_CARD_CONFIG,
    )


def _install_agent(mocker: MockerFixture, *contents: str) -> Any:
    """Patch ``build_agent`` to return mock agent responses."""
    streams = [
        mock_agent_run_stream(create_text_agent_stream_events(mocker, content=content))
        for content in contents
    ]
    mock_agent = mocker.Mock()
    if len(streams) == 1:
        mock_agent.run_stream_events.return_value = streams[0]
    else:
        mock_agent.run_stream_events.side_effect = streams
    return mocker.patch("app.endpoints.a2a.build_agent", return_value=mock_agent)


def _jsonrpc_body(
    text: str,
    *,
    context_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    parts: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a ``message/send`` JSON-RPC request body.

    Parameters:
        text: Text content for the default single text part. Ignored when
            ``parts`` is given explicitly (e.g. to build an empty-input message).
        context_id: Optional A2A context id to attach to the message.
        metadata: Optional message metadata (e.g. ``model``, ``vector_store_ids``).
        parts: Optional explicit parts list, overriding the default single
            text part. Pass ``[]`` to build a message with no input content.
    """
    message: dict[str, Any] = {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": parts if parts is not None else [{"kind": "text", "text": text}],
    }
    if context_id is not None:
        message["contextId"] = context_id
    if metadata is not None:
        message["metadata"] = metadata
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {"message": message},
    }


def _task_state(result: dict[str, Any]) -> str:
    """Return ``status.state`` from an A2A task."""
    return result.get("status", {}).get("state", "")


def _context_id(result: dict[str, Any]) -> str:
    """Return the context id from an A2A result."""
    return result.get("contextId", "")


async def _post_a2a(body: dict[str, Any], auth: AuthTuple) -> Any:
    """POST a JSON-RPC request to the A2A handler."""
    return await a2a_endpoint.handle_a2a_jsonrpc_post(
        request=build_a2a_request(body),
        auth=auth,
        mcp_headers={},
    )


def _parse_jsonrpc_response(response: Any) -> dict[str, Any]:
    """Parse and validate a JSON-RPC response."""
    assert response.status_code == 200, response.body
    payload = json.loads(response.body)
    assert isinstance(payload, dict), payload
    return payload


def _jsonrpc_result(response: Any) -> dict[str, Any]:
    """Decode a non-streaming JSON-RPC success result."""
    payload = _parse_jsonrpc_response(response)
    assert not payload.get("error"), payload
    result = payload.get("result")
    assert isinstance(result, dict), payload
    return result


@pytest.mark.asyncio
async def test_a2a_jsonrpc_forbidden_without_action(
    test_config: AppConfig,
    test_auth: AuthTuple,
) -> None:
    """An authenticated caller without ``A2A_JSONRPC`` action receives 403."""
    assert test_config._configuration is not None
    test_config._configuration.authentication = AuthenticationConfiguration(
        module=constants.AUTH_MOD_RH_IDENTITY,
        skip_for_health_probes=False,
        skip_for_metrics=False,
        rh_identity_config=RHIdentityConfiguration(required_entitlements=[]),
    )
    test_config._configuration.authorization = AuthorizationConfiguration(
        access_rules=[AccessRule(role="*", actions=[Action.INFO])],
    )

    with pytest.raises(HTTPException) as exc_info:
        await _post_a2a(_jsonrpc_body("What is a pod?"), test_auth)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_message_send_returns_failed_task_when_ogx_is_unreachable(
    mock_ogx_client: Any,
    test_auth: AuthTuple,
) -> None:
    """``message/send`` returns a failed task when OGX cannot be reached."""
    mock_ogx_client.openai.list.side_effect = ApiException(status=None)

    result = _jsonrpc_result(
        await _post_a2a(_jsonrpc_body("What is a pod?"), test_auth)
    )

    assert _task_state(result) == "failed"


@pytest.mark.asyncio
async def test_follow_up_reuses_one_conversation(
    mock_ogx_client: Any,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Follow-up with same context id reuses the OGX conversation."""
    build_agent = _install_agent(mocker, "first answer", "second answer")

    first = _jsonrpc_result(
        await _post_a2a(_jsonrpc_body("What is the capital of France?"), test_auth)
    )
    context_id = _context_id(first)
    assert context_id

    await _post_a2a(
        _jsonrpc_body("What is its population?", context_id=context_id),
        test_auth,
    )

    mock_ogx_client.conversations.create.assert_awaited_once()
    assert build_agent.call_args.args[1].conversation == "conv_" + "a" * 48


@pytest.mark.asyncio
async def test_message_metadata_overrides_model(
    mock_ogx_client: Any,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Message metadata ``model`` and ``provider`` select the agent model."""
    mock_ogx_client.openai.list.return_value = make_openai_models_list_response(
        make_openai_model(model_id="together/llama3.1", provider_id="together"),
    )
    build_agent = _install_agent(mocker, "A pod is the smallest deployable unit.")

    await _post_a2a(
        _jsonrpc_body(
            "What is a pod?",
            metadata={"model": "llama3.1", "provider": "together"},
        ),
        test_auth,
    )

    assert build_agent.call_args.args[1].model == "together/llama3.1"


@pytest.mark.asyncio
async def test_message_metadata_sets_vector_store_ids(
    mock_ogx_client: Any,  # pylint: disable=unused-argument
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """Message metadata ``vector_store_ids`` are routed to the file_search tool."""
    build_agent = _install_agent(mocker, "Found relevant docs.")

    await _post_a2a(
        _jsonrpc_body(
            "What does the runbook say?",
            metadata={"vector_store_ids": ["vs_abc123"]},
        ),
        test_auth,
    )

    agent_params = build_agent.call_args.args[1]
    file_search_tools = [
        tool
        for tool in (agent_params.tools or [])
        if getattr(tool, "type", None) == "file_search"
    ]
    assert len(file_search_tools) == 1
    assert file_search_tools[0].vector_store_ids == ["vs_abc123"]


@pytest.mark.asyncio
async def test_message_send_without_text_returns_input_required(
    mock_ogx_client: Any,  # pylint: disable=unused-argument
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """A message with no text part short-circuits to an ``input_required`` task.

    Note: the parts list itself can't be empty -- the a2a-sdk's own
    ``new_task()`` raises ``ValueError`` for an empty ``parts`` list before
    our handler ever runs (see ``a2a.utils.task.new_task``), which surfaces
    as a JSON-RPC -32603 Internal Error rather than our own
    ``input_required`` handling. To reach our ``if not user_input`` branch
    for real, the message must carry a non-text part (e.g. ``DataPart``) so
    ``RequestContext.get_user_input()`` -- which only extracts ``TextPart``
    content -- returns an empty string while ``parts`` stays non-empty.
    """
    build_agent = mocker.patch("app.endpoints.a2a.build_agent")

    result = _jsonrpc_result(
        await _post_a2a(
            _jsonrpc_body("", parts=[{"kind": "data", "data": {"foo": "bar"}}]),
            test_auth,
        )
    )

    # TaskState serializes with a hyphen on the wire ("input-required"),
    # unlike the Python enum member name (TaskState.input_required).
    assert _task_state(result) == "input-required"
    build_agent.assert_not_called()
