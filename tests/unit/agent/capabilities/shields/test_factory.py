"""Unit tests for shield capability construction."""

import logging
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture, MockType

from agent.capabilities.shields.factory import ShieldFactory
from agent.types.settings import ShieldSettings
from models.config import (
    GraniteGuardianConfig,
    QuestionValidityConfig,
    RedactionConfig,
    RiskDefinition,
)


def _question(name: str = "topic") -> SimpleNamespace:
    """Build a question-validity shield entry."""
    return SimpleNamespace(
        name=name,
        config=QuestionValidityConfig(model_id="guard-model"),
    )


def _redaction(name: str = "pii") -> SimpleNamespace:
    """Build a redaction shield entry."""
    return SimpleNamespace(name=name, config=RedactionConfig())


def _guardian(name: str = "guardian") -> SimpleNamespace:
    """Build a Granite Guardian shield entry."""
    return SimpleNamespace(
        name=name,
        config=GraniteGuardianConfig(
            url="http://guardian.example/v1",
            risks=[
                RiskDefinition(
                    name="harm",
                    description="Harmful content",
                    points=["input"],
                    violation_message="blocked",
                )
            ],
        ),
    )


def _install(
    mocker: MockerFixture, shields: list[SimpleNamespace]
) -> dict[str, MockType]:
    """Patch shield configuration and the capability constructors."""
    mocker.patch(
        "agent.capabilities.shields.factory.configuration",
        SimpleNamespace(shields=shields),
    )
    return {
        "question": mocker.patch("agent.capabilities.shields.factory.QuestionValidity"),
        "redaction": mocker.patch(
            "agent.capabilities.shields.factory.PiiRedactionCapability"
        ),
        "guardian": mocker.patch("agent.capabilities.shields.factory.GraniteGuardian"),
    }


def test_empty_settings_build_nothing() -> None:
    """No shield settings produce no capabilities."""
    assert ShieldFactory.build_capabilities([]) == []


def test_disabled_shield_is_skipped(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A disabled setting does not look up or warn about the shield."""
    builders = _install(mocker, [])

    with caplog.at_level(logging.WARNING):
        assert (
            ShieldFactory.build_capability(ShieldSettings(id="topic", enabled=False))
            is None
        )

    assert "not configured" not in caplog.text
    builders["question"].assert_not_called()


def test_unknown_shield_is_skipped(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A shield name that is not configured is logged and skipped."""
    _install(mocker, [_question()])

    with caplog.at_level(logging.WARNING):
        assert ShieldFactory.build_capability(ShieldSettings(id="missing")) is None

    assert "Shield 'missing' is not configured" in caplog.text


def test_question_validity_redaction_and_guardian_are_built(
    mocker: MockerFixture,
) -> None:
    """Each supported shield config builds the matching capability, in order."""
    question = _question()
    redaction = _redaction()
    guardian = _guardian()
    builders = _install(mocker, [question, redaction, guardian])

    capabilities = ShieldFactory.build_capabilities(
        [
            ShieldSettings(id="topic"),
            ShieldSettings(id="pii", enabled=False),
            ShieldSettings(id="missing"),
            ShieldSettings(id="pii"),
            ShieldSettings(id="guardian"),
        ]
    )

    assert capabilities == [
        builders["question"].return_value,
        builders["redaction"].return_value,
        builders["guardian"].return_value,
    ]
    builders["question"].assert_called_once_with(config=question.config)
    builders["redaction"].assert_called_once_with(config=redaction.config)
    builders["guardian"].assert_called_once_with(config=guardian.config)


def test_unsupported_shield_config_is_rejected(mocker: MockerFixture) -> None:
    """A shield whose config type is not recognized raises ValueError."""
    _install(mocker, [SimpleNamespace(name="custom", config=SimpleNamespace())])

    with pytest.raises(
        ValueError, match="Unsupported shield config type for shield 'custom'"
    ):
        ShieldFactory.build_capability(ShieldSettings(id="custom"))
