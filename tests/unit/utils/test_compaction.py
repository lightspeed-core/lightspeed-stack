"""Unit tests for utils/compaction — partitioning, prompt, summarization."""

# pylint: disable=too-few-public-methods

from typing import Any

import pytest
from pytest_mock import MockerFixture

from models.compaction import ConversationSummary
from utils.compaction import (
    RECURSIVE_RESUMMARIZATION_PROMPT,
    SUMMARIZATION_PROMPT,
    _extract_response_text,
    extract_message_text,
    format_conversation_for_summary,
    is_message_item,
    partition_conversation,
    recursively_resummarize,
    summarize_chunk,
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
        items.append(_MessageItem("assistant", (snippet * words_per_message) + f"A{i}"))
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


# ---------------------------------------------------------------------------
# SUMMARIZATION_PROMPT
# ---------------------------------------------------------------------------


class TestSummarizationPrompt:
    """Tests for the SUMMARIZATION_PROMPT constant.

    JIRA AC: "Summarization prompt includes all 5 preservation directives".
    """

    def test_includes_red_hat_domain(self) -> None:
        """Prompt is domain-scoped to Red Hat product support."""
        assert "Red Hat product support" in SUMMARIZATION_PROMPT

    def test_includes_user_question_and_environment_directive(self) -> None:
        """Directive 1: user's original question and environment details."""
        assert "original question" in SUMMARIZATION_PROMPT
        assert "environment" in SUMMARIZATION_PROMPT

    def test_includes_error_messages_and_commands_directive(self) -> None:
        """Directive 2: error messages, commands run, and their outcomes."""
        assert "error messages" in SUMMARIZATION_PROMPT
        assert "commands" in SUMMARIZATION_PROMPT
        assert "outcomes" in SUMMARIZATION_PROMPT

    def test_includes_decisions_and_rationale_directive(self) -> None:
        """Directive 3: key decisions and their rationale."""
        assert "decisions" in SUMMARIZATION_PROMPT
        assert "rationale" in SUMMARIZATION_PROMPT

    def test_includes_resolved_versus_open_directive(self) -> None:
        """Directive 4: what was resolved and what remains open."""
        assert "resolved" in SUMMARIZATION_PROMPT
        assert "open" in SUMMARIZATION_PROMPT

    def test_includes_attribution_directive(self) -> None:
        """Directive 5: attribution (user vs assistant)."""
        assert "attribution" in SUMMARIZATION_PROMPT
        assert "user reported" in SUMMARIZATION_PROMPT
        assert "assistant suggested" in SUMMARIZATION_PROMPT


# ---------------------------------------------------------------------------
# _extract_response_text
# ---------------------------------------------------------------------------


class TestExtractResponseText:
    """Tests for the private response-text extractor."""

    def test_concatenates_text_parts(self, mocker: MockerFixture) -> None:
        """Text fragments across output items are concatenated."""
        part1 = mocker.Mock(text="Hello, ")
        part2 = mocker.Mock(text="world.")
        item = mocker.Mock(content=[part1, part2])
        response = mocker.Mock(output=[item])
        assert _extract_response_text(response) == "Hello, world."

    def test_no_output_yields_empty(self, mocker: MockerFixture) -> None:
        """An empty .output attribute yields the empty string."""
        response = mocker.Mock(output=[])
        assert _extract_response_text(response) == ""


# ---------------------------------------------------------------------------
# summarize_chunk
# ---------------------------------------------------------------------------


def _make_summary_response(mocker: MockerFixture, text: str) -> Any:
    """Build a Responses-API-shaped mock that yields *text*."""
    part = mocker.Mock(text=text)
    item = mocker.Mock(content=[part])
    return mocker.Mock(output=[item])


class TestSummarizeChunk:
    """Tests for summarize_chunk (the additive primitive)."""

    @pytest.mark.asyncio
    async def test_returns_conversation_summary_with_populated_fields(
        self, mocker: MockerFixture
    ) -> None:
        """Happy path: LLM returns text; we get a populated ConversationSummary."""
        client = mocker.AsyncMock()
        client.responses.create.return_value = _make_summary_response(
            mocker, "User asked about Kubernetes. Assistant gave overview."
        )
        items: list[Any] = [
            _MessageItem("user", "What is Kubernetes?"),
            _MessageItem("assistant", "An orchestrator."),
        ]
        summary = await summarize_chunk(
            client=client,
            model="openai/gpt-4o-mini",
            old_items=items,
            summarized_through_turn=2,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert (
            summary.summary_text
            == "User asked about Kubernetes. Assistant gave overview."
        )
        assert summary.summarized_through_turn == 2
        assert summary.token_count > 0
        assert summary.model_used == "openai/gpt-4o-mini"
        assert summary.created_at  # non-empty ISO 8601

    @pytest.mark.asyncio
    async def test_invokes_responses_create_with_store_false(
        self, mocker: MockerFixture
    ) -> None:
        """The summarization call uses store=False and stream=False, and
        passes the system prompt via `instructions` (not bundled into `input`)."""
        client = mocker.AsyncMock()
        client.responses.create.return_value = _make_summary_response(
            mocker, "Summary."
        )
        await summarize_chunk(
            client=client,
            model="openai/gpt-4o-mini",
            old_items=[_MessageItem("user", "hi")],
            summarized_through_turn=1,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        kwargs = client.responses.create.call_args.kwargs
        assert kwargs["store"] is False
        assert kwargs["stream"] is False
        assert kwargs["model"] == "openai/gpt-4o-mini"
        # System directives travel as `instructions`, transcript as `input`.
        # This keeps the directives in their own channel (resilient to
        # prompt-injection from user content) and matches the convention used
        # by utils.responses.get_topic_summary.
        assert kwargs["instructions"] == SUMMARIZATION_PROMPT
        assert SUMMARIZATION_PROMPT not in kwargs["input"]
        assert "user: hi" in kwargs["input"]

    @pytest.mark.asyncio
    async def test_raises_when_llm_returns_empty(self, mocker: MockerFixture) -> None:
        """An empty LLM response surfaces ValueError, not a silent empty summary."""
        client = mocker.AsyncMock()
        client.responses.create.return_value = _make_summary_response(mocker, "")
        with pytest.raises(ValueError, match="no extractable text"):
            await summarize_chunk(
                client=client,
                model="openai/gpt-4o-mini",
                old_items=[_MessageItem("user", "hi")],
                summarized_through_turn=1,
                encoding_name=DEFAULT_ENCODING_NAME,
            )

    @pytest.mark.asyncio
    async def test_additive_second_call_does_not_resummarize_first(
        self, mocker: MockerFixture
    ) -> None:
        """Two sequential calls produce two independent summaries (additive).

        JIRA AC: "Additive mode: second compaction appends a new summary
        chunk, does not re-summarize the first."
        """
        client = mocker.AsyncMock()
        client.responses.create.side_effect = [
            _make_summary_response(mocker, "First summary."),
            _make_summary_response(mocker, "Second summary."),
        ]

        first_chunk: list[Any] = [_MessageItem("user", "First topic.")]
        second_chunk: list[Any] = [_MessageItem("user", "Second topic.")]

        first = await summarize_chunk(
            client=client,
            model="openai/gpt-4o-mini",
            old_items=first_chunk,
            summarized_through_turn=1,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        second = await summarize_chunk(
            client=client,
            model="openai/gpt-4o-mini",
            old_items=second_chunk,
            summarized_through_turn=2,
            encoding_name=DEFAULT_ENCODING_NAME,
        )

        # Each call summarized exactly its own chunk — the second call's
        # prompt body does not include first_chunk's content.
        first_input = client.responses.create.call_args_list[0].kwargs["input"]
        second_input = client.responses.create.call_args_list[1].kwargs["input"]
        assert "First topic." in first_input
        assert "First topic." not in second_input
        assert "Second topic." in second_input

        # The two summaries are distinct records — additive, not rolled up.
        assert first.summary_text == "First summary."
        assert second.summary_text == "Second summary."
        assert second.summarized_through_turn > first.summarized_through_turn


# ---------------------------------------------------------------------------
# recursively_resummarize
# ---------------------------------------------------------------------------


def _make_summary(text: str, through: int, tokens: int = 5) -> ConversationSummary:
    """Build a ConversationSummary value for tests."""
    return ConversationSummary(
        summary_text=text,
        summarized_through_turn=through,
        token_count=tokens,
        created_at="2026-05-11T00:00:00Z",
        model_used="openai/gpt-4o-mini",
    )


class TestRecursivelyResummarize:
    """Tests for the recursive-fold fallback."""

    @pytest.mark.asyncio
    async def test_collapses_n_summaries_into_one(self, mocker: MockerFixture) -> None:
        """Multiple summaries fold into one ConversationSummary."""
        client = mocker.AsyncMock()
        client.responses.create.return_value = _make_summary_response(
            mocker, "Combined summary covering all prior chunks."
        )
        summaries = [
            _make_summary("First chunk summary.", through=5),
            _make_summary("Second chunk summary.", through=10),
            _make_summary("Third chunk summary.", through=15),
        ]
        folded = await recursively_resummarize(
            client=client,
            model="openai/gpt-4o-mini",
            summaries=summaries,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        assert folded.summary_text == "Combined summary covering all prior chunks."
        # The fold inherits the most recent input's running total — no
        # new turns were summarized by this call.
        assert folded.summarized_through_turn == 15
        assert folded.token_count > 0
        assert folded.model_used == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_prompt_lists_each_summary(self, mocker: MockerFixture) -> None:
        """All input summary texts appear in `input`; the fallback prompt
        is passed via `instructions`."""
        client = mocker.AsyncMock()
        client.responses.create.return_value = _make_summary_response(
            mocker, "Folded summary."
        )
        summaries = [
            _make_summary("Alpha facts.", through=5),
            _make_summary("Beta facts.", through=10),
        ]
        await recursively_resummarize(
            client=client,
            model="openai/gpt-4o-mini",
            summaries=summaries,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        kwargs = client.responses.create.call_args.kwargs
        assert kwargs["instructions"] == RECURSIVE_RESUMMARIZATION_PROMPT
        assert RECURSIVE_RESUMMARIZATION_PROMPT not in kwargs["input"]
        assert "Alpha facts." in kwargs["input"]
        assert "Beta facts." in kwargs["input"]
        assert "Summary 1" in kwargs["input"]
        assert "Summary 2" in kwargs["input"]

    @pytest.mark.asyncio
    async def test_uses_store_false(self, mocker: MockerFixture) -> None:
        """The recursive call also uses store=False — like the additive one."""
        client = mocker.AsyncMock()
        client.responses.create.return_value = _make_summary_response(mocker, "Folded.")
        summaries = [
            _make_summary("a", through=1),
            _make_summary("b", through=2),
        ]
        await recursively_resummarize(
            client=client,
            model="openai/gpt-4o-mini",
            summaries=summaries,
            encoding_name=DEFAULT_ENCODING_NAME,
        )
        kwargs = client.responses.create.call_args.kwargs
        assert kwargs["store"] is False
        assert kwargs["stream"] is False

    @pytest.mark.asyncio
    async def test_raises_for_single_summary(self, mocker: MockerFixture) -> None:
        """Folding a single summary is a no-op the caller must avoid."""
        client = mocker.AsyncMock()
        with pytest.raises(ValueError, match="at least 2 summary chunks"):
            await recursively_resummarize(
                client=client,
                model="openai/gpt-4o-mini",
                summaries=[_make_summary("only one", through=5)],
                encoding_name=DEFAULT_ENCODING_NAME,
            )

    @pytest.mark.asyncio
    async def test_raises_for_empty_list(self, mocker: MockerFixture) -> None:
        """Folding an empty list is a no-op the caller must avoid."""
        client = mocker.AsyncMock()
        with pytest.raises(ValueError, match="at least 2 summary chunks"):
            await recursively_resummarize(
                client=client,
                model="openai/gpt-4o-mini",
                summaries=[],
                encoding_name=DEFAULT_ENCODING_NAME,
            )

    @pytest.mark.asyncio
    async def test_raises_when_llm_returns_empty(self, mocker: MockerFixture) -> None:
        """Empty LLM response surfaces ValueError, not an empty fold."""
        client = mocker.AsyncMock()
        client.responses.create.return_value = _make_summary_response(mocker, "")
        summaries = [
            _make_summary("a", through=1),
            _make_summary("b", through=2),
        ]
        with pytest.raises(ValueError, match="no extractable text"):
            await recursively_resummarize(
                client=client,
                model="openai/gpt-4o-mini",
                summaries=summaries,
                encoding_name=DEFAULT_ENCODING_NAME,
            )
