"""Integration tests for RHEL Lightspeed rlsapi v1 /infer endpoint."""

import pytest
from fastapi.testclient import TestClient

from configuration import configuration


@pytest.fixture(name="client")
def test_client() -> TestClient:
    """Create a test client for the FastAPI app."""
    configuration.load_configuration(
        "tests/configuration/lightspeed-stack-proper-name.yaml"
    )
    from app.main import app  # pylint: disable=import-outside-toplevel

    return TestClient(app, raise_server_exceptions=False)


def test_v1_infer_endpoint_registered(client: TestClient) -> None:
    """Verify /v1/infer endpoint is registered (not 404)."""
    response = client.post("/v1/infer", json={"question": "test"})
    assert response.status_code != 404
