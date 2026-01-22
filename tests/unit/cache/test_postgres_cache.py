"""Unit tests for PostgreSQL cache implementation."""

import json

from typing import Any

import pytest
from pytest_mock import MockerFixture
from pydantic import SecretStr, AnyUrl

import psycopg2

from models.config import PostgreSQLDatabaseConfiguration
from models.cache_entry import CacheEntry
from models.responses import ConversationData, ReferencedDocument
from utils import suid
from utils.types import ToolCallSummary, ToolResultSummary
from cache.cache_error import CacheError
from cache.postgres_cache import PostgresCache

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

# pylint: disable=fixme


# pylint: disable=too-few-public-methods
class CursorMock:
    """Mock class for simulating DB cursor exceptions."""

    def __init__(self) -> None:
        """Construct the mock cursor class.

        Initialize the mock database cursor used in tests.

        Sets up internal state so the cursor simulates a DatabaseError when `execute` is called.
        """

    def execute(self, command: Any) -> None:
        """Execute any SQL command.

        Execute the given SQL command using the database cursor.

        Parameters:
                command (Any): SQL statement or command object to execute.

        Raises:
                psycopg2.DatabaseError: Always raised with the message "can not INSERT".
        """
        raise psycopg2.DatabaseError("can not INSERT")


# pylint: disable=too-few-public-methods
class ConnectionMock:
    """Mock class for connection."""

    def __init__(self) -> None:
        """Construct the connection mock class."""

    def cursor(self) -> None:
        """Getter for mock cursor.

        Simulate obtaining a database cursor and raise an OperationalError to
        represent a failed connection.

        Raises:
            psycopg2.OperationalError: Always raised to simulate inability to acquire a cursor.
        """
        raise psycopg2.OperationalError("can not SELECT")


@pytest.fixture(scope="module", name="postgres_cache_config_fixture")
def postgres_cache_config() -> PostgreSQLDatabaseConfiguration:
    """Fixture containing initialized instance of PostgreSQL cache.

    Create a PostgreSQLDatabaseConfiguration with placeholder connection values for use in tests.

    Returns:
        PostgreSQLDatabaseConfiguration: A configuration object with host,
        port, db, user, and a SecretStr password. Values are placeholders and
        not intended for real database connections.
    """
    # can be any configuration, becuase tests won't really try to
    # connect to database
    return PostgreSQLDatabaseConfiguration(
        host="localhost",
        port=1234,
        db="database",
        user="user",
        password=SecretStr("password"),
    )


@pytest.fixture(scope="module", name="postgres_cache_config_fixture_wrong_namespace")
def postgres_cache_config_wrong_namespace() -> PostgreSQLDatabaseConfiguration:
    """Fixture with invalid namespace containing spaces for validation testing.

    Create a PostgreSQLDatabaseConfiguration with an invalid namespace ("foo bar baz")
    to verify that the PostgresCache constructor properly rejects namespaces with spaces.

    Returns:
        PostgreSQLDatabaseConfiguration: A configuration object with host,
        port, db, user, SecretStr password, and an invalid namespace containing
        spaces. Values are placeholders and not intended for real database
        connections.
    """
    # can be any configuration, becuase tests won't really try to
    # connect to database
    return PostgreSQLDatabaseConfiguration(
        host="localhost",
        port=1234,
        db="database",
        user="user",
        password=SecretStr("password"),
        namespace="foo bar baz",
    )


@pytest.fixture(scope="module", name="postgres_cache_config_fixture_too_long_namespace")
def postgres_cache_config_too_long_namespace() -> PostgreSQLDatabaseConfiguration:
    """Fixture with namespace exceeding PostgreSQL's 63-character limit.

    Create a PostgreSQLDatabaseConfiguration with an overly long namespace
    to verify that the PostgresCache constructor enforces the maximum length constraint.

    Returns:
        PostgreSQLDatabaseConfiguration: A configuration object with host,
        port, db, user, SecretStr password, and a namespace exceeding 63
        characters. Values are placeholders and not intended for real database
        connections.
    """
    # can be any configuration, becuase tests won't really try to
    # connect to database
    return PostgreSQLDatabaseConfiguration(
        host="localhost",
        port=1234,
        db="database",
        user="user",
        password=SecretStr("password"),
        namespace="too long namespace that is longer than allowed 63 characters limit",
    )


