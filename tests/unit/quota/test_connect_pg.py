"""Unit tests for PostgreSQL connection handler."""

import pytest
from psycopg2 import OperationalError
from pydantic import SecretStr
from pytest_mock import MockerFixture

from lightspeed_stack import constants
from lightspeed_stack.models.config import PostgreSQLDatabaseConfiguration
from lightspeed_stack.quota.connect_pg import connect_pg


def test_connect_pg_when_connection_established(mocker: MockerFixture) -> None:
    """Test the connection to PostgreSQL database.

    Verify that connect_pg returns a non-None connection object when the
    underlying psycopg2 connection succeeds.

    Patches psycopg2.connect to avoid a real network call and asserts the
    returned connection is not None.
    """
    # any correct PostgreSQL configuration can be used
    configuration = PostgreSQLDatabaseConfiguration(
        db="db",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        host="host",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )

    # do not use connection to real PostgreSQL instance
    mocker.patch("psycopg2.connect")

    # connection should be established
    connection = connect_pg(configuration)
    assert connection is not None


def test_connect_pg_when_connection_error(mocker: MockerFixture) -> None:
    """Test the connection to PostgreSQL database.

    Verifies that connect_pg propagates psycopg2.OperationalError when the
    underlying connection attempt fails.

    Asserts that calling connect_pg with a valid configuration raises an
    OperationalError with the original error message when psycopg2.connect
    raises OperationalError.
    """
    # any correct PostgreSQL configuration can be used
    configuration = PostgreSQLDatabaseConfiguration(
        host="foo",
        db="db",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )

    # do not use connection to real PostgreSQL instance
    mocker.patch("psycopg2.connect", side_effect=OperationalError("ERROR"))
    with pytest.raises(OperationalError, match="ERROR"):
        # connection should not be established
        _ = connect_pg(configuration)
