"""Unit tests for PostgreSQLDatabaseConfiguration model."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_subtests import SubTests

from lightspeed_stack.constants import (
    POSTGRES_DEFAULT_GSS_ENCMODE,
    POSTGRES_DEFAULT_SSL_MODE,
)
from lightspeed_stack.models.config import PostgreSQLDatabaseConfiguration


def test_postgresql_database_configuration() -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    # pylint: disable=no-member
    c = PostgreSQLDatabaseConfiguration(
        db="db",
        user="user",
        password="password",
    )  # pyright: ignore[reportCallIssue]

    # most attributes are set to default values
    assert c is not None
    assert c.host == "localhost"
    assert c.port == 5432
    assert c.db == "db"
    assert c.user == "user"
    assert c.password.get_secret_value() == "password"
    assert c.ssl_mode == POSTGRES_DEFAULT_SSL_MODE
    assert c.gss_encmode == POSTGRES_DEFAULT_GSS_ENCMODE
    assert c.namespace == "public"
    assert c.ca_cert_path is None


def test_postgresql_database_configuration_missing_values(subtests: SubTests) -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    with subtests.test(msg="Missing 'db' attribute"):
        with pytest.raises(ValueError, match="Field required"):
            PostgreSQLDatabaseConfiguration(
                user="user",
                password="password",
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Missing 'user' attribute"):
        with pytest.raises(ValueError, match="Field required"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                password="password",
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Missing 'password' attribute"):
        with pytest.raises(ValueError, match="Field required"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Missing 'db' and 'user' attributes"):
        with pytest.raises(ValueError, match="Field required"):
            PostgreSQLDatabaseConfiguration(
                password="password",
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Missing 'id' and 'user' attributes"):
        with pytest.raises(ValueError, match="Field required"):
            PostgreSQLDatabaseConfiguration(
                password="password",
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Missing 'user' and 'password' attributes"):
        with pytest.raises(ValueError, match="Field required"):
            PostgreSQLDatabaseConfiguration(
                db="db",
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Missing all required attributes"):
        with pytest.raises(ValueError, match="Field required"):
            PostgreSQLDatabaseConfiguration()  # pyright: ignore[reportCallIssue]


def test_postgresql_database_configuration_namespace_specification() -> None:
    """Test the PostgreSQLDatabaseConfiguration model.

    Verify that an explicit `namespace` is preserved and other fields use their defaults.

    Asserts that providing `namespace="foo"` results in `namespace` set to
    "foo", `host` defaulting to "localhost", `port` defaulting to 5432, `db`
    and `user` preserved, `password` stored as a secret whose
    `get_secret_value()` returns the original, `ssl_mode` and `gss_encmode`
    matching their PostgreSQL defaults, and `ca_cert_path` being `None`.
    """
    # pylint: disable=no-member
    c = PostgreSQLDatabaseConfiguration(
        db="db", user="user", password="password", namespace="foo"
    )  # pyright: ignore[reportCallIssue]

    # most attributes are set to default values
    assert c is not None
    assert c.host == "localhost"
    assert c.port == 5432
    assert c.db == "db"
    assert c.user == "user"
    assert c.password.get_secret_value() == "password"
    assert c.ssl_mode == POSTGRES_DEFAULT_SSL_MODE
    assert c.gss_encmode == POSTGRES_DEFAULT_GSS_ENCMODE
    assert c.namespace == "foo"
    assert c.ca_cert_path is None


def test_postgresql_database_configuration_port_setting(subtests: SubTests) -> None:
    """Test the PostgreSQLDatabaseConfiguration model.

    Validate port handling of PostgreSQLDatabaseConfiguration.

    Checks three scenarios:
    - A valid explicit port (1234) is preserved on the model.
    - A negative port raises ValidationError with message "Input should be greater than 0".
    - A port >= 65536 raises ValueError with message "Port value should be less than 65536".
    """
    with subtests.test(msg="Correct port value"):
        c = PostgreSQLDatabaseConfiguration(
            db="db",
            user="user",
            password="password",
            port=1234,
        )  # pyright: ignore[reportCallIssue]
        assert c is not None
        assert c.port == 1234

    with subtests.test(msg="Negative port value"):
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port=-1,
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Zero port value"):
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port=0,
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Too big port value"):
        with pytest.raises(ValueError, match="Port value should be less than 65536"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port=100000,
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Non integer port value"):
        with pytest.raises(ValueError, match="Input should be a valid integer"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port="xyzzy",
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Null port value"):
        with pytest.raises(ValueError, match="Input should be a valid integer"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port=None,
            )  # pyright: ignore[reportCallIssue]


def test_postgresql_database_configuration_ca_cert_path(subtests: SubTests) -> None:
    """Test the PostgreSQLDatabaseConfiguration model.

    Validate ca_cert_path handling in PostgreSQLDatabaseConfiguration.

    Verifies two behaviors using subtests:
    - When `ca_cert_path` points to an existing file, the value is preserved on the model.
    - When `ca_cert_path` points to a non-existent path, a ValidationError is
      raised with the message "Path does not point to a file".

    Parameters:
    ----------
        subtests (SubTests): Test helper providing subtest contexts.
    """
    with subtests.test(msg="Path exists"):
        c = PostgreSQLDatabaseConfiguration(
            db="db",
            user="user",
            password="password",
            port=1234,
            ca_cert_path=Path("tests/configuration/server.crt"),
        )  # pyright: ignore[reportCallIssue]
        assert c.ca_cert_path == Path("tests/configuration/server.crt")

    with subtests.test(msg="Path does not exist"):
        with pytest.raises(ValidationError, match="Path does not point to a file"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port=1234,
                ca_cert_path=Path("not a file"),
            )  # pyright: ignore[reportCallIssue]

    with subtests.test(msg="Path is empty"):
        with pytest.raises(ValidationError, match="Path does not point to a file"):
            PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                port=1234,
                ca_cert_path=Path(""),
            )  # pyright: ignore[reportCallIssue]


def test_postgresql_database_configuration_ssl_mode(subtests: SubTests) -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    ssl_modes = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")

    for ssl_mode in ssl_modes:
        with subtests.test(msg=f"SSL mode {ssl_mode}"):
            # pylint: disable=no-member
            c = PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                ssl_mode=ssl_mode,
            )  # pyright: ignore[reportCallIssue]

            # most attributes are set to default values
            assert c is not None
            assert c.host == "localhost"
            assert c.port == 5432
            assert c.db == "db"
            assert c.user == "user"
            assert c.password.get_secret_value() == "password"
            assert c.ssl_mode == ssl_mode
            assert c.gss_encmode == POSTGRES_DEFAULT_GSS_ENCMODE
            assert c.namespace == "public"
            assert c.ca_cert_path is None


def test_postgresql_database_configuration_improper_ssl_mode(
    subtests: SubTests,
) -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    ssl_modes = ("foo", "bar", "baz", "")

    for ssl_mode in ssl_modes:
        with subtests.test(msg=f"SSL mode {ssl_mode}"):
            with pytest.raises(ValueError, match="Input should be 'disable'"):
                # pylint: disable=no-member
                PostgreSQLDatabaseConfiguration(
                    db="db",
                    user="user",
                    password="password",
                    ssl_mode=ssl_mode,
                )  # pyright: ignore[reportCallIssue]


def test_postgresql_database_configuration_gss_encmode(subtests: SubTests) -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    gss_encmodes = ("disable", "prefer", "require")

    for gss_encmode in gss_encmodes:
        with subtests.test(msg=f"GSS encmode {gss_encmode}"):
            # pylint: disable=no-member
            c = PostgreSQLDatabaseConfiguration(
                db="db",
                user="user",
                password="password",
                gss_encmode=gss_encmode,
            )  # pyright: ignore[reportCallIssue]

            # most attributes are set to default values
            assert c is not None
            assert c.host == "localhost"
            assert c.port == 5432
            assert c.db == "db"
            assert c.user == "user"
            assert c.password.get_secret_value() == "password"
            assert c.ssl_mode == POSTGRES_DEFAULT_SSL_MODE
            assert c.gss_encmode == gss_encmode
            assert c.namespace == "public"
            assert c.ca_cert_path is None


def test_postgresql_database_configuration_improper_gss_encmode(
    subtests: SubTests,
) -> None:
    """Test the PostgreSQLDatabaseConfiguration model."""
    gss_encmodes = ("foo", "bar", "baz", "")

    for gss_encmode in gss_encmodes:
        with subtests.test(msg=f"GSS encmode {gss_encmode}"):
            with pytest.raises(ValueError, match="Input should be 'disable'"):
                # pylint: disable=no-member
                PostgreSQLDatabaseConfiguration(
                    db="db",
                    user="user",
                    password="password",
                    gss_encmode=gss_encmode,
                )  # pyright: ignore[reportCallIssue]
