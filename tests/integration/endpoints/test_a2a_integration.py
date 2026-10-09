"""Integration tests for the A2A JSON-RPC endpoint."""

# pylint: disable=protected-access

import asyncio
import json
import uuid
from collections.abc import Generator
from typing import Any, Optional

import pytest
from fastapi import HTTPException, Request, status
from fastapi.testclient import TestClient
from ogx_client import ApiException
from pytest_mock import MockerFixture
from starlette.responses import StreamingResponse

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
    method: str = "message/send",
) -> dict[str, Any]:
    """Build a JSON-RPC request body for message/send or message/stream.

    Parameters:
        text: Text content for the default single text part. Ignored when
            ``parts`` is given explicitly (e.g. to build an empty-input message).
        context_id: Optional A2A context id to attach to the message.
        metadata: Optional message metadata (e.g. ``model``, ``vector_store_ids``).
        parts: Optional explicit parts list, overriding the default single
            text part. Pass ``[]`` to build a message with no input content.
        method: JSON-RPC method, either "message/send" or "message/stream".
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
        "method": method,
        "params": {"message": message},
    }


def _task_state(result: dict[str, Any]) -> str:
    """Return ``status.state`` from an A2A task."""
    return result.get("status", {}).get("state", "")


def _context_id(result: dict[str, Any]) -> str:
    """Return the context id from an A2A result."""
    return result.get("contextId", "")


async def _collect_stream_results(response: Any) -> list[dict[str, Any]]:
    """Consume a ``message/stream`` SSE response and return each event's ``result``.

    Parameters:
        response: ``StreamingResponse`` returned for a ``message/stream`` request.

    Returns:
        One parsed JSON-RPC ``result`` dict per ``data:`` frame in the SSE
        stream, in emission order.
    """
    results: list[dict[str, Any]] = []
    async for chunk in response.body_iterator:
        text = chunk if isinstance(chunk, str) else bytes(chunk).decode()
        for line in text.splitlines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                result = payload.get("result")
                if isinstance(result, dict):
                    results.append(result)
    return results


def _stream_artifact_text(results: list[dict[str, Any]]) -> str:
    """Return concatenated text parts from the stream's artifact-update event."""
    text = ""
    for result in results:
        if result.get("kind") != "artifact-update":
            continue
        for part in result.get("artifact", {}).get("parts", []):
            if part.get("kind") == "text":
                text += part.get("text", "")
    return text


def _build_a2a_request(body: dict[str, Any]) -> Request:
    """Build a POST ``/a2a`` FastAPI Request wrapping a JSON-RPC body.

    The synthetic ``receive()`` here blocks forever on any call after the
    body is delivered, instead of immediately returning another
    ``http.request``. ``message/stream`` responses are served via
    sse-starlette's ``EventSourceResponse``, which spawns a background task
    that repeatedly calls ``receive()`` to detect client disconnection; a
    non-yielding coroutine there spins the event loop forever, hanging any
    test that fully consumes a streaming response's ``body_iterator``.
    Blocking on an unresolved ``Future`` yields control properly (no busy
    loop) without falsely signaling a premature disconnect (which would
    short-circuit the A2A app before it produces any events). The pending
    call is cancelled along with the rest of the background task once the
    stream ends.

    Parameters:
        body: JSON-RPC request payload (e.g. a ``message/send`` body) to
            serialize as the request body.

    Returns:
        Request: FastAPI Request object whose body yields the serialized
        ``body`` dict when read (e.g. via ``await request.body()``).
    """
    body_bytes = json.dumps(body).encode()
    body_sent = False

    async def receive() -> dict[str, Any]:
        """Return the JSON-RPC body once, then block forever (no disconnect)."""
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        await asyncio.Future()
        raise AssertionError("unreachable")  # pragma: no cover

    return Request(
        scope={
            "type": "http",
            "method": "POST",
            "path": "/a2a",
            "root_path": "",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "scheme": "http",
            "server": ("localhost", 8080),
        },
        receive=receive,
    )


