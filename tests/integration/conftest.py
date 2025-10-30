"""Shared fixtures for integration tests."""

from pathlib import Path
from typing import Generator

import pytest
from fastapi import Request, Response

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

from authentication.noop import NoopAuthDependency
from authentication.interface import AuthTuple

from configuration import configuration
from models.database.base import Base


@pytest.fixture(autouse=True)
def reset_configuration_state() -> Generator:
    """Reset configuration state before each integration test.

    This autouse fixture ensures test independence by resetting the
    singleton configuration state before each test runs. This allows
    tests to verify both loaded and unloaded configuration states
    regardless of execution order.
    """
    # pylint: disable=protected-access
    configuration._configuration = None
    yield


@pytest.fixture(name="test_config", scope="function")
def test_config_fixture() -> Generator:
    """Load real configuration for integration tests.

    This fixture loads the actual configuration file used in testing,
    demonstrating integration with the configuration system.
    """
    config_path = (
        Path(__file__).parent.parent / "configuration" / "lightspeed-stack.yaml"
    )
    assert config_path.exists(), f"Config file not found: {config_path}"

    # Load configuration
    configuration.load_configuration(str(config_path))

    yield configuration
    # Note: Cleanup is handled by the autouse reset_configuration_state fixture


@pytest.fixture(name="current_config", scope="function")
def current_config_fixture() -> Generator:
    """Load current configuration for integration tests.

    This fixture loads the actual configuration file from project root (current configuration),
    demonstrating integration with the configuration system.
    """
    config_path = Path(__file__).parent.parent.parent / "lightspeed-stack.yaml"
    assert config_path.exists(), f"Config file not found: {config_path}"

    # Load configuration
    configuration.load_configuration(str(config_path))

    yield configuration
    # Note: Cleanup is handled by the autouse reset_configuration_state fixture


@pytest.fixture(name="test_db_engine", scope="function")
def test_db_engine_fixture() -> Generator:
    """Create an in-memory SQLite database engine for testing.

    This provides a real database (not mocked) for integration tests.
    Each test gets a fresh database.
    """
    # Create in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,  # Set to True to see SQL queries
        connect_args={"check_same_thread": False},  # Allow multi-threaded access
    )

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(name="test_db_session", scope="function")
def test_db_session_fixture(test_db_engine: Engine) -> Generator[Session, None, None]:
    """Create a database session for testing.

    Provides a real database session connected to the in-memory test database.
    """
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=test_db_engine)
    session = session_local()

    yield session

    session.close()


@pytest.fixture(name="test_request")
def test_request_fixture() -> Request:
    """Create a test FastAPI Request object with proper scope."""
    return Request(
        scope={
            "type": "http",
            "query_string": b"",
            "headers": [],
        }
    )


@pytest.fixture(name="test_response")
def test_response_fixture() -> Response:
    """Create a test FastAPI Response object with proper scope."""
    return Response(content="", status_code=200, media_type="application/json")


@pytest.fixture(name="test_auth")
async def test_auth_fixture(test_request: Request) -> AuthTuple:
    """Create authentication using real noop auth module.

    This uses the actual NoopAuthDependency instead of mocking,
    making this a true integration test.
    """
    noop_auth = NoopAuthDependency()
    return await noop_auth(test_request)
