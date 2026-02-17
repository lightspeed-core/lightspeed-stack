"""Benchmarks for app.database module."""

from pytest_benchmark.fixture import BenchmarkFixture

from .db_benchmarks import (
    benchmark_store_new_user_conversations,
    benchmark_update_user_conversation,
    benchmark_list_conversations_for_all_users,
    benchmark_list_conversations_for_one_user,
    benchmark_retrieve_conversation,
    benchmark_retrieve_conversation_for_one_user,
)

# number of records to be stored in database before benchmarks
SMALL_DB_RECORDS_COUNT = 100
MIDDLE_DB_RECORDS_COUNT = 1000
LARGE_DB_RECORDS_COUNT = 10000


def test_sqlite_store_new_user_conversations_empty_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against empty DB.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, 0)


def test_sqlite_store_new_user_conversations_small_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against small DB.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, SMALL_DB_RECORDS_COUNT)


def test_sqlite_store_new_user_conversations_middle_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against middle-sized DB.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_sqlite_store_new_user_conversations_large_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against large DB.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, LARGE_DB_RECORDS_COUNT)


def test_sqlite_update_user_conversation_empty_db(
    sqlite_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on an empty database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, 0)


def test_sqlite_update_user_conversation_small_db(
    sqlite_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, SMALL_DB_RECORDS_COUNT)


def test_sqlite_update_user_conversation_middle_db(
    sqlite_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on a medium-sized database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_sqlite_update_user_conversation_large_db(
    sqlite_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on a large database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, LARGE_DB_RECORDS_COUNT)


def test_sqlite_list_conversations_for_all_users_empty_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on an empty database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, 0)


def test_sqlite_list_conversations_for_all_users_small_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, SMALL_DB_RECORDS_COUNT)


def test_sqlite_list_conversations_for_all_users_middle_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a medium-sized database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_sqlite_list_conversations_for_all_users_large_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a large database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, LARGE_DB_RECORDS_COUNT)


def test_sqlite_list_conversations_for_one_user_empty_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on an empty database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, 0)


def test_sqlite_list_conversations_for_one_user_small_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on an small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, SMALL_DB_RECORDS_COUNT)


def test_sqlite_list_conversations_for_one_user_middle_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a medium-sized database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_sqlite_list_conversations_for_one_user_large_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a large database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, LARGE_DB_RECORDS_COUNT)


def test_sqlite_retrieve_conversation_empty_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on an empty database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, 0)


def test_sqlite_retrieve_conversation_small_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, SMALL_DB_RECORDS_COUNT)


def test_sqlite_retrieve_conversation_middle_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a medium-sized database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_sqlite_retrieve_conversation_large_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a large database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, LARGE_DB_RECORDS_COUNT)


def test_sqlite_retrieve_conversation_for_one_user_empty_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on an empty database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, 0)


def test_sqlite_retrieve_conversation_for_one_user_small_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, SMALL_DB_RECORDS_COUNT)


def test_sqlite_retrieve_conversation_for_one_user_middle_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a medium-sized database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_sqlite_retrieve_conversation_for_one_user_large_db(
    sqlite_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a large database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, LARGE_DB_RECORDS_COUNT)


def test_postgres_store_new_user_conversations_empty_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against empty DB.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, 0)


def test_postgres_store_new_user_conversations_small_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against small DB.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, SMALL_DB_RECORDS_COUNT)


def test_postgres_store_new_user_conversations_middle_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against middle-sized DB.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_postgres_store_new_user_conversations_large_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against large DB.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_store_new_user_conversations(benchmark, LARGE_DB_RECORDS_COUNT)


def test_postgres_update_user_conversation_empty_db(
    postgres_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on an empty database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, 0)


def test_postgres_update_user_conversation_small_db(
    postgres_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on small database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, SMALL_DB_RECORDS_COUNT)


def test_postgres_update_user_conversation_middle_db(
    postgres_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on a medium-sized database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_postgres_update_user_conversation_large_db(
    postgres_database: None,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on a large database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_update_user_conversation(benchmark, LARGE_DB_RECORDS_COUNT)


def test_postgres_list_conversations_for_all_users_empty_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on an empty database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, 0)


def test_postgres_list_conversations_for_all_users_small_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on small database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, SMALL_DB_RECORDS_COUNT)


def test_postgres_list_conversations_for_all_users_middle_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a medium-sized database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_postgres_list_conversations_for_all_users_large_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a large database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_all_users(benchmark, LARGE_DB_RECORDS_COUNT)


def test_postgres_list_conversations_for_one_user_empty_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on an empty database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, 0)


def test_postgres_list_conversations_for_one_user_small_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on an small database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, SMALL_DB_RECORDS_COUNT)


def test_postgres_list_conversations_for_one_user_middle_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a medium-sized database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_postgres_list_conversations_for_one_user_large_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark listing conversations on a large database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_list_conversations_for_one_user(benchmark, LARGE_DB_RECORDS_COUNT)


def test_postgres_retrieve_conversation_empty_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on an empty database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, 0)


def test_postgres_retrieve_conversation_small_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a small database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, SMALL_DB_RECORDS_COUNT)


def test_postgres_retrieve_conversation_middle_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a medium-sized database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_postgres_retrieve_conversation_large_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a large database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation(benchmark, LARGE_DB_RECORDS_COUNT)


def test_postgres_retrieve_conversation_for_one_user_empty_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on an empty database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, 0)


def test_postgres_retrieve_conversation_for_one_user_small_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a small database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, SMALL_DB_RECORDS_COUNT)


def test_postgres_retrieve_conversation_for_one_user_middle_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a medium-sized database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, MIDDLE_DB_RECORDS_COUNT)


def test_postgres_retrieve_conversation_for_one_user_large_db(
    postgres_database: None, benchmark: BenchmarkFixture
) -> None:
    """Benchmark retrieving conversations on a large database.

    Parameters:
        postgres_database: Fixture that prepares a temporary PostgreSQL DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    benchmark_retrieve_conversation_for_one_user(benchmark, LARGE_DB_RECORDS_COUNT)
