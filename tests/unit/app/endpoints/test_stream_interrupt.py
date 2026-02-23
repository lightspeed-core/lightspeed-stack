"""Unit tests for streaming query interrupt endpoint."""

import asyncio
from collections.abc import Generator

import pytest
from fastapi import HTTPException

from app.endpoints.stream_interrupt import stream_interrupt_endpoint_handler
from models.requests import StreamingInterruptRequest
from models.responses import StreamingInterruptResponse
from utils.stream_interrupts import StreamInterruptRegistry

REQUEST_ID_SUCCESS = "123e4567-e89b-12d3-a456-426614174000"
REQUEST_ID_NOT_FOUND = "123e4567-e89b-12d3-a456-426614174001"
REQUEST_ID_WRONG_USER = "123e4567-e89b-12d3-a456-426614174002"
REQUEST_ID_ALREADY_COMPLETED = "123e4567-e89b-12d3-a456-426614174004"

OWNER_USER_ID = "00000001-0001-0001-0001-000000000001"
NON_OWNER_USER_ID = "00000001-0001-0001-0001-000000000999"

TEST_REQUEST_IDS = (
    REQUEST_ID_SUCCESS,
    REQUEST_ID_NOT_FOUND,
    REQUEST_ID_WRONG_USER,
    REQUEST_ID_ALREADY_COMPLETED,
)


@pytest.fixture(name="registry")
def registry_fixture() -> Generator[StreamInterruptRegistry, None, None]:
    """Provide singleton registry with deterministic per-test cleanup."""
    registry = StreamInterruptRegistry()
    for request_id in TEST_REQUEST_IDS:
        registry.deregister_stream(request_id)
    yield registry
    for request_id in TEST_REQUEST_IDS:
        registry.deregister_stream(request_id)


@pytest.mark.asyncio
async def test_stream_interrupt_endpoint_success(
    registry: StreamInterruptRegistry,
) -> None:
    """Interrupt endpoint cancels an active stream for the same user."""
    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(REQUEST_ID_SUCCESS, OWNER_USER_ID, task)

    response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=REQUEST_ID_SUCCESS),
        auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
        registry=registry,
    )

    assert isinstance(response, StreamingInterruptResponse)
    assert response.request_id == REQUEST_ID_SUCCESS
    assert response.interrupted is True

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_stream_interrupt_endpoint_not_found(
    registry: StreamInterruptRegistry,
) -> None:
    """Interrupt endpoint returns 404 for unknown request id."""
    with pytest.raises(HTTPException) as exc_info:
        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=REQUEST_ID_NOT_FOUND),
            auth=(
                OWNER_USER_ID,
                "mock_username",
                False,
                "mock_token",
            ),
            registry=registry,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_interrupt_endpoint_wrong_user(
    registry: StreamInterruptRegistry,
) -> None:
    """Interrupt endpoint does not cancel streams owned by other users."""
    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(
        request_id=REQUEST_ID_WRONG_USER,
        user_id=OWNER_USER_ID,
        task=task,
    )

    with pytest.raises(HTTPException) as exc_info:
        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=REQUEST_ID_WRONG_USER),
            auth=(
                NON_OWNER_USER_ID,
                "mock_username",
                False,
                "mock_token",
            ),
            registry=registry,
        )

    assert exc_info.value.status_code == 403
    assert task.done() is False

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_stream_interrupt_endpoint_already_completed(
    registry: StreamInterruptRegistry,
) -> None:
    """Interrupt endpoint reports already-completed streams without error."""
    async def completed_stream() -> None:
        return None

    task = asyncio.create_task(completed_stream())
    await task
    registry.register_stream(REQUEST_ID_ALREADY_COMPLETED, OWNER_USER_ID, task)

    response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(
            request_id=REQUEST_ID_ALREADY_COMPLETED
        ),
        auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
        registry=registry,
    )

    assert isinstance(response, StreamingInterruptResponse)
    assert response.request_id == REQUEST_ID_ALREADY_COMPLETED
    assert response.interrupted is False
