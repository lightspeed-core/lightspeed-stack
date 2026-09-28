"""Unit tests for the owner of the turns lightspeed-stack stores itself (LCORE-3908).

Every test asserts on the items that reach the conversation, captured by a
client that records its writes, not on a helper having been called.
"""

from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import HTTPException
from ogx_api.openai_responses import OpenAIResponseMessage
from ogx_client import ApiException
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from models.config import CompactionConfiguration, InferenceConfiguration
from utils.conversation_compaction import MARKER_SENTINEL, apply_compaction_blocking
from utils.pending_turn import PendingTurn, TurnNotStoredError, pending_turn
from utils.token_estimator import extract_message_text

CONVERSATION = "conv_abc123"
MODEL = "openai/gpt-4o-mini"
QUERY = "new question"
ANSWER = OpenAIResponseMessage(role="assistant", content="the answer")
REFUSAL = OpenAIResponseMessage(role="assistant", content="blocked by a shield")


class RecordingClient:  # pylint: disable=too-few-public-methods
    """Stand-in for the OGX client that keeps what is written to a conversation."""

    def __init__(self, fail_with: Optional[Exception] = None) -> None:
        """Create the client, optionally one whose writes fail."""
        self.stored: list[tuple[str, str, str]] = []
        self.writes = 0
        self._fail_with = fail_with
        self.items = self

    async def create(
        self, conversation_id: str, *, add_items_request: Any = None, **_: Any
    ) -> None:
        """Record the items of one write as (conversation, role, text)."""
        self.writes += 1
        if self._fail_with is not None:
            raise self._fail_with
        self.stored.extend(
            (conversation_id, str(item.role), extract_message_text(item))
            for item in add_items_request.items
        )


def _params(
    compacted: bool = False,
    store: bool = True,
    previous_response_id: Optional[str] = None,
) -> ResponsesApiParams:
    """Build request params the way the endpoints hand them over."""
    explicit: ResponseInput = [
        OpenAIResponseMessage(role="user", content="Summary of earlier turns"),
        OpenAIResponseMessage(role="user", content=QUERY),
    ]
    return ResponsesApiParams(
        input=explicit if compacted else QUERY,
        model=MODEL,
        conversation=CONVERSATION,
        previous_response_id=previous_response_id,
        store=store,
        stream=False,
        omit_conversation=compacted,
    )


def _turn(client: RecordingClient, **kwargs: Any) -> PendingTurn:
    """Build the pending turn of a request; a compacted one gets its original input."""
    params = _params(**kwargs)
    original = QUERY if params.omit_conversation else None
    return PendingTurn.for_request(client, params, original)  # type: ignore[arg-type]


USER = (CONVERSATION, "user", QUERY)


# --- who stores a completed turn ---


@pytest.mark.asyncio
async def test_completed_turn_is_left_to_ogx_when_it_got_the_conversation() -> None:
    """With the conversation parameter sent, a completed turn is not ours."""
    client = RecordingClient()
    turn = _turn(client)

    assert await turn.store_completed([ANSWER]) is False

    assert not client.stored
    assert turn.settled


@pytest.mark.asyncio
async def test_completed_turn_in_compacted_mode_is_stored() -> None:
    """In compacted mode the turn is stored against the input as it arrived."""
    client = RecordingClient()
    turn = _turn(client, compacted=True)

    assert await turn.store_completed([ANSWER]) is True

    assert client.stored == [USER, (CONVERSATION, "assistant", "the answer")]
    assert client.writes == 1


@pytest.mark.asyncio
async def test_completed_turn_continuing_a_previous_response_is_stored() -> None:
    """OGX does not store a turn that continues from a previous response."""
    client = RecordingClient()
    turn = _turn(client, previous_response_id="resp_1")

    assert await turn.store_completed([ANSWER]) is True

    assert client.stored == [USER, (CONVERSATION, "assistant", "the answer")]


@pytest.mark.asyncio
async def test_input_given_as_items_is_stored_as_given() -> None:
    """An input that arrived as a list of items is stored item by item."""
    client = RecordingClient()
    original: ResponseInput = [
        OpenAIResponseMessage(role="user", content="first part"),
        OpenAIResponseMessage(role="user", content="second part"),
    ]
    turn = PendingTurn.for_request(
        client, _params(compacted=True), original  # type: ignore[arg-type]
    )

    await turn.store_completed([ANSWER])

    assert client.stored == [
        (CONVERSATION, "user", "first part"),
        (CONVERSATION, "user", "second part"),
        (CONVERSATION, "assistant", "the answer"),
    ]


