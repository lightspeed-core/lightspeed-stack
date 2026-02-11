"""Unit tests for functions and types defined in utils/types.py."""

from llama_stack_client.types.shared.interleaved_content_item import (
    ImageContentItem,
    TextContentItem,
)
import pytest
from pydantic import AnyUrl, ValidationError
from pytest_mock import MockerFixture

from utils.types import (
    GraniteToolParser,
    ReferencedDocument,
    ToolCallSummary,
    ToolResultSummary,
    content_to_str,
)


class TestGraniteToolParser:
    """Unit tests for functions defined in utils/types.py."""

    def test_get_tool_parser_when_model_is_is_not_granite(self) -> None:
        """Test that the tool_parser is None when model_id is not a granite model."""
        assert (
            GraniteToolParser.get_parser("ollama3.3") is None
        ), "tool_parser should be None"

    def test_get_tool_parser_when_model_id_does_not_start_with_granite(self) -> None:
        """Test that the tool_parser is None when model_id does not start with granite."""
        assert (
            GraniteToolParser.get_parser("a-fine-trained-granite-model") is None
        ), "tool_parser should be None"

    def test_get_tool_parser_when_model_id_starts_with_granite(self) -> None:
        """Test that the tool_parser is not None when model_id starts with granite."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool_parser should not be None"

    def test_get_tool_calls_from_completion_message_when_none(self) -> None:
        """Test that get_tool_calls returns an empty array when CompletionMessage is None."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        result = tool_parser.get_tool_calls(None)  # pyright: ignore[reportArgumentType]
        assert result == [], "get_tool_calls should return []"

    def test_get_tool_calls_from_completion_message_when_not_none(
        self, mocker: MockerFixture
    ) -> None:
        """Test that get_tool_calls returns an empty array when CompletionMessage has no tool_calls."""  # pylint: disable=line-too-long
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        completion_message = mocker.Mock()
        completion_message.tool_calls = []
        assert not tool_parser.get_tool_calls(
            completion_message
        ), "get_tool_calls should return []"

    def test_get_tool_calls_from_completion_message_when_message_has_tool_calls(
        self, mocker: MockerFixture
    ) -> None:
        """Test that get_tool_calls returns the tool_calls when CompletionMessage has tool_calls."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        completion_message = mocker.Mock()
        tool_calls = [mocker.Mock(tool_name="tool-1"), mocker.Mock(tool_name="tool-2")]
        completion_message.tool_calls = tool_calls
        assert (
            tool_parser.get_tool_calls(completion_message) == tool_calls
        ), f"get_tool_calls should return {tool_calls}"


class TestContentToStr:
    """Tests for content_to_str function."""

    def test_content_to_str_none(self) -> None:
        """Test content_to_str with None."""
        assert content_to_str(None) == ""

    def test_content_to_str_string(self) -> None:
        """Test content_to_str with string."""
        assert content_to_str("test string") == "test string"

    def test_content_to_str_text_content_item(self) -> None:
        """Test content_to_str with TextContentItem."""
        text_item = TextContentItem(text="text content")
        result = content_to_str(text_item)
        assert result == "text content"

    def test_content_to_str_image_content_item(self) -> None:
        """Test content_to_str with ImageContentItem."""

        # ImageContentItem is a Pydantic model that requires 'image' parameter, not 'image_url'
        # Use a mock that passes isinstance check by creating a subclass
        class MockImageContentItem(ImageContentItem):
            """Mock ImageContentItem for testing."""

        image_item = MockImageContentItem.__new__(MockImageContentItem)
        result = content_to_str(image_item)
        assert result == "<image>"

    def test_content_to_str_list(self) -> None:
        """Test content_to_str with list."""
        result = content_to_str(["item1", "item2", "item3"])
        assert result == "item1 item2 item3"

    def test_content_to_str_nested_list(self) -> None:
        """Test content_to_str with nested list."""
        text_item = TextContentItem(text="nested text")
        result = content_to_str(["outer", text_item, ["inner1", "inner2"]])
        assert "outer" in result
        assert "nested text" in result
        assert "inner1" in result
        assert "inner2" in result

    def test_content_to_str_mixed_types(self) -> None:
        """Test content_to_str with mixed types in list."""
        text_item = TextContentItem(text="text")
        result = content_to_str(["string", text_item, 123, None])
        assert "string" in result
        assert "text" in result
        assert "123" in result

    def test_content_to_str_other_type(self) -> None:
        """Test content_to_str with other type falls back to str()."""
        result = content_to_str(123)
        assert result == "123"


class TestToolCallSummary:
    """Test cases for ToolCallSummary type."""

    def test_constructor(self) -> None:
        """Test ToolCallSummary with all fields."""
        tool_call = ToolCallSummary(
            id="call-1",
            name="knowledge_search",
            args={"query": "test"},
            type="tool_call",
        )
        assert tool_call.id == "call-1"
        assert tool_call.name == "knowledge_search"
        assert tool_call.args == {"query": "test"}
        assert tool_call.type == "tool_call"

    def test_missing_required_fields(self) -> None:
        """Test ToolCallSummary raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ToolCallSummary()  # type: ignore[call-arg]


class TestToolResultSummary:
    """Test cases for ToolResultSummary type."""

    def test_constructor(self) -> None:
        """Test ToolResultSummary with all fields."""
        tool_result = ToolResultSummary(
            id="call-1",
            status="success",
            content='{"chunks_found": 5}',
            type="tool_result",
            round=1,
        )
        assert tool_result.id == "call-1"
        assert tool_result.status == "success"
        assert tool_result.content == '{"chunks_found": 5}'
        assert tool_result.type == "tool_result"
        assert tool_result.round == 1

    def test_missing_required_fields(self) -> None:
        """Test ToolResultSummary raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ToolResultSummary()  # type: ignore[call-arg]


class TestReferencedDocument:
    """Test cases for ReferencedDocument type."""

    def test_constructor(self) -> None:
        """Test ReferencedDocument with all fields."""
        doc = ReferencedDocument(
            doc_url=AnyUrl("https://example.com/doc"),
            doc_title="Test Document",
        )
        assert str(doc.doc_url) == "https://example.com/doc"
        assert doc.doc_title == "Test Document"

    def test_constructor_with_defaults(self) -> None:
        """Test ReferencedDocument with no arguments uses None defaults."""
        doc = ReferencedDocument()
        assert doc.doc_url is None
        assert doc.doc_title is None

    def test_constructor_partial_fields(self) -> None:
        """Test ReferencedDocument with partial fields."""
        doc = ReferencedDocument(doc_url=AnyUrl("https://example.com/doc"))
        assert str(doc.doc_url) == "https://example.com/doc"
        assert doc.doc_title is None

        doc = ReferencedDocument(doc_title="Test Title")
        assert doc.doc_url is None
        assert doc.doc_title == "Test Title"
