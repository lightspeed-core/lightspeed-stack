"""Unit tests for streaming query interrupt endpoint."""

import asyncio

import pytest
from fastapi import HTTPException

from app.endpoints.stream_interrupt import stream_interrupt_endpoint_handler
from models.requests import StreamingInterruptRequest
from models.responses import StreamingInterruptResponse
from utils.stream_interrupts import StreamInterruptRegistry


@pytest.fixture(name="registry")
def registry_fixture() -> StreamInterruptRegistry:
    """Provide a fresh, isolated registry for each test."""
    return StreamInterruptRegistry()


@pytest.mark.asyncio
async def test_stream_interrupt_endpoint_success(
    registry: StreamInterruptRegistry,
) -> None:
    """Interrupt endpoint cancels an active stream for the same user."""
    request_id = "123e4567-e89b-12d3-a456-426614174000"
    user_id = "00000001-0001-0001-0001-000000000001"

    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(request_id, user_id, task)

    response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=request_id),
        auth=(user_id, "mock_username", False, "mock_token"),
        registry=registry,
    )

    assert isinstance(response, StreamingInterruptResponse)
    assert response.request_id == request_id
    assert response.interrupted is True

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_stream_interrupt_endpoint_not_found(
    registry: StreamInterruptRegistry,
) -> None:
    """Interrupt endpoint returns 404 for unknown request id."""
    request_id = "123e4567-e89b-12d3-a456-426614174001"

    with pytest.raises(HTTPException) as exc_info:
        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=request_id),
            auth=(
                "00000001-0001-0001-0001-000000000001",
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
    request_id = "123e4567-e89b-12d3-a456-426614174002"

    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(
        request_id=request_id,
        user_id="00000001-0001-0001-0001-000000000001",
        task=task,
    )

    with pytest.raises(HTTPException) as exc_info:
        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=request_id),
            auth=(
                "00000001-0001-0001-0001-000000000999",
                "mock_username",
                False,
                "mock_token",
            ),
            registry=registry,
        )

    assert exc_info.value.status_code == 404
    assert task.done() is False

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
