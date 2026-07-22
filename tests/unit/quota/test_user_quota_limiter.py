"""Unit tests for UserQuotaLimiter class."""

import pytest

from lightspeed_stack.models.config import (
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    SQLiteDatabaseConfiguration,
)
from lightspeed_stack.quota.quota_exceed_error import QuotaExceedError
from lightspeed_stack.quota.user_quota_limiter import UserQuotaLimiter

# pylint: disable=protected-access


def create_quota_limiter(
    name: str, initial_quota: int, quota_limit: int
) -> UserQuotaLimiter:
    """Create new quota limiter instance."""
    configuration = QuotaHandlersConfiguration()  # pyright: ignore[reportCallIssue]
    configuration.sqlite = SQLiteDatabaseConfiguration(
        db_path=":memory:",
    )
    configuration.limiters = [
        QuotaLimiterConfiguration(
            type="user_limiter",
            name=name,
            initial_quota=quota_limit,
            quota_increase=1,
            period="5 days",
        ),
    ]
    quota_limiter = UserQuotaLimiter(configuration, initial_quota, 1)
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

    # init quota for given user
    quota_limiter._init_quota()

    assert str(quota_limiter) == "UserQuotaLimiter: initial quota: 1000 increase by: 1"


def test_available_quota() -> None:
    """Test the available quota operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given user
    quota_limiter._init_quota()

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota


def test_consume_tokens() -> None:
    """Test the consume tokens operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given user
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

    # init quota for given user
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

    # init quota for given user
    quota_limiter._init_quota()

    quota_limiter.ensure_available_quota("foo")


def test_ensure_available_quota_no_quota() -> None:
    """Test the ensure_available_quota operation.

    Verify that ensure_available_quota raises QuotaExceedError when the user's
    available quota is zero.

    Initializes a limiter with initial_quota set to 0, calls the limiter
    initialization routine, and asserts that calling
    ensure_available_quota("foo") raises QuotaExceedError with the message
    "User foo has no available tokens".
    """
    initial_quota = 0
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given user
    quota_limiter._init_quota()

    with pytest.raises(QuotaExceedError, match="User foo has no available tokens"):
        quota_limiter.ensure_available_quota("foo")


def test_revoke_quota() -> None:
    """Test the revoke_quota operation."""
    initial_quota = 1000
    quota_limit = 100

    quota_limiter = create_quota_limiter("foo", initial_quota, quota_limit)

    # init quota for given user
    quota_limiter._init_quota()

    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota

    quota_limiter.consume_tokens(1, 1, "foo")
    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota - 2

    quota_limiter.revoke_quota("foo")
    available_quota = quota_limiter.available_quota("foo")
    assert available_quota == initial_quota
