"""Unit tests for the guardrails PoC config loader (LCORE-2657 spike)."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from guardrails.poc_loader import POC_CONFIG_ENV_VAR, load_poc_config

POC_YAML = """
detector:
  url: http://localhost:11434/v1
  model: granite3-guardian:2b
rules:
  - name: jailbreak
    risk: jailbreak
    points: [input]
  - name: leet-speak
    risk: custom
    definition: Flag leet speak obfuscation.
    points: [input]
violation_message: Custom refusal.
"""


@pytest.fixture(autouse=True)
def clear_loader_cache() -> Iterator[None]:
    """Reset the lru_cache between tests."""
    load_poc_config.cache_clear()
    yield
    load_poc_config.cache_clear()


def test_returns_none_when_env_var_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the env var the PoC is disabled."""
    monkeypatch.delenv(POC_CONFIG_ENV_VAR, raising=False)
    assert load_poc_config() is None


def test_loads_and_validates_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A valid YAML file parses into a GuardrailsPocConfig."""
    config_path = tmp_path / "guardrails.yaml"
    config_path.write_text(POC_YAML, encoding="utf-8")
    monkeypatch.setenv(POC_CONFIG_ENV_VAR, str(config_path))

    config = load_poc_config()

    assert config is not None
    assert config.detector.model == "granite3-guardian:2b"
    assert [rule.name for rule in config.rules] == ["jailbreak", "leet-speak"]
    assert config.rules[1].definition == "Flag leet speak obfuscation."
    assert config.violation_message == "Custom refusal."
