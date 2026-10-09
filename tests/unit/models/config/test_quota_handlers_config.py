"""Unit tests for QuotaHandlersConfiguration model."""

# pylint: disable=no-member
from typing import Any

import pytest
from pydantic import ValidationError
from pytest_subtests import SubTests

from models.config import QuotaHandlersConfiguration, QuotaSchedulerConfiguration


def test_quota_handlers_configuration(subtests: SubTests) -> None:
    """Test the quota handlers configuration."""
    with subtests.test(msg="Token history disabled"):
        cfg = QuotaHandlersConfiguration(
            sqlite=None,
            postgres=None,
            limiters=[],
            scheduler=QuotaSchedulerConfiguration(
                database_reconnection_count=10,
                database_reconnection_delay=60,
                period=10,
            ),
            enable_token_history=False,
        )
        assert cfg is not None
        assert cfg.sqlite is None
        assert cfg.postgres is None
        assert cfg.limiters == []
        assert cfg.scheduler is not None
        assert cfg.scheduler.database_reconnection_count == 10
        assert cfg.scheduler.database_reconnection_delay == 60
        assert cfg.scheduler.period == 10
        assert not cfg.enable_token_history

    with subtests.test(msg="Token history enabled"):
        cfg = QuotaHandlersConfiguration(
            sqlite=None,
            postgres=None,
            limiters=[],
            scheduler=QuotaSchedulerConfiguration(
                database_reconnection_count=10,
                database_reconnection_delay=60,
                period=10,
            ),
            enable_token_history=True,
        )
        assert cfg is not None
        assert cfg.sqlite is None
        assert cfg.postgres is None
        assert cfg.limiters == []
        assert cfg.scheduler is not None
        assert cfg.scheduler.database_reconnection_count == 10
        assert cfg.scheduler.database_reconnection_delay == 60
        assert cfg.scheduler.period == 10
        assert cfg.enable_token_history


def test_quota_handlers_scheduler_configuration(subtests: SubTests) -> None:
    """Test the quota handlers configuration."""
    with subtests.test(msg="Different reconnection_count"):
        cfg = QuotaHandlersConfiguration(
            sqlite=None,
            postgres=None,
            limiters=[],
            scheduler=QuotaSchedulerConfiguration(
                database_reconnection_count=42,
                database_reconnection_delay=60,
                period=10,
            ),
            enable_token_history=True,
        )
        assert cfg is not None
        assert cfg.sqlite is None
        assert cfg.postgres is None
        assert cfg.limiters == []
        assert cfg.scheduler is not None
        assert cfg.scheduler.database_reconnection_count == 42
        assert cfg.scheduler.database_reconnection_delay == 60
        assert cfg.scheduler.period == 10
        assert cfg.enable_token_history

    with subtests.test(msg="Different reconnection_delay"):
        cfg = QuotaHandlersConfiguration(
            sqlite=None,
            postgres=None,
            limiters=[],
            scheduler=QuotaSchedulerConfiguration(
                database_reconnection_count=10,
                database_reconnection_delay=42,
                period=10,
            ),
            enable_token_history=True,
        )
        assert cfg is not None
        assert cfg.sqlite is None
        assert cfg.postgres is None
        assert cfg.limiters == []
        assert cfg.scheduler is not None
        assert cfg.scheduler.database_reconnection_count == 10
        assert cfg.scheduler.database_reconnection_delay == 42
        assert cfg.scheduler.period == 10
        assert cfg.enable_token_history

    with subtests.test(msg="Different period"):
        cfg = QuotaHandlersConfiguration(
            sqlite=None,
            postgres=None,
            limiters=[],
            scheduler=QuotaSchedulerConfiguration(
                database_reconnection_count=10,
                database_reconnection_delay=60,
                period=600,
            ),
            enable_token_history=True,
        )
        assert cfg is not None
        assert cfg.sqlite is None
        assert cfg.postgres is None
        assert cfg.limiters == []
        assert cfg.scheduler is not None
        assert cfg.scheduler.database_reconnection_count == 10
        assert cfg.scheduler.database_reconnection_delay == 60
        assert cfg.scheduler.period == 600
        assert cfg.enable_token_history


def test_quota_handlers_configuration_improper_values(subtests: SubTests) -> None:
    """Test the quota handlers configuration."""
    with subtests.test(msg="Improper SQLite settings"):
        with pytest.raises(
            ValidationError,
            match="Input should be a valid dictionary or instance of SQLiteDatabaseConfiguration",
        ):
            QuotaHandlersConfiguration(
                sqlite="not a proper config",  # pyright: ignore[reportArgumentType]
                postgres=None,
                limiters=[],
                scheduler=QuotaSchedulerConfiguration(
                    database_reconnection_count=10,
                    database_reconnection_delay=60,
                    period=10,
                ),
                enable_token_history=False,
            )

    with subtests.test(msg="Improper PostgreSQL settings"):
        with pytest.raises(
            ValidationError,
            match="should be a valid dictionary or instance of PostgreSQLDatabaseConfiguration",
        ):
            QuotaHandlersConfiguration(
                sqlite=None,
                postgres="not a proper config",  # pyright: ignore[reportArgumentType]
                limiters=[],
                scheduler=QuotaSchedulerConfiguration(
                    database_reconnection_count=10,
                    database_reconnection_delay=60,
                    period=10,
                ),
                enable_token_history=False,
            )

    with subtests.test(msg="None limiters settings"):
        with pytest.raises(
            ValidationError,
            match="Input should be a valid list",
        ):
            QuotaHandlersConfiguration(
                sqlite=None,
                postgres=None,
                limiters=None,  # pyright: ignore[reportArgumentType]
                scheduler=QuotaSchedulerConfiguration(
                    database_reconnection_count=10,
                    database_reconnection_delay=60,
                    period=10,
                ),
                enable_token_history=False,
            )

    with subtests.test(msg="Improper limiters settings"):
        with pytest.raises(
            ValidationError,
            match="Input should be a valid list",
        ):
            QuotaHandlersConfiguration(
                sqlite=None,
                postgres=None,
                limiters="should be a list of limiters",  # pyright: ignore[reportArgumentType]
                scheduler=QuotaSchedulerConfiguration(
                    database_reconnection_count=10,
                    database_reconnection_delay=60,
                    period=10,
                ),
                enable_token_history=False,
            )

    with subtests.test(msg="Improper enable_token_history"):
        with pytest.raises(
            ValidationError,
            match="Input should be a valid boolean",
        ):
            QuotaHandlersConfiguration(
                sqlite=None,
                postgres=None,
                limiters=[],
                scheduler=QuotaSchedulerConfiguration(
                    database_reconnection_count=10,
                    database_reconnection_delay=60,
                    period=10,
                ),
                enable_token_history="enabled",  # pyright: ignore[reportArgumentType]
            )

    with subtests.test(msg="Improper scheduler"):
        with pytest.raises(
            ValidationError,
            match="Input should be a valid dictionary or instance of QuotaSchedulerConfiguration",
        ):
            QuotaHandlersConfiguration(
                sqlite=None,
                postgres=None,
                limiters=[],
                scheduler="scheduler",  # pyright: ignore[reportArgumentType]
                enable_token_history=False,
            )


