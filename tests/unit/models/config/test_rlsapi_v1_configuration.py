"""Unit tests for RlsapiV1Configuration and related startup validators."""

import logging
from typing import Any

import pytest
from pydantic import ValidationError

from models.config import Configuration, RlsapiV1Configuration

# --- Test RlsapiV1Configuration ---


def test_defaults() -> None:
    """Test RlsapiV1Configuration defaults to disabled state."""
    config = RlsapiV1Configuration()
    assert config.allow_verbose_infer is False
    assert config.quota_subject is None


@pytest.mark.parametrize(
    "quota_subject",
    [
        pytest.param("user_id", id="user_id"),
        pytest.param("org_id", id="org_id"),
        pytest.param("system_id", id="system_id"),
    ],
)
def test_valid_quota_subject_values(quota_subject: str) -> None:
    """Test all valid quota_subject literal values are accepted."""
    config = RlsapiV1Configuration(
        quota_subject=quota_subject  # pyright: ignore[reportArgumentType]
    )
    assert config.quota_subject == quota_subject


def test_invalid_quota_subject_rejected() -> None:
    """Test invalid quota_subject value is rejected by Literal validation."""
    with pytest.raises(ValidationError, match="quota_subject"):
        RlsapiV1Configuration(
            quota_subject="invalid_value"  # pyright: ignore[reportArgumentType]
        )


def test_rejects_unknown_fields() -> None:
    """Test RlsapiV1Configuration rejects unknown fields (extra=forbid)."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RlsapiV1Configuration(
            unknown_field="should_fail"  # pyright: ignore[reportCallIssue]
        )


# --- Test Configuration-level startup validators ---


def _build_config_dict(**overrides: Any) -> dict[str, Any]:
    """Build a minimal Configuration dict with optional overrides.

    Args:
        **overrides: Keys to override in the base config dict.

    Returns:
        A dict suitable for Configuration(**dict).
    """
    base: dict[str, Any] = {
        "name": "test",
        "service": {"host": "localhost", "port": 8080},
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {},
        "authentication": {"module": "noop"},
        "authorization": {"access_rules": []},
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("quota_subject", "auth_module"),
    [
        pytest.param("org_id", "noop", id="org_id_noop"),
        pytest.param("org_id", "k8s", id="org_id_k8s"),
        pytest.param("system_id", "noop", id="system_id_noop"),
        pytest.param("system_id", "k8s", id="system_id_k8s"),
    ],
)
def test_identity_quota_subject_requires_rh_identity(
    quota_subject: str, auth_module: str
) -> None:
    """Test startup validation rejects org_id/system_id without rh-identity auth."""
    config_dict = _build_config_dict(
        rlsapi_v1={"quota_subject": quota_subject},
        authentication={"module": auth_module},
    )
    with pytest.raises(ValidationError, match="rh-identity"):
        Configuration(**config_dict)


def test_quota_subject_user_id_works_with_any_auth() -> None:
    """Test user_id quota_subject is accepted with any authentication module."""
    config_dict = _build_config_dict(
        rlsapi_v1={"quota_subject": "user_id"},
        authentication={"module": "noop"},
    )
    config = Configuration(**config_dict)
    assert config.rlsapi_v1.quota_subject == "user_id"  # pylint: disable=no-member


def test_quota_subject_org_id_accepted_with_rh_identity() -> None:
    """Test org_id quota_subject is accepted when rh-identity auth is configured."""
    config_dict = _build_config_dict(
        rlsapi_v1={"quota_subject": "org_id"},
        authentication={"module": "rh-identity", "rh_identity_config": {}},
    )
    config = Configuration(**config_dict)
    assert config.rlsapi_v1.quota_subject == "org_id"  # pylint: disable=no-member


def test_quota_subject_none_by_default() -> None:
    """Test quota_subject defaults to None when not configured."""
    config_dict = _build_config_dict()
    config = Configuration(**config_dict)
    assert config.rlsapi_v1.quota_subject is None  # pylint: disable=no-member


def test_quota_subject_warns_when_no_limiters(caplog: pytest.LogCaptureFixture) -> None:
    """Test startup validation warns when quota_subject is set but no limiters exist."""
    config_dict = _build_config_dict(
        rlsapi_v1={"quota_subject": "user_id"},
        authentication={"module": "noop"},
        quota_handlers={},
    )
    with caplog.at_level(logging.WARNING, logger="lightspeed_stack.models.config"):
        Configuration(**config_dict)

    assert "quota enforcement is not fully configured" in caplog.text


def test_quota_subject_warns_when_no_storage_backend(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test startup validation warns when limiters exist but no storage backend."""
    config_dict = _build_config_dict(
        rlsapi_v1={"quota_subject": "user_id"},
        authentication={"module": "noop"},
        quota_handlers={
            "limiters": [
                {
                    "name": "test",
                    "type": "user_limiter",
                    "initial_quota": 1000,
                    "quota_increase": 0,
                    "period": "1 month",
                }
            ],
        },
    )
    with caplog.at_level(logging.WARNING, logger="lightspeed_stack.models.config"):
        Configuration(**config_dict)

    assert "quota enforcement is not fully configured" in caplog.text
