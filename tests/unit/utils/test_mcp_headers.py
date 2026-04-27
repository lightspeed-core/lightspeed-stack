"""Unit tests for MCP headers utility functions."""

from typing import Optional

import pytest
from fastapi import Request
from pytest_mock import MockerFixture

import constants
from models.config import ModelContextProtocolServer
from utils import mcp_headers
from utils.mcp_headers import (
    build_server_headers,
    extract_propagated_headers,
    find_unresolved_auth_headers,
)


def test_extract_mcp_headers_empty_headers(mocker: MockerFixture) -> None:
    """Test the extract_mcp_headers function for request without any headers."""
    request = mocker.Mock(spec=Request)
    # no headers
    request.headers = {}

    result = mcp_headers.extract_mcp_headers(request)
    assert result == {}


def test_extract_mcp_headers_mcp_headers_empty(mocker: MockerFixture) -> None:
    """Test the extract_mcp_headers function for request with empty MCP-HEADERS header."""
    request = mocker.Mock(spec=Request)
    # empty MCP-HEADERS
    request.headers = {"MCP-HEADERS": ""}

    # empty dict should be returned
    result = mcp_headers.extract_mcp_headers(request)
    assert result == {}


def test_extract_mcp_headers_valid_mcp_header(mocker: MockerFixture) -> None:
    """Test the extract_mcp_headers function for request with valid MCP-HEADERS header."""
    request = mocker.Mock(spec=Request)
    # valid MCP-HEADERS
    request.headers = {"MCP-HEADERS": '{"http://www.redhat.com": {"auth": "token123"}}'}

    result = mcp_headers.extract_mcp_headers(request)

    expected = {"http://www.redhat.com": {"auth": "token123"}}
    assert result == expected


def test_extract_mcp_headers_valid_mcp_headers(mocker: MockerFixture) -> None:
    """Test the extract_mcp_headers function for request with valid MCP-HEADERS headers."""
    request = mocker.Mock(spec=Request)
    # valid MCP-HEADERS
    header1 = '"http://www.redhat.com": {"auth": "token123"}'
    header2 = '"http://www.example.com": {"auth": "tokenXYZ"}'

    request.headers = {"MCP-HEADERS": f"{{{header1}, {header2}}}"}

    result = mcp_headers.extract_mcp_headers(request)

    expected = {
        "http://www.redhat.com": {"auth": "token123"},
        "http://www.example.com": {"auth": "tokenXYZ"},
    }
    assert result == expected


def test_extract_mcp_headers_invalid_json_mcp_header(mocker: MockerFixture) -> None:
    """Test the extract_mcp_headers function for request with invalid MCP-HEADERS header."""
    request = mocker.Mock(spec=Request)
    # invalid MCP-HEADERS - not a JSON
    request.headers = {"MCP-HEADERS": "this-is-invalid"}

    # empty dict should be returned
    result = mcp_headers.extract_mcp_headers(request)
    assert result == {}


def test_extract_mcp_headers_invalid_mcp_header_type(mocker: MockerFixture) -> None:
    """Test the extract_mcp_headers function for request with invalid MCP-HEADERS header type."""
    request = mocker.Mock(spec=Request)
    # invalid MCP-HEADERS - not a dict
    request.headers = {"MCP-HEADERS": "[]"}

    # empty dict should be returned
    result = mcp_headers.extract_mcp_headers(request)
    assert result == {}


def test_extract_mcp_headers_invalid_mcp_header_null_value(
    mocker: MockerFixture,
) -> None:
    """Test the extract_mcp_headers function for request with invalid MCP-HEADERS header type."""
    request = mocker.Mock(spec=Request)
    # invalid MCP-HEADERS - not a dict
    request.headers = {"MCP-HEADERS": "null"}

    # empty dict should be returned
    result = mcp_headers.extract_mcp_headers(request)
    assert result == {}


@pytest.mark.asyncio
async def test_mcp_headers_dependency_empty_headers(mocker: MockerFixture) -> None:
    """Test the mcp_headers_dependency function for request with empty MCP-HEADERS header."""
    request = mocker.Mock(spec=Request)
    # empty MCP-HEADERS
    request.headers = {"MCP-HEADERS": ""}

    # empty dict should be returned
    result = await mcp_headers.mcp_headers_dependency(request)
    assert result == {}


