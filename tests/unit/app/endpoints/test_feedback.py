# pylint: disable=protected-access

"""Unit tests for the /feedback REST API endpoint."""

from typing import Any

import pytest
from fastapi import HTTPException, status
from pytest_mock import MockerFixture

from app.endpoints.feedback import (
    assert_feedback_enabled,
    feedback_endpoint_handler,
    feedback_status,
    is_feedback_enabled,
    store_feedback,
    update_feedback_status,
)
from authentication.interface import AuthTuple
from configuration import AppConfig, configuration
from models.config import UserDataCollection
from models.requests import FeedbackRequest, FeedbackStatusUpdateRequest
from tests.unit.utils.auth_helpers import mock_authorization_resolvers

MOCK_AUTH = ("mock_user_id", "mock_username", False, "mock_token")
VALID_BASE = {
    "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
    "user_question": "What is Kubernetes?",
    "llm_response": "Kubernetes is an open-source container orchestration system.",
}


def test_is_feedback_enabled(mocker: MockerFixture) -> None:
    """Test that is_feedback_enabled returns True when feedback is not disabled."""
    mock_config = AppConfig()
    mock_config._configuration = mocker.Mock()
    mock_config._configuration.user_data_collection = UserDataCollection(
        feedback_enabled=True,
        feedback_storage="/tmp",
        transcripts_enabled=False,
        transcripts_storage=None,
    )
    mocker.patch("app.endpoints.feedback.configuration", mock_config)
    assert is_feedback_enabled() is True, "Feedback should be enabled"


def test_is_feedback_disabled(mocker: MockerFixture) -> None:
    """Test that is_feedback_enabled returns False when feedback is disabled."""
    mock_config = AppConfig()
    mock_config._configuration = mocker.Mock()
    mock_config._configuration.user_data_collection = UserDataCollection(
        feedback_enabled=False,
        feedback_storage=None,
        transcripts_enabled=False,
        transcripts_storage=None,
    )
    mocker.patch("app.endpoints.feedback.configuration", mock_config)
    assert is_feedback_enabled() is False, "Feedback should be disabled"


async def test_assert_feedback_enabled_disabled(mocker: MockerFixture) -> None:
    """Test that assert_feedback_enabled raises HTTPException when feedback is disabled."""

    # Simulate feedback being disabled
    mocker.patch("app.endpoints.feedback.is_feedback_enabled", return_value=False)

    with pytest.raises(HTTPException) as exc_info:
        await assert_feedback_enabled(mocker.Mock())

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail["response"] == "Storing feedback is disabled"  # type: ignore
    assert exc_info.value.detail["cause"] == "Storing feedback is disabled."  # type: ignore


async def test_assert_feedback_enabled(mocker: MockerFixture) -> None:
    """Test that assert_feedback_enabled does not raise an exception when feedback is enabled."""

    # Simulate feedback being enabled
    mocker.patch("app.endpoints.feedback.is_feedback_enabled", return_value=True)

    # Should not raise an exception
    await assert_feedback_enabled(mocker.Mock())


@pytest.mark.parametrize(
    "feedback_request_data",
    [
        {},
        {
            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
            "user_question": "What is Kubernetes?",
            "llm_response": "It's some computer thing.",
            "sentiment": -1,
            "categories": ["incorrect", "incomplete"],
        },
    ],
    ids=["no_categories", "with_negative_categories"],
)
@pytest.mark.asyncio
async def test_feedback_endpoint_handler(
    mocker: MockerFixture, feedback_request_data: dict[str, Any]
) -> None:
    """Test that feedback_endpoint_handler processes feedback for different payloads."""

    mock_authorization_resolvers(mocker)

    # Mock the dependencies
    mocker.patch("app.endpoints.feedback.assert_feedback_enabled", return_value=None)
    mocker.patch("app.endpoints.feedback.store_feedback", return_value=None)

    # Mock retrieve_conversation to return a conversation owned by test_user_id
    mock_conversation = mocker.Mock()
    mock_conversation.user_id = "test_user_id"
    mocker.patch(
        "app.endpoints.feedback.retrieve_conversation", return_value=mock_conversation
    )

    # Prepare the feedback request mock
    feedback_request = mocker.Mock()
    feedback_request.model_dump.return_value = feedback_request_data
    feedback_request.conversation_id = "12345678-abcd-0000-0123-456789abcdef"

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    # Call the endpoint handler
    result = await feedback_endpoint_handler(
        feedback_request=feedback_request,
        _ensure_feedback_enabled=assert_feedback_enabled,
        auth=auth,
    )

    # Assert that the expected response is returned
    assert result.response == "feedback received"


