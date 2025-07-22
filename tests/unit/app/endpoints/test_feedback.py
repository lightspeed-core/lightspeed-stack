"""Unit tests for the /feedback REST API endpoint."""

from fastapi import HTTPException, status
import pytest

from configuration import configuration
from app.endpoints.feedback import (
    is_feedback_enabled,
    assert_feedback_enabled,
    feedback_endpoint_handler,
    store_feedback,
    feedback_status,
)


def test_is_feedback_enabled():
    """Test that is_feedback_enabled returns True when feedback is not disabled."""
    configuration.user_data_collection_configuration.feedback_enabled = True
    assert is_feedback_enabled() is True, "Feedback should be enabled"


def test_is_feedback_disabled():
    """Test that is_feedback_enabled returns False when feedback is disabled."""
    configuration.user_data_collection_configuration.feedback_enabled = False
    assert is_feedback_enabled() is False, "Feedback should be disabled"


async def test_assert_feedback_enabled_disabled(mocker):
    """Test that assert_feedback_enabled raises HTTPException when feedback is disabled."""

    # Simulate feedback being disabled
    mocker.patch("app.endpoints.feedback.is_feedback_enabled", return_value=False)

    with pytest.raises(HTTPException) as exc_info:
        await assert_feedback_enabled(mocker.Mock())

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Forbidden: Feedback is disabled"


async def test_assert_feedback_enabled(mocker):
    """Test that assert_feedback_enabled does not raise an exception when feedback is enabled."""

    # Simulate feedback being enabled
    mocker.patch("app.endpoints.feedback.is_feedback_enabled", return_value=True)

    # Should not raise an exception
    await assert_feedback_enabled(mocker.Mock())


def test_feedback_endpoint_handler(mocker):
    """Test that feedback_endpoint_handler processes feedback correctly."""
    # Mock the dependencies
    mocker.patch("app.endpoints.feedback.assert_feedback_enabled", return_value=None)
    mocker.patch("utils.common.retrieve_user_id", return_value="test_user_id")
    mocker.patch("app.endpoints.feedback.store_feedback", return_value=None)

    # Mock the feedback request
    feedback_request = mocker.Mock()

    # Call the endpoint handler
    result = feedback_endpoint_handler(
        _request=mocker.Mock(),
        feedback_request=feedback_request,
        _ensure_feedback_enabled=assert_feedback_enabled,
    )

    # Assert that the response is as expected
    assert result.response == "feedback received"


def test_feedback_endpoint_handler_error(mocker):
    """Test that feedback_endpoint_handler raises an HTTPException on error."""
    # Mock the dependencies
    mocker.patch("app.endpoints.feedback.assert_feedback_enabled", return_value=None)
    mocker.patch("utils.common.retrieve_user_id", return_value="test_user_id")
    mocker.patch(
        "app.endpoints.feedback.store_feedback",
        side_effect=Exception("Error storing feedback"),
    )

    # Mock the feedback request
    feedback_request = mocker.Mock()

    # Call the endpoint handler and assert it raises an exception
    with pytest.raises(HTTPException) as exc_info:
        feedback_endpoint_handler(
            _request=mocker.Mock(),
            feedback_request=feedback_request,
            _ensure_feedback_enabled=assert_feedback_enabled,
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail["response"] == "Error storing user feedback"


def test_store_feedback(mocker):
    """Test that store_feedback calls the correct storage function."""
    configuration.user_data_collection_configuration.feedback_storage = "fake-path"

    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("app.endpoints.feedback.Path", return_value=mocker.MagicMock())
    mocker.patch("app.endpoints.feedback.get_suid", return_value="fake-uuid")

    # Mock the JSON to assert the data is stored correctly
    mock_json = mocker.patch("app.endpoints.feedback.json")

    user_id = "test_user_id"
    feedback_request = {
        "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
        "user_question": "What is OpenStack?",
        "llm_response": "OpenStack is a cloud computing platform.",
        "user_feedback": "Great service!",
        "sentiment": 1,
    }

    store_feedback(user_id, feedback_request)
    mock_json.dump.assert_called_once_with(
        {
            "user_id": user_id,
            "timestamp": mocker.ANY,
            **feedback_request,
        },
        mocker.ANY,
    )


def test_feedback_status():
    """Test that feedback_status returns the correct status response."""
    configuration.user_data_collection_configuration.feedback_enabled = True

    response = feedback_status()
    assert response.functionality == "feedback"
    assert response.status == {"enabled": True}