correct_configurations = [
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Brittany Perez",
                "initial_quota": 533,
                "quota_increase": 921,
                "period": "All instead purpose pull be spend use.",
            }
        ],
        "scheduler": {
            "period": 279,
            "database_reconnection_count": 766,
            "database_reconnection_delay": 809,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": {"db_path": "/tmp/foo/bar/baz"},
        "postgres": {
            "host": "Only himself prevent walk.",
            "port": 362,
            "db": "Present ever art central. Work smile six.",
            "user": "Later spring song.",
            "password": "&8wr@Mt@lMZG",
            "namespace": "Seem own offer deal energy.",
            "ssl_mode": "disable",
            "gss_encmode": "disable",
        },
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Christina Hall",
                "initial_quota": 723,
                "quota_increase": 112,
                "period": "1 day",
            }
        ],
        "scheduler": {
            "period": 479,
            "database_reconnection_count": 808,
            "database_reconnection_delay": 836,
        },
        "enable_token_history": True,
    },
    {
        "sqlite": {"db_path": "Between room attorney weight dream."},
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Xavier Anthony",
                "initial_quota": 536,
                "quota_increase": 80,
                "period": "30 seconds",
            },
            {
                "type": "user_limiter",
                "name": "Caroline Weaver",
                "initial_quota": 31,
                "quota_increase": 57,
                "period": "2 hours",
            },
        ],
        "scheduler": {
            "period": 960,
            "database_reconnection_count": 5,
            "database_reconnection_delay": 336,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Kyle Whitehead",
                "initial_quota": 998,
                "quota_increase": 506,
                "period": "Pm recently character deal person.",
            },
            {
                "type": "user_limiter",
                "name": "Gary Ward",
                "initial_quota": 948,
                "quota_increase": 349,
                "period": "We physical seven follow turn front establish reme",
            },
        ],
        "scheduler": {
            "period": 83,
            "database_reconnection_count": 88,
            "database_reconnection_delay": 428,
        },
        "enable_token_history": True,
    },
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Christopher Flores",
                "initial_quota": 589,
                "quota_increase": 815,
                "period": "Page power would end he stage.",
            }
        ],
        "scheduler": {
            "period": 217,
            "database_reconnection_count": 374,
            "database_reconnection_delay": 70,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Shannon Martin",
                "initial_quota": 110,
                "quota_increase": 755,
                "period": "Case material system career ever these short.",
            },
            {
                "type": "user_limiter",
                "name": "Gabrielle Meadows",
                "initial_quota": 760,
                "quota_increase": 55,
                "period": "Page serve civil question series purpose.",
            },
            {
                "type": "user_limiter",
                "name": "Kelly Velasquez",
                "initial_quota": 419,
                "quota_increase": 633,
                "period": "Behavior half loss during pay.",
            },
        ],
        "scheduler": {
            "period": 387,
            "database_reconnection_count": 216,
            "database_reconnection_delay": 894,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": {"db_path": "Camera agent general always like."},
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Bill Boyd",
                "initial_quota": 582,
                "quota_increase": 84,
                "period": "7 days",
            }
        ],
        "scheduler": {
            "period": 414,
            "database_reconnection_count": 407,
            "database_reconnection_delay": 109,
        },
        "enable_token_history": True,
    },
    {
        "sqlite": {"db_path": "Begin remain inside practice ability Mrs."},
        "postgres": {
            "host": "Police stuff black.",
            "port": 589,
            "db": "Decide history worker can stand.",
            "user": "Type away organization debate stand.",
            "password": "@alvNH%qK%47",
            "namespace": "Compare gun trip establish key.",
            "ssl_mode": "disable",
            "gss_encmode": "disable",
        },
        "limiters": [
            {
                "type": "user_limiter",
                "name": "William Armstrong",
                "initial_quota": 305,
                "quota_increase": 648,
                "period": "5 minutes",
            },
            {
                "type": "user_limiter",
                "name": "Terry Mitchell",
                "initial_quota": 206,
                "quota_increase": 316,
                "period": "1 month",
            },
            {
                "type": "user_limiter",
                "name": "Deborah Vazquez",
                "initial_quota": 24,
                "quota_increase": 24,
                "period": "1 year",
            },
        ],
        "scheduler": {
            "period": 959,
            "database_reconnection_count": 125,
            "database_reconnection_delay": 94,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": {"db_path": "Than draw security away."},
        "postgres": {
            "host": "Beat decade start performance without summer.",
            "port": 554,
            "db": "Election wall us notice.",
            "user": "Each go improve happy.",
            "password": "UXR&Zm4$W*8^",
            "namespace": None,
            "ssl_mode": "allow",
            "gss_encmode": "prefer",
        },
        "limiters": [
            {
                "type": "user_limiter",
                "name": "James Burgess",
                "initial_quota": 698,
                "quota_increase": 945,
                "period": "3 seconds",
            },
            {
                "type": "user_limiter",
                "name": "Brenda Richard",
                "initial_quota": 583,
                "quota_increase": 582,
                "period": "12 hours",
            },
            {
                "type": "user_limiter",
                "name": "Carol Colon",
                "initial_quota": 26,
                "quota_increase": 527,
                "period": "30 days",
            },
        ],
        "scheduler": {
            "period": 609,
            "database_reconnection_count": 225,
            "database_reconnection_delay": 316,
        },
        "enable_token_history": True,
    },
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Katherine Gibson",
                "initial_quota": 971,
                "quota_increase": 482,
                "period": "Many debate myself.",
            },
            {
                "type": "user_limiter",
                "name": "David Mcclure",
                "initial_quota": 883,
                "quota_increase": 55,
                "period": "Under from often.",
            },
            {
                "type": "user_limiter",
                "name": "Nicholas Jones",
                "initial_quota": 622,
                "quota_increase": 333,
                "period": "Research situation apply positive.",
            },
        ],
        "scheduler": {
            "period": 278,
            "database_reconnection_count": 173,
            "database_reconnection_delay": 666,
        },
        "enable_token_history": True,
    },
]


