"""Unit tests for environment-reference normalization and OGX resolution."""

import copy
import os
from typing import Any, Final, Optional

import pytest
from ogx.core.stack import EnvVarError
from pytest_mock import MockerFixture

from utils.env_vars import (
    _ENV_REFERENCE_PATTERN,
    canonicalize_reference,
    normalize_env_references,
    resolve_env_references,
)

_COMMON_REFERENCE_CASES: Final[tuple[tuple[str, str], ...]] = (
    ("${HOST}", "${env.HOST}"),
    ("${env.HOST}", "${env.HOST}"),
)


@pytest.fixture(
    name="reference_prefix", params=["", "env."], ids=["short", "canonical"]
)
def reference_prefix_fixture(request: pytest.FixtureRequest) -> str:
    """Exercise both environment-reference spellings."""
    return str(request.param)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        *_COMMON_REFERENCE_CASES,
        ("${HOST:=localhost}", "${env.HOST:=localhost}"),
        ("${HOST:=}", "${env.HOST:=}"),
        ("${HOST:+enabled}", "${env.HOST:+enabled}"),
        ("${HOST:+}", "${env.HOST:+}"),
        ("${HOST:=local host #1}", "${env.HOST:=local host #1}"),
        ("${HOST:+use #1}", "${env.HOST:+use #1}"),
        ("${env.HOST:=localhost}", "${env.HOST:=localhost}"),
        ("${env.HOST:=}", "${env.HOST:=}"),
        ("${env.HOST:+enabled}", "${env.HOST:+enabled}"),
        ("${env.HOST:+}", "${env.HOST:+}"),
    ],
)
def test_canonicalize_reference(source: str, expected: str) -> None:
    """Convert one supported regex match to its canonical reference."""
    match = _ENV_REFERENCE_PATTERN.fullmatch(source)
    assert match is not None

    assert canonicalize_reference(match) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        *_COMMON_REFERENCE_CASES,
        ("${A}", "${env.A}"),
        ("${1}", "${env.1}"),
        ("${_}", "${env._}"),
        ("${_HOST_2}", "${env._HOST_2}"),
        ("${123}", "${env.123}"),
        ("https://${HOST}:${PORT}/api", "https://${env.HOST}:${env.PORT}/api"),
        ("${HOST}/${HOST}", "${env.HOST}/${env.HOST}"),
        ("${HOST}/${env.PORT}", "${env.HOST}/${env.PORT}"),
        ("${env.HOST:=${OTHER}}", "${env.HOST:=${OTHER}}"),
        # Unsupported expressions remain literal; OGX does not reject them.
        ("${}", "${}"),
        ("${env.}", "${env.}"),
        ("${host}", "${host}"),
        ("${env.host}", "${env.host}"),
        # OGX supports := and :+, but not the shell's :- default operator.
        ("${HOST:-localhost}", "${HOST:-localhost}"),
        ("${env.HOST:-localhost}", "${env.HOST:-localhost}"),
        ("${HOST:+value", "${HOST:+value"),
        ("${HOST:localhost}", "${HOST:localhost}"),
        ("${HOST+enabled}", "${HOST+enabled}"),
        ("${HOST-NAME}", "${HOST-NAME}"),
        ("${other.HOST}", "${other.HOST}"),
        ("{HOST}", "{HOST}"),
        ("$HOST", "$HOST"),
        ("plain text", "plain text"),
        ("", ""),
    ],
)
def test_normalize_env_references(source: str, expected: str) -> None:
    """Match supported references in complete strings and preserve unsupported syntax."""
    assert normalize_env_references(source) == expected


