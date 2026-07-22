"""Stream interrupt registry and persistence utilities."""

import asyncio
import datetime
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Optional, cast

from ogx_api import OpenAIResponseMessage

from constants import (
    INTERRUPTED_RESPONSE_MESSAGE,
    TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS,
)
from log import get_logger
from models.common.responses.contexts import ResponseGeneratorContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from models.common.turn_summary import TurnSummary
from utils.conversations import append_turn_items_to_conversation
from utils.markdown_repair import close_open_markdown
from utils.query import store_query_results, update_conversation_topic_summary
from utils.responses import get_topic_summary
from utils.shields import append_turn_to_conversation
from utils.types import Singleton

logger = get_logger(__name__)


@dataclass
class ActiveStream:
    """Represents one active streaming request bound to a user.

    Attributes:
        user_id: Owner of the streaming request.
        task: Asyncio task producing the stream response.
        on_interrupt: Optional async callback invoked when the stream
            is cancelled, scheduled as a separate task so it runs
            regardless of where the ``CancelledError`` lands.
    """

    user_id: str
    task: asyncio.Task[None]
    on_interrupt: Optional[Callable[[], Coroutine[Any, Any, None]]] = field(
        default=None, repr=False
    )


class CancelStreamResult(str, Enum):
    """Outcomes when attempting to cancel a stream."""

    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    ALREADY_DONE = "already_done"


class StreamInterruptRegistry(metaclass=Singleton):
    """Registry for active streaming tasks keyed by request ID."""

    def __init__(self) -> None:
        """Initialize an empty registry with a lock for thread-safety."""
        self._streams: dict[str, ActiveStream] = {}
        self._lock = Lock()

    def register_stream(
        self,
        request_id: str,
        user_id: str,
        task: asyncio.Task[None],
        on_interrupt: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
    ) -> None:
        """Register an active stream task for interrupt support.

        Parameters:
        ----------
            request_id: Unique streaming request identifier.
            user_id: User identifier that owns the stream.
            task: Asyncio task associated with the stream.
            on_interrupt: Optional async callback to run when the stream
                is cancelled, executed in a separate task.
        """
        with self._lock:
            self._streams[request_id] = ActiveStream(
                user_id=user_id, task=task, on_interrupt=on_interrupt
            )

    def cancel_stream(self, request_id: str, user_id: str) -> CancelStreamResult:
        """Cancel an active stream owned by user.

        The entire lookup-check-cancel sequence is performed under the
        lock so that a concurrent ``deregister_stream`` cannot remove
        the entry between the ownership check and the cancel call.

        When an ``on_interrupt`` callback was registered, it is
        scheduled as a **separate** asyncio task after the cancel so
        persistence runs regardless of where the ``CancelledError``
        is raised (inside the generator or in Starlette's send).

        Parameters:
        ----------
            request_id: Unique streaming request identifier.
            user_id: User identifier attempting the interruption.

        Returns:
        -------
            CancelStreamResult: Structured cancellation result.
        """
        on_interrupt = None
        with self._lock:
            stream = self._streams.get(request_id)
            if stream is None:
                return CancelStreamResult.NOT_FOUND
            if stream.user_id != user_id:
                logger.warning(
                    "User %s attempted to interrupt request %s owned by another user",
                    user_id,
                    request_id,
                )
                return CancelStreamResult.FORBIDDEN
            if stream.task.done():
                return CancelStreamResult.ALREADY_DONE
            stream.task.cancel()
            on_interrupt = stream.on_interrupt

        if on_interrupt is not None:
            asyncio.get_running_loop().create_task(on_interrupt())

        return CancelStreamResult.CANCELLED

    def deregister_stream(self, request_id: str) -> None:
        """Remove stream task from registry once completed/cancelled.

        Parameters:
        ----------
            request_id: Unique streaming request identifier.
        """
        with self._lock:
            self._streams.pop(request_id, None)

    def get_stream(self, request_id: str) -> Optional[ActiveStream]:
        """Get currently registered stream metadata for tests/introspection.

        Parameters:
        ----------
            request_id: Unique streaming request identifier.

        Returns:
        -------
            Optional[ActiveStream]: Registered stream metadata, or None when absent.
        """
        with self._lock:
            return self._streams.get(request_id)


def get_stream_interrupt_registry() -> StreamInterruptRegistry:
    """Return the module-level interrupt registry.

    Exposed as a callable so it can be used as a FastAPI dependency
    and overridden in tests via ``app.dependency_overrides``.
    """
    return StreamInterruptRegistry()


def deregister_stream(request_id: str) -> None:
    """Remove a stream from the interrupt registry after completion or cancellation.

    Parameters:
    ----------
        request_id: Unique streaming request identifier.
    """
    get_stream_interrupt_registry().deregister_stream(request_id)


async def background_update_topic_summary(
    context: ResponseGeneratorContext,
    model: str,
) -> None:
    """Generate topic summary and update DB/cache in the background.

    Runs as a fire-and-forget task after an interrupted turn is persisted.
    All errors are caught and logged.

    Parameters:
    ----------
        context: The response generator context.
        model: Model identifier used for topic summary generation.
    """
    try:
        topic_summary = await asyncio.wait_for(
            get_topic_summary(
                context.query_request.query,
                context.client,
                model,
            ),
            timeout=TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS,
        )
        if topic_summary:
            update_conversation_topic_summary(
                context.conversation_id,
                topic_summary,
                user_id=context.user_id,
                skip_userid_check=context.skip_userid_check,
            )
    except asyncio.TimeoutError:
        logger.warning(
            "Topic summary timed out for interrupted turn, request %s",
            context.request_id,
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to generate topic summary for interrupted turn, request %s",
            context.request_id,
        )