@pytest.mark.parametrize("config_dict", correct_configurations)
def test_quota_handlers_from_dict(config_dict: dict[str, Any]) -> None:
    """Test the configuration initialization from dictionary with config values."""
    # try to initialize the app config and load configuration from a Python
    # dictionary
    QuotaHandlersConfiguration(**config_dict)


incorrect_configurations = [
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Brittany Perez",
                "initial_quota": None,
                "quota_increase": 921,
                "period": "All instead purpose pull be spend use.",
            }
        ],
        "scheduler": {
            "period": 279,
            "database_reconnection_count": 766,
            "database_reconnection_delay": 809,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": {"db_path": "/tmp/foo/bar/baz"},
        "postgres": {
            "host": "Only himself prevent walk.",
            "port": 362,
            "db": "Present ever art central. Work smile six.",
            "user": "Later spring song.",
            "password": "&8wr@Mt@lMZG",
            "namespace": "Seem own offer deal energy.",
            "ssl_mode": "disable",
            "gss_encmode": "disable",
        },
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Christina Hall",
                "initial_quota": 723,
                "quota_increase": None,
                "period": "Media pretty recently push gas.",
            }
        ],
        "scheduler": {
            "period": 479,
            "database_reconnection_count": 808,
            "database_reconnection_delay": 836,
        },
        "enable_token_history": True,
    },
    {
        "sqlite": {"db_path": "Between room attorney weight dream."},
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Xavier Anthony",
                "initial_quota": 536,
                "quota_increase": 80,
                "period": "Wrong class strategy.",
            },
            {
                "type": "user_limiter",
                "name": "Caroline Weaver",
                "initial_quota": 31,
                "quota_increase": 57,
                "period": "Lead boy least base.",
            },
        ],
        "scheduler": {
            "period": 960,
            "database_reconnection_count": None,
            "database_reconnection_delay": 336,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Kyle Whitehead",
                "initial_quota": 998,
                "quota_increase": 506,
                "period": "Pm recently character deal person.",
            },
            {
                "type": "user_limiter",
                "name": "Gary Ward",
                "initial_quota": 948,
                "quota_increase": 349,
                "period": "We physical seven follow turn front establish reme",
            },
        ],
        "scheduler": {
            "period": 83,
            "database_reconnection_count": 88,
            "database_reconnection_delay": None,
        },
        "enable_token_history": True,
    },
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Christopher Flores",
                "initial_quota": 589,
                "quota_increase": 815,
                "period": "Page power would end he stage.",
            }
        ],
        "scheduler": {
            "period": None,
            "database_reconnection_count": 374,
            "database_reconnection_delay": 70,
        },
        "enable_token_history": False,
    },
    {
        "sqlite": None,
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Shannon Martin",
                "initial_quota": 110,
                "quota_increase": 755,
                "period": "Case material system career ever these short.",
            },
            {
                "type": "user_limiter",
                "name": "Gabrielle Meadows",
                "initial_quota": 760,
                "quota_increase": 55,
                "period": "Page serve civil question series purpose.",
            },
            {
                "type": "user_limiter",
                "name": "Kelly Velasquez",
                "initial_quota": 419,
                "quota_increase": 633,
                "period": "Behavior half loss during pay.",
            },
        ],
        "scheduler": {
            "period": 387,
            "database_reconnection_count": 216,
            "database_reconnection_delay": 894,
        },
        "enable_token_history": None,
    },
    {
        "sqlite": {"db_path": "Camera agent general always like."},
        "postgres": None,
        "limiters": [
            {
                "type": "user_limiter",
                "name": "Bill Boyd",
                "initial_quota": 582,
                "quota_increase": 84,
                "period": "Side no born set. Different weight speak why daugh",
            }
        ],
        "scheduler": None,
        "enable_token_history": True,
    },
    {
        "sqlite": {"db_path": "Begin remain inside practice ability Mrs."},
        "postgres": {
            "host": "Police stuff black.",
            "port": None,
            "db": "Decide history worker can stand.",
            "user": "Type away organization debate stand.",
            "password": "@alvNH%qK%47",
            "namespace": "Compare gun trip establish key.",
            "ssl_mode": "disable",
            "gss_encmode": "disable",
        },
        "limiters": [
            {
                "type": "user_limiter",
                "name": "William Armstrong",
                "initial_quota": 305,
                "quota_increase": 648,
                "period": "Relate couple song way wind rule model.",
            },
            {
                "type": "user_limiter",
                "name": "Terry Mitchell",
                "initial_quota": 206,
                "quota_increase": 316,
                "period": "Onto within arrive type group. Black none human re",
            },
            {
                "type": "user_limiter",
                "name": "Deborah Vazquez",
                "initial_quota": 24,
                "quota_increase": 24,
                "period": "Call close table.",
            },
        ],
        "scheduler": {
            "period": 959,
            "database_reconnection_count": 125,
            "database_reconnection_delay": 94,
        },
        "enable_token_history": False,
    },
]


