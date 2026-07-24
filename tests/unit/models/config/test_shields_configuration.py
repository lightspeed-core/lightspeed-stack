"""Unit tests for ShieldConfiguration model and the Configuration.shields list."""

# pylint: disable=no-member

import pytest
from pydantic import ValidationError

from models.config import (
    CompactionConfiguration,
    Configuration,
    LlamaStackConfiguration,
    QuestionValidityConfig,
    QuestionValidityShieldConfiguration,
    RedactionConfig,
    RedactionRule,
    RedactionShieldConfiguration,
    ServiceConfiguration,
    UserDataCollection,
)


class TestShieldConfiguration:
    """Tests for the ShieldConfiguration discriminated union variants."""

    def test_question_validity_shield(self) -> None:
        """A question_validity shield parses config into QuestionValidityConfig."""
        shield = QuestionValidityShieldConfiguration.model_validate(
            {
                "name": "topic-guard",
                "type": "question_validity",
                "config": {"model_id": "test-model"},
            }
        )
        assert shield.name == "topic-guard"
        assert shield.type == "question_validity"
        assert isinstance(shield.config, QuestionValidityConfig)
        assert shield.config.model_id == "test-model"

    def test_redaction_shield(self) -> None:
        """A redaction shield parses config into RedactionConfig."""
        shield = RedactionShieldConfiguration.model_validate(
            {
                "name": "pii-guard",
                "type": "redaction",
                "config": {"rules": [{"pattern": r"\d+", "replacement": "[NUM]"}]},
            }
        )
        assert shield.name == "pii-guard"
        assert shield.type == "redaction"
        assert isinstance(shield.config, RedactionConfig)
        assert len(shield.config.compiled_patterns) == 1

    def test_accepts_already_constructed_config_instance(self) -> None:
        """config may be passed as an already-constructed model instance."""
        shield = QuestionValidityShieldConfiguration(
            name="topic-guard",
            type="question_validity",
            config=QuestionValidityConfig(model_id="test-model"),
        )
        assert isinstance(shield.config, QuestionValidityConfig)

    def test_rejects_config_mismatched_with_type(self) -> None:
        """A redaction type with question_validity-shaped config is rejected."""
        with pytest.raises(ValidationError, match="model_id"):
            RedactionShieldConfiguration.model_validate(
                {
                    "name": "bad",
                    "type": "redaction",
                    "config": {"model_id": "oops"},
                }
            )

    def test_rejects_unknown_type(self) -> None:
        """An unrecognized shield type is rejected by the root Configuration union."""
        with pytest.raises(ValidationError):
            Configuration.model_validate(
                {
                    **_minimal_configuration_kwargs(),
                    "shields": [
                        {
                            "name": "bad",
                            "type": "unknown_type",
                            "config": {"model_id": "test-model"},
                        }
                    ],
                }
            )

    def test_rejects_unknown_fields(self) -> None:
        """Unknown fields are forbidden on shield configuration variants."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            QuestionValidityShieldConfiguration.model_validate(
                {
                    "name": "topic-guard",
                    "type": "question_validity",
                    "config": {"model_id": "test-model"},
                    "unknown_field": "value",
                }
            )


def _minimal_configuration_kwargs() -> dict:
    return {
        "name": "test",
        "service": ServiceConfiguration(),
        "llama_stack": LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        "user_data_collection": UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        "compaction": CompactionConfiguration(),
    }


def test_root_configuration_has_shields_field() -> None:
    """The root Configuration declares a shields list field, empty by default."""
    field_info = Configuration.model_fields.get("shields")
    assert field_info is not None

    factory = field_info.default_factory
    assert factory is not None
    assert factory() == []  # type: ignore[call-arg]


def test_root_configuration_default_shields_is_empty() -> None:
    """Configuration constructed without shields defaults to an empty list."""
    cfg = Configuration(**_minimal_configuration_kwargs())
    assert cfg.shields == []


def test_root_configuration_accepts_multiple_shields_of_same_type() -> None:
    """Multiple shields of the same type may be configured with distinct names."""
    cfg = Configuration(
        **_minimal_configuration_kwargs(),
        shields=[
            QuestionValidityShieldConfiguration(
                name="topic-guard-a",
                type="question_validity",
                config=QuestionValidityConfig(model_id="model-a"),
            ),
            QuestionValidityShieldConfiguration(
                name="topic-guard-b",
                type="question_validity",
                config=QuestionValidityConfig(model_id="model-b"),
            ),
        ],
    )
    assert len(cfg.shields) == 2
    assert cfg.shields[0].name == "topic-guard-a"
    assert cfg.shields[1].name == "topic-guard-b"


def test_root_configuration_accepts_mixed_shield_types() -> None:
    """Shields of different types may be mixed in the same list."""
    cfg = Configuration(
        **_minimal_configuration_kwargs(),
        shields=[
            QuestionValidityShieldConfiguration(
                name="topic-guard",
                type="question_validity",
                config=QuestionValidityConfig(model_id="test-model"),
            ),
            RedactionShieldConfiguration(
                name="pii-guard",
                type="redaction",
                config=RedactionConfig(
                    rules=[RedactionRule(pattern=r"\d+", replacement="[NUM]")]
                ),
            ),
        ],
    )
    assert len(cfg.shields) == 2
    assert cfg.shields[0].type == "question_validity"
    assert cfg.shields[1].type == "redaction"


def test_root_configuration_rejects_duplicate_shield_names() -> None:
    """Shield names must be unique across the shields list."""
    with pytest.raises(ValidationError, match="Shield names must be unique"):
        Configuration(
            **_minimal_configuration_kwargs(),
            shields=[
                QuestionValidityShieldConfiguration(
                    name="dup",
                    type="question_validity",
                    config=QuestionValidityConfig(model_id="model-a"),
                ),
                RedactionShieldConfiguration(
                    name="dup",
                    type="redaction",
                    config=RedactionConfig(),
                ),
            ],
        )
