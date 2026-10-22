"""Unit tests for safety.utils."""

import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    ImageUrl,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextContent,
    TextPart,
    ToolReturn,
    UserPromptPart,
)

from safety.utils import (
    append_latest_message,
    extract_latest_message_text,
    find_latest_message,
    find_latest_part,
    replace_latest_message,
    tool_result_to_str,
)


class _Payload(BaseModel):  # pylint: disable=too-few-public-methods
    """Small model used to exercise tool-result rendering."""

    value: str


class _Opaque:  # pylint: disable=too-few-public-methods
    """Object with no JSON representation and a stable string form."""

    def __str__(self) -> str:
        """Return a stable rendering."""
        return "<opaque>"


class TestFindLatestPart:
    """Tests for find_latest_part."""

    def test_returns_the_newest_matching_part(self) -> None:
        """Test that scanning walks messages and parts from newest to oldest."""
        older = UserPromptPart(content="old")
        newer = UserPromptPart(content="new")
        older_system = SystemPromptPart(content="sys")
        newer_system = SystemPromptPart(content="later")
        messages = [
            ModelRequest(parts=[older, older_system]),
            ModelRequest(parts=[newer_system, newer]),
        ]

        assert find_latest_part(messages, UserPromptPart) is newer
        assert find_latest_part(messages, SystemPromptPart) is newer_system

    def test_returns_none_when_nothing_matches(self) -> None:
        """Test that a history with no matching part returns None."""
        messages = [ModelRequest(parts=[SystemPromptPart(content="sys")])]

        assert find_latest_part(messages, UserPromptPart) is None

    def test_returns_none_for_an_empty_history(self) -> None:
        """Test that an empty history returns None."""
        assert find_latest_part([], UserPromptPart) is None


class TestFindLatestMessage:
    """Tests for find_latest_message."""

    def test_returns_the_newest_message_of_the_requested_type(self) -> None:
        """Test that a later response does not hide an earlier request."""
        first = ModelRequest(parts=[UserPromptPart(content="ask")])
        response = ModelResponse(parts=[TextPart(content="answer")])
        second = ModelRequest(parts=[UserPromptPart(content="follow-up")])
        messages = [first, response, second]

        assert find_latest_message(messages, ModelRequest) is second
        assert find_latest_message(messages, ModelResponse) is response

    def test_returns_none_when_the_type_is_absent(self) -> None:
        """Test that a history of only responses has no request to return."""
        messages = [ModelResponse(parts=[TextPart(content="answer")])]

        assert find_latest_message(messages, ModelRequest) is None


class TestExtractLatestMessageText:
    """Tests for extract_latest_message_text."""

    def test_returns_the_newest_user_prompt_text(self) -> None:
        """Test that the latest user prompt is returned as text."""
        messages = [
            ModelRequest(parts=[UserPromptPart(content="old")]),
            ModelResponse(parts=[TextPart(content="answer")]),
            ModelRequest(parts=[UserPromptPart(content="new")]),
        ]

        assert extract_latest_message_text(messages) == "new"

    def test_stringifies_non_text_user_content(self) -> None:
        """Test that multimodal user content is rendered with str."""
        content = ["hello", TextContent(content="world")]
        messages = [ModelRequest(parts=[UserPromptPart(content=content)])]

        assert extract_latest_message_text(messages) == str(content)

    def test_returns_none_when_there_is_no_user_prompt(self) -> None:
        """Test that a system-only request has no prompt text."""
        messages = [ModelRequest(parts=[SystemPromptPart(content="sys")])]

        assert extract_latest_message_text(messages) is None