def build_interrupted_response(partial_tokens: list[str]) -> tuple[str, str]:
    """Build the final interrupted response text from accumulated tokens.

    Joins partial tokens, repairs any open markdown constructs, and appends
    an italicized interruption indicator.

    Parameters:
        partial_tokens: List of text deltas accumulated during streaming.

    Returns:
        A tuple of (full_response_text, suffix_to_emit) where full_response_text
        is the complete message for persistence and suffix_to_emit is the new
        content to send as a final SSE token event.
    """
    partial_text = "".join(partial_tokens)
    repaired_text = close_open_markdown(partial_text)
    interrupted_indicator = f"\n\n*{INTERRUPTED_RESPONSE_MESSAGE}*"
    suffix = repaired_text + interrupted_indicator
    final_text = partial_text + suffix
    return final_text, suffix


async def persist_interrupted_turn(
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
    background_topic_summary_tasks: list[asyncio.Task[None]],
    original_input: Optional[ResponseInput] = None,
) -> None:
    """Persist the user query and an interrupted response into the conversation.

    Called when a streaming request is cancelled so the exchange is not lost.
    Persists immediately with topic_summary=None so the conversation exists
    when the client fetches. Topic summary is generated in a background task
    and updated when ready.

    Parameters:
    ----------
        context: The response generator context.
        responses_params: The Responses API parameters.
        turn_summary: TurnSummary with llm_response already set to the
            interrupted message.
        background_topic_summary_tasks: Mutable list tracking fire-and-forget
            topic summary tasks for graceful shutdown.
        original_input: In compacted mode, the original user input before the
            explicit-input rewrite. When set, the turn is persisted against it
            (the ``conversation`` parameter was dropped, and
            ``responses_params.input`` is the explicit rewrite); ``None``
            otherwise (LCORE-1572).
    """
    try:
        if original_input is not None:
            await append_turn_items_to_conversation(
                context.client,
                responses_params.conversation,
                original_input,
                [
                    OpenAIResponseMessage(
                        role="assistant", content=turn_summary.llm_response
                    )
                ],
            )
        else:
            await append_turn_to_conversation(
                context.client,
                responses_params.conversation,
                cast(str, responses_params.input),
                turn_summary.llm_response,
            )
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to append interrupted turn to conversation for request %s",
            context.request_id,
        )

    try:
        completed_at = datetime.datetime.now(datetime.UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        store_query_results(
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            model=responses_params.model,
            completed_at=completed_at,
            started_at=context.started_at,
            summary=turn_summary,
            query=context.query_request.query,
            skip_userid_check=context.skip_userid_check,
            topic_summary=None,
        )

        if (
            not context.query_request.conversation_id
            and context.query_request.generate_topic_summary
        ):
            task = asyncio.create_task(
                background_update_topic_summary(
                    context=context,
                    model=responses_params.model,
                )
            )
            background_topic_summary_tasks.append(task)
            task.add_done_callback(background_topic_summary_tasks.remove)
    except Exception:  # pylint: disable=broad-except
        logger.exception(
            "Failed to store interrupted query results for request %s",
            context.request_id,
        )


def register_interrupt_callback(
    context: ResponseGeneratorContext,
    responses_params: ResponsesApiParams,
    turn_summary: TurnSummary,
    background_topic_summary_tasks: list[asyncio.Task[None]],
    original_input: Optional[ResponseInput] = None,
) -> list[bool]:
    """Build an interrupt callback and register the stream for cancellation.

    The callback is invoked by ``cancel_stream`` when the client
    interrupts, so persistence runs regardless of where the
    ``CancelledError`` is raised in the ASGI stack.

    A mutable one-element list is used as a shared guard so the
    callback and the in-generator ``CancelledError`` handler never
    both persist the same turn.

    Parameters:
    ----------
        context: The response generator context.
        responses_params: The Responses API parameters.
        turn_summary: TurnSummary populated during streaming.
        background_topic_summary_tasks: Mutable list tracking fire-and-forget
            topic summary tasks for graceful shutdown.
        original_input: In compacted mode, the original user input before the
            explicit-input rewrite; ``None`` otherwise.

    Returns:
    -------
        A mutable list ``[False]`` used as a persist-done guard; the
        caller should check ``guard[0]`` before persisting and set
        it to ``True`` afterwards.
    """
    guard: list[bool] = [False]

    async def _on_interrupt() -> None:
        if guard[0]:
            return
        guard[0] = True
        full_text, _ = build_interrupted_response(turn_summary.partial_tokens)
        turn_summary.llm_response = full_text
        await persist_interrupted_turn(
            context,
            responses_params,
            turn_summary,
            background_topic_summary_tasks,
            original_input,
        )

    current_task = asyncio.current_task()
    if current_task is not None:
        get_stream_interrupt_registry().register_stream(
            request_id=context.request_id,
            user_id=context.user_id,
            task=current_task,
            on_interrupt=_on_interrupt,
        )
    else:
        logger.warning(
            "No current asyncio task for request %s; "
            "stream interruption will not be available",
            context.request_id,
        )

    return guard
