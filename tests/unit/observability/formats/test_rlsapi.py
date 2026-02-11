"""Unit tests for rlsapi v1 event builders."""

from unittest.mock import patch

import pytest

from observability.formats.rlsapi import InferenceEventData, build_inference_event


@pytest.fixture(name="sample_event_data")
def sample_event_data_fixture() -> InferenceEventData:
    """Create sample inference event data for testing."""
    return InferenceEventData(
        question="How do I configure SSH?",
        response="To configure SSH, edit /etc/ssh/sshd_config...",
        inference_time=2.34,
        model="granite-3-8b-instruct",
        org_id="12345678",
        system_id="abc-def-123",
        request_id="req_xyz789",
        cla_version="CLA/0.4.1",
        system_os="RHEL",
        system_version="9.3",
        system_arch="x86_64",
    )


def test_builds_event_with_all_fields(sample_event_data: InferenceEventData) -> None:
    """Test event contains all required fields and placeholders."""
    with patch("observability.formats.rlsapi.configuration") as mock_config:
        mock_config.deployment_environment = "production"

        event = build_inference_event(sample_event_data)

        assert event["question"] == "How do I configure SSH?"
        assert event["response"] == "To configure SSH, edit /etc/ssh/sshd_config..."
        assert event["inference_time"] == 2.34
        assert event["model"] == "granite-3-8b-instruct"
        assert event["org_id"] == "12345678"
        assert event["system_id"] == "abc-def-123"
        assert event["request_id"] == "req_xyz789"
        assert event["cla_version"] == "CLA/0.4.1"
        assert event["system_os"] == "RHEL"
        assert event["system_version"] == "9.3"
        assert event["system_arch"] == "x86_64"
        assert event["deployment"] == "production"
        assert not event["refined_questions"]
        assert event["context"] == ""
        assert event["total_llm_tokens"] == 0


def test_handles_auth_disabled_values() -> None:
    """Test event handles auth_disabled placeholder values."""
    data = InferenceEventData(
        question="test",
        response="test",
        inference_time=1.0,
        model="test-model",
        org_id="auth_disabled",
        system_id="auth_disabled",
        request_id="req_123",
        cla_version="test/1.0",
        system_os="",
        system_version="",
        system_arch="",
    )

    with patch("observability.formats.rlsapi.configuration") as mock_config:
        mock_config.deployment_environment = "test"

        event = build_inference_event(data)

        assert event["org_id"] == "auth_disabled"
        assert event["system_id"] == "auth_disabled"
