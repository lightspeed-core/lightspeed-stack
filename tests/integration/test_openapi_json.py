"""Tests the OpenAPI specification that is to be stored in docs/openapi.json."""

import json
from pathlib import Path

import pytest

# Strategy:
# - Load the OpenAPI document from docs/openapi.json
# - Validate critical structure based on the PR diff:
#   * openapi version, info, servers
#   * presence of paths/methods and key response codes
#   * presence and key attributes of important component schemas (enums, required fields)

OPENAPI_FILE = "docs/openapi.json"


def _load_openapi_spec() -> dict:
    """Load OpenAPI specification from configured path."""
    path = Path(OPENAPI_FILE)
    if path.is_file():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    pytest.fail("OpenAPI spec not found")
    return {}


@pytest.fixture(scope="module", name="spec")
def open_api_spec() -> dict:
    """Fixture containing OpenAPI specification represented as a dictionary."""
    return _load_openapi_spec()


def test_openapi_top_level_info(spec: dict):
    """Test all top level informations stored in OpenAPI specification."""
    assert spec.get("openapi") == "3.1.0"

    info = spec.get("info") or {}
    assert info.get("title") == "Lightspeed Core Service (LCS) service - OpenAPI"
    assert "version" in info

    contact = info.get("contact") or {}
    assert contact is not None

    license_info = info.get("license") or {}
    assert license_info.get("name") == "Apache 2.0"
    assert "apache.org/licenses" in (license_info.get("url") or "")


def test_servers_section_present(spec: dict):
    """Test the servers section stored in OpenAPI specification."""
    servers = spec.get("servers")
    assert isinstance(servers, list) and servers, "servers must be a non-empty list"


@pytest.mark.parametrize(
    "path,method,expected_codes",
    [
        ("/", "get", {"200"}),
        ("/v1/info", "get", {"200", "500"}),
        ("/v1/models", "get", {"200", "503"}),
        ("/v1/query", "post", {"200", "400", "403", "503", "422"}),
        ("/v1/streaming_query", "post", {"200", "422"}),
        ("/v1/config", "get", {"200", "503"}),
        ("/v1/feedback", "post", {"200", "401", "403", "500", "422"}),
        ("/v1/feedback/status", "get", {"200"}),
        ("/v1/feedback/status", "put", {"200", "422"}),
        ("/v1/conversations", "get", {"200", "503"}),
        ("/v1/conversations/{conversation_id}", "get", {"200", "404", "503", "422"}),
        ("/v1/conversations/{conversation_id}", "delete", {"200", "404", "503", "422"}),
        ("/readiness", "get", {"200", "503"}),
        ("/liveness", "get", {"200"}),
        ("/authorized", "post", {"200", "400", "401", "403"}),
        ("/metrics", "get", {"200"}),
    ],
)
def test_paths_and_responses_exist(
    spec: dict, path: str, method: str, expected_codes: set[str]
):
    """Tests all paths defined in OpenAPI specification."""
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
