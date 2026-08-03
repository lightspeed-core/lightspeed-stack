"""Unit tests for functions defined in src/lightspeed_stack.py."""

import logging
from pathlib import Path

import pytest
import yaml

from lightspeed_stack import cli
from lightspeed_stack.cli import create_argument_parser, main
from lightspeed_stack.configuration import AppConfig

LEGACY_DEPRECATION_MARKER = "DEPRECATED: the two-file configuration"

COMMON_CONFIG_SECTIONS = """
name: test
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
user_data_collection:
  feedback_enabled: false
mcp_servers: []
"""


def test_create_argument_parser() -> None:
    """Test for create_argument_parser function.

    Verify that create_argument_parser returns a parser instance.

    Asserts the factory function returns a non-None argument parser
    object and does not exercise parsing behavior.
    """
    arg_parser = create_argument_parser()
    # nothing more to test w/o actual parsing is done
    assert arg_parser is not None


def test_argument_parser_accepts_migrate_flags() -> None:
    """The parser accepts --migrate-config, --run-yaml, and --migrate-output."""
    args = create_argument_parser().parse_args(
        [
            "--migrate-config",
            "--run-yaml",
            "run.yaml",
            "-c",
            "lightspeed-stack.yaml",
            "--migrate-output",
            "unified.yaml",
        ]
    )
    assert args.migrate_config is True
    assert args.run_yaml == "run.yaml"
    assert args.config_file == "lightspeed-stack.yaml"
    assert args.migrate_output == "unified.yaml"


def test_main_migrate_config_writes_unified_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--migrate-config` migrates the legacy pair and exits without starting the service."""
    run_path = tmp_path / "run.yaml"
    run_path.write_text(
        yaml.dump({"version": 2, "apis": ["inference"]}), encoding="utf-8"
    )
    lcs_path = tmp_path / "lightspeed-stack.yaml"
    lcs_path.write_text(
        yaml.dump(
            {
                "name": "LCS",
                "llama_stack": {
                    "use_as_library_client": True,
                    "library_client_config_path": "run.yaml",
                },
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "unified.yaml"
    monkeypatch.setattr(
        "sys.argv",
        [
            "lightspeed-stack",
            "--migrate-config",
            "--run-yaml",
            str(run_path),
            "-c",
            str(lcs_path),
            "--migrate-output",
            str(out_path),
        ],
    )

    main()  # returns early, never starts uvicorn

    migrated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert "library_client_config_path" not in migrated["llama_stack"]
    assert migrated["llama_stack"]["config"]["baseline"] == "empty"
    assert migrated["llama_stack"]["config"]["native_override"] == {
        "version": 2,
        "apis": ["inference"],
    }


def test_main_migrate_config_requires_run_yaml_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--migrate-config` without --run-yaml / --migrate-output exits with status 1."""
    monkeypatch.setattr(
        "sys.argv",
        ["lightspeed-stack", "--migrate-config", "-c", "lightspeed-stack.yaml"],
    )
    with pytest.raises(SystemExit):
        main()


def run_main_with_config(
    config_yaml: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run main() against a config file, with the runners stubbed out.

    Writes ``config_yaml`` to a temporary file, points argv at it, replaces
    the module-level configuration singleton with a fresh AppConfig (so the
    shared singleton is not mutated for other tests), and stubs the quota
    scheduler and uvicorn runners.
    """
    cfg_file = tmp_path / "lightspeed-stack.yaml"
    cfg_file.write_text(config_yaml, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["lightspeed-stack", "-c", str(cfg_file)])
    monkeypatch.setattr(cli, "configuration", AppConfig())
    monkeypatch.setattr(cli, "start_quota_scheduler", lambda _: None)
    monkeypatch.setattr(cli, "start_uvicorn", lambda _: None)
    main()


def test_main_warns_on_legacy_two_file_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A legacy library_client_config_path config emits one deprecation WARN."""
    run_yaml = tmp_path / "run.yaml"
    run_yaml.write_text("version: 2\n", encoding="utf-8")
    config_yaml = COMMON_CONFIG_SECTIONS + f"""
llama_stack:
  use_as_library_client: true
  library_client_config_path: {run_yaml}
"""
    with caplog.at_level(logging.WARNING):
        run_main_with_config(config_yaml, tmp_path, monkeypatch)
    warnings = [
        r for r in caplog.records if LEGACY_DEPRECATION_MARKER in r.getMessage()
    ]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING
    # the WARN carries a stable link to the migration doc
    assert "#migration--backwards-compatibility" in warnings[0].getMessage()


def test_main_does_not_warn_in_unified_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A unified-mode config (llama_stack.config) emits no deprecation WARN."""
    config_yaml = COMMON_CONFIG_SECTIONS + """
llama_stack:
  use_as_library_client: true
  config:
    baseline: default
"""
    with caplog.at_level(logging.WARNING):
        run_main_with_config(config_yaml, tmp_path, monkeypatch)
    assert not any(LEGACY_DEPRECATION_MARKER in r.getMessage() for r in caplog.records)


def test_main_does_not_warn_in_server_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A server-mode config (url, no legacy fields) emits no deprecation WARN."""
    config_yaml = COMMON_CONFIG_SECTIONS + """
llama_stack:
  use_as_library_client: false
  url: http://localhost:8321
  api_key: xyzzy
"""
    with caplog.at_level(logging.WARNING):
        run_main_with_config(config_yaml, tmp_path, monkeypatch)
    assert not any(LEGACY_DEPRECATION_MARKER in r.getMessage() for r in caplog.records)