@pytest.mark.asyncio
async def test_mcp_headers_dependency_mcp_headers_empty(mocker: MockerFixture) -> None:
    """Test the mcp_headers_dependency function for request with empty MCP-HEADERS header."""
    request = mocker.Mock(spec=Request)
    # empty MCP-HEADERS
    request.headers = {"MCP-HEADERS": ""}

    # empty dict should be returned
    result = await mcp_headers.mcp_headers_dependency(request)
    assert result == {}


@pytest.mark.asyncio
async def test_mcp_headers_dependency_valid_mcp_header(mocker: MockerFixture) -> None:
    """Test the mcp_headers_dependency function for request with valid MCP-HEADERS header."""
    request = mocker.Mock(spec=Request)
    # valid MCP-HEADERS
    request.headers = {"MCP-HEADERS": '{"http://www.redhat.com": {"auth": "token123"}}'}

    result = await mcp_headers.mcp_headers_dependency(request)

    expected = {"http://www.redhat.com": {"auth": "token123"}}
    assert result == expected


@pytest.mark.asyncio
async def test_mcp_headers_dependency_valid_mcp_headers(mocker: MockerFixture) -> None:
    """Test the mcp_headers_dependency function for request with valid MCP-HEADERS headers."""
    request = mocker.Mock(spec=Request)
    # valid MCP-HEADERS
    header1 = '"http://www.redhat.com": {"auth": "token123"}'
    header2 = '"http://www.example.com": {"auth": "tokenXYZ"}'

    request.headers = {"MCP-HEADERS": f"{{{header1}, {header2}}}"}

    result = await mcp_headers.mcp_headers_dependency(request)

    expected = {
        "http://www.redhat.com": {"auth": "token123"},
        "http://www.example.com": {"auth": "tokenXYZ"},
    }
    assert result == expected


@pytest.mark.asyncio
async def test_mcp_headers_dependency_invalid_json_mcp_header(
    mocker: MockerFixture,
) -> None:
    """Test the mcp_headers_dependency function for request with invalid MCP-HEADERS header."""
    request = mocker.Mock(spec=Request)
    # invalid MCP-HEADERS - not a JSON
    request.headers = {"MCP-HEADERS": "this-is-invalid"}

    # empty dict should be returned
    result = await mcp_headers.mcp_headers_dependency(request)
    assert result == {}


@pytest.mark.asyncio
async def test_mcp_headers_dependency_invalid_mcp_header_type(
    mocker: MockerFixture,
) -> None:
    """Test the mcp_headers_dependency function for request with invalid MCP-HEADERS header type."""
    request = mocker.Mock(spec=Request)
    # invalid MCP-HEADERS - not a dict
    request.headers = {"MCP-HEADERS": "[]"}

    # empty dict should be returned
    result = await mcp_headers.mcp_headers_dependency(request)
    assert result == {}


@pytest.mark.asyncio
async def test_mcp_headers_dependency_invalid_mcp_header_null_value(
    mocker: MockerFixture,
) -> None:
    """Test the mcp_headers_dependency function for request with invalid MCP-HEADERS header type."""
    request = mocker.Mock(spec=Request)
    # invalid MCP-HEADERS - not a dict
    request.headers = {"MCP-HEADERS": "null"}

    # empty dict should be returned
    result = await mcp_headers.mcp_headers_dependency(request)
    assert result == {}


class TestExtractPropagatedHeaders:
    """Test cases for extract_propagated_headers function."""

    def test_extracts_matching_headers(self) -> None:
        """Test that allowlisted headers present in the request are extracted."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            headers=["x-rh-identity", "x-request-id"],
            provider_id="xyzzy",
        )
        request_headers = {
            "x-rh-identity": "encoded-identity-value",
            "x-request-id": "req-123",
            "content-type": "application/json",
        }
        result = extract_propagated_headers(server, request_headers)
        assert result == {
            "x-rh-identity": "encoded-identity-value",
            "x-request-id": "req-123",
        }

    def test_skips_missing_headers(self) -> None:
        """Test that allowlisted headers missing from the request are omitted."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            headers=["x-rh-identity", "x-missing-header"],
            provider_id="xyzzy",
        )
        request_headers = {
            "x-rh-identity": "identity-value",
        }
        result = extract_propagated_headers(server, request_headers)
        assert result == {"x-rh-identity": "identity-value"}

    def test_empty_allowlist(self) -> None:
        """Test that an empty allowlist returns no headers."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            headers=[],
            provider_id="xyzzy",
        )
        request_headers = {"x-rh-identity": "identity-value"}
        result = extract_propagated_headers(server, request_headers)
        assert not result

    def test_empty_request_headers(self) -> None:
        """Test that empty request headers returns no headers."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            headers=["x-rh-identity"],
            provider_id="xyzzy",
        )
        result = extract_propagated_headers(server, {})
        assert not result

    def test_case_insensitive_lookup(self) -> None:
        """Test that header lookup is case-insensitive."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            headers=["X-Rh-Identity"],
            provider_id="xyzzy",
        )
        # FastAPI/Starlette lowercases header names internally
        request_headers = {"x-rh-identity": "identity-value"}
        result = extract_propagated_headers(server, request_headers)
        assert result == {"X-Rh-Identity": "identity-value"}

    def test_case_insensitive_lookup_mixed_case_request(self) -> None:
        """Test allowlist lowercase matches uppercase request header in plain dict."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            headers=["x-rh-identity"],
            provider_id="xyzzy",
        )
        # Plain dict with mixed-case keys (not Starlette Headers)
        request_headers = {"X-RH-Identity": "identity-value"}
        result = extract_propagated_headers(server, request_headers)
        assert result == {"x-rh-identity": "identity-value"}

    def test_no_headers_field_configured(self) -> None:
        """Test server with no headers allowlist configured (default empty)."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            provider_id="xyzzy",
        )
        request_headers = {"x-rh-identity": "identity-value"}
        result = extract_propagated_headers(server, request_headers)
        assert not result


class TestFindUnresolvedAuthHeaders:
    """Test cases for find_unresolved_auth_headers function."""

    def test_all_configured_headers_present(self) -> None:
        """Test that an empty list is returned when all configured headers are resolved."""
        configured = {"Authorization": "kubernetes", "X-Api-Key": "/var/secrets/key"}
        resolved = {"Authorization": "Bearer tok", "X-Api-Key": "secret"}
        assert not find_unresolved_auth_headers(configured, resolved)

    def test_missing_header_is_returned(self) -> None:
        """Test that a configured header absent from resolved is returned."""
        configured = {"Authorization": "kubernetes"}
        resolved: dict[str, str] = {}
        assert find_unresolved_auth_headers(configured, resolved) == ["Authorization"]

    def test_partially_resolved_returns_missing(self) -> None:
        """Test that only unresolved headers are returned when some are resolved."""
        configured = {"Authorization": "kubernetes", "X-Api-Key": "/var/secrets/key"}
        resolved = {"Authorization": "Bearer tok"}
        assert find_unresolved_auth_headers(configured, resolved) == ["X-Api-Key"]

    def test_comparison_is_case_insensitive(self) -> None:
        """Test that header name matching is case-insensitive."""
        configured = {"Authorization": "kubernetes"}
        resolved = {"authorization": "Bearer tok"}
        assert not find_unresolved_auth_headers(configured, resolved)

    def test_empty_configured_returns_empty(self) -> None:
        """Test that an empty configured dict returns an empty list."""
        assert not find_unresolved_auth_headers({}, {"Authorization": "Bearer tok"})

    def test_empty_resolved_returns_all_configured(self) -> None:
        """Test that all configured headers are returned when resolved is empty."""
        configured = {"Authorization": "kubernetes", "X-Api-Key": "/path"}
        result = find_unresolved_auth_headers(configured, {})
        assert sorted(result) == ["Authorization", "X-Api-Key"]


class TestBuildServerHeaders:
    """Test cases for build_server_headers function."""

    def _make_server(
        self,
        resolved_auth: Optional[dict[str, str]] = None,
        headers: Optional[list[str]] = None,
    ) -> ModelContextProtocolServer:
        """Create a ModelContextProtocolServer with given auth and allowlist headers."""
        server = ModelContextProtocolServer(
            name="test-server",
            url="http://test:8080",
            provider_id="xyzzy",
            headers=headers or [],
        )
        object.__setattr__(
            server, "_resolved_authorization_headers", resolved_auth or {}
        )
        return server

    def test_static_resolved_header_is_added(self) -> None:
        """Test that a statically resolved header value is included in the result."""
        server = self._make_server(resolved_auth={"Authorization": "static-token"})
        result = build_server_headers(server, {}, None, None)
        assert result == {"Authorization": "static-token"}

    def test_kubernetes_token_resolves_to_bearer(self) -> None:
        """Test that a kubernetes keyword resolves to a Bearer token."""
        server = self._make_server(
            resolved_auth={"Authorization": constants.MCP_AUTH_KUBERNETES}
        )
        result = build_server_headers(server, {}, None, token="my-k8s-token")
        assert result == {"Authorization": "Bearer my-k8s-token"}

    def test_kubernetes_without_token_is_skipped(self) -> None:
        """Test that a kubernetes keyword with no token produces no header."""
        server = self._make_server(
            resolved_auth={"Authorization": constants.MCP_AUTH_KUBERNETES}
        )
        result = build_server_headers(server, {}, None, token=None)
        assert not result

    def test_client_keyword_is_skipped(self) -> None:
        """Test that a client keyword is skipped (value comes from client_headers)."""
        server = self._make_server(
            resolved_auth={"Authorization": constants.MCP_AUTH_CLIENT}
        )
        result = build_server_headers(server, {}, None, None)
        assert not result

    def test_oauth_keyword_is_skipped(self) -> None:
        """Test that an oauth keyword is skipped (value comes from client_headers)."""
        server = self._make_server(
            resolved_auth={"Authorization": constants.MCP_AUTH_OAUTH}
        )
        result = build_server_headers(server, {}, None, None)
        assert not result

    def test_client_headers_take_priority_over_resolved(self) -> None:
        """Test that a client-supplied header is not overwritten by a resolved value."""
        server = self._make_server(resolved_auth={"Authorization": "static-token"})
        result = build_server_headers(
            server, {"Authorization": "client-token"}, None, None
        )
        assert result == {"Authorization": "client-token"}

    def test_client_headers_priority_is_case_insensitive(self) -> None:
        """Test that case-insensitive comparison prevents overwriting client headers."""
        server = self._make_server(resolved_auth={"authorization": "static-token"})
        result = build_server_headers(
            server, {"Authorization": "client-token"}, None, None
        )
        assert result == {"Authorization": "client-token"}

    def test_propagated_request_headers_are_added(self) -> None:
        """Test that allowlisted request headers are propagated."""
        server = self._make_server(headers=["x-rh-identity"])
        result = build_server_headers(
            server, {}, {"x-rh-identity": "my-identity"}, None
        )
        assert result == {"x-rh-identity": "my-identity"}

    def test_existing_header_blocks_propagation(self) -> None:
        """Test that a propagated header does not overwrite an already-set header."""
        server = self._make_server(headers=["x-rh-identity"])
        result = build_server_headers(
            server,
            {"x-rh-identity": "client-identity"},
            {"x-rh-identity": "request-identity"},
            None,
        )
        assert result == {"x-rh-identity": "client-identity"}

    def test_no_headers_no_config_returns_empty(self) -> None:
        """Test that a server with no applicable headers returns an empty dict."""
        server = self._make_server()
        result = build_server_headers(server, {}, None, None)
        assert not result

    def test_multiple_sources_are_merged(self) -> None:
        """Test that all header sources are combined into one dictionary."""
        server = self._make_server(
            resolved_auth={
                "Authorization": constants.MCP_AUTH_KUBERNETES,
                "X-Api-Key": "static-key",
            },
            headers=["x-request-id"],
        )
        result = build_server_headers(
            server,
            {"X-Client-Header": "client-value"},
            {"x-request-id": "req-123"},
            token="k8s-token",
        )
        assert result == {
            "X-Client-Header": "client-value",
            "Authorization": "Bearer k8s-token",
            "X-Api-Key": "static-key",
            "x-request-id": "req-123",
        }
