"""Integration tests for Red Hat Identity authentication."""

# pylint: disable=redefined-outer-name

import base64
import json
import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from configuration import configuration


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create test client for FastAPI app with RH Identity config.

    Provides a TestClient for the FastAPI application configured with the RH
    Identity test configuration.

    Yields:
        TestClient: A test client instance for the FastAPI app.
    """
    # Save original env var if it exists
    original_config = os.environ.get("LIGHTSPEED_STACK_CONFIG_PATH")

    # Set config path before importing app
    os.environ["LIGHTSPEED_STACK_CONFIG_PATH"] = (
        "tests/configuration/rh-identity-config.yaml"
    )

    # Load the configuration
    configuration.load_configuration("tests/configuration/rh-identity-config.yaml")

    # Import app after configuration is loaded
    from app.main import app  # pylint: disable=import-outside-toplevel

    yield TestClient(app)

    # Restore original env var
    if original_config:
        os.environ["LIGHTSPEED_STACK_CONFIG_PATH"] = original_config
    else:
        os.environ.pop("LIGHTSPEED_STACK_CONFIG_PATH", None)


@pytest.fixture
def user_identity_json() -> dict:
    """Fixture providing valid User identity JSON."""
    return {
        "identity": {
            "account_number": "123",
            "org_id": "321",
            "type": "User",
            "user": {
                "user_id": "test-user-123",
                "username": "testuser@redhat.com",
                "is_org_admin": False,
            },
        },
        "entitlements": {
            "rhel": {"is_entitled": True, "is_trial": False},
            "ansible": {"is_entitled": True, "is_trial": False},
            "openshift": {"is_entitled": False, "is_trial": True},
        },
    }


@pytest.fixture
def system_identity_json() -> dict:
    """Fixture providing valid System identity JSON.

    Provide a valid RH Identity "System" payload suitable for tests.

    Returns:
        dict: JSON with keys:
            - "identity": contains "account_number", "org_id", "type" set to
              "System", and "system" with "cn".
            - "entitlements": contains "rhel" with "is_entitled" and "is_trial" boolean flags.
    """
    return {
        "identity": {
            "account_number": "456",
            "org_id": "654",
            "type": "System",
            "system": {"cn": "c87dcb4c-8af1-40dd-878e-60c744edddd0"},
        },
        "entitlements": {
            "rhel": {"is_entitled": True, "is_trial": False},
        },
    }


def encode_identity(identity_json: dict) -> str:
    """Encode identity JSON to base64.

    Parameters:
        identity_json (dict): JSON-serializable identity payload to encode.

    Returns:
        str: Base64-encoded UTF-8 string representation of the JSON payload.
    """
    json_str = json.dumps(identity_json)
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


class TestRHIdentityIntegration:
    """Integration test suite for RH Identity authentication."""

    def test_valid_user_identity(
        self, client: TestClient, user_identity_json: dict
    ) -> None:
        """Test successful request with valid User identity.

        Verify that a GET to /api/v1/conversations with a valid User RH
        Identity is accepted.

        Sends the provided User identity encoded in the `x-rh-identity` header
        and asserts the response status code is `200` (success) or `404` (no
        conversations).
        """
        headers = {"x-rh-identity": encode_identity(user_identity_json)}

        response = client.get("/api/v1/conversations", headers=headers)

        # Should succeed (200) or return empty conversations list
        assert response.status_code in [200, 404]

    def test_valid_system_identity(
        self, client: TestClient, system_identity_json: dict
    ) -> None:
        """Test successful request with valid System identity."""
        headers = {"x-rh-identity": encode_identity(system_identity_json)}

        response = client.get("/api/v1/conversations", headers=headers)

        # Should succeed (200) or return empty conversations list
        assert response.status_code in [200, 404]