@pytest.mark.parametrize("key", ["${KEY}", "${env.KEY}"])
def test_normalize_nested_containers_without_mutating_input(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    """Normalize dictionary values and lists while preserving keys and scalars."""
    monkeypatch.setenv("KEY", "must-not-replace-key")
    config = {
        key: ["${HOST}", {"port": "${PORT:=5432}"}],
        "unchanged": [None, True, 42, 1.5, ("${TUPLE_VALUE}",)],
    }
    original = copy.deepcopy(config)

    result = normalize_env_references(config)

    assert result == {
        key: ["${env.HOST}", {"port": "${env.PORT:=5432}"}],
        "unchanged": [None, True, 42, 1.5, ("${TUPLE_VALUE}",)],
    }
    assert config == original


@pytest.mark.parametrize("value", [None, True, 42, 1.5, b"data", ("${HOST}",)])
def test_non_container_values_pass_through(value: object) -> None:
    """Keep non-string leaves unchanged through normalization and full resolution."""
    assert normalize_env_references(value) is value
    assert resolve_env_references(value) is value


def test_normalize_does_not_read_environment(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """Normalization leaves secrets and defaults deferred without environment I/O."""
    environment = mocker.MagicMock()

    with monkeypatch.context() as patch:
        patch.setattr(os, "environ", environment)
        result = normalize_env_references(["${SECRET}", "${HOST:=localhost}"])

    assert result == ["${env.SECRET}", "${env.HOST:=localhost}"]
    assert not environment.mock_calls


@pytest.mark.parametrize(
    ("suffix", "environment_value", "expected"),
    [
        ("", "configured", "configured"),
        (":=fallback", None, "fallback"),
        (":=fallback", "", "fallback"),
        (":=fallback", "configured", "configured"),
        (":=", None, None),
        (":=", "", None),
        (":=", "configured", "configured"),
        (":+enabled", None, None),
        (":+enabled", "", None),
        (":+enabled", "configured", "enabled"),
        (":+", None, None),
        (":+", "", None),
        (":+", "configured", None),
        ("", "5432", 5432),
        ("", "1.5", 1.5),
        ("", "true", True),
        ("", "FALSE", False),
    ],
)
def test_resolve_matches_ogx_semantics(
    monkeypatch: pytest.MonkeyPatch,
    reference_prefix: str,
    suffix: str,
    environment_value: Optional[str],
    expected: Any,
) -> None:
    """Read environment values and apply OGX defaults, conditionals, and type conversion."""
    variable = "LCORE_ENV_REFERENCE_TEST"
    monkeypatch.delenv(variable, raising=False)
    if environment_value is not None:
        monkeypatch.setenv(variable, environment_value)

    result = resolve_env_references(f"${{{reference_prefix}{variable}{suffix}}}")

    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize("environment_value", [None, ""])
def test_resolve_missing_variable_preserves_ogx_error(
    monkeypatch: pytest.MonkeyPatch,
    reference_prefix: str,
    environment_value: Optional[str],
) -> None:
    """Preserve OGX's missing-variable error and nested configuration path."""
    variable = "LCORE_ENV_REFERENCE_TEST"
    monkeypatch.delenv(variable, raising=False)
    if environment_value is not None:
        monkeypatch.setenv(variable, environment_value)
    config = {"providers": [{"key": f"${{{reference_prefix}{variable}}}"}]}
    original = copy.deepcopy(config)

    with pytest.raises(EnvVarError) as error:
        resolve_env_references(config)

    assert error.value.var_name == variable
    assert error.value.path == "providers[0].key"
    assert config == original


def test_resolve_embedded_and_mixed_references(
    monkeypatch: pytest.MonkeyPatch, reference_prefix: str
) -> None:
    """Resolve nested references and numeric ports without changing keys or input."""
    monkeypatch.setenv("LCORE_ENV_REFERENCE_HOST", "example.test")
    monkeypatch.setenv("LCORE_ENV_REFERENCE_PORT", "8443")
    monkeypatch.setenv("LCORE_ENV_REFERENCE_KEY", "must-not-replace-key")
    key = f"${{{reference_prefix}LCORE_ENV_REFERENCE_KEY}}"
    config = {
        key: [
            (
                f"https://${{{reference_prefix}LCORE_ENV_REFERENCE_HOST}}:"
                "${env.LCORE_ENV_REFERENCE_PORT}/api"
            ),
            {"repeated": "${LCORE_ENV_REFERENCE_HOST}/${env.LCORE_ENV_REFERENCE_HOST}"},
        ],
        "port": f"${{{reference_prefix}LCORE_ENV_REFERENCE_PORT}}",
        "unchanged": [None, True, 42],
    }
    original = copy.deepcopy(config)

    assert resolve_env_references(config) == {
        key: [
            "https://example.test:8443/api",
            {"repeated": "example.test/example.test"},
        ],
        "port": 8443,
        "unchanged": [None, True, 42],
    }
    assert config == original


@pytest.mark.parametrize("environment_value", ["${OTHER}", "${env.OTHER}"])
def test_resolve_does_not_expand_environment_values_again(
    monkeypatch: pytest.MonkeyPatch, reference_prefix: str, environment_value: str
) -> None:
    """Keep placeholder-like environment values literal, matching OGX's single pass."""
    monkeypatch.setenv("LCORE_ENV_REFERENCE_TEST", environment_value)
    monkeypatch.setenv("OTHER", "must-not-expand")

    result = resolve_env_references(f"${{{reference_prefix}LCORE_ENV_REFERENCE_TEST}}")

    assert result == environment_value
