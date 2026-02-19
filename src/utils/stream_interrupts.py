"""In-memory registry for interrupting active streaming requests."""

import asyncio
from dataclasses import dataclass
from threading import Lock
from log import get_logger

logger = get_logger(__name__)


@dataclass
class ActiveStream:
    """Represents one active streaming request bound to a user.

    Attributes:
        user_id: Owner of the streaming request.
        task: Asyncio task producing the stream response.
    """

    user_id: str
    task: asyncio.Task[None]


class StreamInterruptRegistry:
    """Registry for active streaming tasks keyed by request ID."""

    def __init__(self) -> None:
        """Initialize an empty registry with a lock for thread-safety."""
        self._streams: dict[str, ActiveStream] = {}
        self._lock = Lock()

    def register_stream(
        self, request_id: str, user_id: str, task: asyncio.Task
    ) -> None:
        """Register an active stream task for interrupt support.

        Parameters:
            request_id: Unique streaming request identifier.
            user_id: User identifier that owns the stream.
            task: Asyncio task associated with the stream.
        """
        with self._lock:
            self._streams[request_id] = ActiveStream(user_id=user_id, task=task)

    def cancel_stream(self, request_id: str, user_id: str) -> bool:
        """Cancel an active stream owned by user.

        The entire lookup-check-cancel sequence is performed under the
        lock so that a concurrent ``deregister_stream`` cannot remove
        the entry between the ownership check and the cancel call.

        Parameters:
            request_id: Unique streaming request identifier.
            user_id: User identifier attempting the interruption.

        Returns:
            bool: True when cancellation was requested, otherwise False.
        """
        with self._lock:
            stream = self._streams.get(request_id)
            if stream is None:
                return False
            if stream.user_id != user_id:
                logger.warning(
                    "User %s attempted to interrupt request %s owned by another user",
                    user_id,
                    request_id,
                )
                return False
            if stream.task.done():
                return False
            stream.task.cancel()
            return True

    def deregister_stream(self, request_id: str) -> None:
        """Remove stream task from registry once completed/cancelled.

        Parameters:
            request_id: Unique streaming request identifier.
        """
        with self._lock:
            self._streams.pop(request_id, None)

    def get_stream(self, request_id: str) -> ActiveStream | None:
        """Get currently registered stream metadata for tests/introspection.

        Parameters:
            request_id: Unique streaming request identifier.

        Returns:
            ActiveStream | None: Registered stream metadata, or None when absent.
        """
        with self._lock:
            return self._streams.get(request_id)


stream_interrupt_registry = StreamInterruptRegistry()


def get_stream_interrupt_registry() -> StreamInterruptRegistry:
    """Return the module-level interrupt registry.

    Exposed as a callable so it can be used as a FastAPI dependency
    and overridden in tests via ``app.dependency_overrides``.
    """
    return stream_interrupt_registry