class TestAppendLatestMessage:
    """Tests for append_latest_message."""

    def test_appends_a_user_prompt_to_the_latest_request(self) -> None:
        """Test that a new user prompt is added without dropping existing parts."""
        request = ModelRequest(parts=[UserPromptPart(content="first")])
        response = ModelResponse(parts=[TextPart(content="answer")])

        append_latest_message([request, response], "second")

        assert [part.content for part in request.parts] == ["first", "second"]
        assert len(response.parts) == 1

    def test_accepts_multimodal_content(self) -> None:
        """Test that appended content can be a sequence of user content."""
        request = ModelRequest(parts=[UserPromptPart(content="first")])
        content = ["more", TextContent(content="detail")]

        append_latest_message([request], content)

        assert request.parts[1].content == content

    def test_raises_when_no_model_request_exists(self) -> None:
        """Test that appending fails when the history has no model request."""
        messages = [ModelResponse(parts=[TextPart(content="answer")])]

        with pytest.raises(RuntimeError, match="ModelRequest"):
            append_latest_message(messages, "follow-up")


class TestReplaceLatestMessage:
    """Tests for replace_latest_message."""

    def test_rewrites_only_the_newest_user_prompt(self) -> None:
        """Test that an older user prompt is left unchanged."""
        first = ModelRequest(parts=[UserPromptPart(content="old")])
        second = ModelRequest(parts=[UserPromptPart(content="new")])

        assert replace_latest_message([first, second], "rewritten") is True

        assert first.parts[0].content == "old"
        assert second.parts[0].content == "rewritten"

    def test_replaces_text_with_multimodal_content(self) -> None:
        """Test that a text prompt can be replaced by a content sequence."""
        request = ModelRequest(parts=[UserPromptPart(content="text")])
        content = ["redacted", TextContent(content="ok")]

        assert replace_latest_message([request], content) is True

        assert request.parts[0].content == content

    def test_returns_false_when_there_is_no_user_prompt(self) -> None:
        """Test that a response-only history is left unchanged."""
        messages = [ModelResponse(parts=[TextPart(content="answer")])]

        assert replace_latest_message(messages, "rewritten") is False

    def test_rejects_plain_text_over_a_multimodal_prompt(self) -> None:
        """Test that plain text cannot overwrite attached multimodal parts."""
        request = ModelRequest(
            parts=[UserPromptPart(content=[ImageUrl(url="https://example.com/a.png")])]
        )

        with pytest.raises(UserError, match="multimodal"):
            replace_latest_message([request], "text only")

        assert request.parts[0].content[0].url == "https://example.com/a.png"


class TestToolResultToStr:
    """Tests for tool_result_to_str."""

    def test_string_passes_through(self) -> None:
        """Test that a plain string is returned unchanged."""
        assert tool_result_to_str("hello") == "hello"

    def test_dict_and_list_and_tuple_are_json(self) -> None:
        """Test that common containers are rendered as JSON."""
        assert tool_result_to_str({"key": "value"}) == '{"key": "value"}'
        assert tool_result_to_str([1, "two"]) == '[1, "two"]'
        assert tool_result_to_str((1, "two")) == '[1, "two"]'

    def test_scalars_are_json(self) -> None:
        """Test that None and numbers use their JSON forms."""
        assert tool_result_to_str(None) == "null"
        assert tool_result_to_str(3) == "3"

    def test_pydantic_model_uses_model_dump_json(self) -> None:
        """Test that a Pydantic model is rendered with model_dump_json."""
        assert tool_result_to_str(_Payload(value="secret")) == '{"value":"secret"}'

    def test_tool_return_unwraps_its_return_value(self) -> None:
        """Test that ToolReturn is rendered from its return value."""
        assert tool_result_to_str(ToolReturn(return_value="actual")) == "actual"
        assert tool_result_to_str(ToolReturn(return_value={"a": 1})) == '{"a": 1}'
        assert (
            tool_result_to_str(ToolReturn(return_value=_Payload(value="secret")))
            == '{"value":"secret"}'
        )

    def test_non_json_object_uses_its_string_form(self) -> None:
        """Test that an arbitrary object is JSON-encoded via str."""
        assert tool_result_to_str(_Opaque()) == '"<opaque>"'

    def test_non_string_keys_fall_back_to_str(self) -> None:
        """Test that a TypeError from json.dumps falls back to str."""
        assert tool_result_to_str({(1, 2): "a"}) == "{(1, 2): 'a'}"
