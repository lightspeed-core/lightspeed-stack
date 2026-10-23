"""Unit tests for knowledge.utils message-history helpers."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextContent,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)

from knowledge.utils import (
    append_latest_message,
    extract_latest_message_text,
    find_latest_message,
    find_latest_part,
)


class TestFindLatestPart:
    """Tests for `find_latest_part`."""

    def test_empty_history_returns_none(self) -> None:
        """No messages yields no part."""
        assert find_latest_part([], UserPromptPart) is None

    def test_returns_none_when_no_part_matches(self) -> None:
        """Unrelated part types are ignored."""
        messages = [ModelRequest(parts=[SystemPromptPart(content="system")])]

        assert find_latest_part(messages, UserPromptPart) is None

    def test_returns_none_when_parts_are_empty(self) -> None:
        """A request with no parts does not match."""
        assert find_latest_part([ModelRequest(parts=[])], UserPromptPart) is None

    def test_returns_matching_part(self) -> None:
        """The matching part is returned by identity."""
        prompt = UserPromptPart(content="hello")

        result = find_latest_part([ModelRequest(parts=[prompt])], UserPromptPart)

        assert result is prompt

    def test_prefers_later_part_within_a_message(self) -> None:
        """Parts are scanned newest-first inside the latest message."""
        earlier = UserPromptPart(content="earlier")
        later = UserPromptPart(content="later")

        result = find_latest_part(
            [ModelRequest(parts=[earlier, later])],
            UserPromptPart,
        )

        assert result is later

    def test_prefers_part_from_later_message(self) -> None:
        """Messages are scanned newest-first across the history."""
        older = UserPromptPart(content="older")
        newer = UserPromptPart(content="newer")

        result = find_latest_part(
            [
                ModelRequest(parts=[older]),
                ModelRequest(parts=[newer]),
            ],
            UserPromptPart,
        )

        assert result is newer

    def test_skips_later_message_without_matching_part(self) -> None:
        """A trailing response does not hide a matching part in an earlier request."""
        prompt = UserPromptPart(content="hello")

        result = find_latest_part(
            [
                ModelRequest(parts=[prompt]),
                ModelResponse(parts=[TextPart(content="reply")]),
            ],
            UserPromptPart,
        )

        assert result is prompt

    def test_finds_tool_return_part(self) -> None:
        """Any part type can be located, including tool returns."""
        prompt = UserPromptPart(content="search")
        tool = ToolReturnPart(
            tool_name="search_knowledge",
            content="hit",
            tool_call_id="call-1",
        )

        result = find_latest_part(
            [ModelRequest(parts=[prompt, tool])],
            ToolReturnPart,
        )

        assert result is tool


class TestFindLatestMessage:
    """Tests for `find_latest_message`."""

    def test_empty_history_returns_none(self) -> None:
        """No messages yields no match."""
        assert find_latest_message([], ModelRequest) is None

    def test_returns_none_when_no_message_matches(self) -> None:
        """Unrelated message types are ignored."""
        messages = [ModelResponse(parts=[TextPart(content="reply")])]

        assert find_latest_message(messages, ModelRequest) is None

    def test_returns_matching_message(self) -> None:
        """The matching message is returned by identity."""
        request = ModelRequest(parts=[UserPromptPart(content="hello")])

        assert find_latest_message([request], ModelRequest) is request

    def test_prefers_later_matching_message(self) -> None:
        """Messages are scanned newest-first."""
        earlier = ModelRequest(parts=[UserPromptPart(content="earlier")])
        later = ModelRequest(parts=[UserPromptPart(content="later")])

        assert find_latest_message([earlier, later], ModelRequest) is later

    def test_finds_latest_of_each_message_type(self) -> None:
        """Request and response lookups each return the newest matching message."""
        first_request = ModelRequest(parts=[UserPromptPart(content="q1")])
        response = ModelResponse(parts=[TextPart(content="a1")])
        second_request = ModelRequest(parts=[UserPromptPart(content="q2")])
        messages = [first_request, response, second_request]

        assert find_latest_message(messages, ModelRequest) is second_request
        assert find_latest_message(messages, ModelResponse) is response


class TestExtractLatestMessageText:
    """Tests for `extract_latest_message_text`."""

    def test_empty_history_returns_none(self) -> None:
        """No messages yields no prompt text."""
        assert extract_latest_message_text([]) is None

    def test_returns_none_when_no_user_prompt_exists(self) -> None:
        """System or model text is not treated as the user prompt."""
        messages = [
            ModelRequest(parts=[SystemPromptPart(content="system")]),
            ModelResponse(parts=[TextPart(content="reply")]),
        ]

        assert extract_latest_message_text(messages) is None

    def test_returns_string_user_prompt(self) -> None:
        """Plain-string prompt content is returned unchanged."""
        messages = [ModelRequest(parts=[UserPromptPart(content="how do I?")])]

        assert extract_latest_message_text(messages) == "how do I?"

    def test_returns_empty_string_prompt(self) -> None:
        """An empty user prompt is distinct from a missing one."""
        messages = [ModelRequest(parts=[UserPromptPart(content="")])]

        assert extract_latest_message_text(messages) == ""

    def test_stringifies_non_string_prompt_content(self) -> None:
        """Structured prompt content is coerced with `str()`."""
        content = [TextContent(content="rich")]
        messages = [ModelRequest(parts=[UserPromptPart(content=content)])]

        assert extract_latest_message_text(messages) == str(content)

    def test_uses_the_latest_user_prompt(self) -> None:
        """Older user prompts are ignored once a newer one exists."""
        messages = [
            ModelRequest(parts=[UserPromptPart(content="older")]),
            ModelResponse(parts=[TextPart(content="reply")]),
            ModelRequest(parts=[UserPromptPart(content="newer")]),
        ]

        assert extract_latest_message_text(messages) == "newer"

    def test_uses_latest_prompt_part_within_a_request(self) -> None:
        """Multiple prompt parts in one request resolve to the newest."""
        messages = [
            ModelRequest(
                parts=[
                    UserPromptPart(content="first"),
                    UserPromptPart(content="second"),
                ]
            )
        ]

        assert extract_latest_message_text(messages) == "second"


class TestAppendLatestMessage:
    """Tests for `append_latest_message`."""

    def test_appends_text_content_as_a_new_user_prompt(self) -> None:
        """A single `UserContent` value is wrapped and appended."""
        original = UserPromptPart(content="question")
        request = ModelRequest(parts=[original])
        knowledge = TextContent(content="<knowledge/>")

        append_latest_message([request], knowledge)

        assert request.parts[0] is original
        added = request.parts[-1]
        assert isinstance(added, UserPromptPart)
        assert added.content == [knowledge]

    def test_appends_string_content_without_wrapping(self) -> None:
        """String content is passed through as a plain user prompt."""
        request = ModelRequest(parts=[UserPromptPart(content="question")])

        append_latest_message([request], "follow-up")

        added = request.parts[-1]
        assert isinstance(added, UserPromptPart)
        assert added.content == "follow-up"

    def test_appends_sequence_content_without_wrapping(self) -> None:
        """A sequence of `UserContent` is used as the new part's content as-is."""
        request = ModelRequest(parts=[UserPromptPart(content="question")])
        content = [TextContent(content="a"), TextContent(content="b")]

        append_latest_message([request], content)

        added = request.parts[-1]
        assert isinstance(added, UserPromptPart)
        assert added.content is content

    def test_mutates_the_latest_request_in_place(self) -> None:
        """Earlier requests are left unchanged; only the newest is appended to."""
        earlier = ModelRequest(parts=[UserPromptPart(content="old")])
        latest = ModelRequest(parts=[UserPromptPart(content="new")])
        messages = [earlier, ModelResponse(parts=[TextPart(content="reply")]), latest]

        append_latest_message(messages, TextContent(content="injected"))

        assert len(earlier.parts) == 1
        assert len(latest.parts) == 2
        assert messages[-1] is latest

    def test_raises_when_history_has_no_model_request(self) -> None:
        """Appending requires a `ModelRequest` to mutate."""
        messages = [ModelResponse(parts=[TextPart(content="reply")])]

        with pytest.raises(
            RuntimeError, match="model request history must include a ModelRequest"
        ):
            append_latest_message(messages, TextContent(content="injected"))