def test_compacted_request_needs_its_original_input() -> None:
    """Without the original input a compacted turn cannot be stored correctly."""
    with pytest.raises(ValueError, match="original input"):
        PendingTurn.for_request(
            RecordingClient(), _params(compacted=True)  # type: ignore[arg-type]
        )


# --- blocked and interrupted turns ---


@pytest.mark.asyncio
@pytest.mark.parametrize("compacted", [False, True])
async def test_blocked_turn_is_stored(compacted: bool) -> None:
    """A blocked request never reaches OGX, so the refusal turn is always ours."""
    client = RecordingClient()
    turn = _turn(client, compacted=compacted)

    assert await turn.store_blocked(REFUSAL) is True

    assert client.stored == [USER, (CONVERSATION, "assistant", "blocked by a shield")]


@pytest.mark.asyncio
@pytest.mark.parametrize("compacted", [False, True])
async def test_interrupted_turn_is_stored(compacted: bool) -> None:
    """An interrupted stream stores the part of the answer that was received."""
    client = RecordingClient()
    turn = _turn(client, compacted=compacted)

    assert await turn.store_interrupted("half an ans") is True

    assert client.stored == [USER, (CONVERSATION, "assistant", "half an ans")]


@pytest.mark.asyncio
async def test_nothing_is_stored_when_the_request_says_so() -> None:
    """A request with ``store`` off leaves the conversation alone, whatever happens."""
    client = RecordingClient()

    assert (
        await _turn(client, compacted=True, store=False).store_completed([ANSWER])
        is False
    )
    assert await _turn(client, store=False).store_blocked(REFUSAL) is False
    assert await _turn(client, store=False).store_interrupted("half") is False

    assert client.writes == 0


# --- exactly once ---


@pytest.mark.asyncio
async def test_a_turn_is_stored_once() -> None:
    """A turn that is stored is not stored again, however the second caller ends it."""
    client = RecordingClient()
    turn = _turn(client, compacted=True)

    assert await turn.store_completed([ANSWER]) is True
    assert await turn.store_completed([ANSWER]) is False
    assert await turn.store_interrupted("half an ans") is False
    assert await turn.store_blocked(REFUSAL) is False

    assert client.stored == [USER, (CONVERSATION, "assistant", "the answer")]
    assert client.writes == 1


@pytest.mark.asyncio
async def test_a_blocked_turn_is_not_stored_again_by_an_interrupt() -> None:
    """A turn settled as blocked is the turn; a later interrupt report adds none."""
    client = RecordingClient()
    turn = _turn(client)

    assert await turn.store_blocked(REFUSAL) is True
    assert await turn.store_interrupted("block") is False

    assert client.stored == [USER, (CONVERSATION, "assistant", "blocked by a shield")]


@pytest.mark.asyncio
async def test_a_failed_write_is_not_repeated() -> None:
    """A write that failed is reported to the caller and never tried again."""
    client = RecordingClient(fail_with=ApiException(status=500, reason="boom"))
    turn = _turn(client, compacted=True)

    with pytest.raises(HTTPException):
        await turn.store_completed([ANSWER])

    assert turn.settled
    assert await turn.store_completed([ANSWER]) is False
    assert client.writes == 1


# --- a turn nobody settled ---


def test_unsettled_turn_of_ours_is_an_error() -> None:
    """A compacted turn that nobody tried to store is a lost turn."""
    turn = _turn(RecordingClient(), compacted=True)

    with pytest.raises(TurnNotStoredError, match=CONVERSATION):
        turn.ensure_settled()


@pytest.mark.asyncio
async def test_settled_turn_passes_the_check() -> None:
    """Stored, left to OGX and not wanted are all fine."""
    stored = _turn(RecordingClient(), compacted=True)
    await stored.store_completed([ANSWER])
    stored.ensure_settled()

    _turn(RecordingClient()).ensure_settled()
    _turn(RecordingClient(), compacted=True, store=False).ensure_settled()


@pytest.mark.asyncio
async def test_scope_reports_a_turn_nobody_settled() -> None:
    """Leaving the scope with a compacted turn unsettled raises."""
    with pytest.raises(TurnNotStoredError):
        async with pending_turn(
            RecordingClient(), _params(compacted=True), QUERY  # type: ignore[arg-type]
        ):
            pass


@pytest.mark.asyncio
async def test_scope_lets_a_settled_turn_through() -> None:
    """The scope hands out the turn and is silent once it is stored."""
    client = RecordingClient()

    async with pending_turn(
        client, _params(compacted=True), QUERY  # type: ignore[arg-type]
    ) as turn:
        await turn.store_completed([ANSWER])

    assert client.stored == [USER, (CONVERSATION, "assistant", "the answer")]


