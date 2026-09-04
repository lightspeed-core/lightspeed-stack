"""Integration tests for the unified-mode CLI contracts (LCORE-2343).

These cover the surfaces the unified-mode e2e features used to exercise by
shelling out to ``src/`` — which e2e steps must not do (see
``docs/testing/e2e_testing.md``, "Choosing the Test Layer"): configuration
validation through ``lightspeed_stack.py --dump-configuration``,
legacy-to-unified migration through ``--migrate-config``, and the committed
migrated e2e fixture that replaced the migration step in
``unified-mode-migration.feature``.

Everything here runs the real entrypoint as a subprocess from the repository
root, the way operators and the container entrypoint invoke it; the in-process
half of the same pipeline lives in ``test_unified_synthesis.py``.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from ogx_configuration import synthesize_configuration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRYPOINT = _REPO_ROOT / "src" / "lightspeed_stack.py"
_FIXTURES = _REPO_ROOT / "tests" / "configuration" / "unified-mode"
_E2E_FIXTURES = _REPO_ROOT / "tests" / "e2e" / "configuration" / "unified-mode"
# The run.yaml the e2e harness materializes at the repo root in CI; the
# committed migrated e2e fixtures were generated against it.
_E2E_RUN_YAML = _REPO_ROOT / "tests" / "e2e" / "configs" / "run-ci.yaml"
_MIGRATED_FIXTURE = "lightspeed-stack-unified-migrated.yaml"
_LEGACY_PAIR_FIXTURE = "lightspeed-stack-legacy-for-migration.yaml"
_CLI_TIMEOUT_SECONDS = 120


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the service entrypoint as a subprocess from the repo root, never raising."""
    return subprocess.run(
        [sys.executable, str(_ENTRYPOINT), *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_CLI_TIMEOUT_SECONDS,
        check=False,
    )


def _load_yaml(path: Path) -> Any:
    """Parse a YAML file."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _migrate(lcs_config: Path, run_yaml: Path, output: Path) -> None:
    """Run ``--migrate-config`` for a legacy pair and assert it succeeded."""
    result = _run_cli(
        "--migrate-config",
        "--run-yaml",
        str(run_yaml),
        "-c",
        str(lcs_config),
        "--migrate-output",
        str(output),
    )
    assert result.returncode == 0 and output.is_file(), (
        f"--migrate-config failed (rc={result.returncode}).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Validation through the CLI (R3 mutual exclusion, R11 format-version marker)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "expected_message"),
    [
        pytest.param(
            "lightspeed-stack-invalid-providers-and-legacy.yaml",
            "--migrate-config",
            id="inference-providers-plus-legacy-path",
        ),
        pytest.param(
            "lightspeed-stack-invalid-config-and-legacy.yaml",
            "--migrate-config",
            id="config-block-plus-legacy-path",
        ),
        pytest.param(
            "lightspeed-stack-invalid-version-legacy-unified-body.yaml",
            "config_format_version",
            id="legacy-version-marker-on-unified-body",
        ),
    ],
)
def test_cli_rejects_invalid_configuration(fixture: str, expected_message: str) -> None:
    """``--dump-configuration`` exits non-zero and names the problem.

    ``main()`` loads (and thereby validates) the configuration before any dump
    handling, so a failed cross-field validation surfaces as a non-zero exit
    with the Pydantic message on stderr. The fixtures point their legacy path
    at an existing run.yaml so the captured failure is the intended
    cross-field error, not a file-not-found.
    """
    result = _run_cli("--dump-configuration", "-c", str(_FIXTURES / fixture))
    output = result.stdout + result.stderr

    assert result.returncode != 0, (
        f"expected {fixture} to fail validation, but the load succeeded. "
        f"Output:\n{output}"
    )
    assert expected_message in output, (
        f"validation failure for {fixture} does not mention "
        f"{expected_message!r}. Full output:\n{output}"
    )


# ---------------------------------------------------------------------------
# --migrate-config contract
# ---------------------------------------------------------------------------


def test_cli_migrate_config_writes_unified_owner_only(tmp_path: Path) -> None:
    """``--migrate-config`` emits a unified file, owner-only, that round-trips.

    The output carries the run.yaml as ``native_override`` and drops the legacy
    ``library_client_config_path``; it is written 0600 because migrated files
    may carry lifted secrets (R10); and synthesizing it reproduces the pair's
    run.yaml data (migrate-then-synthesize round trip).
    """
    output = tmp_path / "unified.yaml"
    _migrate(_FIXTURES / _LEGACY_PAIR_FIXTURE, _E2E_RUN_YAML, output)

    mode = stat.S_IMODE(os.stat(output).st_mode)
    assert mode == 0o600, f"migrated file mode is {oct(mode)}, expected 0o600"

    text = output.read_text(encoding="utf-8")
    migrated = yaml.safe_load(text)
    assert migrated["ogx"]["config"][
        "native_override"
    ], "migrated config carries no native_override"
    assert "library_client_config_path" not in text

    synthesized = synthesize_configuration(migrated, config_file_dir=str(tmp_path))
    assert synthesized == _load_yaml(_E2E_RUN_YAML)


@pytest.mark.parametrize("mode", ["library-mode", "server-mode"])
def test_committed_migrated_fixture_matches_cli_output(
    tmp_path: Path, mode: str
) -> None:
    """The committed migrated e2e fixture is exactly what the CLI produces today.

    ``unified-mode-migration.feature`` boots
    ``tests/e2e/configuration/unified-mode/<mode>/lightspeed-stack-unified-migrated.yaml``
    instead of generating it in a step (e2e steps never run ``src/`` CLIs).
    This guard fails the moment ``--migrate-config`` output drifts from the
    committed file. To refresh the fixture, run from the repo root::

        uv run python src/lightspeed_stack.py --migrate-config \\
            --run-yaml tests/e2e/configs/run-ci.yaml \\
            -c tests/e2e/configuration/unified-mode/<mode>/lightspeed-stack-legacy-for-migration.yaml \\
            --migrate-output tests/e2e/configuration/unified-mode/<mode>/lightspeed-stack-unified-migrated.yaml
        chmod 644 tests/e2e/configuration/unified-mode/<mode>/lightspeed-stack-unified-migrated.yaml
    """
    output = tmp_path / "migrated.yaml"
    _migrate(_E2E_FIXTURES / mode / _LEGACY_PAIR_FIXTURE, _E2E_RUN_YAML, output)

    committed = _E2E_FIXTURES / mode / _MIGRATED_FIXTURE
    assert _load_yaml(output) == _load_yaml(committed), (
        f"{committed} no longer matches --migrate-config output; regenerate it "
        "(see this test's docstring)"
    )
