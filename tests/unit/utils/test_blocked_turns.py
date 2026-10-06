"""Unit tests for the mark of a turn a shield blocked (LCORE-3788)."""

from ogx_api.openai_responses import OpenAIResponseMessage
from ogx_client.models.open_ai_response_message11_variants import (
    OpenAIResponseMessage11Variants as ConversationItem,
)
from pydantic_ai.messages import ModelResponse, TextPart
from pytest_mock import MockerFixture

from utils.blocked_turns import (
    BLOCKED_ITEM_ID_PREFIX,
    SHIELD_BLOCKED_METADATA_KEY,
    exclude_blocked_items,
    is_blocked_item,
    mark_blocked,
    new_blocked_item_id,
    shield_refusal_of,
)


def _msg(text: str, item_id: str | None = None) -> OpenAIResponseMessage:
    """Build a stored user message, with the id it was stored under."""
    return OpenAIResponseMessage(role="user", content=text, id=item_id)


def test_new_blocked_item_id_is_prefixed_and_unique() -> None:
    """Every id carries the prefix and 48 random hex characters, as OGX ids do."""
    first, second = new_blocked_item_id(), new_blocked_item_id()

    assert first.startswith(BLOCKED_ITEM_ID_PREFIX)
    assert len(first) == len(BLOCKED_ITEM_ID_PREFIX) + 48
    assert first != second


def test_is_blocked_item_reads_the_id_prefix() -> None:
    """An item is blocked when its id has the prefix, and only then."""
    blocked_id = new_blocked_item_id()
    listed = ConversationItem.from_dict(
        {"type": "message", "role": "user", "content": "x", "id": blocked_id}
    )

    assert is_blocked_item(_msg("x", blocked_id))
    assert is_blocked_item(listed)  # the type OGX lists conversation items as
    assert not is_blocked_item(_msg("x", "msg_0123456789abcdef"))
    assert not is_blocked_item(_msg("x"))
    assert not is_blocked_item({"type": "function_call"})


def test_exclude_blocked_items_keeps_the_rest_as_they_are() -> None:
    """The items that are left are the same objects, in the same order."""
    question, answer = _msg("question", "msg_01"), _msg("answer", "msg_02")
    items = [
        question,
        _msg("blocked question", new_blocked_item_id()),
        _msg("refusal", new_blocked_item_id()),
        answer,
    ]

    kept = exclude_blocked_items(items)

    assert len(kept) == 2
    assert kept[0] is question
    assert kept[1] is answer


def test_mark_blocked_gives_every_message_a_new_blocked_id() -> None:
    """Messages get a blocked id of their own; other items and the input stay."""
    tool_output = {"type": "function_call_output", "call_id": "c1", "output": "o"}
    items = [
        {"type": "message", "role": "user", "content": "q", "id": "msg_client"},
        tool_output,
        {"type": "message", "role": "assistant", "content": "refusal"},
    ]

    marked = mark_blocked(items)

    assert marked[0]["id"].startswith(BLOCKED_ITEM_ID_PREFIX)
    assert marked[2]["id"].startswith(BLOCKED_ITEM_ID_PREFIX)
    assert marked[0]["id"] != marked[2]["id"]
    assert marked[0]["content"] == "q"
    assert marked[1] == tool_output
    # the dicts handed in are not modified
    assert items[0]["id"] == "msg_client"
    assert "id" not in items[2]


def test_shield_refusal_of_reads_the_flag_a_shield_sets(mocker: MockerFixture) -> None:
    """Only a run whose last response carries the flag was rejected by a shield."""
    refusal = ModelResponse(
        [TextPart("refused")], metadata={SHIELD_BLOCKED_METADATA_KEY: True}
    )

    assert shield_refusal_of(mocker.Mock(response=refusal)) == "refused"
    assert (
        shield_refusal_of(mocker.Mock(response=ModelResponse([TextPart("answer")])))
        is None
    )
    # a test double that answers every attribute is not a rejected run
    assert shield_refusal_of(mocker.MagicMock()) is None
