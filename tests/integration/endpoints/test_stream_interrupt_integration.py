"""Integration tests for the streaming query interrupt lifecycle."""

import asyncio

import pytest
from fastapi import HTTPException

from app.endpoints.stream_interrupt import stream_interrupt_endpoint_handler
from models.requests import StreamingInterruptRequest
from utils.stream_interrupts import StreamInterruptRegistry


@pytest.fixture(name="registry")
def registry_fixture() -> StreamInterruptRegistry:
    """Provide a fresh, isolated registry for each test."""
    return StreamInterruptRegistry()


@pytest.mark.asyncio
async def test_stream_interrupt_full_round_trip(
    registry: StreamInterruptRegistry,
) -> None:
    """Full lifecycle: register, interrupt, then verify deregistration."""
    request_id = "123e4567-e89b-12d3-a456-426614174003"
    user_id = "00000001-0001-0001-0001-000000000001"

    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(request_id, user_id, task)

    assert registry.get_stream(request_id) is not None

    response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=request_id),
        auth=(user_id, "mock_username", False, "mock_token"),
        registry=registry,
    )
    assert response.interrupted is True

    with pytest.raises(asyncio.CancelledError):
        await task

    completed_response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=request_id),
        auth=(user_id, "mock_username", False, "mock_token"),
        registry=registry,
    )
    assert completed_response.interrupted is False

    registry.deregister_stream(request_id)
    assert registry.get_stream(request_id) is None

    with pytest.raises(HTTPException) as exc_info:
        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=request_id),
            auth=(user_id, "mock_username", False, "mock_token"),
            registry=registry,
        )
    assert exc_info.value.status_code == 404
