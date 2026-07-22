"""Unit tests for utils/shields.py functions."""

import pytest
from fastapi import HTTPException, status
from pytest_mock import MockerFixture

from models.config import ShieldConfiguration
from pydantic_ai_lightspeed.capabilities.question_validity.core import (
    QuestionValidityResult,
)
from utils.shields import (
    append_turn_to_conversation,
    get_available_shields,
    get_shields_for_request,
    run_input_shields,
    validate_shield_ids_override,
)


def _config_with_shields(
    mocker: MockerFixture, shields: list[ShieldConfiguration]
) -> object:
    """Build a mock AppConfig exposing the given shields list."""
    mock_config = mocker.Mock()
    mock_config.shields = shields
    mock_config.customization = None
    return mock_config


def _sample_shields() -> list[ShieldConfiguration]:
    """Return the two supported shield configurations for tests."""
    return [
        ShieldConfiguration(
            shield_id="lightspeed_question_validity",
            provider_id="lightspeed_question_validity",
            provider_shield_id="model-1",
        ),
        ShieldConfiguration(
            shield_id="lightspeed_pii_redaction",
            provider_id="lightspeed_pii_redaction",
            provider_shield_id="lightspeed_pii_redaction",
            params={"rules": [{"pattern": r"x", "replacement": "y"}]},
        ),
    ]


class TestGetAvailableShields:
    """Tests for get_available_shields function."""

    @pytest.mark.asyncio
    async def test_returns_shield_identifiers(self, mocker: MockerFixture) -> None:
        """Return shield_id values from LCORE configuration."""
        mock_config = _config_with_shields(mocker, _sample_shields())

        result = await get_available_shields(mock_config)

        assert result == [
            "lightspeed_question_validity",
            "lightspeed_pii_redaction",
        ]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_shields(
        self, mocker: MockerFixture
    ) -> None:
        """Return an empty list when no shields are configured."""
        mock_config = _config_with_shields(mocker, [])

        result = await get_available_shields(mock_config)

        assert result == []


