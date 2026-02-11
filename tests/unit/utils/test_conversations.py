"""Unit tests for conversation utility functions."""

from datetime import datetime, UTC
from typing import Any

import pytest
from pytest_mock import MockerFixture

from constants import DEFAULT_RAG_TOOL
from models.database.conversations import UserTurn
from utils.conversations import (
    _build_tool_call_summary_from_item,
    _extract_text_from_content,
    build_conversation_turns_from_items,
)
from utils.types import ToolCallSummary

# Default conversation start time for tests
DEFAULT_CONVERSATION_START_TIME = datetime.fromisoformat(
    "2024-01-01T00:00:00Z"
).replace(tzinfo=UTC)


@pytest.fixture(name="create_mock_user_turn")
def create_mock_user_turn_fixture(mocker: MockerFixture) -> Any:
    """Factory fixture to create mock UserTurn objects.

    Args:
        mocker: Mocker fixture

    Returns:
        Function that creates a mock UserTurn with specified attributes
    """

    def _create(
        turn_number: int = 1,
        started_at: str = "2024-01-01T00:01:00Z",
        completed_at: str = "2024-01-01T00:01:05Z",
        provider: str = "google",
        model: str = "gemini-2.0-flash-exp",
    ) -> Any:
        mock_turn = mocker.Mock(spec=UserTurn)
        mock_turn.turn_number = turn_number
        mock_turn.started_at = datetime.fromisoformat(started_at).replace(tzinfo=UTC)
        mock_turn.completed_at = datetime.fromisoformat(completed_at).replace(
            tzinfo=UTC
        )
        mock_turn.provider = provider
        mock_turn.model = model
        return mock_turn

    return _create


class TestExtractTextFromContent:
    """Test cases for _extract_text_from_content function."""

    def test_string_input(self) -> None:
        """Test extracting text from string input."""
        content = "Simple text message"
        result = _extract_text_from_content(content)

        assert result == "Simple text message"

    def test_composed_input(self) -> None:
        """Test extracting text from composed (list) input."""

        # Create simple objects with text and refusal attributes
        class TextPart:  # pylint: disable=too-few-public-methods
            """Helper class for testing text extraction."""

            def __init__(self, text: str) -> None:
                self.text = text

        class RefusalPart:  # pylint: disable=too-few-public-methods
            """Helper class for testing refusal extraction."""

            def __init__(self, refusal: str) -> None:
                self.refusal = refusal

        # Create composed content with various types
        content = [
            "String part",
            TextPart("First part"),
            RefusalPart("Refusal message"),
            {"text": "Dict text"},
            {"refusal": "Dict refusal"},
        ]

        result = _extract_text_from_content(content)

        assert result == "String partFirst partRefusal messageDict textDict refusal"


