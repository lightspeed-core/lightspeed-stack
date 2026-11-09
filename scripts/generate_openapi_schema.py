"""Utility script to generate OpenAPI schema."""

import json
import os
import pprint
import subprocess
import sys
import tempfile

from fastapi.openapi.utils import get_openapi

from client.ogx import AsyncOgxClientHolder

# it is needed to read proper configuration in order to start the app to generate schema
from configuration import configuration

CFG_FILE = "lightspeed-stack.yaml"
configuration.load_configuration(CFG_FILE)

# OGX client needs to be loaded before REST API is fully initialized
import asyncio  # pylint: disable=C0411,C0413

asyncio.run(AsyncOgxClientHolder().load(configuration.configuration.ogx))

from app.main import app  # pylint: disable=C0413


def read_version_from_openapi(openapi_filename: str) -> str:
    """
    Extract the OpenAPI document's version from a generated OpenAPI JSON file.

    Returns:
        str: The OpenAPI document's `info.version`, converted to a string.

    Raises:
        OSError: If the file cannot be read.
        UnicodeDecodeError: If the file is not valid UTF-8.
        json.JSONDecodeError: If the file is not valid JSON.
        AssertionError: If the document is null or lacks `info` or `version`.
        TypeError: If the document or `info` has an incompatible structure.

    """
    # retrieve pre-generated OpenAPI schema
    with open(openapi_filename, encoding="utf-8") as fin:
        pre_generated_schema = json.load(fin)
        assert pre_generated_schema is not None
        assert "info" in pre_generated_schema, "node 'info' not found in openapi.json"
        info = pre_generated_schema["info"]
        assert "version" in info, "node 'version' not found in 'info'"
        return str(info["version"])


def read_version_from_pyproject() -> str:
    """
    Obtain the project's version using PDM (`pdm show --version`), which supports dynamic versions.

    Returns:
        str: The project version string.

    Raises:
        subprocess.CalledProcessError: If PDM exits unsuccessfully.
        OSError: If PDM cannot be started.
        UnicodeDecodeError: If PDM's output is not valid UTF-8.

    """
    # it is not safe to just try to read version from pyproject.toml file directly
    # the PDM tool itself is able to retrieve the version, even if the version
    # is generated dynamically
    completed = subprocess.run(
        ["pdm", "show", "--version"],
        capture_output=True,
        check=True,
    )
    return completed.stdout.decode("utf-8").strip()


def generate_openapi_schema(schema_file_name: str) -> None:
    """Write the app's OpenAPI schema, then check its version against PDM.

    Overwrites the named JSON file before checking versions; the file remains
    if the check fails.

    Raises:
        AssertionError: If the schema lacks version information or its version
            differs from the project version.
        subprocess.CalledProcessError: If ``pdm show --version`` fails.
        OSError: If the file cannot be accessed or PDM cannot be started.
        UnicodeDecodeError: If PDM's output is not valid UTF-8.

    """
    print("Service metadata:")
    print(app.title)
    print(app.description)

    print()

    print("Routes:")
    pprint.pprint(app.routes)

    # retrieve OpenAPI schema via initialized app
    open_api = get_openapi(
        title=app.title,
        summary=app.summary,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        license_info=app.license_info,
        servers=app.servers,
        contact=app.contact,
        tags=app.openapi_tags,
    )

    # dump the schema into file
    # if dump fail, the original OpenAPI schema file won't be overwritten
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=os.path.dirname(os.path.abspath(schema_file_name)),
            delete=False,
        ) as fout:
            temporary_name = fout.name
            json.dump(open_api, fout, indent=4)
        os.replace(temporary_name, schema_file_name)
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)

    openapi_version = read_version_from_openapi(schema_file_name)
    project_version = read_version_from_pyproject()
    if openapi_version != project_version:
        raise AssertionError(
            f"OpenAPI version {openapi_version} != project version {project_version}"
        )
    print(f"OpenAPI schema generated into file {schema_file_name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_openapi_schema.py <filename>")
        sys.exit(1)

    filename = sys.argv[1]
    generate_openapi_schema(filename)
