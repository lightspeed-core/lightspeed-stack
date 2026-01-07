"""Unit tests for Red Hat Identity authentication module."""

# pylint: disable=redefined-outer-name

import base64
import json
from typing import Optional
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request

from authentication.rh_identity import RHIdentityAuthDependency, RHIdentityData
from constants import NO_USER_TOKEN


@pytest.fixture
def user_identity_data() -> dict:
    """Fixture providing valid User identity data.

    Provide a valid Red Hat identity payload for a User, suitable for unit tests.

    Returns:
        identity_data (dict): A dictionary with two top-level keys:
            - "identity": contains "account_number", "org_id", "type" (set to
              "User"), and "user" (with "user_id", "username", "is_org_admin").
            - "entitlements": maps service names (e.g., "rhel", "ansible",
              "openshift") to entitlement objects with "is_entitled" and
              "is_trial".
    """
    return {
        "identity": {
            "account_number": "123",
            "org_id": "321",
            "type": "User",
            "user": {
                "user_id": "abc123",
                "username": "user@redhat.com",
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
def system_identity_data() -> dict:
    """Fixture providing valid System identity data.

    Provide a sample System identity payload used by tests.

    Returns:
        dict: A System identity dictionary with the following shape:
            - identity: {
                "account_number": str,
                "org_id": str,
                "type": "System",
                "system": {"cn": str}
              }
            - entitlements: mapping of product names to entitlement objects, e.g.
              {"rhel": {"is_entitled": bool, "is_trial": bool}}
    """
    return {
        "identity": {
            "account_number": "123",
            "org_id": "321",
            "type": "System",
            "system": {"cn": "c87dcb4c-8af1-40dd-878e-60c744edddd0"},
        },
        "entitlements": {
            "rhel": {"is_entitled": True, "is_trial": False},
        },
    }


def create_auth_header(identity_data: dict) -> str:
    """Helper to create base64-encoded x-rh-identity header value.

    Create a base64-encoded string suitable for use as an x-rh-identity header from identity data.

    Parameters:
        identity_data (dict): Identity payload (serializable to JSON)
        containing identity, user/system fields, and optional entitlements.

    Returns:
        header_value (str): Base64-encoded JSON string representing the provided identity data.
    """
    json_str = json.dumps(identity_data)
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


def create_request_with_header(header_value: Optional[str]) -> Request:
    """Helper to create mock Request with x-rh-identity header.

    Create a mock FastAPI Request with an `x-rh-identity` header for tests.

    Parameters:
        header_value (Optional[str]): Base64-encoded identity header value to
        set. If `None` or empty, the returned request will have no headers.

    Returns:
        Request: A mocked Request object whose `headers` contains
        `{"x-rh-identity": header_value}` when a value is provided, or an empty
        dict otherwise.
    """
    request = Mock(spec=Request)
    request.headers = {"x-rh-identity": header_value} if header_value else {}
    return request


class TestRHIdentityData:
    """Test suite for RHIdentityData class."""

    def test_user_type_extraction(self, user_identity_data: dict) -> None:
        """Test extraction of User identity fields."""
        rh_identity = RHIdentityData(user_identity_data)

        assert rh_identity.get_user_id() == "abc123"
        assert rh_identity.get_username() == "user@redhat.com"

    def test_system_type_extraction(self, system_identity_data: dict) -> None:
        """Test extraction of System identity fields."""
        rh_identity = RHIdentityData(system_identity_data)

        assert rh_identity.get_user_id() == "c87dcb4c-8af1-40dd-878e-60c744edddd0"
        assert rh_identity.get_username() == "123"

    @pytest.mark.parametrize(
        "service,expected",
        [
            ("rhel", True),  # Entitled service
            ("ansible", True),  # Entitled service
            ("openshift", False),  # Not entitled (is_trial=True)
            ("nonexistent", False),  # Missing service
        ],
    )
    def test_has_entitlement(
        self, user_identity_data: dict, service: str, expected: bool
    ) -> None:
        """Test has_entitlement returns correct result for various services."""
        rh_identity = RHIdentityData(user_identity_data)
        assert rh_identity.has_entitlement(service) is expected

    @pytest.mark.parametrize(
        "services,expected",
        [
            (["rhel", "ansible"], True),  # All entitled
            (["rhel", "openshift"], False),  # One not entitled
            (["openshift", "nonexistent"], False),  # None entitled
        ],
    )
    def test_has_entitlements(
        self, user_identity_data: dict, services: list[str], expected: bool
    ) -> None:
        """Test has_entitlements returns correct result for service lists."""
        rh_identity = RHIdentityData(user_identity_data)
        assert rh_identity.has_entitlements(services) is expected

    @pytest.mark.parametrize(
        "required_entitlements,should_raise,expected_error",
        [
            (["rhel"], False, None),  # Single valid
            (["rhel", "ansible"], False, None),  # Multiple valid
            (None, False, None),  # No requirements
            ([], False, None),  # Empty list
            (
                ["openshift"],
                True,
                "Missing required entitlement: openshift",
            ),  # Single missing
            (
                ["rhel", "ansible", "openshift"],
                True,
                "Missing required entitlement: openshift",
            ),  # Multiple with one missing
        ],
    )
    def test_validate_entitlements(
        self,
        user_identity_data: dict,
        required_entitlements: Optional[list[str]],
        should_raise: bool,
        expected_error: Optional[str],
    ) -> None:
        """Test validate_entitlements with various requirement configurations.

        Verify that RHIdentityData.validate_entitlements enforces required entitlements.

        Creates an RHIdentityData instance from the provided identity
        dictionary and required_entitlements; asserts that calling
        validate_entitlements raises an HTTPException with status code 403
        containing expected_error when should_raise is True, and does not raise
        when should_raise is False.
        """
        rh_identity = RHIdentityData(user_identity_data, required_entitlements)

        if should_raise:
            with pytest.raises(HTTPException) as exc_info:
                rh_identity.validate_entitlements()
            assert exc_info.value.status_code == 403
            assert expected_error is not None
            assert expected_error in str(exc_info.value.detail)
        else:
            # Should not raise
            rh_identity.validate_entitlements()

    @pytest.mark.parametrize(
        "missing_field,expected_error",
        [
            ({"identity": None}, "Missing 'identity' field"),
            ({"identity": {"org_id": "123"}}, "Missing identity 'type' field"),
            (
                {"identity": {"type": "User", "org_id": "123"}},
                "Missing 'user' field for User type",
            ),
            (
                {
                    "identity": {
                        "type": "User",
                        "org_id": "123",
                        "user": {"username": "test"},
                    }
                },
                "Missing 'user_id' in user data",
            ),
            (
                {
                    "identity": {
                        "type": "User",
                        "org_id": "123",
                        "user": {"user_id": "123"},
                    }
                },
                "Missing 'username' in user data",
            ),
            (
                {"identity": {"type": "System", "org_id": "123"}},
                "Missing 'system' field for System type",
            ),
            (
                {"identity": {"type": "System", "org_id": "123", "system": {}}},
                "Missing 'cn' in system data",
            ),
            (
                {
                    "identity": {
                        "type": "System",
                        "org_id": "123",
                        "system": {"cn": "test"},
                    }
                },
                "Missing 'account_number' for System type",
            ),
        ],
    )
    def test_validation_failures(
        self, missing_field: dict, expected_error: str
    ) -> None:
        """Test validation failures for various missing fields."""
        with pytest.raises(HTTPException) as exc_info:
            RHIdentityData(missing_field)

        assert exc_info.value.status_code == 400
        assert expected_error in str(exc_info.value.detail)

    def test_unsupported_identity_type(self) -> None:
        """Test validation fails with unsupported identity type."""
        invalid_data = {"identity": {"type": "Unknown", "org_id": "123"}}

        with pytest.raises(HTTPException) as exc_info:
            RHIdentityData(invalid_data)

        assert exc_info.value.status_code == 400
        assert "Unsupported identity type: Unknown" in str(exc_info.value.detail)


class TestRHIdentityAuthDependency:
    """Test suite for RHIdentityAuthDependency class."""

    @pytest.mark.asyncio
    async def test_user_authentication_success(self, user_identity_data: dict) -> None:
        """Test successful User authentication."""
        auth_dep = RHIdentityAuthDependency()
        header_value = create_auth_header(user_identity_data)
        request = create_request_with_header(header_value)

        user_id, username, _, _ = await auth_dep(request)

        assert user_id == "abc123"
        assert username == "user@redhat.com"

    @pytest.mark.asyncio
    async def test_system_authentication_success(
        self, system_identity_data: dict
    ) -> None:
        """Test successful System authentication."""
        auth_dep = RHIdentityAuthDependency()
        header_value = create_auth_header(system_identity_data)
        request = create_request_with_header(header_value)

        user_id, username, skip_check, token = await auth_dep(request)

        assert user_id == "c87dcb4c-8af1-40dd-878e-60c744edddd0"
        assert username == "123"
        assert skip_check is False
        assert token == NO_USER_TOKEN

    @pytest.mark.asyncio
    async def test_missing_header(self) -> None:
        """Test authentication fails when header is missing."""
        auth_dep = RHIdentityAuthDependency()
        request = create_request_with_header(None)

        with pytest.raises(HTTPException) as exc_info:
            await auth_dep(request)

        assert exc_info.value.status_code == 401
        assert "Missing x-rh-identity header" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_invalid_base64(self) -> None:
        """Test authentication fails with invalid base64."""
        auth_dep = RHIdentityAuthDependency()
        request = create_request_with_header("not-valid-base64!!!")

        with pytest.raises(HTTPException) as exc_info:
            await auth_dep(request)

        assert exc_info.value.status_code == 400
        assert "Invalid base64 encoding" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_invalid_json(self) -> None:
        """Test authentication fails with invalid JSON."""
        auth_dep = RHIdentityAuthDependency()
        invalid_json = base64.b64encode(b"not valid json").decode("utf-8")
        request = create_request_with_header(invalid_json)

        with pytest.raises(HTTPException) as exc_info:
            await auth_dep(request)

        assert exc_info.value.status_code == 400
        assert "Invalid JSON" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "required_entitlements,should_raise,expected_error",
        [
            (["rhel"], False, None),  # Single valid
            (["rhel", "ansible"], False, None),  # Multiple valid
            (None, False, None),  # No requirements
            (
                ["openshift"],
                True,
                "Missing required entitlement: openshift",
            ),  # Single missing
            (
                ["rhel", "ansible", "openshift"],
                True,
                "Missing required entitlement: openshift",
            ),  # Multiple with one missing
        ],
    )
    async def test_entitlement_validation(
        self,
        user_identity_data: dict,
        required_entitlements: Optional[list[str]],
        should_raise: bool,
        expected_error: Optional[str],
    ) -> None:
        """Test authentication with various entitlement requirements."""
        auth_dep = RHIdentityAuthDependency(required_entitlements=required_entitlements)
        header_value = create_auth_header(user_identity_data)
        request = create_request_with_header(header_value)

        if should_raise:
            with pytest.raises(HTTPException) as exc_info:
                await auth_dep(request)
            assert exc_info.value.status_code == 403
            assert expected_error is not None
            assert expected_error in str(exc_info.value.detail)
        else:
            user_id, username, _, _ = await auth_dep(request)
            assert user_id == "abc123"
            assert username == "user@redhat.com"

    @pytest.mark.asyncio
    async def test_no_entitlement_data(self, user_identity_data: dict) -> None:
        """Test authentication succeeds when no entitlements are present in identity data."""
        user_identity_data_no_entitlements = user_identity_data.copy()
        user_identity_data_no_entitlements["entitlements"] = {}

        auth_dep = RHIdentityAuthDependency()
        header_value = create_auth_header(user_identity_data_no_entitlements)
        request = create_request_with_header(header_value)

        user_id, username, _, _ = await auth_dep(request)
        assert user_id == "abc123"
        assert username == "user@redhat.com"
