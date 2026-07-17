"""Unit tests for ClusterQuotaLimiter class."""

import pytest

from lightspeed_stack.models.config import (
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    SQLiteDatabaseConfiguration,
)
from lightspeed_stack.quota.cluster_quota_limiter import ClusterQuotaLimiter
from lightspeed_stack.quota.quota_exceed_error import QuotaExceedError

# pylint: disable=protected-access


def create_quota_limiter(
    name: str, initial_quota: int, quota_limit: int
) -> ClusterQuotaLimiter:
    """Create new quota limiter instance.

    Builds and returns a ClusterQuotaLimiter using an in-memory
    SQLite configuration for testing.

    Parameters:
        - name (str): Name assigned to the configured quota limiter.
        - initial_quota (int): Initial quota value passed to the
          ClusterQuotaLimiter instance.
        - quota_limit (int): Initial quota value placed into the limiter
          configuration (mapped to the configuration's `initial_quota`).

    Returns:
        ClusterQuotaLimiter: A configured ClusterQuotaLimiter backed by an
        in-memory SQLite database.
    """
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.sqlite = SQLiteDatabaseConfiguration(
        db_path=":memory:",
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="cluster_limiter",
            name=name,
            initial_quota=quota_limit,
            quota_increase=1,
            period="5 days",
        ),
    ]
    quota_limiter = ClusterQuotaLimiter(configuration, initial_quota, 1)
    assert quota_limiter is not None
    return quota_limiter


def test_connected() -> None:
    """Test the connected method."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)
    assert quota_limiter.connected()


def test_init_quota() -> None:
    """Test the init quota operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given cluster
    quota_limiter._init_quota()

    assert (
        str(quota_limiter) == "ClusterQuotaLimiter: initial quota: 1000 increase by: 1"
    )


def test_available_quota() -> None:
    """Test the available quota operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given cluster
    quota_limiter._init_quota()

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota


def test_consume_tokens() -> None:
    """Test the consume tokens operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given cluster
    quota_limiter._init_quota()

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota

    quota_limiter.consume_tokens(0, 1, "foo")

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota - 1

    quota_limiter.consume_tokens(1, 0, "foo")

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota - 2

    quota_limiter.consume_tokens(1, 1, "foo")

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota - 4


def test_increase_quota() -> None:
    """Test the increase_quota operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given cluster
    quota_limiter._init_quota()

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota

    quota_limiter.consume_tokens(1, 1, "foo")
    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota - 2

    quota_limiter.increase_quota("foo")
    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota - 1


def test_ensure_available_quota() -> None:
    """Test the ensure_available_quota operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given cluster
    quota_limiter._init_quota()

    quota_limiter.ensure_available_quota("foo")


def test_ensure_available_quota_no_quota() -> None:
    """Test the ensure_available_quota operation.

    Verify ensure_available_quota raises QuotaExceedError when the cluster has zero tokens.

    Sets up a limiter with initial quota 0, initializes quota for cluster
    "foo", and asserts that calling ensure_available_quota("foo") raises
    QuotaExceedError with a message matching "Cluster has no available tokens".
    """
    initial_quota = 0
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given cluster
    quota_limiter._init_quota()

    with pytest.raises(QuotaExceedError, match="Cluster has no available tokens"):
        quota_limiter.ensure_available_quota("foo")


def test_revoke_quota() -> None:
    """Test the revoke_quota operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given cluster
    quota_limiter._init_quota()

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota

    quota_limiter.consume_tokens(1, 1, "foo")
    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota - 2

    quota_limiter.revoke_quota("foo")
    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota
