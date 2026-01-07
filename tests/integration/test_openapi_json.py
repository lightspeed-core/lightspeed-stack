"""Tests the OpenAPI specification that is to be stored in docs/openapi.json."""

import json
from pathlib import Path
from typing import Any

import pytest
import requests
from fastapi.testclient import TestClient

from configuration import configuration

# Strategy:
# - Load the OpenAPI document from docs/openapi.json and from endpoint handler
# - Validate critical structure based on the PR diff:
#   * openapi version, info, servers
#   * presence of paths/methods and key response codes
#   * presence and key attributes of important component schemas (enums, required fields)

OPENAPI_FILE = "docs/openapi.json"
URL = "/openapi.json"


def _load_openapi_spec_from_file() -> dict[str, Any]:
    """Load OpenAPI specification from configured path.

    Load and return the OpenAPI JSON document from the configured file path.

    If the configured file is present, its contents are parsed as JSON and
    returned as a dictionary.
    If the file is missing, the running test is failed via pytest.fail.

    Returns:
        spec (dict[str, Any]): Parsed OpenAPI specification.

    Raises:
        AssertionError: Causes the test to fail through pytest.fail when the file is not found.
    """
    path = Path(OPENAPI_FILE)
    if path.is_file():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    pytest.fail("OpenAPI spec not found")
    return {}


def _load_openapi_spec_from_url() -> dict[str, Any]:
    """Load OpenAPI specification from URL.

    Retrieve the OpenAPI specification by requesting the application's /openapi.json endpoint.

    Returns:
        dict[str, Any]: The parsed OpenAPI specification as a dictionary.
    """
    configuration_filename = "tests/configuration/lightspeed-stack-proper-name.yaml"
    cfg = configuration
    cfg.load_configuration(configuration_filename)
    from app.main import app  # pylint: disable=C0415

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == requests.codes.ok  # pylint: disable=no-member

    # this line ensures that response payload contains proper JSON
    payload = response.json()
    assert payload is not None, "Incorrect response"

    return payload


@pytest.fixture(scope="module", name="spec_from_file")
def open_api_spec_from_file() -> dict[str, Any]:
    """Fixture containing OpenAPI specification represented as a dictionary.

    Provides the parsed OpenAPI specification as a dictionary for tests.

    Returns:
        openapi_spec (dict[str, Any]): The OpenAPI document parsed from docs/openapi.json.
    """
    return _load_openapi_spec_from_file()


@pytest.fixture(scope="module", name="spec_from_url")
def open_api_spec_from_url() -> dict[str, Any]:
    """Fixture containing OpenAPI specification represented as a dictionary.

    Provides the OpenAPI specification loaded from the running application's
    /openapi.json endpoint.

    Returns:
        dict: The OpenAPI document parsed into a dictionary.
    """
    return _load_openapi_spec_from_url()


def _check_openapi_top_level_info(spec: dict[str, Any]) -> None:
    """Check all top level informations stored in OpenAPI specification.

    Checks that the OpenAPI version, info section (title and version), contact, and license
    (name and URL) match the expected values used by the project.

    Parameters:
        spec (dict): Parsed OpenAPI specification document.

    Raises:
        AssertionError: If any required top-level field is missing or does not
        match the expected value.
    """
    assert spec.get("openapi") == "3.1.0"

    info = spec.get("info") or {}
    assert info.get("title") == "Lightspeed Core Service (LCS) service - OpenAPI"
    assert "version" in info

    contact = info.get("contact") or {}
    assert contact is not None

    license_info = info.get("license") or {}
    assert license_info.get("name") == "Apache 2.0"
    assert "apache.org/licenses" in (license_info.get("url") or "")


def _check_server_section_present(spec: dict[str, Any]) -> None:
    """Check if the servers section stored in OpenAPI specification.

    Parameters:
        spec (dict[str, Any]): Parsed OpenAPI specification.

    Raises:
        AssertionError: If the 'servers' field is missing, not a list, or empty.
    """
    servers = spec.get("servers")
    assert isinstance(servers, list) and servers, "servers must be a non-empty list"


