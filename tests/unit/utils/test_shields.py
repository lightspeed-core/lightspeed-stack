"""Unit tests for utils/shields.py functions."""

import pytest
from fastapi import HTTPException, status
from pytest_mock import MockerFixture

from models.config import QuestionValidityConfig, QuestionValidityShieldConfiguration
from utils.shields import (
    append_turn_to_conversation,
    get_shields_for_request,
    validate_shield_ids_override,
)


def _shield(name: str) -> QuestionValidityShieldConfiguration:
    """Build a minimal question-validity shield configuration for tests."""
    return QuestionValidityShieldConfiguration(
        name=name,
        type="question_validity",
        config=QuestionValidityConfig(model_id="test-model"),
    )


class TestAppendTurnToConversation:  # pylint: disable=too-few-public-methods
    """Tests for append_turn_to_conversation function."""

    @pytest.mark.asyncio
    async def test_appends_user_and_assistant_messages(
        self, mocker: MockerFixture
    ) -> None:
        """Test that append_turn_to_conversation creates conversation items correctly."""
        mock_client = mocker.Mock()
        mock_client.conversations.items.create = mocker.AsyncMock(return_value=None)

        await append_turn_to_conversation(
            mock_client,
            conversation_id="conv-123",
            user_message="Hello",
            assistant_message="I cannot help with that",
        )

        mock_client.conversations.items.create.assert_called_once_with(
            "conv-123",
            items=[
                {"type": "message", "role": "user", "content": "Hello"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "I cannot help with that",
                },
            ],
        )


class TestValidateShieldIdsOverride:
    """Tests for validate_shield_ids_override function."""

    def test_allows_shield_ids_when_override_enabled(
        self, mocker: MockerFixture
    ) -> None:
        """Test that shield_ids is allowed when override is not disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = None

        query_request = mocker.Mock()
        query_request.shield_ids = ["shield-1"]

        # Should not raise exception
        validate_shield_ids_override(query_request, mock_config)

    def test_allows_shield_ids_when_customization_exists_but_override_not_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Test shield_ids allowed when customization exists but override not disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = False

        query_request = mocker.Mock()
        query_request.shield_ids = ["shield-1"]

        # Should not raise exception
        validate_shield_ids_override(query_request, mock_config)

    def test_allows_none_shield_ids_when_override_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Test that None shield_ids is allowed even when override is disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = True

        query_request = mocker.Mock()
        query_request.shield_ids = None

        # Should not raise exception
        validate_shield_ids_override(query_request, mock_config)

    def test_raises_422_when_shield_ids_provided_and_override_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Test HTTPException 422 raised when shield_ids provided but override disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = True

        query_request = mocker.Mock()
        query_request.shield_ids = ["shield-1"]

        with pytest.raises(HTTPException) as exc_info:
            validate_shield_ids_override(query_request, mock_config)

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Shield IDs customization is disabled" in detail["response"]
        assert "disable_shield_ids_override" in detail["cause"]

    def test_raises_422_when_empty_list_shield_ids_and_override_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Test that HTTPException 422 is raised when shield_ids=[] and override disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = True

        query_request = mocker.Mock()
        query_request.shield_ids = []

        with pytest.raises(HTTPException) as exc_info:
            validate_shield_ids_override(query_request, mock_config)

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestGetShieldsForRequest:
    """Tests for get_shields_for_request function."""

    def test_returns_all_shields_when_shield_ids_none(self) -> None:
        """Return all configured shields when shield_ids is None."""
        shields = [_shield("shield-1"), _shield("shield-2")]

        result = get_shields_for_request(shields, shield_ids=None)

        assert result == shields

    def test_returns_empty_list_when_shield_ids_empty(self) -> None:
        """Return no shields when an empty shield_ids list is provided."""
        shields = [_shield("shield-1"), _shield("shield-2")]

        result = get_shields_for_request(shields, shield_ids=[])

        assert result == []

    def test_filters_to_requested_shields_when_all_exist(self) -> None:
        """Return only shields whose names appear in shield_ids."""
        shield1 = _shield("shield-1")
        shield2 = _shield("shield-2")
        shield3 = _shield("shield-3")

        result = get_shields_for_request(
            [shield1, shield2, shield3], shield_ids=["shield-1", "shield-3"]
        )

        assert result == [shield1, shield3]

    def test_raises_404_when_requested_shield_not_configured(self) -> None:
        """Raise 404 when a requested shield name is not configured."""
        with pytest.raises(HTTPException) as exc_info:
            get_shields_for_request(
                [_shield("shield-1")], shield_ids=["shield-1", "missing-shield"]
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Shield" in detail["response"]
        assert "missing-shield" in detail["cause"]

    def test_raises_404_when_multiple_requested_shields_not_configured(self) -> None:
        """Raise 404 listing all missing shield names."""
        with pytest.raises(HTTPException) as exc_info:
            get_shields_for_request([], shield_ids=["missing-1", "missing-2"])

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Shields" in detail["response"]
        assert "missing-1" in detail["cause"]
        assert "missing-2" in detail["cause"]
