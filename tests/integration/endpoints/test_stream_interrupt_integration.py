"""Integration tests for the streaming query interrupt lifecycle."""

import asyncio
from collections.abc import Generator

import pytest
from fastapi import HTTPException

from app.endpoints.stream_interrupt import stream_interrupt_endpoint_handler
from models.requests import StreamingInterruptRequest
from utils.stream_interrupts import StreamInterruptRegistry

TEST_REQUEST_ID = "123e4567-e89b-12d3-a456-426614174003"
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
    registry: StreamInterruptRegistry,
) -> None:
    """Full lifecycle: register, interrupt, then verify deregistration."""
    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(TEST_REQUEST_ID, OWNER_USER_ID, task)

    assert registry.get_stream(TEST_REQUEST_ID) is not None

    response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=TEST_REQUEST_ID),
        auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
        registry=registry,
    )
    assert response.interrupted is True

    with pytest.raises(asyncio.CancelledError):
        await task

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
