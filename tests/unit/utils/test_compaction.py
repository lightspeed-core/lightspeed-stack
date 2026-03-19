"""Unit tests for utils/compaction.py."""

# pylint: disable=too-few-public-methods

from typing import Any

import pytest
from pytest_mock import MockerFixture

from utils.compaction import (
    COMPACTION_TRIGGER_THRESHOLD,
    RECENT_MESSAGES_TO_KEEP,
    _extract_message_text,
    _format_conversation_for_summary,
    _is_message_item,
    compact_conversation_if_needed,
    split_conversation_items,
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


def _make_conversation_history(num_turns: int) -> list[Any]:
    """Build alternating user/assistant message items for *num_turns* turns."""
    items: list[Any] = []
    for i in range(num_turns):
        items.append(_MessageItem("user", f"User message {i + 1}"))
        items.append(_MessageItem("assistant", f"Assistant response {i + 1}"))
    return items


def _setup_compaction_mocks(mocker: MockerFixture, num_turns: int = 12) -> Any:
    """Wire up a mock Llama Stack client ready for a compaction test.

    Returns:
        The mock client with conversations, items, and responses pre-configured.
    """
    mock_client = mocker.AsyncMock()

    items = _make_conversation_history(num_turns)
    mock_items_response = mocker.Mock()
    mock_items_response.data = items
    mock_client.conversations.items.list.return_value = mock_items_response

    mock_summary_conv = mocker.Mock()
    mock_summary_conv.id = "conv_summary_temp"
    mock_new_conv = mocker.Mock()
    mock_new_conv.id = "conv_compacted"
    mock_client.conversations.create.side_effect = [
        mock_summary_conv,
        mock_new_conv,
    ]

    mock_text_part = mocker.Mock()
    mock_text_part.text = "Summary of the conversation."
    mock_output_item = mocker.Mock()
    mock_output_item.content = [mock_text_part]
    mock_response = mocker.Mock()
    mock_response.output = [mock_output_item]
    mock_client.responses.create.return_value = mock_response

    return mock_client


# ---------------------------------------------------------------------------
# _is_message_item
# ---------------------------------------------------------------------------


class TestIsMessageItem:
    """Tests for _is_message_item."""

    def test_returns_true_for_message(self) -> None:
        """Test message item is recognised."""
        assert _is_message_item(_MessageItem("user", "hi")) is True

    def test_returns_false_for_tool_call(self) -> None:
        """Test tool-call item is not treated as a message."""
        assert _is_message_item(_ToolCallItem()) is False

    def test_returns_false_for_dict_without_type(self) -> None:
        """Test plain dict without type attribute."""
        assert _is_message_item({"role": "user"}) is False


# ---------------------------------------------------------------------------
# _extract_message_text
# ---------------------------------------------------------------------------


class TestExtractMessageText:
    """Tests for _extract_message_text."""

    def test_string_content(self) -> None:
        """Test extraction from string content."""
        item = _MessageItem("user", "hello world")
        assert _extract_message_text(item) == "hello world"

    def test_list_content_with_text_attr(self) -> None:
        """Test extraction from list of content parts with .text attribute."""

        class _Part:
            text = "part one"

        item = _MessageItem("user", "placeholder")
        item.content = [_Part()]  # type: ignore[assignment]
        assert _extract_message_text(item) == "part one"

    def test_list_content_with_dict(self) -> None:
        """Test extraction from list of dicts with 'text' key."""
        item = _MessageItem("user", "placeholder")
        item.content = [{"text": "from dict"}]  # type: ignore[assignment]
        assert _extract_message_text(item) == "from dict"

    def test_none_content(self) -> None:
        """Test extraction when content is None."""
        item = _MessageItem("user", "placeholder")
        item.content = None  # type: ignore[assignment]
        assert _extract_message_text(item) == ""


# ---------------------------------------------------------------------------
# _format_conversation_for_summary
# ---------------------------------------------------------------------------


class TestFormatConversationForSummary:
    """Tests for _format_conversation_for_summary."""

    def test_formats_messages(self) -> None:
        """Test messages are formatted as role: text lines."""
        items: list[Any] = [
            _MessageItem("user", "What is Kubernetes?"),
            _MessageItem("assistant", "Kubernetes is a container orchestrator."),
        ]
        result = _format_conversation_for_summary(items)
        assert "user: What is Kubernetes?" in result
        assert "assistant: Kubernetes is a container orchestrator." in result

    def test_skips_tool_calls(self) -> None:
        """Test tool-call items are excluded from formatted text."""
        items: list[Any] = [
            _MessageItem("user", "hello"),
            _ToolCallItem(),
            _MessageItem("assistant", "world"),
        ]
        result = _format_conversation_for_summary(items)
        assert "function_call" not in result
        assert "user: hello" in result
        assert "assistant: world" in result


# ---------------------------------------------------------------------------
# split_conversation_items
# ---------------------------------------------------------------------------


class TestSplitConversationItems:
    """Tests for split_conversation_items."""

    def test_no_split_when_too_few_messages(self) -> None:
        """Test that conversations shorter than the threshold are not split."""
        items = _make_conversation_history(3)
        old, recent = split_conversation_items(items, recent_to_keep=4)
        assert old == []
        assert recent == items

    def test_splits_at_correct_boundary(self) -> None:
        """Test that split preserves the correct number of recent turns."""
        items = _make_conversation_history(8)
        old, recent = split_conversation_items(items, recent_to_keep=2)

        recent_messages = [i for i in recent if _is_message_item(i)]
        assert len(recent_messages) == 4  # 2 pairs = 4 messages
        assert len(old) > 0

    def test_old_and_recent_cover_all_items(self) -> None:
        """Test that old + recent equals the original list."""
        items = _make_conversation_history(10)
        old, recent = split_conversation_items(items, recent_to_keep=3)
        assert old + recent == items

    def test_handles_interleaved_tool_calls(self) -> None:
        """Test split with non-message items interspersed."""
        items: list[Any] = [
            _MessageItem("user", "q1"),
            _MessageItem("assistant", "a1"),
            _ToolCallItem(),
            _MessageItem("user", "q2"),
            _MessageItem("assistant", "a2"),
            _MessageItem("user", "q3"),
            _MessageItem("assistant", "a3"),
            _MessageItem("user", "q4"),
            _MessageItem("assistant", "a4"),
            _MessageItem("user", "q5"),
            _MessageItem("assistant", "a5"),
        ]
        old, recent = split_conversation_items(items, recent_to_keep=2)
        assert old + recent == items
        recent_msgs = [i for i in recent if _is_message_item(i)]
        assert len(recent_msgs) == 4


# ---------------------------------------------------------------------------
# compact_conversation_if_needed
# ---------------------------------------------------------------------------


class TestCompactConversationIfNeeded:
    """Tests for the top-level compact_conversation_if_needed function."""

    @pytest.mark.asyncio
    async def test_skips_below_threshold(self, mocker: MockerFixture) -> None:
        """Test that compaction is skipped when message_count is below threshold."""
        mock_client = mocker.AsyncMock()

        result = await compact_conversation_if_needed(
            client=mock_client,
            llama_stack_conv_id="conv_original",
            model="provider/model",
            message_count=COMPACTION_TRIGGER_THRESHOLD - 1,
        )

        assert result == "conv_original"
        mock_client.conversations.items.list.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_at_threshold(self, mocker: MockerFixture) -> None:
        """Test that compaction is skipped when message_count equals threshold."""
        mock_client = mocker.AsyncMock()

        result = await compact_conversation_if_needed(
            client=mock_client,
            llama_stack_conv_id="conv_original",
            model="provider/model",
            message_count=COMPACTION_TRIGGER_THRESHOLD,
        )

        assert result == "conv_original"

    @pytest.mark.asyncio
    async def test_skips_when_no_items(self, mocker: MockerFixture) -> None:
        """Test that compaction is skipped when conversation has no items."""
        mock_client = mocker.AsyncMock()
        mock_items_response = mocker.Mock()
        mock_items_response.data = []
        mock_client.conversations.items.list.return_value = mock_items_response

        result = await compact_conversation_if_needed(
            client=mock_client,
            llama_stack_conv_id="conv_original",
            model="provider/model",
            message_count=COMPACTION_TRIGGER_THRESHOLD + 5,
        )

        assert result == "conv_original"

    @pytest.mark.asyncio
    async def test_compacts_above_threshold(self, mocker: MockerFixture) -> None:
        """Test full compaction flow when message_count exceeds threshold."""
        mock_client = _setup_compaction_mocks(mocker, num_turns=12)

        result = await compact_conversation_if_needed(
            client=mock_client,
            llama_stack_conv_id="conv_original",
            model="provider/model",
            message_count=COMPACTION_TRIGGER_THRESHOLD + 5,
        )

        assert result == "conv_compacted"

        # Verify history was fetched
        mock_client.conversations.items.list.assert_called_once_with(
            conversation_id="conv_original",
            after=None,
            include=None,
            limit=None,
            order="asc",
        )

        # Verify summarization LLM call was made
        mock_client.responses.create.assert_called_once()
        call_kwargs = mock_client.responses.create.call_args
        assert call_kwargs.kwargs["model"] == "provider/model"
        assert call_kwargs.kwargs["store"] is False

        # Verify new conversation was seeded with items
        mock_client.conversations.items.create.assert_called_once()
        seed_call = mock_client.conversations.items.create.call_args
        assert seed_call.args[0] == "conv_compacted"
        seed_items = seed_call.kwargs.get("items") or seed_call.args[1]

        # First two items should be the summary exchange
        assert seed_items[0]["role"] == "user"
        assert "summary" in seed_items[0]["content"].lower()
        assert seed_items[1]["role"] == "assistant"
        assert "understood" in seed_items[1]["content"].lower()

        # Remaining items should be the recent messages
        recent_msgs = seed_items[2:]
        assert len(recent_msgs) == RECENT_MESSAGES_TO_KEEP * 2

    @pytest.mark.asyncio
    async def test_preserves_recent_messages(self, mocker: MockerFixture) -> None:
        """Test that the most recent turns are preserved verbatim after compaction."""
        mock_client = _setup_compaction_mocks(mocker, num_turns=12)

        await compact_conversation_if_needed(
            client=mock_client,
            llama_stack_conv_id="conv_original",
            model="provider/model",
            message_count=15,
        )

        seed_call = mock_client.conversations.items.create.call_args
        seed_items = seed_call.kwargs.get("items") or seed_call.args[1]

        # Skip summary exchange (first 2), check recent messages
        recent = seed_items[2:]
        expected_start = 12 * 2 - RECENT_MESSAGES_TO_KEEP * 2
        for i, msg in enumerate(recent):
            idx = expected_start + i
            turn = idx // 2 + 1
            if idx % 2 == 0:
                assert msg["role"] == "user"
                assert f"User message {turn}" == msg["content"]
            else:
                assert msg["role"] == "assistant"
                assert f"Assistant response {turn}" == msg["content"]

    @pytest.mark.asyncio
    async def test_skips_when_not_enough_old_messages(
        self, mocker: MockerFixture
    ) -> None:
        """Test that compaction is skipped when there aren't enough old messages."""
        mock_client = mocker.AsyncMock()

        # 4 turns = 8 messages. With RECENT_MESSAGES_TO_KEEP=4 we need
        # at least 4*2+1=9 messages for a split, so 8 is not enough.
        items = _make_conversation_history(4)
        mock_items_response = mocker.Mock()
        mock_items_response.data = items
        mock_client.conversations.items.list.return_value = mock_items_response

        result = await compact_conversation_if_needed(
            client=mock_client,
            llama_stack_conv_id="conv_original",
            model="provider/model",
            message_count=COMPACTION_TRIGGER_THRESHOLD + 1,
        )

        assert result == "conv_original"
        mock_client.conversations.create.assert_not_called()
