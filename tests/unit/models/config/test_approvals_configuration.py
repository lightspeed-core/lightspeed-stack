"""Unit tests for human-in-the-loop approvals configuration models."""

# pylint: disable=no-member

import pytest
from pydantic import ValidationError

from lightspeed_stack.models.config import (
    ApprovalFilter,
    ApprovalsConfiguration,
    CompactionConfiguration,
    Configuration,
    LlamaStackConfiguration,
    ServiceConfiguration,
    UserDataCollection,
)


def test_approvals_configuration_defaults() -> None:
    """ApprovalsConfiguration uses design-doc defaults for timeout and retention."""
    config = ApprovalsConfiguration()
    assert config.approval_timeout_seconds == 300
    assert config.approval_retention_days == 30


def test_approvals_configuration_custom_timeout() -> None:
    """approval_timeout_seconds accepts positive integers."""
    config = ApprovalsConfiguration(approval_timeout_seconds=600)
    assert config.approval_timeout_seconds == 600


def test_approvals_configuration_custom_retention() -> None:
    """approval_retention_days accepts positive integers."""
    config = ApprovalsConfiguration(approval_retention_days=90)
    assert config.approval_retention_days == 90


def test_approvals_configuration_rejects_non_positive_retention() -> None:
    """approval_retention_days rejects zero and negative values."""
    with pytest.raises(ValidationError):
        ApprovalsConfiguration(approval_retention_days=0)

    with pytest.raises(ValidationError):
        ApprovalsConfiguration(approval_retention_days=-1)


def test_approvals_configuration_rejects_non_positive_timeout() -> None:
    """approval_timeout_seconds rejects zero and negative values."""
    with pytest.raises(ValidationError):
        ApprovalsConfiguration(approval_timeout_seconds=0)

    with pytest.raises(ValidationError):
        ApprovalsConfiguration(approval_timeout_seconds=-1)


def test_approvals_configuration_rejects_unknown_field() -> None:
    """Unknown fields are forbidden on ApprovalsConfiguration."""
    with pytest.raises(ValidationError):
        ApprovalsConfiguration(approval_ttl_seconds=300)  # type: ignore[call-arg]


def test_approval_filter_always_and_never_lists() -> None:
    """ApprovalFilter stores always and never tool name lists."""
    filt = ApprovalFilter(
        always=["create_issue", "delete_branch"],
        never=["list_repos", "get_issue"],
    )
    assert filt.always == ["create_issue", "delete_branch"]
    assert filt.never == ["list_repos", "get_issue"]


def test_approval_filter_defaults_to_empty_lists() -> None:
    """ApprovalFilter always and never default to empty lists."""
    filt = ApprovalFilter()
    assert filt.always == []
    assert filt.never == []


def test_approval_filter_rejects_overlapping_tool_names() -> None:
    """A tool cannot appear in both always and never lists."""
    with pytest.raises(ValidationError, match="both always and never lists"):
        ApprovalFilter(always=["shared_tool"], never=["shared_tool"])


def test_approval_filter_rejects_unknown_field() -> None:
    """Unknown fields are forbidden on ApprovalFilter."""
    with pytest.raises(ValidationError):
        ApprovalFilter(always=[], unknown=True)  # type: ignore[call-arg]


def test_root_configuration_has_approvals_field() -> None:
    """The root Configuration declares an approvals field with defaults."""
    field_info = Configuration.model_fields.get("approvals")
    assert field_info is not None
    assert field_info.annotation is ApprovalsConfiguration

    factory = field_info.default_factory
    assert factory is not None
    default = factory()  # type: ignore[call-arg]
    assert isinstance(default, ApprovalsConfiguration)
    assert default.approval_timeout_seconds == 300
    assert default.approval_retention_days == 30


def test_root_configuration_default_includes_approvals() -> None:
    """Configuration constructed with required fields gets default approvals."""
    cfg = Configuration(
        name="test",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        compaction=CompactionConfiguration(),
    )
    approvals: ApprovalsConfiguration = cfg.approvals
    assert approvals.approval_timeout_seconds == 300
    assert approvals.approval_retention_days == 30
