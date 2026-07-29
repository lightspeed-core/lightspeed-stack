"""Unit tests for utils/shields.py functions."""

import pytest
from fastapi import HTTPException, status
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pytest_mock import MockerFixture

from models.common.moderation import ShieldModerationBlocked, ShieldModerationPassed
from models.config import (
    QuestionValidityConfig,
    QuestionValidityShieldConfiguration,
    ShieldConfiguration,
)
from utils.shields import (
    append_turn_to_conversation,
    get_shields_for_request,
    run_shield_moderation_v2,
    validate_shield_ids_override,
)


def _shield_config(name: str) -> QuestionValidityShieldConfiguration:
    """Build a minimal question-validity shield configuration for tests."""
    return QuestionValidityShieldConfiguration(
        name=name,
        provider_id="question_validity",
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


class TestRunShieldModerationV2:
    """Tests for run_shield_moderation_v2 function."""

    @pytest.mark.asyncio
    async def test_returns_passed_when_no_shields(self) -> None:
        """Return ShieldModerationPassed when shield list is empty."""
        result = await run_shield_moderation_v2("test input", [])
        assert isinstance(result, ShieldModerationPassed)

    @pytest.mark.asyncio
    async def test_returns_passed_when_all_shields_pass(
        self, mocker: MockerFixture
    ) -> None:
        """Return ShieldModerationPassed when every shield passes."""
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(return_value=ShieldModerationPassed())
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        shields: list[ShieldConfiguration] = [
            _shield_config("s1"),
            _shield_config("s2"),
        ]
        result = await run_shield_moderation_v2("test input", shields)

        assert isinstance(result, ShieldModerationPassed)
        assert mock_shield.run.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_blocked_on_first_block(self, mocker: MockerFixture) -> None:
        """Return blocked result from first shield that blocks."""
        blocked = ShieldModerationBlocked(message="rejected", moderation_id="modr-123")
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(return_value=blocked)
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        shields: list[ShieldConfiguration] = [
            _shield_config("s1"),
            _shield_config("s2"),
        ]
        result = await run_shield_moderation_v2("test input", shields)

        assert isinstance(result, ShieldModerationBlocked)
        assert result.message == "rejected"
        mock_shield.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_filters_by_selected_shield_ids(self, mocker: MockerFixture) -> None:
        """Only run shields matching the selected IDs."""
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(return_value=ShieldModerationPassed())
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        shields: list[ShieldConfiguration] = [
            _shield_config("s1"),
            _shield_config("s2"),
            _shield_config("s3"),
        ]
        result = await run_shield_moderation_v2(
            "test input", shields, selected_shield_ids=["s2"]
        )

        assert isinstance(result, ShieldModerationPassed)
        mock_shield.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_shields_stops_on_first_block(self, mocker: MockerFixture) -> None:
        """Stop at the first blocking shield."""
        blocked = ShieldModerationBlocked(message="rejected", moderation_id="modr-789")
        mock_qv_shield = mocker.Mock()
        mock_qv_shield.run = mocker.AsyncMock(return_value=blocked)

        mock_redact_shield = mocker.Mock()
        mock_redact_shield.run = mocker.AsyncMock(return_value=ShieldModerationPassed())

        mocker.patch(
            "utils.shields.build_shield",
            side_effect=[mock_qv_shield, mock_redact_shield],
        )

        shields: list[ShieldConfiguration] = [
            _shield_config("s-1"),
            _shield_config("s-2"),
        ]
        result = await run_shield_moderation_v2("test input", shields)

        assert isinstance(result, ShieldModerationBlocked)
        mock_qv_shield.run.assert_called_once()
        mock_redact_shield.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_raise_503_on_model_api_error(self, mocker: MockerFixture) -> None:
        """Raise HTTP 503 when a shield raises ModelAPIError."""
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(
            side_effect=ModelAPIError("test", "Incompatible mode")
        )
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        with pytest.raises(HTTPException) as exc_info:
            await run_shield_moderation_v2("test input", [_shield_config("s1")])

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "OGX" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_raise_429_when_exceeds_quota(self, mocker: MockerFixture) -> None:
        """Raise HTTP 429 when a shield raises ModelHTTPError with status 429."""
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(
            side_effect=ModelHTTPError(429, "openai/gpt-4o-mini", "Quota exceeded")
        )
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        with pytest.raises(HTTPException) as exc_info:
            await run_shield_moderation_v2("test input", [_shield_config("s1")])

        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "test-model" in str(exc_info.value.detail)
        assert "The model quota has been exceeded" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_raise_413_when_exceeds_context_length(
        self, mocker: MockerFixture
    ) -> None:
        """Raise HTTP 413 when a shield raises ModelHTTPError due to context length exceeded."""
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(
            side_effect=ModelHTTPError(
                413, "openai/gpt-4o-mini", "Context length exceeded"
            )
        )
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        with pytest.raises(HTTPException) as exc_info:
            await run_shield_moderation_v2("test input", [_shield_config("s1")])

        assert exc_info.value.status_code == status.HTTP_413_CONTENT_TOO_LARGE
        assert "test-model" in str(exc_info.value.detail)
        assert "Prompt is too long" in str(exc_info.value.detail)


class TestGetShieldsForRequest:
    """Tests for get_shields_for_request function."""

    def test_returns_all_shields_when_shield_ids_none(self) -> None:
        """Return all configured shields when shield_ids is None."""
        shields = [
            _shield_config("shield-1"),
            _shield_config("shield-2"),
        ]

        result = get_shields_for_request(shields, shield_ids=None)

        assert result == shields

    def test_returns_empty_list_when_shield_ids_empty(self) -> None:
        """Return no shields when an empty shield_ids list is provided."""
        shields = [
            _shield_config("shield-1"),
            _shield_config("shield-2"),
        ]

        result = get_shields_for_request(shields, shield_ids=[])

        assert result == []

    def test_filters_to_requested_shields_when_all_exist(self) -> None:
        """Return only shields whose names appear in shield_ids."""
        shield1 = _shield_config("shield-1")
        shield2 = _shield_config("shield-2")
        shield3 = _shield_config("shield-3")

        result = get_shields_for_request(
            [shield1, shield2, shield3], shield_ids=["shield-1", "shield-3"]
        )

        assert result == [shield1, shield3]

    def test_raises_404_when_requested_shield_not_configured(self) -> None:
        """Raise 404 when a requested shield name is not configured."""
        with pytest.raises(HTTPException) as exc_info:
            get_shields_for_request(
                [_shield_config("shield-1")],
                shield_ids=["shield-1", "missing-shield"],
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
