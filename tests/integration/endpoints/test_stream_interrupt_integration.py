"""Integration tests for the streaming query interrupt lifecycle."""

import asyncio
import json
from collections.abc import AsyncIterator, Generator
from typing import Any

import pytest
from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic_ai import CancellationToken
from pydantic_ai.messages import PartStartEvent, TextPart
from pytest_mock import AsyncMockType
from sqlalchemy.orm import Session

from app.endpoints.stream_interrupt import stream_interrupt_endpoint_handler
from app.endpoints.streaming_query import streaming_query_endpoint_handler
from authentication.interface import AuthTuple
from configuration import AppConfig
from models.api.requests import QueryRequest, StreamingInterruptRequest
from utils.stream_interrupts import StreamInterruptRegistry

TEST_REQUEST_ID = "123e4567-e89b-12d3-a456-426614174003"
REQUEST_ID_NOT_IN_REGISTRY = "00000000-0000-0000-0000-000000000000"
OWNER_USER_ID = "00000001-0001-0001-0001-000000000001"


@pytest.fixture(name="registry")
def registry_fixture() -> Generator[StreamInterruptRegistry, None, None]:
    """Provide singleton registry with deterministic per-test cleanup."""
    registry = StreamInterruptRegistry()
    registry.deregister_stream(TEST_REQUEST_ID)
    yield registry
    registry.deregister_stream(TEST_REQUEST_ID)


@pytest.mark.asyncio
async def test_stream_interrupt_full_round_trip(
    test_config: AppConfig,
    registry: StreamInterruptRegistry,
) -> None:
    """Full lifecycle: register, interrupt, then verify deregistration."""
    # test_config loads configuration so @authorize on the handler can resolve.
    _ = test_config

    token = CancellationToken()
    registry.register_stream(TEST_REQUEST_ID, OWNER_USER_ID, token)

    assert registry.get_stream(TEST_REQUEST_ID) is not None

    response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=TEST_REQUEST_ID),
        auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
        registry=registry,
    )
    assert response.interrupted is True
    assert token.cancelled is True

    completed_response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=TEST_REQUEST_ID),
        auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
        registry=registry,
    )
    assert completed_response.interrupted is False

    registry.deregister_stream(TEST_REQUEST_ID)
    assert registry.get_stream(TEST_REQUEST_ID) is None

    with pytest.raises(HTTPException) as exc_info:
        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=TEST_REQUEST_ID),
            auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
            registry=registry,
        )
    assert exc_info.value.status_code == 404


def test_stream_interrupt_nonexistent_request_returns_404(
    integration_http_client: TestClient,
) -> None:
    """POST /v1/streaming_query/interrupt for unknown stream returns 404."""
    response = integration_http_client.post(
        "/v1/streaming_query/interrupt",
        json={"request_id": REQUEST_ID_NOT_IN_REGISTRY},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def _stream_that_stalls(release: asyncio.Event) -> Any:
    """Build an agent stream that sends one token and then waits to be released."""

    async def _events() -> AsyncIterator[Any]:
        yield PartStartEvent(index=0, part=TextPart(content="Partial"))
        await release.wait()

    class _RunStreamCtx:
        """Async context manager matching ``agent.run_stream_events``."""

        async def __aenter__(self) -> AsyncIterator[Any]:
            return _events()

        async def __aexit__(self, *_args: object) -> None:
            return None

    return _RunStreamCtx()


@pytest.mark.asyncio
async def test_running_stream_is_registered_and_its_token_cancelled_by_the_endpoint(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    test_config: AppConfig,
    mock_ogx_client: AsyncMockType,
    mock_streaming_query_agent: AsyncMockType,
    test_request: Request,
    test_auth: AuthTuple,
    patch_db_session: Session,
) -> None:
    """A live /v1/streaming_query run is in the registry under the id its start event
    carries, the interrupt endpoint cancels its token, and the entry is gone once the
    stream ends (LCORE-4733)."""
    _ = (test_config, mock_ogx_client, patch_db_session)
    release = asyncio.Event()
    mock_streaming_query_agent.run_stream_events.return_value = _stream_that_stalls(
        release
    )

    response = await streaming_query_endpoint_handler(
        request=test_request,
        query_request=QueryRequest(
            query="Say hello"
        ),  # pyright: ignore[reportCallIssue]
        auth=test_auth,
        mcp_headers={},
    )
    assert isinstance(response, StreamingResponse)
    chunks: list[str] = []
    first_token = asyncio.Event()

    async def _consume() -> None:
        async for chunk in response.body_iterator:
            chunks.append(str(chunk))
            if '"event": "token"' in str(chunk):
                first_token.set()

    consumer = asyncio.create_task(_consume())
    try:
        await asyncio.wait_for(first_token.wait(), timeout=5)
        request_id = json.loads(chunks[0].removeprefix("data: "))["data"]["request_id"]
        registry = StreamInterruptRegistry()
        active = registry.get_stream(request_id)
        assert active is not None
        assert active.user_id == test_auth[0]
        assert active.token.cancelled is False

        interrupt = await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=request_id),
            auth=test_auth,
            registry=registry,
        )

        assert interrupt.interrupted is True
        assert active.token.cancelled is True
        # The run is passed the same token, so a real agent would stop here.
        passed = mock_streaming_query_agent.run_stream_events.call_args.kwargs[
            "cancellation_token"
        ]
        assert passed is active.token
    finally:
        release.set()
        await asyncio.wait_for(consumer, timeout=5)

    assert registry.get_stream(request_id) is None
