"""Unit tests for SQLite cache implementation."""

from pathlib import Path

from typing import Any

import sqlite3

from pydantic import AnyUrl
import pytest

from models.config import SQLiteDatabaseConfiguration
from models.cache_entry import CacheEntry
from models.responses import ConversationData
from utils import suid
from utils.types import ReferencedDocument, ToolCallSummary, ToolResultSummary

from cache.cache_error import CacheError
from cache.sqlite_cache import SQLiteCache

USER_ID_1 = suid.get_suid()
USER_ID_2 = suid.get_suid()
CONVERSATION_ID_1 = suid.get_suid()
CONVERSATION_ID_2 = suid.get_suid()
cache_entry_1 = CacheEntry(
    query="user message1",
    response="AI message1",
    provider="foo",
    model="bar",
    started_at="2025-10-03T09:31:25Z",
    completed_at="2025-10-03T09:31:29Z",
)
cache_entry_2 = CacheEntry(
    query="user message2",
    response="AI message2",
    provider="foo",
    model="bar",
    started_at="2025-10-03T09:31:25Z",
    completed_at="2025-10-03T09:31:29Z",
)


# pylint: disable=too-few-public-methods
class CursorMock:
    """Mock class for simulating DB cursor exceptions."""

    def __init__(self) -> None:
        """Construct the mock cursor class."""

    def execute(self, command: Any) -> None:
        """Execute any SQL command.

        Execute the provided SQL command on this cursor.

        Raises:
            sqlite3.Error: Always raised with message "can not SELECT".
        """
        raise sqlite3.Error("can not SELECT")


# pylint: disable=too-few-public-methods
class ConnectionMock:
    """Mock class for connection."""

    def __init__(self) -> None:
        """Construct the connection mock class.

        Create a mock database connection whose cursor simulates execution errors.

        The mock's cursor() method returns a CursorMock whose execute() raises
        sqlite3.Error, used to simulate a faulty connection in tests.
        """

    def cursor(self) -> Any:
        """Getter for mock cursor.

        Provide a mock database cursor for testing.

        Returns:
            CursorMock: A mock cursor instance that simulates a DB cursor; its
            `execute` raises `sqlite3.Error` to emulate select-related errors.
        """
        return CursorMock()


def create_cache(path: Path) -> SQLiteCache:
    """Create the cache instance.

    Create a SQLiteCache configured to use a test.sqlite file
    inside the given directory.

    Parameters:
        path (Path): Directory in which the `test.sqlite` database file will be created.

    Returns:
        SQLiteCache: Cache instance configured to use the `test.sqlite`
        database at the provided path.
    """
    db_path = str(path / "test.sqlite")
    cc = SQLiteDatabaseConfiguration(db_path=db_path)
    return SQLiteCache(cc)


def test_cache_initialization(tmpdir: Path) -> None:
    """Test the get operation when DB is not connected."""
    cache = create_cache(tmpdir)
    assert cache is not None
    assert cache.connection is not None


def test_cache_initialization_wrong_connection() -> None:
    """Test the get operation when DB can not be connected.

    Verify that creating a cache with an invalid database path fails to open the database.

    Asserts that attempting to create a SQLiteCache with a non-existent or
    inaccessible path raises an exception containing the text "unable to open
    database file".
    """
    with pytest.raises(Exception, match="unable to open database file"):
        _ = create_cache(Path("/foo/bar/baz"))


def test_connected_when_connected(tmpdir: Path) -> None:
    """Test the connected() method."""
    # cache should be connected by default
    cache = create_cache(tmpdir)
    assert cache.connected() is True


def test_connected_when_disconnected(tmpdir: Path) -> None:
    """Test the connected() method."""
    # simulate disconnected cache
    cache = create_cache(tmpdir)
    cache.connection = None
    assert cache.connected() is False


