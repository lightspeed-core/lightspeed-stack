"""The owner of the turns lightspeed-stack has to store itself (LCORE-3908).

OGX appends a turn to the conversation only when it is handed the
``conversation`` parameter and runs the inference. In every other case the turn
is lightspeed-stack's to store:

* the conversation is served in compacted mode, where the ``conversation``
  parameter is dropped in favor of explicit input (LCORE-1572),
* the request continues from a ``previous_response_id``,
* a shield blocked the request, so OGX was never called,
* the client interrupted the stream, so the OGX call was cancelled.

When that write goes missing nothing fails: the conversation just stops
growing, and the model loses the turn on the next request (LCORE-3883). So the
write has one owner, :class:`PendingTurn`. It decides whether lightspeed-stack
has to store the turn and which input is stored, and it stores a turn once,
regardless of how many callers ask.

A request served in compacted mode that reaches the end of its handler without
anyone having tried to store its turn, or having dropped it on purpose, fails:
:meth:`PendingTurn.ensure_settled` raises :class:`TurnNotStoredError`. Three
endings are not covered by that check and store nothing: a stream the client
stops reading, a ``/v1/responses`` stream without a final response, and a write
that fails where the failure is logged.

The shield capabilities (``pydantic_ai_lightspeed.capabilities``) are the one
writer outside this module. They store the turn they rejected from inside the
agent run, and only when the model was handed the conversation, so never in
compacted mode.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional

from ogx_api import OpenAIResponseOutput
from ogx_api.openai_responses import OpenAIResponseMessage
from ogx_client import AsyncOgxClient

from log import get_logger
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from utils.conversations import append_turn_items_to_conversation

logger = get_logger(__name__)


class TurnNotStoredError(Exception):
    """Nobody tried to store a turn lightspeed-stack has to store, or dropped it.

    Deliberately not a ``RuntimeError``: the endpoints catch that one around
    the model call and report it as an inference failure, which this is not.
    """


@dataclass
class PendingTurn:
    """The turn of the request being served, until it is settled.

    A turn is settled by the first of :meth:`store_completed`,
    :meth:`store_blocked`, :meth:`store_interrupted` and :meth:`drop` that is
    called. Every later call does nothing, so the write happens once when
    several paths of a request want it (the end of a stream, the cancellation
    handler, the interrupt callback).

    Attributes:
        client: OGX client used for the write.
        conversation_id: Conversation the turn belongs to (OGX format).
        user_input: The input as it arrived. This is what is stored as the
            user's side of the turn; in compacted mode it differs from
            ``params.input``, which holds the explicit rewrite.
        store: Whether the request wants its turn stored at all.
        left_to_ogx: Whether OGX stores a completed turn itself, which it does
            when it gets the ``conversation`` parameter.
        outcome: How the turn was settled; ``None`` while it is pending. A
            write that failed is recorded as ``failed: <outcome>``.
    """

    client: AsyncOgxClient
    conversation_id: str
    user_input: ResponseInput
    store: bool = True
    left_to_ogx: bool = False
    outcome: Optional[str] = field(default=None, init=False)

    @classmethod
    def for_request(
        cls,
        client: AsyncOgxClient,
        params: ResponsesApiParams,
        original_input: Optional[ResponseInput] = None,
    ) -> "PendingTurn":
        """Create the pending turn of a request from its prepared parameters.

        Parameters:
            client: OGX client used for the write.
            params: The parameters the request is sent with, after compaction
                was applied.
            original_input: The input before the explicit-input rewrite, as
                the compaction result carries it. Required in compacted mode.

        Returns:
            The pending turn of the request.

        Raises:
            ValueError: When the request is compacted and its original input
                is missing; the turn could then only be stored against the
                explicit rewrite, which would write the summaries and the
                replayed history into the conversation.
        """
        if not params.omit_conversation:
            return cls(
                client=client,
                conversation_id=params.conversation,
                user_input=params.input,
                store=params.store,
                left_to_ogx=not params.previous_response_id,
            )
        if original_input is None:
            raise ValueError(
                "a request served in compacted mode needs its original input "
                "to store the turn"
            )
        return cls(
            client=client,
            conversation_id=params.conversation,
            user_input=original_input,
            store=params.store,
        )

    @property
    def settled(self) -> bool:
        """Whether the turn has been taken care of.

        That is the case once a write was attempted, whether or not it
        succeeded, or the turn was left to OGX or left out on purpose.
        """
        return self.outcome is not None

    @property
    def ours(self) -> bool:
        """Whether lightspeed-stack has to store the turn when it completes."""
        return self.store and not self.left_to_ogx

    async def store_completed(
        self, output_items: Sequence[OpenAIResponseOutput]
    ) -> bool:
        """Store a completed turn, unless OGX stores it.

        Parameters:
            output_items: The output items of the turn, as OGX returned them.

        Returns:
            Whether this call stored the turn.

        Raises:
            HTTPException: When the write fails.
        """
        if self.left_to_ogx:
            self._settle("left to OGX")
            return False
        return await self._store("completed", output_items)

    async def store_blocked(self, refusal: OpenAIResponseMessage) -> bool:
        """Store the turn of a request a shield blocked.

        Parameters:
            refusal: The refusal message returned in place of an answer.

        Returns:
            Whether this call stored the turn.

        Raises:
            HTTPException: When the write fails.
        """
        return await self._store("blocked", [refusal])

    async def store_interrupted(self, partial_response: str) -> bool:
        """Store the turn of a stream the client interrupted.

        Parameters:
            partial_response: The part of the answer that was received, with
                the interruption notice.

        Returns:
            Whether this call stored the turn.

        Raises:
            HTTPException: When the write fails.
        """
        return await self._store(
            "interrupted",
            [OpenAIResponseMessage(role="assistant", content=partial_response)],
        )

    def drop(self, reason: str) -> None:
        """Leave the turn out of the conversation on purpose.

        Parameters:
            reason: Why the turn is not stored; kept as the outcome and logged.
        """
        if self._settle(f"dropped: {reason}") and self.ours:
            logger.info(
                "Turn on conversation %s is not stored: %s",
                self.conversation_id,
                reason,
            )

    def ensure_settled(self) -> None:
        """Fail when lightspeed-stack has to store the turn and nobody tried to.

        A turn OGX stores needs no check, and neither does one the request
        does not want stored. A write that was tried and failed passes the
        check: the failure was raised or logged where it happened.

        Raises:
            TurnNotStoredError: When the turn has to be stored by
                lightspeed-stack and is still pending.
        """
        if self.ours and not self.settled:
            raise TurnNotStoredError(
                f"the turn on conversation {self.conversation_id} was served "
                "without the conversation parameter, and nobody tried to store "
                "it or dropped it; the next request would not see it"
            )

    def _settle(self, outcome: str) -> bool:
        """Settle the turn; only the first caller gets ``True``.

        There is no ``await`` between the check and the assignment, so of
        several tasks on the event loop exactly one settles the turn.
        """
        if self.outcome is not None:
            return False
        self.outcome = outcome
        return True

    async def _store(
        self, outcome: str, output_items: Sequence[OpenAIResponseOutput]
    ) -> bool:
        """Settle the turn and append it to the conversation.

        The turn is settled before the write starts. A write that fails is
        therefore not repeated by another path of the same request: the turn
        is lost, as it was before this class existed, but never doubled.

        Parameters:
            outcome: How the turn ended; recorded when this call settles it.
            output_items: The assistant's side of the turn.

        Returns:
            Whether this call wrote the turn. ``False`` when the turn was
            settled before, or the request does not want its turn stored.

        Raises:
            HTTPException: When the write fails. The outcome is then recorded
                as ``failed: <outcome>``.
        """
        if not self._settle(outcome) or not self.store:
            return False
        try:
            await append_turn_items_to_conversation(
                self.client, self.conversation_id, self.user_input, output_items
            )
        except BaseException:
            self.outcome = f"failed: {outcome}"
            raise
        return True


@asynccontextmanager
async def pending_turn(
    client: AsyncOgxClient,
    params: ResponsesApiParams,
    original_input: Optional[ResponseInput] = None,
) -> AsyncIterator[PendingTurn]:
    """Serve a request inside a scope that does not let its turn get lost.

    The scope hands out the pending turn of the request. When it is left
    without an error, the turn has to be settled.

    Parameters:
        client: OGX client used for the write.
        params: The parameters the request is sent with, after compaction was
            applied.
        original_input: The input before the explicit-input rewrite; required
            in compacted mode.

    Yields:
        The pending turn of the request.

    Raises:
        TurnNotStoredError: When the scope is left normally with a turn of
            ours still pending.
        ValueError: When the request is compacted and its original input is
            missing.
    """
    turn = PendingTurn.for_request(client, params, original_input)
    yield turn
    turn.ensure_settled()
