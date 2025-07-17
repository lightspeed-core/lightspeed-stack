"""Test if version is handled correcty."""

import subprocess

from version import __version__


def read_version_from_pyproject():
    """Read version from pyproject.toml file."""
    # it is not safe to just try to read version from pyproject.toml file directly
    # the PDM tool itself is able to retrieve the version, even if the version
    # is generated dynamically
    completed = subprocess.run(  # noqa: S603
        ["pdm", "show", "--version"],  # noqa: S607
        capture_output=True,
        check=True,
    )
    return completed.stdout.decode("utf-8").strip()


def test_version_handling():
    """Test how version is handled by the project."""
    source_version = __version__
    project_version = read_version_from_pyproject()
    assert (
        source_version == project_version
    ), f"Source version {source_version} != project version {project_version}"
