"""Integration tests for quota management configured from YAML files (LCORE-4610).

The unit tests build ``QuotaHandlersConfiguration`` objects by hand. These
tests go through ``AppConfig.load_configuration`` instead, so that the YAML
shape, the environment substitution, the LCORE-4606 period validation, the
limiter factory and the scheduler statements are exercised together on a
real SQLite file. The e2e fixtures of ``quota.feature`` are loaded as well,
so that drift in them fails here in seconds rather than in the e2e shard.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from configuration import AppConfig, configuration
from quota.cluster_quota_limiter import ClusterQuotaLimiter
from quota.user_quota_limiter import UserQuotaLimiter
from runners.quota_scheduler import connect
from tests.integration._quota_helpers import (
    CLUSTER,
    CLUSTER_SUBJECT,
    USER_SUBJECT,
    back_date,
    read_available,
    renew,
    spend,
)

CONFIGURATION_DIR = Path(__file__).parent.parent / "configuration"
QUOTA_CONFIG = CONFIGURATION_DIR / "lightspeed-stack-quota-sqlite.yaml"
E2E_CONFIGURATION_DIR = Path(__file__).parent.parent / "e2e" / "configuration"

ALICE = "alice"


@pytest.fixture(name="quota_db")
def quota_db_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``${env.LCS_QUOTA_DB_PATH}`` of the fixture file at a temporary file."""
    db_path = tmp_path / "quota.db"
    monkeypatch.setenv("LCS_QUOTA_DB_PATH", str(db_path))
    return db_path


@pytest.fixture(name="loaded")
def loaded_fixture(quota_db: Path) -> Generator[AppConfig, None, None]:
    """Load the quota fixture file and close what it opened afterwards."""
    _ = quota_db
    configuration.load_configuration(str(QUOTA_CONFIG))
    yield configuration
    # pylint: disable=protected-access
    for limiter in configuration._quota_limiters:
        limiter.connection.close()
    configuration._quota_limiters = []
    if configuration._token_usage_history is not None:
        assert configuration._token_usage_history.connection is not None
        configuration._token_usage_history.connection.close()
        configuration._token_usage_history = None


def test_limiters_and_history_are_built_from_the_file(
    loaded: AppConfig, quota_db: Path
) -> None:
    """The file yields one limiter per entry, in order, on the substituted path."""
    user, cluster = loaded.quota_limiters

    assert isinstance(user, UserQuotaLimiter)
    assert (user.initial_quota, user.increase_by) == (100, 0)
    assert isinstance(cluster, ClusterQuotaLimiter)
    assert (cluster.initial_quota, cluster.increase_by) == (0, 500)
    assert user.sqlite_connection_config is not None
    assert user.sqlite_connection_config.db_path == str(quota_db)
    assert quota_db.exists()

    history = loaded.token_usage_history
    assert history is not None
    assert history.connected()


def test_scheduler_renews_the_database_of_the_file(
    loaded: AppConfig, quota_db: Path
) -> None:
    """The scheduler's statements, chosen from the file, renew the limiters' rows."""
    user, cluster = loaded.quota_limiters
    spend(user, 30, ALICE)
    spend(cluster, 200)
    assert read_available(quota_db, ALICE, USER_SUBJECT) == 70
    assert read_available(quota_db, CLUSTER, CLUSTER_SUBJECT) == -200
    back_date(quota_db)

    quota_handlers = loaded.configuration.quota_handlers
    connection = connect(quota_handlers)
    try:
        renew(connection, quota_handlers)
    finally:
        connection.close()

    assert read_available(quota_db, ALICE, USER_SUBJECT) == 100
    assert read_available(quota_db, CLUSTER, CLUSTER_SUBJECT) == -200 + 500


def test_a_period_sqlite_cannot_use_is_rejected_at_load(
    quota_db: Path, tmp_path: Path
) -> None:
    """A period SQLite's datetime() cannot parse never renews; it is rejected (LCORE-4606)."""
    _ = quota_db
    config = yaml.safe_load(QUOTA_CONFIG.read_text(encoding="utf-8"))
    config["quota_handlers"]["limiters"][0]["period"] = "1 week"
    broken = tmp_path / "lightspeed-stack-quota-broken.yaml"
    broken.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(
        ValidationError, match="period '1 week' can not be used with the SQLite storage"
    ):
        configuration.load_configuration(str(broken))


# ==========================================
# The e2e fixtures of quota.feature
# ==========================================

# The numbers quota.feature relies on: one token lets exactly one request
# through, renewal within a few seconds lets a bounded poll observe it.
E2E_EXHAUSTION_LIMITERS = [
    ("user_limiter", 1, 0, "1 day"),
    ("cluster_limiter", 1_000_000, 0, "1 day"),
]
E2E_RENEWAL_LIMITERS = [
    ("user_limiter", 0, 1_000_000, "2 seconds"),
    ("cluster_limiter", 0, 1_000_000, "2 seconds"),
]


@pytest.mark.parametrize("mode", ["library-mode", "server-mode"])
@pytest.mark.parametrize(
    ("filename", "expected_limiters"),
    [
        pytest.param(
            "lightspeed-stack-quota.yaml", E2E_EXHAUSTION_LIMITERS, id="exhaustion"
        ),
        pytest.param(
            "lightspeed-stack-quota-renewal.yaml", E2E_RENEWAL_LIMITERS, id="renewal"
        ),
    ],
)
def test_e2e_quota_fixture_loads_with_the_values_the_feature_relies_on(
    mode: str,
    filename: str,
    expected_limiters: list[tuple[str, int, int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both e2e quota fixtures load, in both deployment modes, with the expected quotas."""
    monkeypatch.setenv("E2E_OGX_HOSTNAME", "localhost")

    configuration.load_configuration(str(E2E_CONFIGURATION_DIR / mode / filename))

    quota_handlers = configuration.configuration.quota_handlers
    assert quota_handlers.sqlite is not None
    assert quota_handlers.sqlite.db_path == "/tmp/quota.db"
    assert quota_handlers.postgres is None
    assert quota_handlers.scheduler.period == 1
    assert [
        (limiter.type, limiter.initial_quota, limiter.quota_increase, limiter.period)
        for limiter in quota_handlers.limiters
    ] == expected_limiters
    assert configuration.configuration.rlsapi_v1.quota_subject == "user_id"
    assert configuration.configuration.authentication.module == "noop"