def test_connected_when_connection_error(tmpdir: Path) -> None:
    """Test the connected() method."""
    # simulate connection error
    cache = create_cache(tmpdir)
    # connection can have any type
    cache.connection = ConnectionMock()  # pyright: ignore
    assert cache.connection is not None
    assert cache.connected() is False


def test_initialize_cache_when_connected(tmpdir: Path) -> None:
    """Test the initialize_cache()."""
    cache = create_cache(tmpdir)
    # should not fail
    cache.initialize_cache()


def test_initialize_cache_when_disconnected(tmpdir: Path) -> None:
    """Test the initialize_cache().

    Verify that initialize_cache raises a CacheError when the cache is disconnected.

    Raises:
        CacheError: If the cache connection is None with message "cache is disconnected".
    """
    cache = create_cache(tmpdir)
    cache.connection = None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.initialize_cache()


def test_get_operation_when_disconnected(tmpdir: Path) -> None:
    """Test the get() method.

    Verify that retrieving entries raises CacheError when the cache is disconnected.

    Sets the cache connection to None and asserts that calling `get` for a user
    and conversation raises a `CacheError` with the message "cache is
    disconnected".
    """
    cache = create_cache(tmpdir)
    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.get(USER_ID_1, CONVERSATION_ID_1, False)


def test_get_operation_when_connected(tmpdir: Path) -> None:
    """Test the get() method."""
    cache = create_cache(tmpdir)

    # should not fail
    lst = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert not lst


def test_insert_or_append_when_disconnected(tmpdir: Path) -> None:
    """Test the insert_or_append() method."""
    cache = create_cache(tmpdir)
    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)


def test_insert_or_append_operation_when_connected(tmpdir: Path) -> None:
    """Test the insert_or_append() method."""
    cache = create_cache(tmpdir)

    # should not fail
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)


def test_delete_operation_when_disconnected(tmpdir: Path) -> None:
    """Test the delete() method."""
    cache = create_cache(tmpdir)
    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.delete(USER_ID_1, CONVERSATION_ID_1, False)


def test_delete_operation_when_connected(tmpdir: Path) -> None:
    """Test the delete() method."""
    cache = create_cache(tmpdir)

    # should not fail
    deleted = cache.delete(USER_ID_1, CONVERSATION_ID_1, False)

    # nothing should be deleted
    assert deleted is False


def test_list_operation_when_disconnected(tmpdir: Path) -> None:
    """Test the list() method."""
    cache = create_cache(tmpdir)
    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.list(USER_ID_1, False)


def test_list_operation_when_connected(tmpdir: Path) -> None:
    """Test the list() method.

    Verify that listing conversations on a newly created, connected cache returns an empty list.

    Asserts that cache.list(USER_ID_1, False) produces a falsy result and that
    the returned value is a list.
    """
    cache = create_cache(tmpdir)

    # should not fail
    lst = cache.list(USER_ID_1, False)
    assert not lst
    assert isinstance(lst, list)


def test_ready_method(tmpdir: Path) -> None:
    """Test the ready() method."""
    cache = create_cache(tmpdir)

    # should not fail
    ready = cache.ready()
    assert ready is True


def test_get_operation_after_insert_or_append(tmpdir: Path) -> None:
    """Test the get() method called after insert_or_append() one."""
    cache = create_cache(tmpdir)

    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_2, False)

    lst = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert lst[0] == cache_entry_1
    assert lst[1] == cache_entry_2


def test_get_operation_after_delete(tmpdir: Path) -> None:
    """Test the get() method called after delete() one."""
    cache = create_cache(tmpdir)

    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_2, False)

    deleted = cache.delete(USER_ID_1, CONVERSATION_ID_1, False)
    assert deleted is True

    lst = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert not lst