async def _post_a2a(body: dict[str, Any], auth: AuthTuple) -> Any:
    """POST a JSON-RPC request to the A2A handler."""
    return await a2a_endpoint.handle_a2a_jsonrpc_post(
        request=_build_a2a_request(body),
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
@pytest.mark.parametrize(
    "method",
    ["message/send", "message/stream"],
)
async def test_ogx_unreachable_handles_gracefully(
    mock_ogx_client: Any,
    test_auth: AuthTuple,
    method: str,
) -> None:
    """Both message/send and message/stream handle OGX unreachable gracefully."""
    mock_ogx_client.openai.list.side_effect = ApiException(status=None)

    response = await _post_a2a(
        _jsonrpc_body("What is a pod?", method=method), test_auth
    )

    if method == "message/send":
        result = _jsonrpc_result(response)
        assert _task_state(result) == "failed"
    else:
        assert isinstance(response, StreamingResponse)
        results = await _collect_stream_results(response)
        assert any(_task_state(result) == "failed" for result in results)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method",
    ["message/send", "message/stream"],
)
async def test_message_without_text_short_circuits(
    test_auth: AuthTuple,
    mocker: MockerFixture,
    method: str,
) -> None:
    """Message without text short-circuits without calling agent.

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

    response = await _post_a2a(
        _jsonrpc_body(
            "", parts=[{"kind": "data", "data": {"foo": "bar"}}], method=method
        ),
        test_auth,
    )

    if method == "message/send":
        result = _jsonrpc_result(response)
        assert _task_state(result) == "input-required"
    else:
        assert isinstance(response, StreamingResponse)
        results = await _collect_stream_results(response)
        assert any(_task_state(result) == "input-required" for result in results)

    # Consuming the stream above drives the background task that would call
    # build_agent to completion; asserting beforehand would pass trivially
    # since asyncio.create_task() hasn't had a chance to run yet.
    build_agent.assert_not_called()


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

    second = _jsonrpc_result(
        await _post_a2a(
            _jsonrpc_body("What is its population?", context_id=context_id),
            test_auth,
        )
    )
    assert _context_id(second) == context_id

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
async def test_a2a_health_check_returns_healthy_status() -> None:
    """Health check endpoint returns expected structure and healthy status."""
    result = await a2a_endpoint.a2a_health_check()

    assert result["status"] == "healthy"
    assert result["service"] == "lightspeed-a2a"
    assert "version" in result
    assert result["version"]
    assert "a2a_sdk_version" in result
    assert result["a2a_sdk_version"]
    assert "timestamp" in result
    assert result["timestamp"]


@pytest.mark.parametrize(
    "endpoint_path",
    [
        "/.well-known/agent.json",
        "/.well-known/agent-card.json",
    ],
)
def test_agent_card_endpoints_return_same_card(
    integration_http_client: TestClient,
    endpoint_path: str,
) -> None:
    """Both agent card endpoints return identical agent card based on _AGENT_CARD_CONFIG.

    Issues an actual HTTP request through the ASGI app for each
    ``endpoint_path`` so both route registrations (and FastAPI's routing to
    the shared ``get_agent_card`` handler) are exercised, not just the
    handler function in isolation.
    """
    response = integration_http_client.get(endpoint_path)

    assert response.status_code == status.HTTP_200_OK
    agent_card = response.json()

    assert agent_card["name"] == _AGENT_CARD_CONFIG["name"]
    assert agent_card["description"] == _AGENT_CARD_CONFIG["description"]
    assert agent_card["protocolVersion"] == _AGENT_CARD_CONFIG["protocolVersion"]

    assert agent_card["provider"] is not None
    assert (
        agent_card["provider"]["organization"]
        == _AGENT_CARD_CONFIG["provider"]["organization"]
    )
    assert agent_card["provider"]["url"] == _AGENT_CARD_CONFIG["provider"]["url"]

    assert len(agent_card["skills"]) == len(_AGENT_CARD_CONFIG["skills"])
    assert agent_card["skills"][0]["id"] == _AGENT_CARD_CONFIG["skills"][0]["id"]
    assert agent_card["skills"][0]["name"] == _AGENT_CARD_CONFIG["skills"][0]["name"]
    assert (
        agent_card["skills"][0]["description"]
        == _AGENT_CARD_CONFIG["skills"][0]["description"]
    )

    assert agent_card["capabilities"] is not None
    assert (
        agent_card["capabilities"]["streaming"]
        == _AGENT_CARD_CONFIG["capabilities"]["streaming"]
    )
    assert (
        agent_card["capabilities"]["pushNotifications"]
        == _AGENT_CARD_CONFIG["capabilities"]["pushNotifications"]
    )
    assert (
        agent_card["capabilities"]["stateTransitionHistory"]
        == _AGENT_CARD_CONFIG["capabilities"]["stateTransitionHistory"]
    )


@pytest.mark.asyncio
async def test_message_stream_with_metadata_returns_streaming_response(
    mock_ogx_client: Any,
    test_auth: AuthTuple,
    mocker: MockerFixture,
) -> None:
    """message/stream with metadata returns the expected stream and model routing."""
    mock_ogx_client.openai.list.return_value = make_openai_models_list_response(
        make_openai_model(model_id="together/llama3.1", provider_id="together"),
    )
    build_agent = _install_agent(mocker, "Response with metadata")

    response = await _post_a2a(
        _jsonrpc_body(
            "What is a pod?",
            method="message/stream",
            metadata={"model": "llama3.1", "provider": "together"},
        ),
        test_auth,
    )

    assert isinstance(response, StreamingResponse)
    results = await _collect_stream_results(response)

    assert any(_task_state(result) == "completed" for result in results)
    assert _stream_artifact_text(results) == "Response with metadata"
    assert build_agent.call_args.args[1].model == "together/llama3.1"
