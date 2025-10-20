"""Unit tests for PostgreSQL cache implementation."""

import json

import pytest
from pytest_mock import MockerFixture

import psycopg2

from cache.cache_error import CacheError
from cache.postgres_cache import PostgresCache
from models.config import PostgreSQLDatabaseConfiguration
from models.cache_entry import CacheEntry
from models.responses import ConversationData, ReferencedDocument
from utils import suid


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

    def __init__(self):
        """Construct the mock cursor class."""

    def execute(self, command):
        """Execute any SQL command."""
        raise psycopg2.DatabaseError("can not INSERT")


# pylint: disable=too-few-public-methods
class ConnectionMock:
    """Mock class for connection."""

    def __init__(self):
        """Construct the connection mock class."""

    def cursor(self):
        """Getter for mock cursor."""
        raise psycopg2.OperationalError("can not SELECT")


@pytest.fixture(scope="module", name="postgres_cache_config_fixture")
def postgres_cache_config():
    """Fixture containing initialized instance of PostgreSQL cache."""
    # can be any configuration, becuase tests won't really try to
    # connect to database
    return PostgreSQLDatabaseConfiguration(
        host="localhost", port=1234, db="database", user="user", password="password"
    )


def test_cache_initialization(postgres_cache_config_fixture, mocker: MockerFixture):
    """Test the get operation when DB is connected."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    assert cache is not None

    # connection is mocked only, but it should exists
    assert cache.connection is not None


def test_cache_initialization_on_error(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the get operation when DB is not connected."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect", side_effect=Exception("foo"))

    # exception should be thrown during PG connection
    with pytest.raises(Exception, match="foo"):
        _ = PostgresCache(postgres_cache_config_fixture)


def test_cache_initialization_connect_finalizer(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the get operation when DB is not connected."""
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


def test_connected_when_connected(postgres_cache_config_fixture, mocker: MockerFixture):
    """Test the connected() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # cache should be connected by default (even if it's mocked connection)
    assert cache.connected() is True


def test_connected_when_disconnected(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the connected() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    # simulate disconnected cache
    cache.connection = None

    # now the cache should be disconnected
    assert cache.connected() is False


def test_connected_when_connection_error(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the connected() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    # simulate connection error
    cache = PostgresCache(postgres_cache_config_fixture)
    cache.connection = ConnectionMock()
    assert cache.connection is not None
    assert cache.connected() is False


def test_initialize_cache_when_connected(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the initialize_cache()."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    # should not fail
    cache.initialize_cache()


def test_initialize_cache_when_disconnected(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the initialize_cache()."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)
    cache.connection = None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.initialize_cache()


def test_ready_method(postgres_cache_config_fixture, mocker: MockerFixture):
    """Test the ready() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    ready = cache.ready()
    assert ready is True


def test_get_operation_when_disconnected(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the get() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    cache.connection = None
    # no operation for @connection decorator
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.get(USER_ID_1, CONVERSATION_ID_1, False)


def test_get_operation_when_connected(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the get() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    lst = cache.get(USER_ID_1, CONVERSATION_ID_1, False)
    assert not lst


def test_get_operation_returned_values():
    """Test the get() method."""
    # TODO: LCORE-721
    # TODO: Implement proper unit test for testing PostgreSQL cache 'get' operation
    #       returning 'real' values
    # Need to mock the cursor.execute() method


def test_insert_or_append_when_disconnected(
    postgres_cache_config_fixture, mocker: MockerFixture
):
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
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the insert_or_append() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)


def test_insert_or_append_operation_operation_error(
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the insert_or_append() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # no operation for @connection decorator
    cache.connect = lambda: None
    cache.connection = ConnectionMock()

    with pytest.raises(CacheError, match="insert_or_append"):
        cache.insert_or_append(USER_ID_1, CONVERSATION_ID_1, cache_entry_1, False)


def test_delete_when_disconnected(postgres_cache_config_fixture, mocker: MockerFixture):
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
    postgres_cache_config_fixture, mocker: MockerFixture
):
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
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the delete() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # no operation for @connection decorator
    cache.connect = lambda: None
    cache.connection = ConnectionMock()

    with pytest.raises(CacheError, match="delete"):
        cache.delete(USER_ID_1, CONVERSATION_ID_1, False)


def test_list_operation_when_disconnected(
    postgres_cache_config_fixture, mocker: MockerFixture
):
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
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test the list() method."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    # should not fail
    lst = cache.list(USER_ID_1, False)
    assert not lst
    assert isinstance(lst, list)


def test_topic_summary_operations(postgres_cache_config_fixture, mocker: MockerFixture):
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
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test that topic summary is deleted when conversation is deleted."""
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
    postgres_cache_config_fixture, mocker: MockerFixture
):
    """Test topic summary operations when cache is disconnected."""
    # prevent real connection to PG instance
    mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    cache.connection = None
    cache.connect = lambda: None

    with pytest.raises(CacheError, match="cache is disconnected"):
        cache.set_topic_summary(USER_ID_1, CONVERSATION_ID_1, "Test", False)


def test_insert_and_get_with_referenced_documents(
    postgres_cache_config_fixture, mocker
):
    """Test that a CacheEntry with referenced_documents is stored and retrieved correctly."""
    # prevent real connection to PG instance
    mock_connect = mocker.patch("psycopg2.connect")
    cache = PostgresCache(postgres_cache_config_fixture)

    mock_connection = mock_connect.return_value
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    # Create a CacheEntry with referenced documents
    docs = [ReferencedDocument(doc_title="Test Doc", doc_url="http://example.com/")]
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
    inserted_json_str = sql_params[-1]

    assert json.loads(inserted_json_str) == [
        {"doc_url": "http://example.com/", "doc_title": "Test Doc"}
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
    )
    mock_cursor.fetchall.return_value = [db_return_value]

    # Call the get method
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_with_docs
    assert retrieved_entries[0].referenced_documents[0].doc_title == "Test Doc"


def test_insert_and_get_without_referenced_documents(
    postgres_cache_config_fixture, mocker
):
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
    assert sql_params[-1] is None

    # Simulate the database returning a row with None
    db_return_value = (
        entry_without_docs.query,
        entry_without_docs.response,
        entry_without_docs.provider,
        entry_without_docs.model,
        entry_without_docs.started_at,
        entry_without_docs.completed_at,
        None,  # referenced_documents is None in the DB
    )
    mock_cursor.fetchall.return_value = [db_return_value]

    # Call the get method
    retrieved_entries = cache.get(USER_ID_1, CONVERSATION_ID_1)

    # Assert that the retrieved entry matches the original
    assert len(retrieved_entries) == 1
    assert retrieved_entries[0] == entry_without_docs
    assert retrieved_entries[0].referenced_documents is None
