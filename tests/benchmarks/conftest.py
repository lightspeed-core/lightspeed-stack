"""Fixtures used by benchmarks."""

from pathlib import Path
import pytest

import psycopg2

from app import database
from configuration import configuration, AppConfig


@pytest.fixture(name="configuration_filename_sqlite")
def configuration_filename_sqlite_fixture() -> str:
    """Retrieve configuration file name to be used by benchmarks.

    Parameters:
        None

    Returns:
        str: Path to the benchmark configuration file to load.
    """
    return "tests/configuration/benchmarks-sqlite.yaml"


@pytest.fixture(name="configuration_filename_postgres")
def configuration_filename_postgres_fixture() -> str:
    """Retrieve configuration file name to be used by benchmarks.

    Parameters:
        None

    Returns:
        str: Path to the benchmark configuration file to load.
    """
    return "tests/configuration/benchmarks-postgres.yaml"


@pytest.fixture(name="sqlite_database")
def sqlite_database_fixture(configuration_filename_sqlite: str, tmp_path: Path) -> None:
    """Initialize a temporary SQLite database for benchmarking.

    This fixture:
    - Loads the provided configuration file.
    - Ensures an SQLite configuration is present.
    - Uses a temp path for the SQLite DB file to guarantee a fresh DB for each run.
    - Initializes the DB engine and creates required tables.

    Parameters:
        configuration_filename_sqlite (str): Path to the YAML configuration file to load.
        tmp_path (Path): pytest-provided temporary directory for creating the DB file.

    Raises:
        AssertionError: If the configuration does not include an sqlite configuration.
    """
    # try to load the configuration containing SQLite database setup
    configuration.load_configuration(configuration_filename_sqlite)
    assert configuration.database_configuration.sqlite is not None

    # we need to start each benchmark with empty database
    configuration.database_configuration.sqlite.db_path = str(tmp_path / "database.db")

    # initialize database session and create tables
    database.initialize_database()
    database.create_tables()


def drop_postgres_tables(configuration: AppConfig) -> None:
    """Drop postgres tables used by benchmarks.

    The tables will be re-created so every benchmark start with fresh DB.
    """
    pgconfig = configuration.database_configuration.postgres
    assert pgconfig is not None

    # try to connect to Postgres
    conn = psycopg2.connect(
        database=pgconfig.db,
        user=pgconfig.user,
        password=pgconfig.password.get_secret_value(),
        host=pgconfig.host,
        port=pgconfig.port,
    )

    # try to drop tables used by benchmarks
    try:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS user_turn;")
            cursor.execute("DROP TABLE IF EXISTS user_conversation;")
        conn.commit()
    finally:
        # closing the connection
        conn.close()


@pytest.fixture(name="postgres_database")
def postgres_database_fixture(configuration_filename_postgres: str) -> None:
    """Initialize a temporary postgres database for benchmarking.

    This fixture:
    - Loads the provided configuration file.
    - Ensures an Postgres configuration is present.
    - Initializes the DB engine and creates required tables.

    Parameters:
        configuration_filename_postgres (str): Path to the YAML configuration file to load.

    Raises:
        AssertionError: If the configuration does not include an postgres configuration.
    """
    # try to load the configuration containing postgres database setup
    configuration.load_configuration(configuration_filename_postgres)
    assert configuration.database_configuration.postgres is not None

    # make sure all tables will be re-initialized
    drop_postgres_tables(configuration)

    # initialize database session and create tables
    database.initialize_database()
    database.create_tables()
