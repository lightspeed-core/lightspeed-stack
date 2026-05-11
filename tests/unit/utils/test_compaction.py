"""Unit tests for utils/compaction — partitioning + duck-type helpers."""

from typing import Any

from utils.compaction import (
    extract_message_text,
    format_conversation_for_summary,
    is_message_item,
    partition_conversation,
)
from utils.token_estimator import (
    DEFAULT_ENCODING_NAME,
    estimate_conversation_tokens,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MessageItem:
    """Minimal stand-in for a Llama Stack conversation message item."""

    def __init__(self, role: str, text: str) -> None:
        self.type = "message"
        self.role = role
        self.content = text


class _ToolCallItem:
    """Minimal stand-in for a non-message conversation item."""

    def __init__(self) -> None:
        self.type = "function_call"


class _TextPart:
    """Content part with a .text attribute."""

    def __init__(self, text: str) -> None:
        self.text = text


def _make_history(num_pairs: int, words_per_message: int = 1) -> list[Any]:
    """Build a Llama-Stack-shaped conversation with *num_pairs* user/assistant pairs.

    Each message text is ``words_per_message`` repetitions of a short
    sentence so callers can dial the per-message token cost.
    """
    items: list[Any] = []
    snippet = "alpha "
    for i in range(num_pairs):
        items.append(_MessageItem("user", (snippet * words_per_message) + str(i)))
        items.append(
            _MessageItem("assistant", (snippet * words_per_message) + f"A{i}")
        )
    return items


# ---------------------------------------------------------------------------
# is_message_item
# ---------------------------------------------------------------------------


class TestIsMessageItem:
    """Tests for is_message_item."""

    def test_llama_stack_message(self) -> None:
        """Llama-stack message item is recognised."""
        assert is_message_item(_MessageItem("user", "hi")) is True

    def test_llama_stack_tool_call(self) -> None:
        """Tool-call item is not a message."""
        assert is_message_item(_ToolCallItem()) is False

    def test_openai_dict_with_role(self) -> None:
        """OpenAI-style dict with role key is a message."""
        assert is_message_item({"role": "user", "content": "hi"}) is True

    def test_dict_without_role(self) -> None:
        """Dict without role key is not a message."""
        assert is_message_item({"content": "hi"}) is False


# ---------------------------------------------------------------------------
# extract_message_text
# ---------------------------------------------------------------------------


class TestExtractMessageText:
    """Tests for extract_message_text."""

    def test_string_content_object(self) -> None:
        """Plain string content on an object is returned as-is."""
        assert extract_message_text(_MessageItem("user", "hello")) == "hello"

    def test_string_content_dict(self) -> None:
        """Plain string content in a dict is returned as-is."""
        assert extract_message_text({"role": "user", "content": "hi"}) == "hi"

    def test_list_content_with_text_attr(self) -> None:
        """List of content-parts with .text is joined."""
        item: Any = _MessageItem("user", "ignored")
        item.content = [_TextPart("one"), _TextPart("two")]
        assert extract_message_text(item) == "one two"

    def test_list_content_with_text_dict(self) -> None:
        """List of dicts with 'text' key is joined."""
        item = {
            "role": "user",
            "content": [{"text": "alpha"}, {"text": "beta"}],
        }
        assert extract_message_text(item) == "alpha beta"

    def test_none_content(self) -> None:
        """None content yields the empty string."""
        item: Any = _MessageItem("user", "ignored")
        item.content = None
        assert extract_message_text(item) == ""


# ---------------------------------------------------------------------------
# format_conversation_for_summary
# ---------------------------------------------------------------------------


class TestFormatConversationForSummary:
    """Tests for format_conversation_for_summary."""

    def test_formats_role_and_text(self) -> None:
        """Each message becomes one 'role: text' line."""
        items: list[Any] = [
            _MessageItem("user", "What is Kubernetes?"),
            _MessageItem("assistant", "A container orchestrator."),
        ]
        out = format_conversation_for_summary(items)
        assert "user: What is Kubernetes?" in out
        assert "assistant: A container orchestrator." in out

    def test_skips_non_message_items(self) -> None:
        """Tool-call items are not rendered into the prompt body."""
        items: list[Any] = [
            _MessageItem("user", "hello"),
            _ToolCallItem(),
            _MessageItem("assistant", "world"),
        ]
        out = format_conversation_for_summary(items)
        assert "function_call" not in out
        assert "user: hello" in out and "assistant: world" in out

    def test_handles_dict_shape(self) -> None:
        """OpenAI-style dicts are rendered alongside Llama-Stack items."""
        items: list[Any] = [
            {"role": "user", "content": "from dict"},
            _MessageItem("assistant", "from object"),
        ]
        out = format_conversation_for_summary(items)
        assert "user: from dict" in out
        assert "assistant: from object" in out


# ---------------------------------------------------------------------------
# partition_conversation — degrading guard
# ---------------------------------------------------------------------------


class TestPartitionConversation:
    """Tests for partition_conversation (decision 9 — degrading guard)."""

    def test_twenty_turn_conversation_produces_non_empty_partitions(self) -> None:
        """JIRA AC: 20+ turn conversation produces non-empty old AND recent."""
        items = _make_history(num_pairs=20)
        old, recent = partition_conversation(
            items,
            available_budget_tokens=10_000,
            buffer_turns=4,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert len(old) > 0
        assert len(recent) > 0

    def test_buffer_keeps_n_turn_pairs_when_budget_is_generous(self) -> None:
        """With ample budget, the buffer is exactly buffer_turns pairs."""
        items = _make_history(num_pairs=10)
        old, recent = partition_conversation(
            items,
            available_budget_tokens=1_000_000,
            buffer_turns=4,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        # 4 pairs = 8 messages.
        assert len(recent) == 8
        assert len(old) == len(items) - 8

    def test_buffer_degrades_when_budget_is_tight(self) -> None:
        """Recent chunk shrinks turn-by-turn until it fits the budget."""
        # 20 pairs, each turn pair carrying enough text that all 4
        # pairs together exceed a small budget but a single pair fits.
        items = _make_history(num_pairs=20, words_per_message=8)
        # Compute the per-pair token count so we can size the budget.
        single_pair = items[-2:]
        single_pair_tokens = estimate_conversation_tokens(
            single_pair, encoding_name=DEFAULT_ENCODING_NAME
        )
        # Allow strictly less than 2 pairs.
        tight_budget = int(single_pair_tokens * 1.5)
        old, recent = partition_conversation(
            items,
            available_budget_tokens=tight_budget,
            buffer_turns=4,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        # Buffer degraded to one pair (two messages).
        assert len(recent) == 2
        assert len(old) == len(items) - 2

    def test_buffer_degrades_to_zero_when_no_pair_fits(self) -> None:
        """When even one turn pair exceeds the budget, the buffer is empty."""
        items = _make_history(num_pairs=5, words_per_message=8)
        old, recent = partition_conversation(
            items,
            available_budget_tokens=1,
            buffer_turns=4,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert recent == []
        assert old == items

    def test_buffer_turns_zero_treats_everything_as_old(self) -> None:
        """A buffer_turns of zero short-circuits to fully old."""
        items = _make_history(num_pairs=4)
        old, recent = partition_conversation(
            items,
            available_budget_tokens=1_000_000,
            buffer_turns=0,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert recent == []
        assert old == items

    def test_no_messages_short_circuits(self) -> None:
        """Empty conversation returns empty partitions."""
        old, recent = partition_conversation(
            [],
            available_budget_tokens=1_000_000,
            buffer_turns=4,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert old == []
        assert recent == []

    def test_fewer_messages_than_buffer_takes_smaller_buffer(self) -> None:
        """If conversation has fewer turns than buffer_turns, all fit in buffer."""
        items = _make_history(num_pairs=2)
        old, recent = partition_conversation(
            items,
            available_budget_tokens=1_000_000,
            buffer_turns=4,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert old == []
        assert recent == items

    def test_partitions_are_disjoint_and_cover_input(self) -> None:
        """old + recent = items for every successful partition."""
        items = _make_history(num_pairs=8)
        old, recent = partition_conversation(
            items,
            available_budget_tokens=1_000_000,
            buffer_turns=3,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert old + recent == items