def test_multiple_ids(tmpdir: Path) -> None:
    """Test the get() method called after delete() one."""
    cache = create_cache(tmpdir)

    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_2, False)
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_2, cache_entry_1, False)
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_2, cache_entry_2, False)
    cache.insert_or_append(USER_ID_2, CONVERSATION_ID_1, cache_entry_1, False)
    cache.insert_or_append(USER_ID_2, CONVERSATION_ID_1, cache_entry_2, False)
    cache.insert_or_append(USER_ID_2, CONVERSATION_ID_2, cache_entry_1, False)
    cache.insert_or_append(USER_ID_2, CONVERSATION_ID_2, cache_entry_2, False)

    deleted = cache.delete(USER_ID_1, CONVERSATION_ID_1, False)
    assert deleted is True

    lst = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert not lst

    lst = cache.get(USER_ID_1, CONVERSATION_ID_2, False)
    assert lst[0] == cache_entry_1
    assert lst[1] == cache_entry_2

    lst = cache.get(USER_ID_2, CONVERSATION_ID_1, False)
    assert lst[0] == cache_entry_1
    assert lst[1] == cache_entry_2

    lst = cache.get(USER_ID_2, CONVERSATION_ID_2, False)
    assert lst[0] == cache_entry_1
    assert lst[1] == cache_entry_2


def test_list_with_conversations(tmpdir: Path) -> None:
    """Test the list() method with actual conversations."""
    cache = create_cache(tmpdir)

    # Add some conversations
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_2, cache_entry_2, False)

    # Set topic summaries
    cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, "First conversation", False)
    cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_2, "Second conversation", False)

    # Test list functionality
    conversations = cache.list(USER_ID_1, False)
    assert len(conversations) == 2
    assert all(isinstance(conv, ConversationData) for conv in conversations)

    # Check that conversations are ordered by last_message_timestamp DESC
    assert (
        conversations[0].last_message_timestamp
        >= conversations[1].last_message_timestamp
    )

    # Check conversation IDs
    conv_ids = [conv.conversation_id for conv in conversations]
    assert CONVERSATION_ID_1 in conv_ids
    assert CONVERSATION_ID_2 in conv_ids


def test_topic_summary_operations(tmpdir: Path) -> None:
    """Test topic summary set operations and retrieval via list."""
    cache = create_cache(tmpdir)

    # Add a conversation
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)

    # Set a topic summary
    test_summary = "This conversation is about machine learning and AI"
    cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, test_summary, False)

    # Retrieve the topic summary via list
    conversations = cache.list(USER_ID_1, False)
    assert len(conversations) == 1
    assert conversations[0].topic_summary == test_summary

    # Update the topic summary
    updated_summary = "This conversation is about deep learning and neural networks"
    cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, updated_summary, False)

    # Verify the update via list
    conversations = cache.list(USER_ID_1, False)
    assert len(conversations) == 1
    assert conversations[0].topic_summary == updated_summary


def test_topic_summary_after_conversation_delete(tmpdir: Path) -> None:
    """Test that topic summary is deleted when conversation is deleted."""
    cache = create_cache(tmpdir)

    # Add some cache entries and a topic summary
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)
    cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, "Test summary", False)

    # Verify both exist
    entries = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert len(entries) == 1
    conversations = cache.list(USER_ID_1, False)
    assert len(conversations) == 1
    assert conversations[0].topic_summary == "Test summary"

    # Delete the conversation
    deleted = cache.delete(USER_ID_1, CONVERSATION_ID_1, False)
    assert deleted is True

    # Verify both are deleted
    entries = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert len(entries) == 0
    conversations = cache.list(USER_ID_1, False)
    assert len(conversations) == 0


def test_topic_summary_when_disconnected(tmpdir: Path) -> None:
    """Test topic summary operations when cache is disconnected."""
    cache = create_cache(tmpdir)
    cache.connection = None
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, "Test", False)


