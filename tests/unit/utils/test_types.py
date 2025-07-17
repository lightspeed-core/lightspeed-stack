"""Unit tests for functionns defined in utils/types.py."""

from unittest.mock import Mock

from utils.types import GraniteToolParser


class TestGraniteToolParser:
    """Unit tests for functionns defined in utils/types.py."""

    def test_get_tool_parser_when_model_is_is_not_granite(self):
        """Test that the tool_parser is None when model_id is not a granite model."""
        assert (
            GraniteToolParser.get_parser("ollama3.3") is None
        ), "tool_parser should be None"

    def test_get_tool_parser_when_model_id_does_not_start_with_granite(self):
        """Test that the tool_parser is None when model_id does not start with granite."""
        assert (
            GraniteToolParser.get_parser("a-fine-trained-granite-model") is None
        ), "tool_parser should be None"

    def test_get_tool_parser_when_model_id_starts_with_granite(self):
        """Test that the tool_parser is not None when model_id starts with granite."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool_parser should not be None"

    def test_get_tool_calls_from_completion_message_when_none(self):
        """Test that get_tool_calls returns an empty array when CompletionMessage is None."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        assert tool_parser.get_tool_calls(None) == [], "get_tool_calls should return []"

    def test_get_tool_calls_from_completion_message_when_not_none(self):
        """Test that get_tool_calls returns an empty array when CompletionMessage has no tool_calls."""  # pylint: disable=line-too-long
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        completion_message = Mock()
        completion_message.tool_calls = []
        assert not tool_parser.get_tool_calls(
            completion_message
        ), "get_tool_calls should return []"

    def test_get_tool_calls_from_completion_message_when_message_has_tool_calls(self):
        """Test that get_tool_calls returns the tool_calls when CompletionMessage has tool_calls."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        completion_message = Mock()
        tool_calls = [Mock(tool_name="tool-1"), Mock(tool_name="tool-2")]
        completion_message.tool_calls = tool_calls
        assert (
            tool_parser.get_tool_calls(completion_message) == tool_calls
        ), f"get_tool_calls should return {tool_calls}"
