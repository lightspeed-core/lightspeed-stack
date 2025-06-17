"""Utility script to generate OpenAPI schema."""

import json
import pprint
import subprocess
import sys

from fastapi.openapi.utils import get_openapi

# it is needed to read proper configuration in order to start the app to generate schema
from configuration import configuration

cfg_file = "lightspeed-stack.yaml"
configuration.load_configuration(cfg_file)

from app.main import app  # noqa: E402  pylint: disable=C0413


def read_version_from_openapi(filename: str) -> str:
    """Read version from OpenAPI.json file."""
    # retrieve pre-generated OpenAPI schema
    with open(filename, encoding="utf-8") as fin:
        pre_generated_schema = json.load(fin)
        assert pre_generated_schema is not None
        assert "info" in pre_generated_schema, "node 'info' not found in openapi.json"
        info = pre_generated_schema["info"]
        assert "version" in info, "node 'version' not found in 'info'"
        return info["version"]


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


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_openapi_schema.py <filename>")
        sys.exit(1)

    filename = sys.argv[1]

    print("Service metadata:")
    print(app.title)
    print(app.description)

    print()

    print("Routes:")
    pprint.pprint(app.routes)

    # retrieve OpenAPI schema via initialized app
    open_api = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        license_info=app.license_info,
    )

    # dump the schema into file
    with open(filename, "w", encoding="utf-8") as fout:
        json.dump(open_api, fout, indent=4)

    openapi_version = read_version_from_openapi(filename)
    project_version = read_version_from_pyproject()
    assert (
        openapi_version == project_version
    ), f"OpenAPI version {openapi_version} != project version {project_version}"
    print(f"OpenAPI schema generated into file {filename}")
