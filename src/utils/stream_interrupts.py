"""Stream interrupt registry and persistence utilities."""

import asyncio
import datetime
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Optional

from pydantic_ai import CancellationToken

from constants import (
    INTERRUPTED_RESPONSE_MESSAGE,
    TOPIC_SUMMARY_INTERRUPT_TIMEOUT_SECONDS,
)
from log import get_logger
from models.common.responses.contexts import ResponseGeneratorContext
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.turn_summary import TurnSummary
from utils.markdown_repair import close_open_markdown
from utils.pending_turn import PendingTurn
from utils.query import store_query_results, update_conversation_topic_summary
from utils.responses import get_topic_summary
from utils.types import Singleton

logger = get_logger(__name__)


@dataclass
class ActiveStream:
    """Represents one active streaming request bound to a user.

    Attributes:
        user_id: Owner of the streaming request.
        token: Cancellation token of the agent run producing the stream.
        conversation_id: Conversation the streaming request belongs to,
            surfaced for observability of interrupt requests.

    """

    user_id: str
    token: CancellationToken
    conversation_id: Optional[str] = None


class CancelStreamResult(StrEnum):
    """Outcomes when attempting to cancel a stream."""

    CANCELLED = "cancelled"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    ALREADY_DONE = "already_done"


class StreamInterruptRegistry(metaclass=Singleton):
    """Ownership and cancellation index of active streams keyed by request ID."""

    def __init__(self) -> None:
        """Initialize an empty registry with a lock for thread-safety."""
        self._streams: dict[str, ActiveStream] = {}
        self._lock = Lock()

    def register_stream(
        self,
        request_id: str,
        user_id: str,
        token: CancellationToken,
        conversation_id: Optional[str] = None,
    ) -> None:
        """Register an active stream for interrupt support.

        Parameters:
        ----------
            request_id: Unique streaming request identifier.
            user_id: User identifier that owns the stream.
            token: Cancellation token passed to the agent run of the stream.
            conversation_id: Conversation the stream belongs to, retained
                for observability of subsequent interrupt requests.

        """
        with self._lock:
            self._streams[request_id] = ActiveStream(
                user_id=user_id,
                token=token,
                conversation_id=conversation_id,
            )

    def cancel_stream(self, request_id: str, user_id: str) -> CancelStreamResult:
        """Cancel the token of an active stream owned by user.

        The entire lookup-check-cancel sequence is performed under the
        lock so that a concurrent ``deregister_stream`` cannot remove
        the entry between the ownership check and the cancel call, and
        so that only one caller sees a token flip to cancelled.
        Cancelling the token asks the agent run to stop; the streaming
        request itself finalizes the interrupted turn. PAI ignores a
        cancel once the run has finished, so an entry that is still
        registered after its run completed also returns ``CANCELLED``;
        the streaming request should deregister as soon as its agent
        run ends.

        Parameters:
        ----------
            request_id: Unique streaming request identifier.
            user_id: User identifier attempting the interruption.

        Returns:
        -------
            CancelStreamResult: ``NOT_FOUND`` for an unknown request,
            ``FORBIDDEN`` when another user owns it, ``ALREADY_DONE``
            when its token was already cancelled, ``CANCELLED`` otherwise.

        """
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
            if stream.token.cancelled:
                return CancelStreamResult.ALREADY_DONE
            stream.token.cancel()
        return CancelStreamResult.CANCELLED

    def deregister_stream(self, request_id: str) -> None:
        """Remove stream from registry once completed/cancelled.

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
    except TimeoutError:
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
    turn: Optional[PendingTurn] = None,
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
        turn: The pending turn of the request, which stores the turn against
            the input as it arrived and does so once (LCORE-3908). Required in
            compacted mode; created from the parameters otherwise.

    Raises:
    ------
        ValueError: When the request is compacted and no pending turn is given.

    """
    if turn is None:
        turn = PendingTurn.for_request(context.client, responses_params)
    try:
        await turn.store_interrupted(turn_summary.llm_response)
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