class TestAppendTurnToConversation:  # pylint: disable=too-few-public-methods
    """Tests for append_turn_to_conversation function."""

    @pytest.mark.asyncio
    async def test_appends_user_and_assistant_messages(
        self, mocker: MockerFixture
    ) -> None:
        """Create conversation items for a blocked turn."""
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
        """Allow shield_ids when override is not disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = None

        validate_shield_ids_override(["shield-1"], mock_config)

    def test_allows_shield_ids_when_customization_exists_but_override_not_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Allow shield_ids when customization exists but override is enabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = False

        validate_shield_ids_override(["shield-1"], mock_config)

    def test_allows_none_shield_ids_when_override_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Allow None shield_ids even when override is disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = True

        validate_shield_ids_override(None, mock_config)

    def test_raises_422_when_shield_ids_provided_and_override_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Raise 422 when shield_ids is provided but override is disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = True

        with pytest.raises(HTTPException) as exc_info:
            validate_shield_ids_override(["shield-1"], mock_config)

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = exc_info.value.detail
        assert isinstance(detail, dict)
        assert "Shield IDs customization is disabled" in detail["response"]
        assert "disable_shield_ids_override" in detail["cause"]

    def test_raises_422_when_empty_list_shield_ids_and_override_disabled(
        self, mocker: MockerFixture
    ) -> None:
        """Raise 422 when shield_ids=[] and override is disabled."""
        mock_config = mocker.Mock()
        mock_config.customization = mocker.Mock()
        mock_config.customization.disable_shield_ids_override = True

        with pytest.raises(HTTPException) as exc_info:
            validate_shield_ids_override([], mock_config)

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestGetShieldsForRequest:
    """Tests for get_shields_for_request function."""

    def test_returns_all_shields_when_shield_ids_none(self) -> None:
        """Return all shields when shield_ids is None."""
        shields = _sample_shields()

        result = get_shields_for_request(shields, shield_ids=None)

        assert result == shields

    def test_returns_empty_list_when_no_shields_configured(self) -> None:
        """Return an empty list when no shields are provided."""
        result = get_shields_for_request([], shield_ids=None)

        assert result == []

    def test_returns_empty_list_when_shield_ids_empty(self) -> None:
        """Skip all shields when an empty shield_ids list is provided."""
        result = get_shields_for_request(_sample_shields(), shield_ids=[])

        assert result == []

    def test_filters_to_requested_shields_when_all_exist(self) -> None:
        """Return only requested shields when all exist."""
        shields = _sample_shields()

        result = get_shields_for_request(
            shields,
            shield_ids=["lightspeed_question_validity"],
        )

        assert [shield.shield_id for shield in result] == [
            "lightspeed_question_validity"
        ]

    def test_raises_404_when_requested_shield_not_configured(self) -> None:
        """Raise 404 when a requested shield is not configured."""
        with pytest.raises(HTTPException) as exc_info:
            get_shields_for_request(
                _sample_shields()[:1],
                shield_ids=["lightspeed_question_validity", "missing-shield"],
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Shield" in exc_info.value.detail["response"]  # type: ignore[index]
        assert "missing-shield" in exc_info.value.detail["cause"]  # type: ignore[index]

    def test_raises_404_when_multiple_requested_shields_not_configured(self) -> None:
        """Raise 404 with all missing ids when multiple shields are missing."""
        with pytest.raises(HTTPException) as exc_info:
            get_shields_for_request([], shield_ids=["missing-1", "missing-2"])

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Shields" in exc_info.value.detail["response"]  # type: ignore[index]
        cause = exc_info.value.detail["cause"]  # type: ignore[index]
        assert "missing-1" in cause
        assert "missing-2" in cause


class TestRunInputShields:
    """Tests for run_input_shields input-only pipeline."""

    @pytest.mark.asyncio
    async def test_returns_passed_when_no_shields(self, mocker: MockerFixture) -> None:
        """Return passed moderation when the shield list is empty."""
        result = await run_input_shields("hello", [], client=mocker.Mock())

        assert result.blocked is False
        assert result.text == "hello"
        assert result.moderation.decision == "passed"

    @pytest.mark.asyncio
    async def test_redacts_pii_from_input(self, mocker: MockerFixture) -> None:
        """Apply PII redaction shields to the input text."""
        shields = [
            ShieldConfiguration(
                shield_id="lightspeed_pii_redaction",
                provider_id="lightspeed_pii_redaction",
                provider_shield_id="lightspeed_pii_redaction",
                params={"rules": [{"pattern": r"secret", "replacement": "[REDACTED]"}]},
            )
        ]

        result = await run_input_shields(
            "my secret value", shields, client=mocker.Mock()
        )

        assert result.blocked is False
        assert result.text == "my [REDACTED] value"
        assert result.moderation.decision == "passed"

    @pytest.mark.asyncio
    async def test_blocks_with_moderation_compat_id(
        self, mocker: MockerFixture
    ) -> None:
        """Block with a synthetic modr_* id when question validity rejects."""
        shields = [
            ShieldConfiguration(
                shield_id="lightspeed_question_validity",
                provider_id="lightspeed_question_validity",
                provider_shield_id="model-1",
                params={"invalid_question_response": "Not allowed"},
            )
        ]
        mocker.patch(
            "utils.shields.check_question_validity",
            new=mocker.AsyncMock(
                return_value=QuestionValidityResult(
                    allowed=False, classifier_text="REJECTED"
                )
            ),
        )
        mocker.patch("utils.shields.get_suid", return_value="abc123")

        result = await run_input_shields("off topic", shields, client=mocker.Mock())

        assert result.blocked is True
        assert result.moderation.decision == "blocked"
        assert result.moderation.message == "Not allowed"  # type: ignore[union-attr]
        assert result.moderation.moderation_id == "modr_abc123"  # type: ignore[union-attr]
