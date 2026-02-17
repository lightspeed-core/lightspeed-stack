"""Benchmarks to compare performances of SQLite and PostgreSQL databases."""

import pytest
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
DB_RECORDS_COUNT = 10000


@pytest.mark.parametrize("db_fixture", ["sqlite_database", "postgres_database"])
def test_store_new_user_conversations(
    request: pytest.FixtureRequest,
    db_fixture: str,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark for the DB operation to create and store new topic and conversation ID mapping.

    Benchmark is performed against small DB.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    request.getfixturevalue(db_fixture)
    benchmark_store_new_user_conversations(benchmark, DB_RECORDS_COUNT)


@pytest.mark.parametrize("db_fixture", ["sqlite_database", "postgres_database"])
def test_update_user_conversation(
    request: pytest.FixtureRequest,
    db_fixture: str,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark updating conversation on small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    request.getfixturevalue(db_fixture)
    benchmark_update_user_conversation(benchmark, DB_RECORDS_COUNT)


@pytest.mark.parametrize("db_fixture", ["sqlite_database", "postgres_database"])
def test_list_conversations_for_all_users(
    request: pytest.FixtureRequest,
    db_fixture: str,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark listing conversations on small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    request.getfixturevalue(db_fixture)
    benchmark_list_conversations_for_all_users(benchmark, DB_RECORDS_COUNT)


@pytest.mark.parametrize("db_fixture", ["sqlite_database", "postgres_database"])
def test_list_conversations_for_one_user(
    request: pytest.FixtureRequest,
    db_fixture: str,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark listing conversations on an small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    request.getfixturevalue(db_fixture)
    benchmark_list_conversations_for_one_user(benchmark, DB_RECORDS_COUNT)


@pytest.mark.parametrize("db_fixture", ["sqlite_database", "postgres_database"])
def test_retrieve_conversation_for_all_users(
    request: pytest.FixtureRequest,
    db_fixture: str,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark retrieving conversations on a small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    request.getfixturevalue(db_fixture)
    benchmark_retrieve_conversation(benchmark, DB_RECORDS_COUNT)


@pytest.mark.parametrize("db_fixture", ["sqlite_database", "postgres_database"])
def test_retrieve_conversation_for_one_user(
    request: pytest.FixtureRequest,
    db_fixture: str,
    benchmark: BenchmarkFixture,
) -> None:
    """Benchmark retrieving conversations on a small database.

    Parameters:
        sqlite_database: Fixture that prepares a temporary SQLite DB.
        benchmark (BenchmarkFixture): pytest-benchmark fixture.

    Returns:
        None
    """
    request.getfixturevalue(db_fixture)
    benchmark_retrieve_conversation_for_one_user(benchmark, DB_RECORDS_COUNT)