@pytest.mark.parametrize("config_dict", incorrect_configurations)
def test_quota_handlers_from_dict_negative_cases(config_dict: dict[str, Any]) -> None:
    """Test the configuration initialization from dictionary with config values."""
    with pytest.raises(
        ValidationError,
        match=" validation error for QuotaHandlersConfiguration",
    ):
        # try to initialize the app config and load configuration from a Python
        # dictionary
        QuotaHandlersConfiguration(**config_dict)


sqlite_storage = {"sqlite": {"db_path": ":memory:"}}

postgres_storage = {"postgres": {"db": "quota", "user": "quota", "password": "secret"}}

no_storage: dict[str, Any] = {}


def configuration_with_period(storage: dict[str, Any], period: str) -> dict[str, Any]:
    """Return quota handlers configuration whose second limiter has the given period."""
    return {
        **storage,
        "limiters": [
            {
                "type": "cluster_limiter",
                "name": "cluster_daily_limits",
                "initial_quota": 1000,
                "quota_increase": 0,
                "period": "1 day",
            },
            {
                "type": "user_limiter",
                "name": "user_weekly_limits",
                "initial_quota": 100,
                "quota_increase": 0,
                "period": period,
            },
        ],
    }


periods_usable_by_sqlite = [
    "3 seconds",
    "30 minutes",
    "2 hours",
    "7 days",
    "1 month",
    "1 year",
]


@pytest.mark.parametrize("period", periods_usable_by_sqlite)
def test_quota_handlers_sqlite_usable_period(period: str) -> None:
    """Test that a period SQLite can use is accepted with the SQLite storage."""
    cfg = QuotaHandlersConfiguration(
        **configuration_with_period(sqlite_storage, period)
    )
    assert cfg.limiters[1].period == period


periods_not_usable_by_sqlite = [
    "1 week",
    "1 day 2 hours",
    "0 days",
    "-1 day",
    "",
    "forever",
]


@pytest.mark.parametrize("period", periods_not_usable_by_sqlite)
def test_quota_handlers_sqlite_unusable_period(period: str) -> None:
    """Test that a period SQLite can not use is rejected with the SQLite storage."""
    with pytest.raises(
        ValidationError,
        match=f"Quota limiter 'user_weekly_limits': period '{period}' can not be "
        "used with the SQLite storage.*for example '7 days'",
    ):
        QuotaHandlersConfiguration(**configuration_with_period(sqlite_storage, period))


@pytest.mark.parametrize("storage", [postgres_storage, no_storage])
def test_quota_handlers_period_not_checked_without_sqlite(
    storage: dict[str, Any],
) -> None:
    """Test that the period is not checked when the SQLite storage is not configured."""
    cfg = QuotaHandlersConfiguration(**configuration_with_period(storage, "1 week"))
    assert cfg.limiters[1].period == "1 week"