@pytest.mark.asyncio
async def test_feedback_endpoint_handler_error(mocker: MockerFixture) -> None:
    """Test feedback_endpoint_handler raises HTTPException when store_feedback raises OSError."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.feedback.assert_feedback_enabled", return_value=None)
    mocker.patch("app.endpoints.feedback.check_configuration_loaded", return_value=None)

    # Mock retrieve_conversation to return a conversation owned by test_user_id
    mock_conversation = mocker.Mock()
    mock_conversation.user_id = "test_user_id"
    mocker.patch(
        "app.endpoints.feedback.retrieve_conversation", return_value=mock_conversation
    )

    # Mock Path.mkdir to raise OSError so the try block in store_feedback catches it
    mocker.patch(
        "app.endpoints.feedback.Path.mkdir", side_effect=OSError("Permission denied")
    )
    feedback_request = FeedbackRequest(
        conversation_id="123e4567-e89b-12d3-a456-426614174000",
        user_question="test question",
        llm_response="test response",
        user_feedback="test feedback",
        sentiment=1,
    )

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as exc_info:
        await feedback_endpoint_handler(
            feedback_request=feedback_request,
            _ensure_feedback_enabled=assert_feedback_enabled,
            auth=auth,
        )
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Failed to store feedback"  # type: ignore
    assert "Failed to store feedback at directory" in detail["cause"]  # type: ignore


@pytest.mark.parametrize(
    "feedback_request_data",
    [
        {
            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
            "user_question": "What is OpenStack?",
            "llm_response": "It's some cloud thing.",
            "user_feedback": "This response is not helpful!",
            "sentiment": -1,
        },
        {
            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
            "user_question": "What is Kubernetes?",
            "llm_response": "K8s.",
            "sentiment": -1,
            "categories": ["incorrect", "not_relevant", "incomplete"],
        },
    ],
    ids=["negative_text_feedback", "negative_feedback_with_categories"],
)
def test_store_feedback(
    mocker: MockerFixture, feedback_request_data: dict[str, Any]
) -> None:
    """Test that store_feedback correctly stores various feedback payloads."""

    configuration.user_data_collection_configuration.feedback_storage = "fake-path"

    # Patch filesystem and helpers
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("app.endpoints.feedback.Path", return_value=mocker.MagicMock())
    mocker.patch("app.endpoints.feedback.get_suid", return_value="fake-uuid")

    # Patch json to inspect stored data
    mock_json = mocker.patch("app.endpoints.feedback.json")

    user_id = "test_user_id"

    store_feedback(user_id, feedback_request_data)

    expected_data = {
        "user_id": user_id,
        "timestamp": mocker.ANY,
        **feedback_request_data,
    }

    mock_json.dump.assert_called_once_with(expected_data, mocker.ANY)


@pytest.mark.parametrize(
    "feedback_request_data",
    [
        {
            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
            "user_question": "What is OpenStack?",
            "llm_response": "It's some cloud thing.",
            "user_feedback": "This response is not helpful!",
            "sentiment": -1,
        },
        {
            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
            "user_question": "What is Kubernetes?",
            "llm_response": "K8s.",
            "sentiment": -1,
            "categories": ["incorrect", "not_relevant", "incomplete"],
        },
    ],
    ids=["negative_text_feedback", "negative_feedback_with_categories"],
)
def test_store_feedback_on_io_error(
    mocker: MockerFixture, feedback_request_data: dict[str, Any]
) -> None:
    """Test the OSError and IOError handlings during feedback storage."""

    # non-writable path
    # avoid touching the real filesystem; simulate a permission error on open
    configuration.user_data_collection_configuration.feedback_storage = "fake-path"
    mocker.patch("app.endpoints.feedback.Path", return_value=mocker.MagicMock())
    mocker.patch("builtins.open", side_effect=PermissionError("EACCES"))

    user_id = "test_user_id"

    with pytest.raises(HTTPException) as exc_info:
        store_feedback(user_id, feedback_request_data)
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Failed to store feedback"  # type: ignore
    assert "Failed to store feedback at directory" in detail["cause"]  # type: ignore


async def test_update_feedback_status_different(mocker: MockerFixture) -> None:
    """Test that update_feedback_status returns the correct status with an update."""
    configuration.user_data_collection_configuration.feedback_enabled = True

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    req = FeedbackStatusUpdateRequest(status=False)
    resp = await update_feedback_status(
        req,
        auth=auth,
    )
    assert resp.status == {
        "previous_status": True,
        "updated_status": False,
        "updated_by": "test_user_id",
        "timestamp": mocker.ANY,
    }


async def test_update_feedback_status_no_change(mocker: MockerFixture) -> None:
    """Test that update_feedback_status returns the correct status with no update."""
    configuration.user_data_collection_configuration.feedback_enabled = True

    # Authorization tuple required by URL endpoint handler
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    req = FeedbackStatusUpdateRequest(status=True)
    resp = await update_feedback_status(
        req,
        auth=auth,
    )
    assert resp.status == {
        "previous_status": True,
        "updated_status": True,
        "updated_by": "test_user_id",
        "timestamp": mocker.ANY,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"sentiment": -1},
        {"user_feedback": "Good answer"},
        {"categories": ["incorrect"]},
    ],
    ids=["test_sentiment_only", "test_user_feedback_only", "test_categories_only"],
)
@pytest.mark.asyncio
async def test_feedback_endpoint_valid_requests(
    mocker: MockerFixture, payload: dict[str, Any]
) -> None:
    """Test endpoint with valid feedback payloads."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.feedback.store_feedback")

    # Mock retrieve_conversation to return a conversation owned by mock_user_id
    mock_conversation = mocker.Mock()
    mock_conversation.user_id = "mock_user_id"
    mocker.patch(
        "app.endpoints.feedback.retrieve_conversation", return_value=mock_conversation
    )

    request = FeedbackRequest(**{**VALID_BASE, **payload})
    response = await feedback_endpoint_handler(
        feedback_request=request,
        auth=MOCK_AUTH,
        _ensure_feedback_enabled=None,
    )
    assert response.response == "feedback received"