class TestBuildToolCallSummaryFromItem:
    """Test cases for _build_tool_call_summary_from_item function."""

    def test_function_call_item(self, mocker: MockerFixture) -> None:
        """Test parsing a function_call item."""
        mock_item = mocker.Mock()
        mock_item.type = "function_call"
        mock_item.call_id = "call_123"
        mock_item.name = "test_function"
        mock_item.arguments = '{"arg1": "value1"}'

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert isinstance(tool_call, ToolCallSummary)
        assert tool_call.id == "call_123"
        assert tool_call.name == "test_function"
        assert tool_call.type == "function_call"
        assert tool_result is None

    def test_file_search_call_with_results(self, mocker: MockerFixture) -> None:
        """Test parsing a file_search_call item with results."""
        mock_result = mocker.Mock()
        mock_result.model_dump.return_value = {"file": "test.txt", "content": "test"}

        mock_item = mocker.Mock()
        mock_item.type = "file_search_call"
        mock_item.id = "file_search_123"
        mock_item.queries = ["query1", "query2"]
        mock_item.status = "success"
        mock_item.results = [mock_result]

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert tool_call.id == "file_search_123"
        assert tool_call.name == DEFAULT_RAG_TOOL
        assert tool_call.type == "file_search_call"
        assert tool_call.args == {"queries": ["query1", "query2"]}

        assert tool_result is not None
        assert tool_result.id == "file_search_123"
        assert tool_result.status == "success"
        assert tool_result.type == "file_search_call"
        assert tool_result.round == 1
        assert "results" in tool_result.content

    def test_file_search_call_without_results(self, mocker: MockerFixture) -> None:
        """Test parsing a file_search_call item without results."""
        mock_item = mocker.Mock()
        mock_item.type = "file_search_call"
        mock_item.id = "file_search_123"
        mock_item.queries = ["query1"]
        mock_item.status = "success"
        mock_item.results = None

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert tool_result is not None
        assert tool_result.content == ""

    def test_web_search_call(self, mocker: MockerFixture) -> None:
        """Test parsing a web_search_call item."""
        mock_item = mocker.Mock()
        mock_item.type = "web_search_call"
        mock_item.id = "web_search_123"
        mock_item.status = "success"

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert tool_call.id == "web_search_123"
        assert tool_call.name == "web_search"
        assert tool_call.type == "web_search_call"
        assert tool_call.args == {}

        assert tool_result is not None
        assert tool_result.id == "web_search_123"
        assert tool_result.status == "success"
        assert tool_result.type == "web_search_call"
        assert tool_result.content == ""
        assert tool_result.round == 1

    def test_mcp_call_with_error(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_call item with error."""
        mock_item = mocker.Mock()
        mock_item.type = "mcp_call"
        mock_item.id = "mcp_123"
        mock_item.name = "test_mcp_tool"
        mock_item.arguments = '{"param": "value"}'
        mock_item.server_label = "test_server"
        mock_item.error = "Error occurred"
        mock_item.output = None

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert tool_call.id == "mcp_123"
        assert tool_call.name == "test_mcp_tool"
        assert tool_call.type == "mcp_call"
        assert "server_label" in tool_call.args
        assert tool_call.args["server_label"] == "test_server"

        assert tool_result is not None
        assert tool_result.status == "failure"
        assert tool_result.content == "Error occurred"

    def test_mcp_call_with_output(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_call item with output."""
        mock_item = mocker.Mock()
        mock_item.type = "mcp_call"
        mock_item.id = "mcp_123"
        mock_item.name = "test_mcp_tool"
        mock_item.arguments = '{"param": "value"}'
        mock_item.server_label = "test_server"
        mock_item.error = None
        mock_item.output = "Success output"

        _, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_result is not None
        assert tool_result.status == "success"
        assert tool_result.content == "Success output"

    def test_mcp_call_without_server_label(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_call item without server_label."""
        mock_item = mocker.Mock()
        mock_item.type = "mcp_call"
        mock_item.id = "mcp_123"
        mock_item.name = "test_mcp_tool"
        mock_item.arguments = '{"param": "value"}'
        mock_item.server_label = None
        mock_item.error = None
        mock_item.output = "output"

        tool_call, _ = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert "server_label" not in tool_call.args

    def test_mcp_list_tools(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_list_tools item."""
        mock_tool = mocker.Mock()
        mock_tool.name = "tool1"
        mock_tool.description = "Description"
        mock_tool.input_schema = {"type": "object"}

        mock_item = mocker.Mock()
        mock_item.type = "mcp_list_tools"
        mock_item.id = "list_tools_123"
        mock_item.server_label = "test_server"
        mock_item.tools = [mock_tool]

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert tool_call.id == "list_tools_123"
        assert tool_call.name == "mcp_list_tools"
        assert tool_call.type == "mcp_list_tools"
        assert tool_call.args == {"server_label": "test_server"}

        assert tool_result is not None
        assert tool_result.status == "success"
        assert "tools" in tool_result.content
        assert "test_server" in tool_result.content

    def test_mcp_approval_request(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_approval_request item."""
        mock_item = mocker.Mock()
        mock_item.type = "mcp_approval_request"
        mock_item.id = "approval_123"
        mock_item.name = "approve_action"
        mock_item.arguments = '{"action": "delete"}'

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is not None
        assert tool_call.id == "approval_123"
        assert tool_call.name == "approve_action"
        assert tool_call.type == "tool_call"
        assert tool_result is None

    def test_mcp_approval_response_approved(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_approval_response item with approval."""
        mock_item = mocker.Mock()
        mock_item.type = "mcp_approval_response"
        mock_item.approval_request_id = "approval_123"
        mock_item.approve = True
        mock_item.reason = "Looks good"

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is None
        assert tool_result is not None
        assert tool_result.id == "approval_123"
        assert tool_result.status == "success"
        assert tool_result.type == "mcp_approval_response"
        assert "reason" in tool_result.content

    def test_mcp_approval_response_denied(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_approval_response item with denial."""
        mock_item = mocker.Mock()
        mock_item.type = "mcp_approval_response"
        mock_item.approval_request_id = "approval_123"
        mock_item.approve = False
        mock_item.reason = "Not allowed"

        _, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_result is not None
        assert tool_result.status == "denied"

    def test_mcp_approval_response_without_reason(self, mocker: MockerFixture) -> None:
        """Test parsing an mcp_approval_response item without reason."""
        mock_item = mocker.Mock()
        mock_item.type = "mcp_approval_response"
        mock_item.approval_request_id = "approval_123"
        mock_item.approve = True
        mock_item.reason = None

        _, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_result is not None
        assert tool_result.content == "{}"

    def test_function_call_output(self, mocker: MockerFixture) -> None:
        """Test parsing a function_call_output item."""
        mock_item = mocker.Mock()
        mock_item.type = "function_call_output"
        mock_item.call_id = "call_123"
        mock_item.status = "success"
        mock_item.output = "Function result"

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is None
        assert tool_result is not None
        assert tool_result.id == "call_123"
        assert tool_result.status == "success"
        assert tool_result.content == "Function result"
        assert tool_result.type == "function_call_output"
        assert tool_result.round == 1

    def test_function_call_output_without_status(self, mocker: MockerFixture) -> None:
        """Test parsing a function_call_output item without status."""
        mock_item = mocker.Mock()
        mock_item.type = "function_call_output"
        mock_item.call_id = "call_123"
        mock_item.status = None
        mock_item.output = "Function result"

        _, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_result is not None
        assert tool_result.status == "success"  # Defaults to "success"

    def test_unknown_item_type(self, mocker: MockerFixture) -> None:
        """Test parsing an unknown item type."""
        mock_item = mocker.Mock()
        mock_item.type = "unknown_type"

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is None
        assert tool_result is None

    def test_item_without_type_attribute(self, mocker: MockerFixture) -> None:
        """Test parsing an item without type attribute."""
        mock_item = mocker.Mock(spec=[])
        # Don't set type attribute

        tool_call, tool_result = _build_tool_call_summary_from_item(mock_item)

        assert tool_call is None
        assert tool_result is None


class TestBuildConversationTurnsFromItems:
    """Test cases for build_conversation_turns_from_items function."""

    def test_empty_items(self) -> None:
        """Test with empty items list."""
        result = build_conversation_turns_from_items(
            [], [], DEFAULT_CONVERSATION_START_TIME
        )

        assert not result

    def test_single_turn_user_and_assistant(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building a single turn with user and assistant messages."""
        mock_user_msg = mocker.Mock()
        mock_user_msg.type = "message"
        mock_user_msg.role = "user"
        mock_user_msg.content = "Hello"

        mock_assistant_msg = mocker.Mock()
        mock_assistant_msg.type = "message"
        mock_assistant_msg.role = "assistant"
        mock_assistant_msg.content = "Hi there!"

        items = [mock_user_msg, mock_assistant_msg]
        turns_metadata = [create_mock_user_turn(turn_number=1)]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 1
        turn = result[0]
        assert len(turn.messages) == 2
        assert turn.messages[0].type == "user"
        assert turn.messages[0].content == "Hello"
        assert turn.messages[1].type == "assistant"
        assert turn.messages[1].content == "Hi there!"
        assert turn.tool_calls == []
        assert turn.tool_results == []

    def test_multiple_turns(
        self, mocker: MockerFixture, create_mock_user_turn: Any
    ) -> None:
        """Test building multiple turns."""
        items = [
            mocker.Mock(type="message", role="user", content="Question 1"),
            mocker.Mock(type="message", role="assistant", content="Answer 1"),
            mocker.Mock(type="message", role="user", content="Question 2"),
            mocker.Mock(type="message", role="assistant", content="Answer 2"),
        ]
        turns_metadata = [
            create_mock_user_turn(turn_number=1),
            create_mock_user_turn(turn_number=2),
        ]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 2
        assert result[0].messages[0].content == "Question 1"
        assert result[0].messages[1].content == "Answer 1"
        assert result[1].messages[0].content == "Question 2"
        assert result[1].messages[1].content == "Answer 2"

    def test_turn_with_tool_calls(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building a turn with tool calls."""
        mock_function_call = mocker.Mock()
        mock_function_call.type = "function_call"
        mock_function_call.call_id = "call_1"
        mock_function_call.name = "test_tool"
        mock_function_call.arguments = '{"arg": "value"}'

        items = [
            mocker.Mock(type="message", role="user", content="Use tool"),
            mock_function_call,
            mocker.Mock(type="message", role="assistant", content="Done"),
        ]
        turns_metadata = [create_mock_user_turn(turn_number=1)]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 1
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0].name == "test_tool"

    def test_turn_with_tool_results(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building a turn with tool results."""
        mock_function_output = mocker.Mock()
        mock_function_output.type = "function_call_output"
        mock_function_output.call_id = "call_1"
        mock_function_output.status = "success"
        mock_function_output.output = "Result"

        items = [
            mocker.Mock(type="message", role="user", content="Use tool"),
            mock_function_output,
            mocker.Mock(type="message", role="assistant", content="Done"),
        ]
        turns_metadata = [create_mock_user_turn(turn_number=1)]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 1
        assert len(result[0].tool_results) == 1
        assert result[0].tool_results[0].status == "success"

    def test_turn_with_both_tool_calls_and_results(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building a turn with both tool calls and results."""
        mock_function_call = mocker.Mock()
        mock_function_call.type = "function_call"
        mock_function_call.call_id = "call_1"
        mock_function_call.name = "test_tool"
        mock_function_call.arguments = "{}"

        mock_function_output = mocker.Mock()
        mock_function_output.type = "function_call_output"
        mock_function_output.call_id = "call_1"
        mock_function_output.status = "success"
        mock_function_output.output = "Result"

        items = [
            mocker.Mock(type="message", role="user", content="Use tool"),
            mock_function_call,
            mock_function_output,
            mocker.Mock(type="message", role="assistant", content="Done"),
        ]
        turns_metadata = [create_mock_user_turn(turn_number=1)]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 1
        assert len(result[0].tool_calls) == 1
        assert len(result[0].tool_results) == 1

    def test_turn_with_file_search_tool(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building a turn with file_search_call tool."""
        mock_file_search = mocker.Mock()
        mock_file_search.type = "file_search_call"
        mock_file_search.id = "file_1"
        mock_file_search.queries = ["query1"]
        mock_file_search.status = "success"
        mock_file_search.results = None

        items = [
            mocker.Mock(type="message", role="user", content="Search files"),
            mock_file_search,
            mocker.Mock(type="message", role="assistant", content="Found files"),
        ]
        turns_metadata = [create_mock_user_turn(turn_number=1)]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 1
        assert len(result[0].tool_calls) == 1
        assert len(result[0].tool_results) == 1
        assert result[0].tool_calls[0].name == DEFAULT_RAG_TOOL

    def test_turn_with_multiple_assistant_messages(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building a turn with multiple assistant messages."""
        items = [
            mocker.Mock(type="message", role="user", content="Question"),
            mocker.Mock(type="message", role="assistant", content="Part 1"),
            mocker.Mock(type="message", role="assistant", content="Part 2"),
        ]
        turns_metadata = [create_mock_user_turn(turn_number=1)]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 1
        assert len(result[0].messages) == 3
        assert result[0].messages[0].type == "user"
        assert result[0].messages[1].type == "assistant"
        assert result[0].messages[2].type == "assistant"

    def test_turn_metadata_used_correctly(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test that turn metadata (provider, model, timestamps) is used correctly."""
        items = [
            mocker.Mock(type="message", role="user", content="Test"),
            mocker.Mock(type="message", role="assistant", content="Response"),
        ]
        turns_metadata = [
            create_mock_user_turn(
                turn_number=1,
                provider="openai",
                model="gpt-4",
                started_at="2024-01-01T10:00:00Z",
                completed_at="2024-01-01T10:00:05Z",
            )
        ]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 1
        turn = result[0]
        assert turn.provider == "openai"
        assert turn.model == "gpt-4"
        assert turn.started_at == "2024-01-01T10:00:00Z"
        assert turn.completed_at == "2024-01-01T10:00:05Z"

    def test_turn_with_only_tool_items_no_messages(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building a turn with only tool items (no messages)."""
        mock_function_call = mocker.Mock()
        mock_function_call.type = "function_call"
        mock_function_call.call_id = "call_1"
        mock_function_call.name = "test_tool"
        mock_function_call.arguments = "{}"

        items = [mock_function_call]
        turns_metadata = [create_mock_user_turn(turn_number=1)]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        # Should still create a turn if there are tool calls/results
        assert len(result) == 1
        assert len(result[0].messages) == 0
        assert len(result[0].tool_calls) == 1

    def test_multiple_turns_with_tools(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test building multiple turns where some have tools."""
        mock_function_call = mocker.Mock()
        mock_function_call.type = "function_call"
        mock_function_call.call_id = "call_1"
        mock_function_call.name = "test_tool"
        mock_function_call.arguments = "{}"

        items = [
            mocker.Mock(type="message", role="user", content="Question 1"),
            mocker.Mock(type="message", role="assistant", content="Answer 1"),
            mocker.Mock(type="message", role="user", content="Question 2"),
            mock_function_call,
            mocker.Mock(type="message", role="assistant", content="Answer 2"),
        ]
        turns_metadata = [
            create_mock_user_turn(turn_number=1),
            create_mock_user_turn(turn_number=2),
        ]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 2
        assert len(result[0].tool_calls) == 0
        assert len(result[1].tool_calls) == 1

    def test_turn_indexing_with_metadata(
        self,
        mocker: MockerFixture,
        create_mock_user_turn: Any,
    ) -> None:
        """Test that turn metadata is correctly indexed by turn number."""
        items = [
            mocker.Mock(type="message", role="user", content="Q1"),
            mocker.Mock(type="message", role="assistant", content="A1"),
            mocker.Mock(type="message", role="user", content="Q2"),
            mocker.Mock(type="message", role="assistant", content="A2"),
            mocker.Mock(type="message", role="user", content="Q3"),
            mocker.Mock(type="message", role="assistant", content="A3"),
        ]
        turns_metadata = [
            create_mock_user_turn(turn_number=1, provider="provider1"),
            create_mock_user_turn(turn_number=2, provider="provider2"),
            create_mock_user_turn(turn_number=3, provider="provider3"),
        ]

        result = build_conversation_turns_from_items(
            items, turns_metadata, DEFAULT_CONVERSATION_START_TIME
        )

        assert len(result) == 3
        assert result[0].provider == "provider1"
        assert result[1].provider == "provider2"
        assert result[2].provider == "provider3"

    def test_legacy_conversation_without_metadata(self, mocker: MockerFixture) -> None:
        """Test building turns for legacy conversation without stored turn metadata."""
        # Legacy conversations have items but no turns_metadata
        items = [
            mocker.Mock(type="message", role="user", content="Question"),
            mocker.Mock(type="message", role="assistant", content="Answer"),
        ]
        turns_metadata: list[UserTurn] = []  # Empty metadata for legacy conversation
        conversation_start_time = datetime.fromisoformat(
            "2024-01-01T10:00:00Z"
        ).replace(tzinfo=UTC)

        result = build_conversation_turns_from_items(
            items, turns_metadata, conversation_start_time
        )

        assert len(result) == 1
        turn = result[0]
        assert len(turn.messages) == 2
        # Legacy conversations should use dummy metadata with N/A values
        assert turn.provider == "N/A"
        assert turn.model == "N/A"
        # Timestamps should match conversation start time
        assert turn.started_at == "2024-01-01T10:00:00Z"
        assert turn.completed_at == "2024-01-01T10:00:00Z"
