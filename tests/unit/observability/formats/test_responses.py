"""Unit tests for responses event builders."""

import pytest
from pytest_mock import MockerFixture

from observability.formats.responses import ResponsesEventData, build_responses_event


@pytest.fixture(name="sample_event_data")
def sample_event_data_fixture() -> ResponsesEventData:
    """Create sample responses event data for testing."""
    return ResponsesEventData(
        input_text="How do I configure SSH?",
        response_text="To configure SSH, edit /etc/ssh/sshd_config...",
        conversation_id="conv-abc-123",
        model="granite-3-8b-instruct",
        org_id="12345678",
        system_id="abc-def-123",
        inference_time=2.34,
    )


def test_builds_event_with_all_fields(
    mocker: MockerFixture, sample_event_data: ResponsesEventData
) -> None:
    """Test event contains all required fields and placeholders."""
    mock_config = mocker.patch("observability.formats.responses.configuration")
    mock_config.deployment_environment = "production"

    event = build_responses_event(sample_event_data)

    assert event["input_text"] == "How do I configure SSH?"
    assert event["response_text"] == "To configure SSH, edit /etc/ssh/sshd_config..."
    assert event["conversation_id"] == "conv-abc-123"
    assert event["inference_time"] == 2.34
    assert event["model"] == "granite-3-8b-instruct"
    assert event["org_id"] == "12345678"
    assert event["system_id"] == "abc-def-123"
    assert event["deployment"] == "production"
    assert event["total_llm_tokens"] == 0


def test_builds_event_with_token_counts(mocker: MockerFixture) -> None:
    """Test total_llm_tokens is computed from input and output token counts."""
    mock_config = mocker.patch("observability.formats.responses.configuration")
    mock_config.deployment_environment = "production"

    data = ResponsesEventData(
        input_text="test",
        response_text="test",
        conversation_id="conv-123",
        inference_time=1.0,
        model="test-model",
        org_id="org1",
        system_id="sys1",
        input_tokens=150,
        output_tokens=75,
    )

    event = build_responses_event(data)

    assert event["total_llm_tokens"] == 225


def test_handles_auth_disabled_values(mocker: MockerFixture) -> None:
    """Test event handles auth_disabled placeholder values."""
    data = ResponsesEventData(
        input_text="test",
        response_text="test",
        conversation_id="conv-456",
        inference_time=1.0,
        model="test-model",
        org_id="auth_disabled",
        system_id="auth_disabled",
    )

    mock_config = mocker.patch("observability.formats.responses.configuration")
    mock_config.deployment_environment = "test"

    event = build_responses_event(data)

    assert event["org_id"] == "auth_disabled"
    assert event["system_id"] == "auth_disabled"


def test_default_token_values() -> None:
    """Test default token values are zero."""
    data = ResponsesEventData(
        input_text="test",
        response_text="test",
        conversation_id="conv-789",
        inference_time=1.0,
        model="test-model",
        org_id="org1",
        system_id="sys1",
    )

    assert data.input_tokens == 0
    assert data.output_tokens == 0
