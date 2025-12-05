"""Unit tests for PostgreSQLDatabaseConfiguration model."""

from pathlib import Path

import pytest
from pytest_subtests import SubTests

from pydantic import ValidationError

from constants import (
    POSTGRES_DEFAULT_SSL_MODE,
    POSTGRES_DEFAULT_GSS_ENCMODE,
)

from models.config import PostgreSQLDatabaseConfiguration


def test_postgresql_database_configuration() -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    # pylint: disable=no-member
    c = PostgreSQLDatabaseConfiguration(db="db", user="user", password="password")
    assert c is not None
    assert c.host == "localhost"
    assert c.port == 5432
    assert c.db == "db"
    assert c.user == "user"
    assert c.password.get_secret_value() == "password"
    assert c.ssl_mode == POSTGRES_DEFAULT_SSL_MODE
    assert c.gss_encmode == POSTGRES_DEFAULT_GSS_ENCMODE
    assert c.namespace == "lightspeed-stack"
    assert c.ca_cert_path is None


def test_postgresql_database_configuration_port_setting(subtests: SubTests) -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    with subtests.test(msg="Correct port value"):
        c = PostgreSQLDatabaseConfiguration(
            db="db", user="user", password="password", port=1234
        )
        assert c is not None
        assert c.port == 1234

    with subtests.test(msg="Negative port value"):
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            PostgreSQLDatabaseConfiguration(
                db="db", user="user", password="password", port=-1
            )

    with subtests.test(msg="Too big port value"):
        with pytest.raises(ValueError, match="Port value should be less than 65536"):
            PostgreSQLDatabaseConfiguration(
                db="db", user="user", password="password", port=100000
            )


def test_postgresql_database_configuration_ca_cert_path(subtests: SubTests) -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    with subtests.test(msg="Path exists"):
        c = PostgreSQLDatabaseConfiguration(
            db="db",
            user="user",
            password="password",
            port=1234,
            ca_cert_path=Path("tests/configuration/server.crt"),
        )
        assert c.ca_cert_path == Path("tests/configuration/server.crt")

    with subtests.test(msg="Path does not exist"):
        with pytest.raises(ValidationError, match="Path does not point to a file"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port=1234,
                ca_cert_path=Path("not a file"),
            )