def _check_paths_and_responses_exist(
    spec: dict[str, Any], path: str, method: str, expected_codes: set[str]
) -> None:
    """Checks if the specified paths and responses exist in the API specification.

    Parameters:
         spec (dict): The API specification.
         path (str): The API endpoint path to check.
         method (str): The HTTP method to check.
         expected_codes (set[str]): The set of expected HTTP status codes.

     Raises:
         AssertionError: If the path, method, or any of the expected response codes are missing.
    """
    paths = spec.get("paths") or {}
    assert path in paths, f"Missing path: {path}"
    op = (paths[path] or {}).get(method)
    assert isinstance(op, dict), f"Missing method {method.upper()} for path {path}"
    responses = op.get("responses") or {}
    got_codes = set(responses.keys())
    for code in expected_codes:
        assert (
            code in got_codes
        ), f"Missing response code {code} for {method.upper()} {path}"


def test_openapi_top_level_info_from_file(spec_from_file: dict[str, Any]) -> None:
    """Test all top level informations stored in OpenAPI specification.

    Asserts that the OpenAPI version, info (title and version), contact, and
    license fields meet the repository's expected values.

    Parameters:
        spec_from_file (dict[str, Any]): OpenAPI specification dictionary
        loaded from docs/openapi.json.
    """
    _check_openapi_top_level_info(spec_from_file)


def test_openapi_top_level_info_from_url(spec_from_url: dict[str, Any]) -> None:
    """Test all top level informations stored in OpenAPI specification.

    Asserts that the OpenAPI version, info section (including title, version,
    and contact), and license (name and URL) meet the project's expectations
    used by the tests.

    Parameters:
        spec_from_url (dict[str, Any]): OpenAPI document parsed from the
        application's /openapi.json endpoint.
    """
    _check_openapi_top_level_info(spec_from_url)


def test_servers_section_present_from_file(spec_from_file: dict[str, Any]) -> None:
    """Test the servers section stored in OpenAPI specification."""
    _check_server_section_present(spec_from_file)


def test_servers_section_present_from_url(spec_from_url: dict[str, Any]) -> None:
    """Test the servers section stored in OpenAPI specification."""
    _check_server_section_present(spec_from_url)


@pytest.mark.parametrize(
    "path,method,expected_codes",
    [
        ("/", "get", {"200"}),
        ("/v1/info", "get", {"200", "401", "403", "503"}),
        ("/v1/models", "get", {"200", "401", "403", "500", "503"}),
        ("/v1/tools", "get", {"200", "401", "403", "500", "503"}),
        ("/v1/shields", "get", {"200", "401", "403", "500", "503"}),
        ("/v1/providers", "get", {"200", "401", "403", "500", "503"}),
        (
            "/v1/providers/{provider_id}",
            "get",
            {"200", "401", "403", "404", "500", "503"},
        ),
        ("/v1/rags", "get", {"200", "401", "403", "500", "503"}),
        (
            "/v1/rags/{rag_id}",
            "get",
            {"200", "401", "403", "404", "500", "503"},
        ),
        ("/v1/query", "post", {"200", "401", "403", "404", "422", "429", "500", "503"}),
        (
            "/v1/streaming_query",
            "post",
            {"200", "401", "403", "404", "422", "429", "500", "503"},
        ),
        ("/v1/config", "get", {"200", "401", "403", "500"}),
        ("/v1/feedback", "post", {"200", "401", "403", "404", "500"}),
        ("/v1/feedback/status", "get", {"200"}),
        ("/v1/feedback/status", "put", {"200", "401", "403", "500"}),
        ("/v1/conversations", "get", {"200", "401", "403", "500", "503"}),
        (
            "/v1/conversations/{conversation_id}",
            "get",
            {"200", "400", "401", "403", "404", "500", "503"},
        ),
        (
            "/v1/conversations/{conversation_id}",
            "delete",
            {"200", "400", "401", "403", "500", "503"},
        ),
        ("/v2/conversations", "get", {"200", "401", "403", "500"}),
        (
            "/v2/conversations/{conversation_id}",
            "get",
            {"200", "400", "401", "403", "404", "500"},
        ),
        (
            "/v2/conversations/{conversation_id}",
            "delete",
            {"200", "400", "401", "403", "500"},
        ),
        (
            "/v2/conversations/{conversation_id}",
            "put",
            {"200", "400", "401", "403", "404", "500"},
        ),
        ("/readiness", "get", {"200", "401", "403", "503"}),
        ("/liveness", "get", {"200", "401", "403"}),
        ("/authorized", "post", {"200", "401", "403"}),
        ("/metrics", "get", {"200", "401", "403", "500", "503"}),
    ],
)
def test_paths_and_responses_exist_from_file(
    spec_from_file: dict, path: str, method: str, expected_codes: set[str]
) -> None:
    """Tests all paths defined in OpenAPI specification.

    Verify that the given path and HTTP method are defined in the provided
    OpenAPI specification and that the operation contains all expected response
    status codes.

    Parameters:
        spec_from_file (dict): OpenAPI specification document loaded from the local file.
        path (str): API path to check (e.g., "/items/{id}").
        method (str): HTTP method to check for the path (e.g., "get", "post").
        expected_codes (set[str]): Set of expected HTTP response status codes
        as strings (e.g., {"200", "404"}).
    """
    _check_paths_and_responses_exist(spec_from_file, path, method, expected_codes)


