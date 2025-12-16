"""Unit tests for A2AStateConfiguration."""

# pylint: disable=no-member

import pytest
from pydantic import ValidationError

from models.config import (
    A2AStateConfiguration,
    SQLiteDatabaseConfiguration,
    PostgreSQLDatabaseConfiguration,
)


class TestA2AStateConfiguration:
    """Tests for A2AStateConfiguration."""

    def test_default_configuration(self) -> None:
        """Test default configuration is memory type (no database configured)."""
        config = A2AStateConfiguration()

        assert config.storage_type == "memory"
        assert config.sqlite is None
        assert config.postgres is None
        assert config.config is None

    def test_sqlite_configuration(self, tmp_path: str) -> None:
        """Test SQLite configuration."""
        db_path = f"{tmp_path}/test.db"
        sqlite_config = SQLiteDatabaseConfiguration(db_path=db_path)
        config = A2AStateConfiguration(sqlite=sqlite_config)

        assert config.storage_type == "sqlite"
        assert config.sqlite is not None
        assert config.sqlite.db_path == db_path
        assert config.config == sqlite_config

    def test_postgres_configuration(self) -> None:
        """Test PostgreSQL configuration."""
        postgres_config = PostgreSQLDatabaseConfiguration(
            host="localhost",
            port=5432,
            db="a2a_state",
            user="lightspeed",
            password="secret",
        )
        config = A2AStateConfiguration(postgres=postgres_config)

        assert config.storage_type == "postgres"
        assert config.postgres is not None
        assert config.postgres.host == "localhost"
        assert config.postgres.port == 5432
        assert config.postgres.db == "a2a_state"
        assert config.config == postgres_config

    def test_postgres_with_all_options(self) -> None:
        """Test PostgreSQL configuration with all options."""
        postgres_config = PostgreSQLDatabaseConfiguration(
            host="postgres.example.com",
            port=5433,
            db="lightspeed",
            user="admin",
            password="secret123",
            namespace="a2a",
            ssl_mode="require",
            ca_cert_path=None,
        )
        config = A2AStateConfiguration(postgres=postgres_config)

        assert config.storage_type == "postgres"
        assert config.postgres.host == "postgres.example.com"
        assert config.postgres.port == 5433
        assert config.postgres.namespace == "a2a"
        assert config.postgres.ssl_mode == "require"

    def test_both_sqlite_and_postgres_raises_error(self, tmp_path: str) -> None:
        """Test that configuring both SQLite and PostgreSQL raises ValidationError."""
        db_path = f"{tmp_path}/test.db"
        sqlite_config = SQLiteDatabaseConfiguration(db_path=db_path)
        postgres_config = PostgreSQLDatabaseConfiguration(
            host="localhost",
            port=5432,
            db="test",
            user="test",
            password="test",
        )

        with pytest.raises(ValidationError) as exc_info:
            A2AStateConfiguration(
                sqlite=sqlite_config,
                postgres=postgres_config,
            )

        errors = exc_info.value.errors()
        assert any(
            "Only one A2A state storage configuration can be provided" in str(e["msg"])
            for e in errors
        )

    def test_forbids_extra_fields(self) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError):
            A2AStateConfiguration(unknown_field="value")  # type: ignore
