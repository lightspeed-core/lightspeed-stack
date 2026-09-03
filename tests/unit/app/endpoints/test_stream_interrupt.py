"""Unit tests for streaming query interrupt endpoint."""

import asyncio
import threading
from collections.abc import Generator
from typing import Any

import pytest
from fastapi import HTTPException
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode
from pytest_mock import MockerFixture

from app.endpoints.stream_interrupt import stream_interrupt_endpoint_handler
from models.api.requests import StreamingInterruptRequest
from models.api.responses.successful import StreamingInterruptResponse
from utils.stream_interrupts import CancelStreamResult, StreamInterruptRegistry

REQUEST_ID_SUCCESS = "123e4567-e89b-12d3-a456-426614174000"
REQUEST_ID_NOT_FOUND = "123e4567-e89b-12d3-a456-426614174001"
REQUEST_ID_WRONG_USER = "123e4567-e89b-12d3-a456-426614174002"
REQUEST_ID_ALREADY_COMPLETED = "123e4567-e89b-12d3-a456-426614174004"

# CI-friendly sync timeouts for concurrent registry tests.
_CONCURRENT_BARRIER_TIMEOUT_S = 5.0
_CONCURRENT_THREAD_JOIN_TIMEOUT_S = 5.0

OWNER_USER_ID = "00000001-0001-0001-0001-000000000001"
NON_OWNER_USER_ID = "00000001-0001-0001-0001-000000000999"

TEST_REQUEST_IDS = (
    REQUEST_ID_SUCCESS,
    REQUEST_ID_NOT_FOUND,
    REQUEST_ID_WRONG_USER,
    REQUEST_ID_ALREADY_COMPLETED,
)

CONVERSATION_ID = "323e4567-e89b-12d3-a456-426614174777"


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
            interrupt_request=StreamingInterruptRequest(
                request_id=REQUEST_ID_NOT_FOUND
            ),
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
            interrupt_request=StreamingInterruptRequest(
                request_id=REQUEST_ID_WRONG_USER
            ),
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


@pytest.mark.asyncio
async def test_stream_interrupt_registry_concurrent_cancel_and_deregister(
    registry: StreamInterruptRegistry,
) -> None:
    """Concurrent cancel and deregister do not raise under the registry lock."""

    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(REQUEST_ID_SUCCESS, OWNER_USER_ID, task)

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def deregister_in_thread() -> None:
        try:
            barrier.wait(timeout=_CONCURRENT_BARRIER_TIMEOUT_S)
            registry.deregister_stream(REQUEST_ID_SUCCESS)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            errors.append(exc)

    thread = threading.Thread(target=deregister_in_thread)
    thread.start()
    barrier.wait(timeout=_CONCURRENT_BARRIER_TIMEOUT_S)

    result = registry.cancel_stream(REQUEST_ID_SUCCESS, OWNER_USER_ID)
    thread.join(timeout=_CONCURRENT_THREAD_JOIN_TIMEOUT_S)
    assert not thread.is_alive(), "Deregister thread did not complete within timeout"

    assert not errors
    assert result in (
        CancelStreamResult.CANCELLED,
        CancelStreamResult.NOT_FOUND,
    )

    if not task.done():
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_stream_interrupt_endpoint_double_interrupt(
    registry: StreamInterruptRegistry,
) -> None:
    """Second interrupt on the same stream returns interrupted=False."""

    async def pending_stream() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(pending_stream())
    registry.register_stream(REQUEST_ID_SUCCESS, OWNER_USER_ID, task)

    first_response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=REQUEST_ID_SUCCESS),
        auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
        registry=registry,
    )
    assert first_response.interrupted is True

    with pytest.raises(asyncio.CancelledError):
        await task

    second_response = await stream_interrupt_endpoint_handler(
        interrupt_request=StreamingInterruptRequest(request_id=REQUEST_ID_SUCCESS),
        auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
        registry=registry,
    )
    assert second_response.interrupted is False


