"""Unit tests for quota limiter factory class."""

import pytest
from pydantic import SecretStr
from pytest_mock import MockerFixture

from lightspeed_stack import constants
from lightspeed_stack.models.config import (
    PostgreSQLDatabaseConfiguration,
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    SQLiteDatabaseConfiguration,
)
from lightspeed_stack.quota.cluster_quota_limiter import ClusterQuotaLimiter
from lightspeed_stack.quota.quota_limiter_factory import QuotaLimiterFactory
from lightspeed_stack.quota.user_quota_limiter import UserQuotaLimiter


def test_quota_limiters_no_storage() -> None:
    """Test the quota limiters creating when no storage is configured."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.sqlite = None
    configuration.postgres = None
    configuration.limiters = []
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert not limiters


def test_quota_limiters_no_limiters_pg_storage() -> None:
    """Test the quota limiters creating when no limiters are specified."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.postgres = PostgreSQLDatabaseConfiguration(
        db="test",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        host="host",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )
    configuration.limiters = None  # pyright: ignore[reportAttributeAccessIssue]
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert not limiters


def test_quota_limiters_no_limiters_sqlite_storage() -> None:
    """Test the quota limiters creating when no limiters are specified."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.sqlite = SQLiteDatabaseConfiguration(
        db_path="/foo/bar",
    )
    configuration.limiters = None  # pyright: ignore[reportAttributeAccessIssue]
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert not limiters


def test_quota_limiters_empty_limiters_pg_storage() -> None:
    """Test the quota limiters creating when no limiters are specified.

    Verify no quota limiters are created when PostgreSQL storage is configured
    but the limiter list is empty.

    Asserts that QuotaLimiterFactory.quota_limiters(configuration) returns an
    empty collection.
    """
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.postgres = PostgreSQLDatabaseConfiguration(
        db="test",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        host="host",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )
    configuration.limiters = []
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert not limiters


def test_quota_limiters_empty_limiters_sqlite_storage() -> None:
    """Test the quota limiters creating when no limiters are specified."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.sqlite = SQLiteDatabaseConfiguration(
        db_path="/foo/bar",
    )
    configuration.limiters = []
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert not limiters


def test_quota_limiters_user_quota_limiter_postgres_storage(
    mocker: MockerFixture,
) -> None:
    """Test the quota limiters creating when one limiter is specified.

    Verify that configuring PostgreSQL storage with a single limiter of type
    "user_limiter" produces exactly one UserQuotaLimiter.

    Sets up a QuotaHandlersConfiguration with PostgreSQL connection settings
    and one QuotaLimiterConfiguration(type="user_limiter"), patches
    psycopg2.connect to avoid real DB connections, and asserts the factory
    returns a single UserQuotaLimiter instance.
    """
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.postgres = PostgreSQLDatabaseConfiguration(
        db="test",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        host="host",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="user_limiter",
            name="foo",
            initial_quota=100,
            quota_increase=1,
            period="5 days",
        ),
    ]
    # do not use connection to real PostgreSQL instance
    mocker.patch("psycopg2.connect")
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert len(limiters) == 1
    assert isinstance(limiters[0], UserQuotaLimiter)


def test_quota_limiters_user_quota_limiter_sqlite_storage() -> None:
    """Test the quota limiters creating when one limiter is specified.

    Verify that providing a single `user_limiter` configuration with in-memory
    SQLite storage produces one UserQuotaLimiter instance.

    Asserts that exactly one limiter is returned and that it is an instance of
    `UserQuotaLimiter`.
    """
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.sqlite = SQLiteDatabaseConfiguration(
        db_path=":memory:",
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="user_limiter",
            name="foo",
            initial_quota=100,
            quota_increase=1,
            period="5 days",
        ),
    ]
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert len(limiters) == 1
    assert isinstance(limiters[0], UserQuotaLimiter)


def test_quota_limiters_cluster_quota_limiter_postgres_storage(
    mocker: MockerFixture,
) -> None:
    """Test the quota limiters creating when one limiter is specified."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.postgres = PostgreSQLDatabaseConfiguration(
        db="test",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        host="host",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="foo",
            initial_quota=100,
            quota_increase=1,
            period="5 days",
        ),
    ]
    # do not use connection to real PostgreSQL instance
    mocker.patch("psycopg2.connect")
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert len(limiters) == 1
    assert isinstance(limiters[0], ClusterQuotaLimiter)


def test_quota_limiters_cluster_quota_limiter_sqlite_storage() -> None:
    """Test the quota limiters creating when one limiter is specified."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.sqlite = SQLiteDatabaseConfiguration(
        db_path=":memory:",
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="foo",
            initial_quota=100,
            quota_increase=1,
            period="5 days",
        ),
    ]
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert len(limiters) == 1
    assert isinstance(limiters[0], ClusterQuotaLimiter)


def test_quota_limiters_two_limiters(mocker: MockerFixture) -> None:
    """Test the quota limiters creating when two limiters are specified."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.postgres = PostgreSQLDatabaseConfiguration(
        db="test",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        host="host",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="user_limiter",
            name="foo",
            initial_quota=100,
            quota_increase=1,
            period="5 days",
        ),
        QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="foo",
            initial_quota=100,
            quota_increase=1,
            period="5 days",
        ),
    ]
    # do not use connection to real PostgreSQL instance
    mocker.patch("psycopg2.connect")
    limiters = QuotaLimiterFactory.quota_limiters(configuration)
    assert len(limiters) == 2
    assert isinstance(limiters[0], UserQuotaLimiter)
    assert isinstance(limiters[1], ClusterQuotaLimiter)


def test_quota_limiters_invalid_limiter_type(mocker: MockerFixture) -> None:
    """Test the quota limiters creating when invalid limiter type is specified."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.postgres = PostgreSQLDatabaseConfiguration(
        db="test",
        user="user",
        password=SecretStr("password"),
        namespace="foo",
        host="host",
        port=1234,
        ssl_mode=constants.POSTGRES_DEFAULT_SSL_MODE,
        gss_encmode=constants.POSTGRES_DEFAULT_GSS_ENCMODE,
        ca_cert_path=None,
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="foo",
            initial_quota=100,
            quota_increase=1,
            period="5 days",
        ),
    ]
    configuration.limiters[0].type = (
        "foo"  # pyright: ignore[reportAttributeAccessIssue]
    )
    # do not use connection to real PostgreSQL instance
    mocker.patch("psycopg2.connect")
    with pytest.raises(ValueError, match="Invalid limiter type: foo"):
        _ = QuotaLimiterFactory.quota_limiters(configuration)
