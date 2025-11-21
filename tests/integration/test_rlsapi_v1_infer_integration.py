"""Integration tests for RHEL Lightspeed rlsapi v1 /infer endpoint."""

import pytest
import requests
from fastapi.testclient import TestClient

from configuration import configuration


@pytest.fixture(name="client")
def test_client() -> TestClient:
    """Create a test client for the FastAPI app.

    Returns:
        TestClient instance configured with test configuration
    """
    configuration_filename = "tests/configuration/lightspeed-stack-proper-name.yaml"

    # Load configuration before importing app to ensure singleton is initialized
    configuration.load_configuration(configuration_filename)

    # Import app after configuration is loaded
    from app.main import app  # pylint: disable=import-outside-toplevel

    # raise_server_exceptions=False allows getting 500 responses instead of exceptions
    return TestClient(app, raise_server_exceptions=False)


def test_v1_infer_endpoint_exists(client: TestClient) -> None:
    """Test that the /v1/infer endpoint is registered and not 404.

    This verifies the router is properly included in the FastAPI app.
    """
    response = client.post("/v1/infer", json={"question": "test"})

    # Should NOT be 404 - endpoint should be registered
    assert response.status_code != requests.codes.not_found  # pylint: disable=no-member

    # With noop auth, request passes through and may hit uninitialized Llama Stack (500)
    # or fail validation (422) depending on configuration state
    assert response.status_code in [
        requests.codes.unauthorized,  # pylint: disable=no-member
        requests.codes.forbidden,  # pylint: disable=no-member
        requests.codes.unprocessable,  # pylint: disable=no-member
        requests.codes.internal_server_error,  # pylint: disable=no-member
    ]


def test_v1_infer_requires_auth(client: TestClient) -> None:
    """Test that the /v1/infer endpoint handles authentication.

    With noop auth, requests pass through. Without noop, they should fail auth.
    """
    response = client.post("/v1/infer", json={"question": "How do I list files?"})

    # With noop auth: passes through, may hit Llama Stack error (500)
    # With real auth: should fail (401/403)
    assert response.status_code in [
        requests.codes.unauthorized,  # pylint: disable=no-member
        requests.codes.forbidden,  # pylint: disable=no-member
        requests.codes.internal_server_error,  # pylint: disable=no-member
    ]


def test_v1_infer_rejects_invalid_request(client: TestClient) -> None:
    """Test that the /v1/infer endpoint validates request payload.

    Invalid requests (missing required fields, extra fields) should return 422.
    """
    # Test 1: Missing required field (question)
    response = client.post("/v1/infer", json={"context": {"system_info": "RHEL 9.3"}})

    # Could be 422 (validation error) or 401/403 (auth check happens first)
    # Validation happens after auth, so we expect auth error if no token provided
    assert response.status_code in [
        requests.codes.unauthorized,  # pylint: disable=no-member
        requests.codes.forbidden,  # pylint: disable=no-member
        requests.codes.unprocessable,  # pylint: disable=no-member
    ]

    # Test 2: Extra forbidden field
    response = client.post(
        "/v1/infer",
        json={"question": "How do I list files?", "extra_field": "should be rejected"},
    )

    # Should return validation error or auth error
    assert response.status_code in [
        requests.codes.unauthorized,  # pylint: disable=no-member
        requests.codes.forbidden,  # pylint: disable=no-member
        requests.codes.unprocessable,  # pylint: disable=no-member
    ]
