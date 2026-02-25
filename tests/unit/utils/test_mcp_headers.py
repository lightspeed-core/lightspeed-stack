"""Unit tests for MCP headers utility functions."""

from pytest_mock import MockerFixture
import pytest

from fastapi import Request

from models.config import ModelContextProtocolServer
from utils import mcp_headers
from utils.mcp_headers import extract_propagated_headers


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
        )
        result = extract_propagated_headers(server, {})
        assert not result

    def test_case_insensitive_lookup(self) -> None:
        """Test that header lookup is case-insensitive."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
            headers=["X-Rh-Identity"],
        )
        # FastAPI/Starlette lowercases header names internally
        request_headers = {"x-rh-identity": "identity-value"}
        result = extract_propagated_headers(server, request_headers)
        assert result == {"X-Rh-Identity": "identity-value"}

    def test_no_headers_field_configured(self) -> None:
        """Test server with no headers allowlist configured (default empty)."""
        server = ModelContextProtocolServer(
            name="rbac",
            url="http://rbac:8080",
        )
        request_headers = {"x-rh-identity": "identity-value"}
        result = extract_propagated_headers(server, request_headers)
        assert not result