def test_feedback_status_enabled(mocker: MockerFixture) -> None:
    """Test that feedback_status returns enabled status when feedback is enabled."""
    mock_config = AppConfig()
    mock_config._configuration = mocker.Mock()
    mock_config._configuration.user_data_collection = UserDataCollection(
        feedback_enabled=True,
        feedback_storage="/tmp",
        transcripts_enabled=False,
        transcripts_storage=None,
    )
    mocker.patch("app.endpoints.feedback.configuration", mock_config)

    response = feedback_status()

    assert response.functionality == "feedback"
    assert response.status == {"enabled": True}


def test_feedback_status_disabled(mocker: MockerFixture) -> None:
    """Test that feedback_status returns disabled status when feedback is disabled."""
    mock_config = AppConfig()
    mock_config._configuration = mocker.Mock()
    mock_config._configuration.user_data_collection = UserDataCollection(
        feedback_enabled=False,
        feedback_storage=None,
        transcripts_enabled=False,
        transcripts_storage=None,
    )
    mocker.patch("app.endpoints.feedback.configuration", mock_config)

    response = feedback_status()

    assert response.functionality == "feedback"
    assert response.status == {"enabled": False}


@pytest.mark.asyncio
async def test_feedback_endpoint_handler_conversation_not_found(
    mocker: MockerFixture,
) -> None:
    """Test that feedback_endpoint_handler returns 404 when conversation doesn't exist."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.feedback.assert_feedback_enabled", return_value=None)
    mocker.patch("app.endpoints.feedback.retrieve_conversation", return_value=None)

    feedback_request = FeedbackRequest(**{**VALID_BASE, "sentiment": 1})
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as exc_info:
        await feedback_endpoint_handler(
            feedback_request=feedback_request,
            _ensure_feedback_enabled=assert_feedback_enabled,
            auth=auth,
        )
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["response"] == "Conversation not found"  # type: ignore[index]


@pytest.mark.asyncio
async def test_feedback_endpoint_handler_conversation_wrong_owner(
    mocker: MockerFixture,
) -> None:
    """Test feedback_endpoint_handler returns 403 for conversation owned by different user."""
    mock_authorization_resolvers(mocker)
    mocker.patch("app.endpoints.feedback.assert_feedback_enabled", return_value=None)

    # Mock retrieve_conversation to return a conversation owned by a different user
    mock_conversation = mocker.Mock()
    mock_conversation.user_id = "different_user_id"
    mocker.patch(
        "app.endpoints.feedback.retrieve_conversation", return_value=mock_conversation
    )

    feedback_request = FeedbackRequest(**{**VALID_BASE, "sentiment": 1})
    auth: AuthTuple = ("test_user_id", "test_user", True, "test_token")

    with pytest.raises(HTTPException) as exc_info:
        await feedback_endpoint_handler(
            feedback_request=feedback_request,
            _ensure_feedback_enabled=assert_feedback_enabled,
            auth=auth,
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert "does not have permission" in detail["response"]  # type: ignore[index]
