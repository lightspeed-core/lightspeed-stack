"""Unit tests for functions defined in src/lightspeed_stack.py."""

from pathlib import Path

import pytest
import yaml

from lightspeed_stack import create_argument_parser, main


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
