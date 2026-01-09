"""
Pytest tests for the MCP Mock Server.

This test suite verifies the mock server functionality without requiring
the full Lightspeed Stack infrastructure.
"""

# pylint: disable=redefined-outer-name
# pyright: reportAttributeAccessIssue=false

import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from typing import Any

import pytest


@pytest.fixture(scope="module")
def mock_server():
    """Start mock server for testing and stop it after tests complete."""
    http_port = 9000
    https_port = 9001

    print(f"\n🚀 Starting mock server on ports {http_port}/{https_port}...")
    process = subprocess.Popen(
        [sys.executable, "dev-tools/mcp-mock-server/server.py", str(http_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to start
    time.sleep(2)

    # Check if server started successfully
    if process.poll() is not None:
        _, stderr = process.communicate()
        pytest.fail(f"Server failed to start: {stderr.decode('utf-8')}")

    yield {
        "process": process,
        "http_url": f"http://localhost:{http_port}",
        "https_url": f"https://localhost:{https_port}",
    }

    # Cleanup: stop server
    print("\n🛑 Stopping mock server...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def make_request(
    url: str,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    use_https: bool = False,
) -> tuple[int, dict[str, Any] | str]:
    """Make HTTP request and return status code and response."""
    try:
        req_headers = headers or {}
        req_data = None
        if data:
            req_data = json.dumps(data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url, data=req_data, headers=req_headers, method=method
        )

        # For HTTPS with self-signed certs, disable SSL verification
        import ssl  # pylint: disable=import-outside-toplevel

        context = (
            ssl._create_unverified_context()
            if use_https
            else None  # pylint: disable=protected-access
        )

        with urllib.request.urlopen(request, context=context, timeout=5) as response:
            body = response.read().decode("utf-8")
            try:
                return response.status, json.loads(body)
            except json.JSONDecodeError:
                return response.status, body

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, body
    except Exception as e:  # pylint: disable=broad-except
        pytest.fail(f"Request failed: {e}")


def test_http_mcp_list_tools(mock_server):
    """Test the MCP list_tools endpoint over HTTP."""
    status, response = make_request(
        f"{mock_server['http_url']}/mcp/v1/list_tools",
        method="POST",
        data={"test": "data"},
        headers={"Authorization": "Bearer test-token-123"},
    )

    assert status == 200, f"Expected 200 OK, got {status}"
    assert isinstance(response, dict), f"Expected dict, got {type(response)}"
    assert "tools" in response, "Response should contain 'tools' key"
    assert isinstance(response["tools"], list), "Tools should be a list"
    assert len(response["tools"]) == 1, "Should have 1 mock tool"
    assert (
        response["tools"][0]["name"] == "mock_tool"
    ), "Tool name should be 'mock_tool'"


def test_https_mcp_list_tools(mock_server):
    """Test the MCP list_tools endpoint over HTTPS."""
    status, response = make_request(
        f"{mock_server['https_url']}/mcp/v1/list_tools",
        method="POST",
        data={"test": "data"},
        headers={"Authorization": "Bearer test-https-token"},
        use_https=True,
    )

    assert status == 200, f"Expected 200 OK over HTTPS, got {status}"
    assert isinstance(response, dict), f"Expected dict, got {type(response)}"


def test_debug_headers_endpoint(mock_server):
    """Test the debug headers endpoint captures authorization headers."""
    # First, make a request with custom headers
    make_request(
        f"{mock_server['http_url']}/mcp/v1/list_tools",
        method="POST",
        headers={
            "Authorization": "Bearer debug-test-token",
            "X-Custom-Header": "custom-value-123",
        },
    )

    # Now check if headers were captured
    status, response = make_request(f"{mock_server['http_url']}/debug/headers")

    assert status == 200, f"Expected 200 OK, got {status}"
    assert isinstance(response, dict), f"Expected dict, got {type(response)}"

    last_headers = response.get("last_headers", {})
    assert "Authorization" in last_headers, "Authorization header not captured"
    assert (
        last_headers["Authorization"] == "Bearer debug-test-token"
    ), f"Wrong Authorization value: {last_headers.get('Authorization')}"
    assert "X-Custom-Header" in last_headers, "Custom header not captured"
    assert (
        last_headers["X-Custom-Header"] == "custom-value-123"
    ), f"Wrong custom header value: {last_headers.get('X-Custom-Header')}"
    assert "request_count" in response, "request_count not in response"


def test_debug_requests_endpoint(mock_server):
    """Test the debug requests endpoint logs request history."""
    # Make a request
    make_request(
        f"{mock_server['http_url']}/mcp/v1/list_tools",
        method="POST",
        headers={"Authorization": "Bearer request-log-test"},
    )

    # Check request log
    status, response = make_request(f"{mock_server['http_url']}/debug/requests")

    assert status == 200, f"Expected 200 OK, got {status}"
    assert isinstance(response, list), f"Expected list, got {type(response)}"
    assert len(response) > 0, "No requests logged"

    # Type narrowing for the last request
    last_request: dict[str, Any] = response[-1]  # type: ignore[assignment,index]
    assert "timestamp" in last_request, "Request missing timestamp"
    assert "method" in last_request, "Request missing method"
    assert (
        last_request["method"] == "POST"
    ), f"Wrong method: {last_request.get('method')}"
    assert "path" in last_request, "Request missing path"
    assert (
        "/mcp/v1/list_tools" in last_request["path"]
    ), f"Wrong path: {last_request.get('path')}"
    assert "headers" in last_request, "Request missing headers"
    assert isinstance(last_request["headers"], dict), "Headers should be dict"


def test_multiple_authorization_headers(mock_server):
    """Test capturing multiple authorization headers simultaneously."""
    make_request(
        f"{mock_server['http_url']}/mcp/v1/list_tools",
        method="POST",
        headers={
            "Authorization": "Bearer multi-test-token",
            "X-Custom-Auth": "custom-auth-value",
        },
    )

    # Check headers were captured
    status, response = make_request(f"{mock_server['http_url']}/debug/headers")

    assert status == 200, f"Expected 200 OK, got {status}"
    assert isinstance(response, dict), f"Expected dict, got {type(response)}"

    last_headers = response.get("last_headers", {})
    assert "Authorization" in last_headers, "Authorization header not captured"
    assert (
        last_headers["Authorization"] == "Bearer multi-test-token"
    ), f"Wrong Authorization: {last_headers.get('Authorization')}"
    assert "X-Custom-Auth" in last_headers, "X-Custom-Auth not captured"
    assert (
        last_headers["X-Custom-Auth"] == "custom-auth-value"
    ), f"Wrong X-Custom-Auth: {last_headers.get('X-Custom-Auth')}"
    # Verify multiple headers captured
    assert (
        len(last_headers) >= 3
    ), f"Should capture multiple headers, got {len(last_headers)}"


def test_all_headers_captured(mock_server):
    """Test that all request headers are captured, not just predefined ones."""
    make_request(
        f"{mock_server['http_url']}/mcp/v1/list_tools",
        method="POST",
        headers={
            "Authorization": "Bearer test",
            "X-Random-Header-Name": "random-value",
            "X-Another-One": "another-value",
        },
    )

    status, response = make_request(f"{mock_server['http_url']}/debug/headers")

    assert status == 200
    last_headers = response.get("last_headers", {})

    # All custom headers should be captured
    assert "X-Random-Header-Name" in last_headers, "Random header not captured"
    assert "X-Another-One" in last_headers, "Another header not captured"


def test_request_count_increments(mock_server):
    """Test that request count increments with each request."""
    # Get initial count
    _, initial_response = make_request(f"{mock_server['http_url']}/debug/headers")
    initial_count = initial_response.get("request_count", 0)

    # Make another request
    make_request(
        f"{mock_server['http_url']}/mcp/v1/list_tools",
        method="POST",
    )

    # Check count increased
    _, final_response = make_request(f"{mock_server['http_url']}/debug/headers")
    final_count = final_response.get("request_count", 0)

    assert final_count > initial_count, "Request count did not increment"
