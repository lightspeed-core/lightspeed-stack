"""Unit tests for utils/token_estimator."""

# pylint: disable=too-few-public-methods

from typing import Any

import pytest
import tiktoken

from models.config import InferenceConfiguration
from utils.token_estimator import (
    DEFAULT_ENCODING_NAME,
    estimate_conversation_tokens,
    estimate_tokens,
    extract_message_text,
    get_context_window,
    is_message_item,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
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
    """Minimal stand-in for a content-part object with a .text attribute."""

    def __init__(self, text: str) -> None:
        self.text = text


# ---------------------------------------------------------------------------
# estimate_tokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """Tests for estimate_tokens."""

    def test_empty_string_is_zero(self) -> None:
        """An empty string contributes zero tokens."""
        assert estimate_tokens("") == 0

    def test_returns_positive_integer_for_text(self) -> None:
        """A non-empty string yields a positive integer (JIRA AC)."""
        assert estimate_tokens("hello world") == 2

    def test_single_word(self) -> None:
        """'hello' is a single cl100k_base token."""
        assert estimate_tokens("hello") == 1

    def test_pangram(self) -> None:
        """The pangram tokenizes to the known cl100k_base count."""
        assert estimate_tokens("The quick brown fox jumps over the lazy dog.") == 10

    def test_known_phrase(self) -> None:
        """A second reference phrase agrees with the published count."""
        assert estimate_tokens("tiktoken is great!") == 6

    def test_default_encoding_used(self) -> None:
        """Omitting encoding_name uses cl100k_base (per module default)."""
        text = "Compaction summarizes older conversation turns."
        assert estimate_tokens(text) == estimate_tokens(
            text, encoding_name=DEFAULT_ENCODING_NAME
        )

    def test_unknown_encoding_raises(self) -> None:
        """An unknown encoding name surfaces a ValueError from tiktoken."""
        with pytest.raises(ValueError):
            estimate_tokens("hello", encoding_name="not_a_real_encoding")

    def test_within_5pct_of_explicit_tiktoken_call(self) -> None:
        """Estimate is within 5% of a direct tiktoken call (JIRA AC).

        The JIRA AC requires accuracy "within 5% of actual token count".
        For OpenAI-family models, the "actual" token count is whatever
        tiktoken produces for the same encoding. This test routes
        through the public estimator and compares to a direct, known
        tiktoken invocation on the same text, asserting the deviation
        is at most 5% — establishing that the estimator does not
        introduce its own off-by-some error.
        """
        encoding = tiktoken.get_encoding(DEFAULT_ENCODING_NAME)
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "Pack my box with five dozen liquor jugs."
        )
        reference = len(encoding.encode(text))
        estimate = estimate_tokens(text)
        delta_ratio = abs(estimate - reference) / reference
        assert delta_ratio <= 0.05


# ---------------------------------------------------------------------------
# is_message_item
# ---------------------------------------------------------------------------


class TestIsMessage:
    """Tests for the is_message_item duck-type check."""

    def test_llama_stack_message_item(self) -> None:
        """A Llama-Stack-shaped object with type == 'message' is a message."""
        assert is_message_item(_MessageItem("user", "hi")) is True

    def test_llama_stack_tool_call_item(self) -> None:
        """A tool-call-shaped object is not a message."""
        assert is_message_item(_ToolCallItem()) is False

    def test_openai_dict_with_role(self) -> None:
        """An OpenAI-style dict with a 'role' key is a message."""
        assert is_message_item({"role": "user", "content": "hi"}) is True

    def test_dict_without_role(self) -> None:
        """A dict without a 'role' key is not a message."""
        assert is_message_item({"content": "hi"}) is False


# ---------------------------------------------------------------------------
# extract_message_text
# ---------------------------------------------------------------------------