def test_insert_and_get_with_referenced_documents(tmpdir: Path) -> None:
    """
    Test that a CacheEntry with referenced_documents is correctly
    serialized, stored, and retrieved.
    """
    cache = create_cache(tmpdir)

    # Create a CacheEntry with referenced documents
    docs = [
        ReferencedDocument(doc_title="Test Doc", doc_url=AnyUrl("http://example.com"))
    ]
    entry_with_docs = CacheEntry(
        query="user message",
        response="AI message",
        provider="foo",
        model="bar",
        started_at="start_time",
        completed_at="end_time",
        referenced_documents=docs,
    )

    # Call the insert method
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, entry_with_docs)
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_with_docs
    assert retrieved_entries[0].referenced_documents is not None
    assert retrieved_entries[0].referenced_documents[0].doc_title == "Test Doc"


def test_insert_and_get_without_referenced_documents(tmpdir: Path) -> None:
    """
    Test that a CacheEntry without referenced_documents is correctly
    stored and retrieved with its referenced_documents attribute as None.
    """
    cache = create_cache(tmpdir)

    # Use CacheEntry without referenced_documents
    entry_without_docs = cache_entry_1

    # Call the insert method
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, entry_without_docs)
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_without_docs
    assert retrieved_entries[0].referenced_documents is None
    assert retrieved_entries[0].tool_calls is None
    assert retrieved_entries[0].tool_results is None


def test_insert_and_get_with_tool_calls_and_results(tmpdir: Path) -> None:
    """
    Test that a CacheEntry with tool_calls and tool_results is correctly
    serialized, stored, and retrieved.
    """
    cache = create_cache(tmpdir)

    # Create tool_calls and tool_results
    tool_calls = [
        ToolCallSummary(
            id="call_1", name="test_tool", args={"param": "value"}, type="tool_call"
        )
    ]
    tool_results = [
        ToolResultSummary(
            id="call_1",
            status="success",
            content="result data",
            type="tool_result",
            round=1,
        )
    ]
    entry_with_tools = CacheEntry(
        query="user message",
        response="AI message",
        provider="foo",
        model="bar",
        started_at="start_time",
        completed_at="end_time",
        tool_calls=tool_calls,
        tool_results=tool_results,
    )

    # Call the insert method
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, entry_with_tools)
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_with_tools
    assert retrieved_entries[0].tool_calls is not None
    assert len(retrieved_entries[0].tool_calls) == 1
    assert retrieved_entries[0].tool_calls[0].name == "test_tool"
    assert retrieved_entries[0].tool_calls[0].args == {"param": "value"}
    assert retrieved_entries[0].tool_results is not None
    assert len(retrieved_entries[0].tool_results) == 1
    assert retrieved_entries[0].tool_results[0].status == "success"
    assert retrieved_entries[0].tool_results[0].content == "result data"


def test_insert_and_get_with_all_fields(tmpdir: Path) -> None:
    """
    Test that a CacheEntry with all fields (referenced_documents, tool_calls,
    tool_results) is correctly serialized, stored, and retrieved.
    """
    cache = create_cache(tmpdir)

    # Create all fields
    docs = [
        ReferencedDocument(doc_title="Test Doc", doc_url=AnyUrl("http://example.com"))
    ]
    tool_calls = [
        ToolCallSummary(
            id="call_1", name="test_tool", args={"key": "value"}, type="tool_call"
        )
    ]
    tool_results = [
        ToolResultSummary(
            id="call_1", status="success", content="output", type="tool_result", round=1
        )
    ]
    entry_with_all = CacheEntry(
        query="user query",
        response="AI response",
        provider="provider",
        model="model",
        started_at="start",
        completed_at="end",
        referenced_documents=docs,
        tool_calls=tool_calls,
        tool_results=tool_results,
    )

    # Call the insert method
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, entry_with_all)
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_with_all
    assert retrieved_entries[0].referenced_documents is not None
    assert retrieved_entries[0].referenced_documents[0].doc_title == "Test Doc"
    assert retrieved_entries[0].tool_calls is not None
    assert retrieved_entries[0].tool_calls[0].name == "test_tool"
    assert retrieved_entries[0].tool_results is not None
    assert retrieved_entries[0].tool_results[0].status == "success"
