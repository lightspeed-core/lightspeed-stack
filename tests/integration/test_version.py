"""Test if version is handled correctly."""

import subprocess

from version import __version__


def read_version_from_pyproject() -> str:
    """Read version from pyproject.toml file.

    Retrieve the project's version as reported by the PDM tool.

    Invokes the `pdm show --version` command and returns the resulting version string
    decoded as UTF-8 with surrounding whitespace removed.

    Returns:
        version (str): The project version reported by PDM.

    Raises:
        subprocess.CalledProcessError: If the `pdm` command exits with a non-zero status.
    """
    # it is not safe to just try to read version from pyproject.toml file directly
    # the PDM tool itself is able to retrieve the version, even if the version
    # is generated dynamically
    completed = subprocess.run(  # noqa: S603
        ["pdm", "show", "--version"],  # noqa: S607
        capture_output=True,
        check=True,
    )
    return completed.stdout.decode("utf-8").strip()


def test_version_handling() -> None:
    """Test how version is handled by the project.

    Verify that the package's source __version__ matches the version reported by the project tool.

    Raises:
        AssertionError: If the source version and the project-reported version
        differ; the message includes both versions.
    """
    source_version = __version__
    project_version = read_version_from_pyproject()
    assert (
        source_version == project_version
    ), f"Source version {source_version} != project version {project_version}"