def test_cache_initialization(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the get operation when DB is connected.

    Verifies that PostgresCache constructs successfully and exposes a non-None
    connection when psycopg2.connect is available.

    Asserts the created cache object is not None and that its `connection` attribute is set.
    """
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    assert cache is not None

    # connection is mocked only, but it should exists
    assert cache.connection is not None


def test_cache_initialization_on_error(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the get operation when DB is not connected."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect", side_effect=Exception("foo"))

    # exception should be thrown during PG connection
    with pytest.raises(Exception, match="foo"):
        _ = PostgresCache(postgres_cache_config_fixture)


def test_cache_initialization_connect_finalizer(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the get operation when DB is not connected.

    Ensure PostgresCache propagates exceptions raised during its initialization.

    Patches psycopg2.connect to avoid real DB access and makes
    PostgresCache.initialize_cache raise an exception; constructing
    PostgresCache must raise that exception.
    """
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")

    # cache initialization should raise an exception
    mocker.patch(
        "cache.postgres_cache.PostgresCache.initialize_cache",
        side_effect=Exception("foo"),
    )

    # exception should be thrown during cache initialization
    with pytest.raises(Exception, match="foo"):
        _ = PostgresCache(postgres_cache_config_fixture)


def test_connected_when_connected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the connected() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # cache should be connected by default (even if it's mocked connection)
    assert cache.connected() is True


def test_connected_when_disconnected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the connected() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    # simulate disconnected cache
    cache.connection = None

    # now the cache should be disconnected
    assert cache.connected() is False


def test_connected_when_connection_error(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the connected() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    # simulate connection error
    cache = PostgresCache(postgres_cache_config_fixture)
    # connection does not have to have proper type
    cache.connection = ConnectionMock()  # pyright: ignore
    assert cache.connection is not None
    assert cache.connected() is False


def test_initialize_cache_when_connected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the initialize_cache()."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    # should not fail
    cache.initialize_cache("public")


def test_initialize_cache_when_disconnected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the initialize_cache()."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    cache.connection = None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.initialize_cache("public")


def test_ready_method(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the ready() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    ready = cache.ready()
    assert ready is True


def test_get_operation_when_disconnected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the get() method.

    Verify that get() raises a CacheError with message "cache is disconnected"
    when the cache has no active database connection.
    """
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.get(USER_ID_1, CONVERSATION_ID_1, False)


def test_get_operation_when_connected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the get() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    lst = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert not lst


def test_get_operation_returned_values() -> None:
    """Test the get() method."""
    # TODO: LCORE-721
    # TODO: Implement proper unit test for testing PostgreSQL cache 'get' operation
    #       returning 'real' values
    # Need to mock the cursor.execute() method


def test_insert_or_append_when_disconnected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the insert_or_append() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)


def test_insert_or_append_operation_when_connected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the insert_or_append() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)


def test_insert_or_append_operation_operation_error(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the insert_or_append() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # no operation for @connection decorator
    cache.connect = lambda: None
    # connection does not have to have proper type
    cache.connection = ConnectionMock()  # pyright: ignore

    with pytest.raises(CacheError, match="insert_or_append"):
        cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)


def test_delete_when_disconnected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the delete() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.delete(USER_ID_1, CONVERSATION_ID_1, False)


def test_delete_operation_when_connected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the delete() method."""
    # prevent real connection to PG instance
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    mock_cursor.rowcount = 1
    assert cache.delete(USER_ID_1, CONVERSATION_ID_1, False) is True

    mock_cursor.rowcount = 0
    assert cache.delete(USER_ID_1, CONVERSATION_ID_1, False) is False


def test_delete_operation_operation_error(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the delete() method.

    Verifies that PostgresCache.delete raises a CacheError when the database
    connection fails during a delete operation.

    The test patches psycopg2.connect, injects a ConnectionMock that simulates
    a connection error, and asserts that calling delete(...) raises a
    CacheError containing the substring "delete".
    """
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # no operation for @connection decorator
    cache.connect = lambda: None
    # connection does not have to have proper type
    cache.connection = ConnectionMock()  # pyright: ignore

    with pytest.raises(CacheError, match="delete"):
        cache.delete(USER_ID_1, CONVERSATION_ID_1, False)


def test_list_operation_when_disconnected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the list() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.list(USER_ID_1, False)


def test_list_operation_when_connected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the list() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    lst = cache.list(USER_ID_1, False)
    assert not lst
    assert isinstance(lst, list)


def test_topic_summary_operations(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test topic summary set operations and retrieval via list."""
    # prevent real connection to PG instance
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    # Mock fetchall to return conversation data
    mock_cursor.fetchall.return_value = [
        (
            CONVERSATION_ID_1,
            "This conversation is about machine learning and AI",
            1234567890.0,
        )
    ]

    # Set a topic summary
    test_summary = "This conversation is about machine learning and AI"
    cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, test_summary, False)

    # Retrieve the topic summary via list
    conversations = cache.list(USER_ID_1, False)
    assert len(conversations) == 1
    assert conversations[0].topic_summary == test_summary
    assert isinstance(conversations[0], ConversationData)


def test_topic_summary_after_conversation_delete(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test that topic summary is deleted when conversation is deleted.

    Verify that deleting a conversation also removes its topic summary from the cache.
    """
    # prevent real connection to PG instance
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    # Mock the delete operation to return 1 (deleted)
    mock_cursor.rowcount = 1

    # Add some cache entries and a topic summary
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)
    cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, "Test summary", False)

    # Delete the conversation
    deleted = cache.delete(USER_ID_1, CONVERSATION_ID_1, False)
    assert deleted is True


def test_topic_summary_when_disconnected(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test topic summary operations when cache is disconnected."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    cache.connection = None
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, "Test", False)


def test_insert_and_get_with_referenced_documents(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test that a CacheEntry with referenced_documents is stored and retrieved correctly."""
    # prevent real connection to PG instance
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    # Create a CacheEntry with referenced documents
    docs = [
        ReferencedDocument(doc_title="Test Doc", doc_url=AnyUrl("http://example.com/"))
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

    # Find the INSERT INTO cache(...) call
    insert_calls = [
        c
        for c in mock_cursor.execute.call_args_list
        if isinstance(c[0][0], str) and "INSERT INTO cache(" in c[0][0]
    ]
    assert insert_calls, "INSERT call not found"
    sql_params = insert_calls[-1][0][1]
    # referenced_documents is now at index -3 (before tool_calls and tool_results)
    inserted_json_str = sql_params[-3]

    assert json.loads(inserted_json_str) == [
        {
            "doc_url": "http://example.com/",
            "doc_title": "Test Doc",
            "document_id": None,
            "product_name": None,
            "product_version": None,
            "source_path": None,
            "score": None,
            "chunk_metadata": None,
        }
    ]

    # Simulate the database returning that data
    db_return_value = (
        "user message",
        "AI message",
        "foo",
        "bar",
        "start_time",
        "end_time",
        [{"doc_url": "http://example.com/", "doc_title": "Test Doc"}],
        None,  # tool_calls
        None,  # tool_results
    )
    mock_cursor.fetchall.return_value = [db_return_value]

    # Call the get method
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_with_docs
    assert retrieved_entries[0].referenced_documents[0].doc_title == "Test Doc"


def test_insert_and_get_without_referenced_documents(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test that a CacheEntry with no referenced_documents is handled correctly."""
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    # Use CacheEntry without referenced_documents
    entry_without_docs = cache_entry_2

    # Call the insert method
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, entry_without_docs)

    insert_calls = [
        c
        for c in mock_cursor.execute.call_args_list
        if isinstance(c[0][0], str) and "INSERT INTO cache(" in c[0][0]
    ]
    assert insert_calls, "INSERT call not found"
    sql_params = insert_calls[-1][0][1]
    # Last 3 params are referenced_documents, tool_calls, tool_results - all should be None
    assert sql_params[-3] is None  # referenced_documents
    assert sql_params[-2] is None  # tool_calls
    assert sql_params[-1] is None  # tool_results

    # Simulate the database returning a row with None
    db_return_value = (
        entry_without_docs.query,
        entry_without_docs.response,
        entry_without_docs.provider,
        entry_without_docs.model,
        entry_without_docs.started_at,
        entry_without_docs.completed_at,
        None,  # referenced_documents is None in the DB
        None,  # tool_calls
        None,  # tool_results
    )
    mock_cursor.fetchall.return_value = [db_return_value]

    # Call the get method
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_without_docs
    assert retrieved_entries[0].referenced_documents is None
    assert retrieved_entries[0].tool_calls is None
    assert retrieved_entries[0].tool_results is None


def test_initialize_cache_with_custom_namespace(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test the initialize_cache() with a custom namespace."""
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value

    # should not fail and should execute CREATE SCHEMA
    cache.initialize_cache("custom_schema")

    # Verify CREATE SCHEMA was called for non-public namespace
    create_schema_calls = [
        call
        for call in mock_cursor.execute.call_args_list
        if "CREATE SCHEMA" in str(call)
    ]
    assert len(create_schema_calls) > 0


def test_connect_to_cache_with_improper_namespace(
    postgres_cache_config_fixture_wrong_namespace: PostgreSQLDatabaseConfiguration,
) -> None:
    """Test that PostgresCache constructor raises ValueError for invalid namespace."""
    # should fail due to invalid namespace containing spaces
    with pytest.raises(ValueError, match="Invalid namespace: foo bar baz"):
        PostgresCache(postgres_cache_config_fixture_wrong_namespace)


def test_connect_to_cache_with_too_long_namespace(
    postgres_cache_config_fixture_too_long_namespace: PostgreSQLDatabaseConfiguration,
) -> None:
    """Test that PostgresCache constructor raises ValueError for invalid namespace."""
    # should fail due to invalid namespace containing spaces
    with pytest.raises(ValueError, match="Invalid namespace: too long namespace"):
        PostgresCache(postgres_cache_config_fixture_too_long_namespace)


def test_insert_and_get_with_tool_calls_and_results(
    postgres_cache_config_fixture: PostgreSQLDatabaseConfiguration,
    mocker: MockerFixture,
) -> None:
    """Test that a CacheEntry with tool_calls and tool_results is stored and retrieved correctly."""
    # prevent real connection to PG instance
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

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

    # Find the INSERT INTO cache(...) call
    insert_calls = [
        c
        for c in mock_cursor.execute.call_args_list
        if isinstance(c[0][0], str) and "INSERT INTO cache(" in c[0][0]
    ]
    assert insert_calls, "INSERT call not found"
    sql_params = insert_calls[-1][0][1]

    # Verify tool_calls JSON
    tool_calls_json = sql_params[-2]
    assert json.loads(tool_calls_json) == [
        {
            "id": "call_1",
            "name": "test_tool",
            "args": {"param": "value"},
            "type": "tool_call",
        }
    ]

    # Verify tool_results JSON
    tool_results_json = sql_params[-1]
    assert json.loads(tool_results_json) == [
        {
            "id": "call_1",
            "status": "success",
            "content": "result data",
            "type": "tool_result",
            "round": 1,
        }
    ]

    # Simulate the database returning that data
    db_return_value = (
        "user message",
        "AI message",
        "foo",
        "bar",
        "start_time",
        "end_time",
        None,  # referenced_documents
        [
            {
                "id": "call_1",
                "name": "test_tool",
                "args": {"param": "value"},
                "type": "tool_call",
            }
        ],
        [
            {
                "id": "call_1",
                "status": "success",
                "content": "result data",
                "type": "tool_result",
                "round": 1,
            }
        ],
    )
    mock_cursor.fetchall.return_value = [db_return_value]

    # Call the get method
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_with_tools
    assert retrieved_entries[0].tool_calls is not None
    assert len(retrieved_entries[0].tool_calls) == 1
    assert retrieved_entries[0].tool_calls[0].name == "test_tool"
    assert retrieved_entries[0].tool_results is not None
    assert len(retrieved_entries[0].tool_results) == 1
    assert retrieved_entries[0].tool_results[0].status == "success"