class TestStreamInterruptOtelSpans:
    """OTEL instrumentation tests for the stream interrupt endpoint."""

    @pytest.mark.asyncio
    async def test_interrupt_success_emits_span_with_attributes(
        self,
        mocker: MockerFixture,
        registry: StreamInterruptRegistry,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """A successful interrupt emits one span with the expected attributes."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.stream_interrupt.tracer", tracer)

        async def pending_stream() -> None:
            await asyncio.sleep(10)

        task = asyncio.create_task(pending_stream())
        registry.register_stream(
            REQUEST_ID_SUCCESS,
            OWNER_USER_ID,
            task,
            conversation_id=CONVERSATION_ID,
        )

        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(request_id=REQUEST_ID_SUCCESS),
            auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
            registry=registry,
        )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.name == "stream.interrupt"

        attrs = dict(span.attributes or {})
        assert attrs["interrupt.request_id"] == REQUEST_ID_SUCCESS
        assert attrs["stream.conversation.id"] == CONVERSATION_ID
        assert attrs["interrupt.result"] == CancelStreamResult.CANCELLED.value
        assert span.status.status_code == StatusCode.OK

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_interrupt_not_found_sets_error_status(
        self,
        mocker: MockerFixture,
        registry: StreamInterruptRegistry,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """An unknown request id records the not_found result and error status."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.stream_interrupt.tracer", tracer)

        with pytest.raises(HTTPException):
            await stream_interrupt_endpoint_handler(
                interrupt_request=StreamingInterruptRequest(
                    request_id=REQUEST_ID_NOT_FOUND
                ),
                auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
                registry=registry,
            )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        attrs = dict(span.attributes or {})
        assert attrs["interrupt.request_id"] == REQUEST_ID_NOT_FOUND
        assert attrs["interrupt.result"] == CancelStreamResult.NOT_FOUND.value
        # No conversation id is recorded when the stream is unknown.
        assert "stream.conversation.id" not in attrs
        assert span.status.status_code == StatusCode.ERROR

    @pytest.mark.asyncio
    async def test_interrupt_wrong_user_sets_error_and_hides_conversation(
        self,
        mocker: MockerFixture,
        registry: StreamInterruptRegistry,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """A non-owner interrupt records forbidden and does not leak conversation id."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.stream_interrupt.tracer", tracer)

        async def pending_stream() -> None:
            await asyncio.sleep(10)

        task = asyncio.create_task(pending_stream())
        registry.register_stream(
            request_id=REQUEST_ID_WRONG_USER,
            user_id=OWNER_USER_ID,
            task=task,
            conversation_id=CONVERSATION_ID,
        )

        with pytest.raises(HTTPException):
            await stream_interrupt_endpoint_handler(
                interrupt_request=StreamingInterruptRequest(
                    request_id=REQUEST_ID_WRONG_USER
                ),
                auth=(NON_OWNER_USER_ID, "mock_username", False, "mock_token"),
                registry=registry,
            )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        attrs = dict(span.attributes or {})
        assert attrs["interrupt.result"] == CancelStreamResult.FORBIDDEN.value
        # A non-owner must not see the stream's conversation id.
        assert "stream.conversation.id" not in attrs
        assert span.status.status_code == StatusCode.ERROR

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_interrupt_already_done_records_ok_status(
        self,
        mocker: MockerFixture,
        registry: StreamInterruptRegistry,
        otel: tuple[Any, InMemorySpanExporter],
    ) -> None:
        """An already-completed stream records already_done with an OK status."""
        tracer, exporter = otel
        mocker.patch("app.endpoints.stream_interrupt.tracer", tracer)

        async def completed_stream() -> None:
            return None

        task = asyncio.create_task(completed_stream())
        await task
        registry.register_stream(
            REQUEST_ID_ALREADY_COMPLETED,
            OWNER_USER_ID,
            task,
            conversation_id=CONVERSATION_ID,
        )

        await stream_interrupt_endpoint_handler(
            interrupt_request=StreamingInterruptRequest(
                request_id=REQUEST_ID_ALREADY_COMPLETED
            ),
            auth=(OWNER_USER_ID, "mock_username", False, "mock_token"),
            registry=registry,
        )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        attrs = dict(span.attributes or {})
        assert attrs["interrupt.result"] == CancelStreamResult.ALREADY_DONE.value
        assert attrs["stream.conversation.id"] == CONVERSATION_ID
        assert span.status.status_code == StatusCode.OK
