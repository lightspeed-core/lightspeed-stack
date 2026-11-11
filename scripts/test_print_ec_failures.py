"""Regression tests for EC report input and optional export."""

import contextlib
import io
import json
import os
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from scripts import print_ec_failures


@pytest.fixture(name="_workdir_fixture")
def workdir() -> Generator:
    """Run each test in a temporary working directory and restore cwd afterward."""
    with tempfile.TemporaryDirectory() as directory:
        previous_directory = Path.cwd()
        os.chdir(directory)
        try:
            yield
        finally:
            os.chdir(previous_directory)


@pytest.fixture(name="report_fixture")
def report() -> dict[str, Any]:
    """Provide a minimal valid EC report payload containing one component violation."""
    return {"components": [{"name": "café", "violations": [{"msg": "échec"}]}]}


def run_report(report_fixture, export=False, *, mocker):
    """Write a test report, run the CLI, and capture its exit code plus stdout/stderr."""
    Path("input.log").write_text(
        "ignored\n[report-json]"
        + json.dumps(report_fixture, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    argv = ["print_ec_failures.py", "input.log"] + (["--json"] if export else [])
    stdout, stderr = io.StringIO(), io.StringIO()

    mocker.patch("sys.argv", argv)
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = print_ec_failures.main()

    return result, stdout.getvalue(), stderr.getvalue()


def test_default_prints_utf8_without_export(
    _workdir_fixture, report_fixture, mocker: MockerFixture
) -> None:
    """Verify the CLI prints UTF-8 output and does not create an export by default."""
    result, output, error = run_report(report_fixture, mocker=mocker)
    assert result == 0
    assert "Component: café" in output
    assert "#1: échec" in output
    assert "total checks: 1" in output
    assert error == ""
    assert not Path("logs.json").exists()


def test_opt_in_export(_workdir_fixture, report_fixture, mocker: MockerFixture) -> None:
    """Verify JSON export is written when explicitly requested."""
    result, output, error = run_report(report_fixture, export=True, mocker=mocker)
    assert result == 0
    assert "Component: café" in output
    assert json.loads(Path("logs.json").read_text(encoding="utf-8")) == report_fixture
    assert error == ""


def test_existing_export_is_preserved_and_results_print(
    _workdir_fixture, report_fixture, mocker: MockerFixture
) -> None:
    """Verify an existing export file is preserved if writing the report fails."""
    Path("logs.json").write_bytes(b"keep me")
    result, output, error = run_report(report_fixture, export=True, mocker=mocker)
    assert result == 1
    assert "Component: café" in output
    assert "Unable to write JSON report:" in error
    assert Path("logs.json").read_bytes() == b"keep me"


@pytest.mark.parametrize(
    "report",
    [
        None,
        [],
        "components",
        42,
        {},
        {"components": None},
        {"components": {}},
        {"components": "bad"},
    ],
)
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_shapes_never_create_or_modify_export(
    _workdir_fixture, report, existing, mocker: MockerFixture
) -> None:
    """Verify invalid report shapes do not create or overwrite the export file."""
    destination = Path("logs.json")
    if existing:
        destination.write_bytes(b"keep me")

    result, output, error = run_report(report, export=True, mocker=mocker)
    assert result == 1
    assert output.strip() == "Unable to find components attribute in EC data"
    assert error == ""

    if existing:
        assert destination.read_bytes() == b"keep me"
    else:
        assert not destination.exists()


def test_unwritable_export_does_not_prevent_terminal_report(
    _workdir_fixture, report_fixture, mocker: MockerFixture
) -> None:
    """Verify export write failures still allow the terminal report to print."""
    original_open = Path.open

    def open_with_denied_export(path, *args, **kwargs):
        if path == Path("logs.json"):
            raise PermissionError("read-only working directory")
        return original_open(path, *args, **kwargs)

    mocker.patch.object(Path, "open", open_with_denied_export)
    result, output, error = run_report(report_fixture, export=True, mocker=mocker)

    assert result == 1
    assert "Component: café" in output
    assert "Unable to write JSON report:" in error


def test_write_failure_does_not_prevent_terminal_report(
    _workdir_fixture, report_fixture, mocker: MockerFixture
) -> None:
    """Verify JSON serialization/write failures still emit the terminal report."""
    mocker.patch.object(
        print_ec_failures.json, "dump", side_effect=OSError("disk full")
    )
    result, output, error = run_report(report_fixture, export=True, mocker=mocker)

    assert result == 1
    assert "Component: café" in output
    assert "Unable to write JSON report:" in error


def test_empty_components_valid(_workdir_fixture, mocker: MockerFixture) -> None:
    """Verify an empty components list is treated as valid and produces no output."""
    result, output, error = run_report({"components": []}, mocker=mocker)
    assert (result, output, error) == (0, "", "")