class TestExtractMessageText:
    """Tests for the extract_message_text duck-type extractor."""

    def test_llama_stack_string_content(self) -> None:
        """Plain string content is returned as-is."""
        assert extract_message_text(_MessageItem("user", "hello")) == "hello"

    def test_openai_dict_string_content(self) -> None:
        """OpenAI-style dict with string content is supported."""
        assert extract_message_text({"role": "user", "content": "hi"}) == "hi"

    def test_list_content_with_text_attr(self) -> None:
        """A list of content parts with .text attribute is joined."""
        item: Any = _MessageItem("user", "placeholder")
        item.content = [_TextPart("first"), _TextPart("second")]
        assert extract_message_text(item) == "first second"

    def test_list_content_with_text_dict(self) -> None:
        """A list of content dicts each with a 'text' key is joined."""
        item = {"role": "user", "content": [{"text": "alpha"}, {"text": "beta"}]}
        assert extract_message_text(item) == "alpha beta"

    def test_none_content(self) -> None:
        """None content yields an empty string."""
        item: Any = _MessageItem("user", "placeholder")
        item.content = None
        assert extract_message_text(item) == ""

    def test_missing_content_on_object(self) -> None:
        """Object without content attribute yields empty string."""

        class _Empty:
            type = "message"
            role = "user"

        assert extract_message_text(_Empty()) == ""


# ---------------------------------------------------------------------------
# estimate_conversation_tokens
# ---------------------------------------------------------------------------


class TestEstimateConversationTokens:
    """Tests for estimate_conversation_tokens."""

    def test_empty_conversation_no_prompt(self) -> None:
        """No messages and no system prompt is zero tokens."""
        assert estimate_conversation_tokens([]) == 0

    def test_system_prompt_only(self) -> None:
        """System prompt alone contributes its own token count."""
        prompt = "You are a helpful assistant."
        total = estimate_conversation_tokens([], system_prompt=prompt)
        assert total == estimate_tokens(prompt)

    def test_sums_messages(self) -> None:
        """Total is the sum of per-message token counts."""
        messages: list[Any] = [
            _MessageItem("user", "hello world"),
            _MessageItem("assistant", "hi"),
        ]
        total = estimate_conversation_tokens(messages)
        assert total == estimate_tokens("hello world") + estimate_tokens("hi")

    def test_accepts_openai_dict_shape(self) -> None:
        """OpenAI-style dicts are counted equivalently to Llama Stack items."""
        dicts = [
            {"role": "user", "content": "hello world"},
            {"role": "assistant", "content": "hi"},
        ]
        items: list[Any] = [
            _MessageItem("user", "hello world"),
            _MessageItem("assistant", "hi"),
        ]
        assert estimate_conversation_tokens(dicts) == estimate_conversation_tokens(
            items
        )

    def test_accepts_mixed_shapes(self) -> None:
        """A mixed list of dicts and Llama Stack items is supported."""
        mixed: list[Any] = [
            _MessageItem("user", "hello world"),
            {"role": "assistant", "content": "hi"},
        ]
        assert estimate_conversation_tokens(mixed) == estimate_tokens(
            "hello world"
        ) + estimate_tokens("hi")

    def test_skips_non_message_items(self) -> None:
        """Tool-call-shaped items in the list are ignored."""
        messages: list[Any] = [
            _MessageItem("user", "hello"),
            _ToolCallItem(),
            _MessageItem("assistant", "world"),
        ]
        assert estimate_conversation_tokens(messages) == estimate_tokens(
            "hello"
        ) + estimate_tokens("world")

    def test_system_prompt_and_messages(self) -> None:
        """System prompt is added on top of message totals."""
        prompt = "You are a helpful assistant."
        messages: list[Any] = [_MessageItem("user", "hello world")]
        total = estimate_conversation_tokens(messages, system_prompt=prompt)
        assert total == estimate_tokens(prompt) + estimate_tokens("hello world")


# ---------------------------------------------------------------------------
# get_context_window
# ---------------------------------------------------------------------------


class TestGetContextWindow:
    """Tests for get_context_window."""

    def test_returns_size_for_known_model(self) -> None:
        """A configured model returns its window size."""
        config = InferenceConfiguration(
            context_windows={"openai/gpt-4o-mini": 128000},
        )  # pyright: ignore[reportCallIssue]
        assert get_context_window("openai/gpt-4o-mini", config) == 128000

    def test_returns_none_for_unknown_model(self) -> None:
        """An unconfigured model returns None — caller decides fallback."""
        config = InferenceConfiguration(
            context_windows={"openai/gpt-4o-mini": 128000},
        )  # pyright: ignore[reportCallIssue]
        assert get_context_window("anthropic/claude-3", config) is None

    def test_returns_none_when_map_empty(self) -> None:
        """An empty context_windows dict returns None for any model."""
        config = InferenceConfiguration()  # pyright: ignore[reportCallIssue]
        assert get_context_window("openai/gpt-4o-mini", config) is None