@pytest.mark.parametrize(
    "path,method,expected_codes",
    [
        ("/", "get", {"200", "401", "403"}),
        ("/v1/info", "get", {"200", "401", "403", "503"}),
        ("/v1/models", "get", {"200", "401", "403", "500", "503"}),
        ("/v1/tools", "get", {"200", "401", "403", "500", "503"}),
        ("/v1/shields", "get", {"200", "401", "403", "500", "503"}),
        ("/v1/providers", "get", {"200", "401", "403", "500", "503"}),
        (
            "/v1/providers/{provider_id}",
            "get",
            {"200", "401", "403", "404", "500", "503"},
        ),
        ("/v1/rags", "get", {"200", "401", "403", "500", "503"}),
        (
            "/v1/rags/{rag_id}",
            "get",
            {"200", "401", "403", "404", "500", "503"},
        ),
        ("/v1/query", "post", {"200", "401", "403", "404", "422", "429", "500", "503"}),
        (
            "/v1/streaming_query",
            "post",
            {"200", "401", "403", "404", "422", "429", "500", "503"},
        ),
        ("/v1/config", "get", {"200", "401", "403", "500"}),
        ("/v1/feedback", "post", {"200", "401", "403", "404", "500"}),
        ("/v1/feedback/status", "get", {"200"}),
        ("/v1/feedback/status", "put", {"200", "401", "403", "500"}),
        ("/v1/conversations", "get", {"200", "401", "403", "500", "503"}),
        (
            "/v1/conversations/{conversation_id}",
            "get",
            {"200", "400", "401", "403", "404", "500", "503"},
        ),
        (
            "/v1/conversations/{conversation_id}",
            "delete",
            {"200", "400", "401", "403", "500", "503"},
        ),
        ("/v2/conversations", "get", {"200", "401", "403", "500"}),
        (
            "/v2/conversations/{conversation_id}",
            "get",
            {"200", "400", "401", "403", "404", "500"},
        ),
        (
            "/v2/conversations/{conversation_id}",
            "delete",
            {"200", "400", "401", "403", "500"},
        ),
        (
            "/v2/conversations/{conversation_id}",
            "put",
            {"200", "400", "401", "403", "404", "500"},
        ),
        ("/readiness", "get", {"200", "401", "403", "503"}),
        ("/liveness", "get", {"200", "401", "403"}),
        ("/authorized", "post", {"200", "401", "403"}),
        ("/metrics", "get", {"200", "401", "403", "500", "503"}),
    ],
)
def test_paths_and_responses_exist_from_url(
    spec_from_url: dict, path: str, method: str, expected_codes: set[str]
) -> None:
    """Tests all paths defined in OpenAPI specification.

    Verify that the OpenAPI spec served at /openapi.json contains the given
    path and HTTP method and that the operation declares the specified response
    status codes.

    Parameters:
        path (str): OpenAPI path string to check (for example, "/items/{id}").
        method (str): HTTP method name for the operation to check (e.g., "get",
        "post"); case-insensitive.
        expected_codes (set[str]): Set of response status code strings expected
        to be present for the operation (for example, {"200", "404"}).
    """
    _check_paths_and_responses_exist(spec_from_url, path, method, expected_codes)