@pytest.mark.asyncio
async def test_scope_does_not_mask_a_failure() -> None:
    """A request that fails inside the scope fails with its own error."""
    with pytest.raises(RuntimeError, match="the model call failed"):
        async with pending_turn(
            RecordingClient(), _params(compacted=True), QUERY  # type: ignore[arg-type]
        ):
            raise RuntimeError("the model call failed")


# --- what the compaction seam hands over ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_items", "compacted"),
    [
        ([], False),
        ([OpenAIResponseMessage(role="user", content="a question")], False),
        (
            [
                OpenAIResponseMessage(role="user", content="a question"),
                OpenAIResponseMessage(
                    role="user", content=f"{MARKER_SENTINEL} an earlier summary"
                ),
            ],
            True,
        ),
    ],
    ids=["new conversation", "never compacted", "compacted before"],
)
async def test_the_seam_hands_over_what_the_owner_needs(
    mocker: MockerFixture, stored_items: list[Any], compacted: bool
) -> None:
    """Dropping the conversation parameter and handing over the input go together.

    The owner takes ``omit_conversation`` as the sign that the turn is ours
    and needs the input as it arrived to store it. The seam sets both or
    neither; were that to change, a turn would be lost or stored twice.
    """
    mocker.patch(
        "utils.conversation_compaction.get_all_conversation_items",
        new=mocker.AsyncMock(return_value=stored_items),
    )
    client = RecordingClient()

    result = await apply_compaction_blocking(
        client,  # type: ignore[arg-type]
        _params(),
        InferenceConfiguration(context_windows={MODEL: 100_000}),
        CompactionConfiguration(enabled=True),
    )

    assert result.compacted is compacted
    assert result.params.omit_conversation is compacted
    assert (result.original_input is not None) is compacted
    turn = PendingTurn.for_request(
        client, result.params, result.original_input  # type: ignore[arg-type]
    )
    assert turn.ours is compacted
    assert turn.user_input == QUERY


# --- who may write to a conversation ---


def _modules_mentioning(name: str) -> list[str]:
    """Return the modules under ``src`` whose source mentions *name*."""
    src = Path(__file__).resolve().parents[3] / "src"
    return sorted(
        str(path.relative_to(src))
        for path in src.rglob("*.py")
        if name in path.read_text(encoding="utf-8")
    )


WRITERS = {
    # the function that appends a turn, and its one caller, the owner
    "append_turn_items_to_conversation": [
        "utils/conversations.py",
        "utils/pending_turn.py",
    ],
    # the shield capabilities store the turn they rejected, from inside the
    # agent run, and only when the model was handed the conversation; in
    # compacted mode it is not, so they write nothing there
    "append_turn_to_conversation": [
        "pydantic_ai_lightspeed/capabilities/granite_guardian/_capability.py",
        "pydantic_ai_lightspeed/capabilities/question_validity/_capability.py",
        "utils/conversations.py",
    ],
    # the call underneath both, and the write of a compaction summary marker
    "items.create(": [
        "utils/conversation_compaction.py",
        "utils/conversations.py",
    ],
    "build_add_items_request": [
        "utils/conversation_compaction.py",
        "utils/conversations.py",
    ],
    # Granite Guardian replaces the answer OGX stored when it rejects an
    # output or a tool result: the last assistant message is deleted and the
    # violation message appended, again only when the model was handed the
    # conversation. conversations_v1.py only names the function in a comment
    "replace_last_assistant_message": [
        "app/endpoints/conversations_v1.py",
        "pydantic_ai_lightspeed/capabilities/granite_guardian/_capability.py",
        "utils/conversations.py",
    ],
}


@pytest.mark.parametrize("writer", sorted(WRITERS))
def test_conversations_are_written_by_the_known_writers_only(writer: str) -> None:
    """No module other than the listed ones appends to a conversation.

    LCORE-3883 happened because every endpoint made the write itself and two
    cleanups removed it. An endpoint that starts writing on its own again,
    through one of the functions that write, shows up here.

    The check reads the source as text. It therefore also fails when a module
    only mentions one of the names, in a comment for example.
    """
    assert _modules_mentioning(writer) == WRITERS[writer], (
        f"the modules that mention {writer!r} changed; a turn has to be stored "
        "through utils.pending_turn.PendingTurn, and a writer that is meant to "
        "be new has to be added to WRITERS in this test"
    )
