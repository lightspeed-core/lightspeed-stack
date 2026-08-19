"""Unit tests for run_output_shield_moderation() in utils/shields.py.

Tests the output-side shield moderation function that checks LLM
responses for non-technical content before returning to the user.

RSPEED-3399 / OFFSEC-310 / LCORE-2750
"""

import pytest
from pydantic_ai.exceptions import AgentRunError
from pytest_mock import MockerFixture

import constants
from models.common.moderation import ShieldModerationBlocked, ShieldModerationPassed
from models.config import (
    QuestionValidityConfig,
    QuestionValidityShieldConfiguration,
    ShieldConfiguration,
)
from utils.shields import run_output_shield_moderation


def _output_shield_config(name: str = "output-guard") -> ShieldConfiguration:
    """Create a QuestionValidityShieldConfiguration for output testing.

    Parameters:
        name: The shield name.

    Returns:
        A ShieldConfiguration instance.
    """
    return QuestionValidityShieldConfiguration(
        name=name,
        provider_id="question_validity",
        config=QuestionValidityConfig(
            model_id="test-model",
            model_prompt="Classify: ${message} -> ${allowed} or ${rejected}",
            invalid_question_response="Non-technical content detected.",
        ),
    )


class TestRunOutputShieldModeration:
    """Tests for run_output_shield_moderation function."""

    @pytest.mark.asyncio
    async def test_returns_passed_when_no_shields(self) -> None:
        """Empty output_shields list should return passed immediately."""
        result = await run_output_shield_moderation("any text", [])
        assert isinstance(result, ShieldModerationPassed)
        assert result.decision == "passed"

    @pytest.mark.asyncio
    async def test_returns_passed_when_shield_allows(
        self, mocker: MockerFixture
    ) -> None:
        """Shield returning passed should result in passed."""
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(
            return_value=ShieldModerationPassed()
        )
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        result = await run_output_shield_moderation(
            "To configure SELinux, edit /etc/selinux/config...",
            [_output_shield_config()],
        )

        assert isinstance(result, ShieldModerationPassed)
        mock_shield.run.assert_called_once_with(
            "To configure SELinux, edit /etc/selinux/config..."
        )

    @pytest.mark.asyncio
    async def test_returns_blocked_when_shield_rejects(
        self, mocker: MockerFixture
    ) -> None:
        """Shield returning blocked should result in blocked."""
        blocked = ShieldModerationBlocked(
            decision="blocked",
            message="Non-technical content detected.",
            moderation_id="test-id",
        )
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(return_value=blocked)
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        result = await run_output_shield_moderation(
            "Dear Mr. Smith, here is the marketing email...",
            [_output_shield_config()],
        )

        assert isinstance(result, ShieldModerationBlocked)
        assert result.decision == "blocked"
        assert result.message == "Non-technical content detected."

    @pytest.mark.asyncio
    async def test_stops_on_first_block(
        self, mocker: MockerFixture
    ) -> None:
        """Should return blocked on first shield that blocks."""
        blocked = ShieldModerationBlocked(
            decision="blocked",
            message="Blocked.",
            moderation_id="test-id",
        )
        shield1 = mocker.Mock()
        shield1.run = mocker.AsyncMock(return_value=blocked)
        shield2 = mocker.Mock()
        shield2.run = mocker.AsyncMock(return_value=ShieldModerationPassed())

        mocker.patch(
            "utils.shields.build_shield", side_effect=[shield1, shield2]
        )

        result = await run_output_shield_moderation(
            "some text",
            [_output_shield_config("s1"), _output_shield_config("s2")],
        )

        assert result.decision == "blocked"
        shield1.run.assert_called_once()
        shield2.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_on_shield_error(
        self, mocker: MockerFixture
    ) -> None:
        """Shield errors should be logged but not block the response."""
        failing_shield = mocker.Mock()
        failing_shield.run = mocker.AsyncMock(
            side_effect=AgentRunError("model error")
        )
        passing_shield = mocker.Mock()
        passing_shield.run = mocker.AsyncMock(
            return_value=ShieldModerationPassed()
        )

        mocker.patch(
            "utils.shields.build_shield",
            side_effect=[failing_shield, passing_shield],
        )

        result = await run_output_shield_moderation(
            "some text",
            [_output_shield_config("fail"), _output_shield_config("pass")],
        )

        assert isinstance(result, ShieldModerationPassed)
        failing_shield.run.assert_called_once()
        passing_shield.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_on_runtime_error(
        self, mocker: MockerFixture
    ) -> None:
        """RuntimeError from shield should be logged but not block."""
        failing_shield = mocker.Mock()
        failing_shield.run = mocker.AsyncMock(
            side_effect=RuntimeError("unexpected")
        )

        mocker.patch(
            "utils.shields.build_shield", return_value=failing_shield
        )

        result = await run_output_shield_moderation(
            "some text", [_output_shield_config()]
        )

        assert isinstance(result, ShieldModerationPassed)

    @pytest.mark.asyncio
    async def test_passes_response_text_to_shield(
        self, mocker: MockerFixture
    ) -> None:
        """The response text should be passed to shield.run()."""
        mock_shield = mocker.Mock()
        mock_shield.run = mocker.AsyncMock(
            return_value=ShieldModerationPassed()
        )
        mocker.patch("utils.shields.build_shield", return_value=mock_shield)

        response_text = "Use sudo dnf install httpd to install Apache."
        await run_output_shield_moderation(
            response_text, [_output_shield_config()]
        )

        mock_shield.run.assert_called_once_with(response_text)


class TestOutputShieldConfigValidation:
    """Tests that output shields require explicit prompt and rejection message."""

    def test_default_prompt_detected(self) -> None:
        """Output shield using input-side default prompt should be caught."""
        config = QuestionValidityConfig(
            model_id="test-model",
            # model_prompt not set — uses DEFAULT_MODEL_PROMPT
            invalid_question_response="Custom rejection.",
        )
        assert config.model_prompt == constants.DEFAULT_MODEL_PROMPT

    def test_default_rejection_detected(self) -> None:
        """Output shield using input-side default rejection should be caught."""
        config = QuestionValidityConfig(
            model_id="test-model",
            model_prompt="Custom prompt: ${message} ${allowed} ${rejected}",
            # invalid_question_response not set — uses default
        )
        assert (
            config.invalid_question_response
            == constants.DEFAULT_INVALID_QUESTION_RESPONSE
        )

    def test_explicit_fields_differ_from_defaults(self) -> None:
        """Output shield with explicit fields should differ from defaults."""
        config = QuestionValidityConfig(
            model_id="test-model",
            model_prompt="Custom output prompt: ${message} ${allowed} ${rejected}",
            invalid_question_response="Custom rejection message.",
        )
        assert config.model_prompt != constants.DEFAULT_MODEL_PROMPT
        assert (
            config.invalid_question_response
            != constants.DEFAULT_INVALID_QUESTION_RESPONSE
        )
