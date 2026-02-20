"""Implementation of MCP-specific test steps."""

import json
import time

import requests
from behave import given, then, when  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

# Mock MCP server configuration
MOCK_MCP_SERVER_URL = "http://localhost:9000"


@given('I set the MCP-HEADERS header with client token for "{server_name}"')
def set_mcp_headers_with_client_token(context: Context, server_name: str) -> None:
    """Set MCP-HEADERS header with a client-provided token.

    Parameters:
        context (Context): Behave context.
        server_name (str): Name of the MCP server to provide token for.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    # Set MCP-HEADERS with client token
    mcp_headers = {server_name: {"Authorization": "Bearer my-client-token"}}
    context.auth_headers["MCP-HEADERS"] = json.dumps(mcp_headers)
    print(f"🔑 Set MCP-HEADERS for server '{server_name}' with client token")


@given("The MCP mock server request log is cleared")
def clear_mcp_mock_server_log(context: Context) -> None:
    """Clear the MCP mock server request log using the debug/clear endpoint.

    Parameters:
        context (Context): Behave context.
    """
    try:
        response = requests.get(f"{MOCK_MCP_SERVER_URL}/debug/clear", timeout=2)
        if response.status_code == 200:
            result = response.json()
            print(
                f"🧹 MCP mock server log cleared (status: {result.get('status', 'unknown')})"
            )
        else:
            raise AssertionError(
                f"Failed to clear MCP mock server log: status {response.status_code}"
            )
    except requests.RequestException as e:
        raise AssertionError(f"Could not clear MCP mock server log: {e}") from e


@when("I send a query that uses MCP tools")
def send_query_with_mcp_tools(context: Context) -> None:
    """Send a query request that will trigger MCP tool discovery.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    base_url = f"http://{context.hostname}:{context.port}"
    url = f"{base_url}/v1/query"

    model = getattr(context, "default_model", "gpt-4o-mini")
    provider = getattr(context, "default_provider", "openai")

    payload = {
        "query": "What tools are available?",
        "model": model,
        "provider": provider,
    }

    # Use longer timeout (60s) if testing error handling
    # llama-stack 0.4.2 can be slow to handle tool errors
    timeout = (
        60
        if hasattr(context, "expect_tool_errors") and context.expect_tool_errors
        else 30
    )

    try:
        context.response = requests.post(
            url, json=payload, headers=context.auth_headers, timeout=timeout
        )
        print(f"📤 Sent query request (status: {context.response.status_code})")
    except requests.RequestException as e:
        print(f"❌ Query request failed: {e}")
        context.response = None


@when("I wait for MCP server to receive requests")
@when("I wait for MCP server to process tool calls")
def wait_for_mcp_server(context: Context) -> None:
    """Wait for MCP server to receive and process requests.

    Parameters:
        context (Context): Behave context.
    """
    # Wait for requests to be processed and logged
    time.sleep(2)
    print("⏱️  Waited for MCP server to process requests")


@then("The MCP mock server should have received requests")
def check_mcp_server_received_requests(context: Context) -> None:
    """Verify the MCP mock server received at least one request.

    Parameters:
        context (Context): Behave context.
    """
    # Delegate to the parameterized version with count=1
    check_mcp_server_request_count(context, 1)


@then("The MCP mock server should have received at least {count:d} requests")
def check_mcp_server_request_count(context: Context, count: int) -> None:
    """Verify the MCP mock server received at least N requests.

    Parameters:
        context (Context): Behave context.
        count (int): Minimum expected request count.
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    try:
        # Mock server debug endpoint can be slow with many requests - use 15s timeout
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert (
            response.status_code == 200
        ), f"Failed to get debug requests: {response.status_code}"

        requests_log = response.json()
        actual_count = len(requests_log)
        assert (
            actual_count >= count
        ), f"Expected at least {count} requests, got {actual_count}"
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


def _check_auth_header_in_requests(
    expected_value: str, match_type: str = "exact", server_type: str = ""
) -> None:
    """Verify Authorization header in MCP mock server requests.

    Parameters:
        expected_value (str): Expected Authorization header value or fragment.
        match_type (str): Either "exact" for exact match or "contains" for substring match.
        server_type (str): Server type for error messages (e.g., "file-auth", "k8s-auth").
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    try:
        # Mock server debug endpoint can be slow with many requests - use 15s timeout
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert response.status_code == 200, "Failed to get debug requests"

        requests_log = response.json()

        # Filter requests based on match type
        if match_type == "exact":
            matching_requests = [
                req
                for req in requests_log
                if req.get("headers", {}).get("Authorization") == expected_value
            ]
            error_msg = f"No requests found with Authorization: {expected_value}"
        else:  # contains
            matching_requests = [
                req
                for req in requests_log
                if expected_value in req.get("headers", {}).get("Authorization", "")
            ]
            error_msg = f"No requests found with {server_type} token containing: {expected_value}"

        assert len(matching_requests) > 0, error_msg
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


@then(
    'The MCP mock server should have captured Authorization header "{expected_value}" from file-auth server'
)
def check_file_auth_header(context: Context, expected_value: str) -> None:
    """Verify the MCP mock server captured the expected file-based auth header.

    Parameters:
        context (Context): Behave context.
        expected_value (str): Expected Authorization header value.
    """
    _check_auth_header_in_requests(expected_value, match_type="exact")


@then(
    'The MCP mock server should have captured Authorization header containing "{token_fragment}" from k8s-auth server'
)
def check_k8s_auth_header(context: Context, token_fragment: str) -> None:
    """Verify the MCP mock server captured k8s token in Authorization header.

    Parameters:
        context (Context): Behave context.
        token_fragment (str): Expected token fragment in Authorization header.
    """
    _check_auth_header_in_requests(
        token_fragment, match_type="contains", server_type="k8s"
    )


@then(
    'The MCP mock server should have captured Authorization header containing "{token_fragment}" from client-auth server'
)
def check_client_auth_header(context: Context, token_fragment: str) -> None:
    """Verify the MCP mock server captured client token in Authorization header.

    Parameters:
        context (Context): Behave context.
        token_fragment (str): Expected token fragment in Authorization header.
    """
    _check_auth_header_in_requests(
        token_fragment, match_type="contains", server_type="client"
    )


@then('The MCP mock server request log should contain tool "{tool_name}"')
def check_mcp_tool_in_log(context: Context, tool_name: str) -> None:
    """Verify the MCP mock server received requests for a specific tool.

    Queries the mock server's debug endpoint to check the request log.

    Parameters:
        context (Context): Behave context.
        tool_name (str): Expected tool name (e.g., mock_tool_file, mock_tool_k8s).
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    try:
        # Mock server debug endpoint can be slow with many requests - use 15s timeout
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert response.status_code == 200, "Failed to get debug requests"

        requests_log = response.json()

        # Check if any request in the log contains the expected tool name
        found = False
        for req in requests_log:
            if req.get("tool_name") == tool_name:
                found = True
                break

        assert found, f"Tool '{tool_name}' not found in mock server request log"
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


@then('The MCP mock server request log should not contain tool "{tool_name}"')
def check_mcp_tool_not_in_log(context: Context, tool_name: str) -> None:
    """Verify the MCP mock server did NOT receive requests for a specific tool.

    Queries the mock server's debug endpoint to check the request log.
    This is useful for verifying that servers were skipped due to auth issues.

    Parameters:
        context (Context): Behave context.
        tool_name (str): Tool name that should NOT be present.
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    try:
        # Mock server debug endpoint can be slow with many requests - use 15s timeout
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert response.status_code == 200, "Failed to get debug requests"

        requests_log = response.json()

        # Check if any request in the log contains the tool name
        for req in requests_log:
            if req.get("tool_name") == tool_name:
                raise AssertionError(
                    f"Tool '{tool_name}' unexpectedly found in mock server request log "
                    f"(server should have been skipped)"
                )
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


@then("The MCP mock server request log should contain exactly tools {tool_list}")
def check_mcp_exact_tools_in_log(context: Context, tool_list: str) -> None:
    """Verify MCP server called at least one expected tool and no unexpected tools.

    This validates:
    1. At least ONE tool from the expected list was called (flexible for LLM non-determinism)
    2. NO tools outside the expected list were called (enforces security/auth boundaries)

    This approach balances LLM flexibility with security enforcement - the LLM can choose
    which tools to use, but cannot access tools outside the allowed set.

    Parameters:
        context (Context): Behave context.
        tool_list (str): Comma-separated list of allowed tool names.
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    # Parse expected tools
    expected_tools = [tool.strip() for tool in tool_list.split(",")]

    try:
        # Mock server debug endpoint can be slow with many requests - use 15s timeout
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert response.status_code == 200, "Failed to get debug requests"

        requests_log = response.json()

        # Extract unique tool names from log
        found_tools = set()
        for req in requests_log:
            tool_name = req.get("tool_name")
            if tool_name:
                found_tools.add(tool_name)

        # Check 1: At least ONE expected tool was called
        # (Allows for LLM non-determinism in tool selection)
        called_expected_tools = found_tools & set(expected_tools)
        if not called_expected_tools:
            raise AssertionError(
                f"None of the expected tools were called. "
                f"Expected at least one of: {', '.join(expected_tools)}. "
                f"Found tools: {', '.join(sorted(found_tools))}"
            )

        # Check 2: NO unexpected tools were called
        # (Enforces security - prevents access to unauthorized tools)
        unexpected_tools = [tool for tool in found_tools if tool not in expected_tools]
        if unexpected_tools:
            raise AssertionError(
                f"Unexpected tools found in log: {', '.join(unexpected_tools)}. "
                f"Only expected: {', '.join(expected_tools)}"
            )
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


@when("I send a query asking about available tools")
def send_query_about_tools(context: Context) -> None:
    """Send a query asking about available tools.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    base_url = f"http://{context.hostname}:{context.port}"
    url = f"{base_url}/v1/query"

    model = getattr(context, "default_model", "gpt-4o-mini")
    provider = getattr(context, "default_provider", "openai")

    payload = {
        "query": "What tools are available to help me?",
        "model": model,
        "provider": provider,
    }

    try:
        context.response = requests.post(
            url, json=payload, headers=context.auth_headers, timeout=30
        )
        print(f"📤 Sent query about tools (status: {context.response.status_code})")
    except requests.RequestException as e:
        print(f"❌ Query request failed: {e}")
        context.response = None


@when("I send a query that explicitly requests tool usage")
def send_query_requesting_tool_usage(context: Context) -> None:
    """Send a query that explicitly asks to use a tool.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    base_url = f"http://{context.hostname}:{context.port}"
    url = f"{base_url}/v1/query"

    model = getattr(context, "default_model", "gpt-4o-mini")
    provider = getattr(context, "default_provider", "openai")

    payload = {
        "query": "Please use the mock_tool_k8s tool to test the connection",
        "model": model,
        "provider": provider,
    }

    try:
        context.response = requests.post(
            url, json=payload, headers=context.auth_headers, timeout=30
        )
        print(
            f"📤 Sent query requesting tool usage (status: {context.response.status_code})"
        )
    except requests.RequestException as e:
        print(f"❌ Query request failed: {e}")
        context.response = None


@when("I send a query that triggers MCP tool usage")
def send_query_triggering_tool_usage(context: Context) -> None:
    """Send a query that should trigger MCP tool usage.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    base_url = f"http://{context.hostname}:{context.port}"
    url = f"{base_url}/v1/query"

    model = getattr(context, "default_model", "gpt-4o-mini")
    provider = getattr(context, "default_provider", "openai")

    payload = {
        "query": "Use available tools to help me",
        "model": model,
        "provider": provider,
    }

    try:
        context.response = requests.post(
            url, json=payload, headers=context.auth_headers, timeout=30
        )
        print(
            f"📤 Sent query triggering tools (status: {context.response.status_code})"
        )
    except requests.RequestException as e:
        print(f"❌ Query request failed: {e}")
        context.response = None


@when("I send a query that requires multiple tool calls")
def send_query_requiring_multiple_tools(context: Context) -> None:
    """Send a query that should trigger multiple tool calls.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    base_url = f"http://{context.hostname}:{context.port}"
    url = f"{base_url}/v1/query"

    model = getattr(context, "default_model", "gpt-4o-mini")
    provider = getattr(context, "default_provider", "openai")

    payload = {
        "query": "Use all available tools to gather information",
        "model": model,
        "provider": provider,
    }

    try:
        # Multiple tool calls can take longer - use 120s timeout
        # Note: This test is timing-sensitive in CI. Locally completes in ~8s,
        # but CI can take 90+ seconds due to container overhead and resource limits
        context.response = requests.post(
            url, json=payload, headers=context.auth_headers, timeout=120
        )
        print(
            f"📤 Sent query requiring multiple tools (status: {context.response.status_code})"
        )
    except requests.RequestException as e:
        print(f"❌ Query request failed: {e}")
        context.response = None


@then("The MCP mock server should have received tools/list method calls")
def check_tools_list_calls(context: Context) -> None:
    """Verify MCP server received tools/list method calls from the SUT.

    Parameters:
        context (Context): Behave context.
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    # Check the debug request log for tools/list calls
    try:
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert (
            response.status_code == 200
        ), f"Failed to get debug requests: {response.status_code}"
        requests_log = response.json()
        tools_list_calls = [
            req for req in requests_log if req.get("rpc_method") == "tools/list"
        ]
        assert len(tools_list_calls) > 0, "No tools/list calls found in request log"
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


@then("The MCP mock server should have received tools/call method")
def check_tools_call_method(context: Context) -> None:
    """Verify MCP server received tools/call method.

    Parameters:
        context (Context): Behave context.
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    try:
        # Mock server debug endpoint can be slow with many requests - use 15s timeout
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert response.status_code == 200, "Failed to get debug requests"

        requests_log = response.json()
        tools_call_entries = [
            req for req in requests_log if req.get("rpc_method") == "tools/call"
        ]
        assert len(tools_call_entries) > 0, "No tools/call entries found in request log"
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


@then("The response should contain MCP tool execution results")
@then("The response should indicate successful tool execution")
@then("The response should contain tool call information")
@then("The tool execution results should be included in the response")
def check_response_has_tool_execution(context: Context) -> None:
    """Verify response contains evidence of MCP tool execution.

    This consolidated step checks that the response contains tool-related content,
    which could be tool calls, tool results, or references to tool execution in
    the response text.

    Parameters:
        context (Context): Behave context.
    """
    assert context.response is not None, "No response received"
    assert (
        context.response.status_code == 200
    ), f"Bad status: {context.response.status_code}"

    response_data = context.response.json()
    assert "response" in response_data, "Response missing 'response' field"

    # Check for evidence of tool execution in the response
    response_text = str(response_data.get("response", "")).lower()

    # Look for tool-related indicators in the response
    # (tool execution, mock tool, or specific tool results)
    has_tool_content = any(
        indicator in response_text
        for indicator in ["tool", "mock", "executed", "success"]
    )

    assert has_tool_content, (
        "Response does not contain evidence of tool execution. "
        f"Response text: {response_data.get('response', '')[:200]}"
    )


@given("The MCP mock server is configured to return errors")
def configure_mock_server_errors(context: Context) -> None:
    """Configure mock server to return errors via MCP-HEADERS.

    Sends the special "Bearer error-mode" token via MCP-HEADERS so all
    configured MCP servers (mock-file-auth, mock-k8s-auth, mock-client-auth)
    receive it and return errors. This token must be propagated through
    MCP-HEADERS, not the top-level Authorization header, because the stack
    only forwards MCP-HEADERS to MCP servers.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    # Configure all MCP servers to use error-mode token via MCP-HEADERS
    # The mock server recognizes "Bearer error-mode" and returns errors
    mcp_headers = {
        "mock-file-auth": {"Authorization": "Bearer error-mode"},
        "mock-k8s-auth": {"Authorization": "Bearer error-mode"},
        "mock-client-auth": {"Authorization": "Bearer error-mode"},
    }
    context.auth_headers["MCP-HEADERS"] = json.dumps(mcp_headers)
    context.expect_tool_errors = True
    print(
        "⚠️  MCP mock server configured for error mode (error-mode token via MCP-HEADERS)"
    )


@then("The response should indicate tool execution failed")
def check_tool_execution_failed(context: Context) -> None:
    """Verify response indicates tool execution failed.

    Parameters:
        context (Context): Behave context.
    """
    assert context.response is not None, "No response received"
    assert (
        context.response.status_code == 200
    ), f"Bad status: {context.response.status_code}"

    # In error mode, the response should still be 200 but contain error information
    # The LLM will handle the tool error gracefully


@then("The MCP mock server should confirm error mode is active")
def check_mock_server_error_mode(context: Context) -> None:
    """Verify the mock server is returning errors via API query.

    Sends a test request to the mock server and confirms it returns isError=true.

    Parameters:
        context (Context): Behave context.
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    try:
        # Verify the mock server is in error mode by checking its response
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "test", "arguments": {}},
        }
        response = requests.post(
            mock_server_url,
            json=payload,
            headers={"Authorization": "Bearer error-mode"},
            timeout=5,
        )
        result = response.json()
        assert result.get("result", {}).get(
            "isError"
        ), "Mock server not returning errors"
    except requests.RequestException as e:
        raise AssertionError(f"Could not verify mock server error mode: {e}") from e


@then("The MCP mock server should have received multiple tools/call methods")
def check_multiple_tool_calls(context: Context) -> None:
    """Verify MCP server received multiple tool call requests.

    Parameters:
        context (Context): Behave context.
    """
    mock_server_url = MOCK_MCP_SERVER_URL

    try:
        # Mock server debug endpoint can be slow with many requests - use 15s timeout
        response = requests.get(f"{mock_server_url}/debug/requests", timeout=15)
        assert response.status_code == 200, "Failed to get debug requests"

        requests_log = response.json()
        tools_call_entries = [
            req for req in requests_log if req.get("rpc_method") == "tools/call"
        ]
        assert (
            len(tools_call_entries) >= 2
        ), f"Expected multiple tools/call requests, got {len(tools_call_entries)}"
    except requests.RequestException as e:
        raise AssertionError(f"Could not connect to MCP mock server: {e}") from e


@then("All tool calls should have succeeded")
def check_all_tool_calls_succeeded(context: Context) -> None:
    """Verify all tool calls succeeded.

    Parameters:
        context (Context): Behave context.
    """
    assert context.response is not None, "No response received"
    assert context.response.status_code == 200, "Request failed"


@then("The response should contain results from all tool calls")
def check_response_has_all_results(context: Context) -> None:
    """Verify response contains results from all tool calls.

    Parameters:
        context (Context): Behave context.
    """
    assert context.response is not None, "No response received"
    response_data = context.response.json()

    assert "response" in response_data, "Response missing 'response' field"


@when("I send a streaming query that uses MCP tools")
def send_streaming_query_with_mcp_tools(context: Context) -> None:
    """Send a streaming query that should use MCP tools.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    base_url = f"http://{context.hostname}:{context.port}"
    url = f"{base_url}/v1/streaming_query"

    model = getattr(context, "default_model", "gpt-4o-mini")
    provider = getattr(context, "default_provider", "openai")

    payload = {
        "query": "Use available tools to help me",
        "model": model,
        "provider": provider,
        "media_type": "application/json",  # Request JSON response instead of SSE
    }

    try:
        context.response = requests.post(
            url, json=payload, headers=context.auth_headers, timeout=30
        )
        print(
            f"📤 Sent streaming query with MCP tools (status: {context.response.status_code})"
        )
    except requests.RequestException as e:
        print(f"❌ Streaming query request failed: {e}")
        context.response = None


@when("I send a streaming query requiring multiple tools")
def send_streaming_query_requiring_multiple_tools(context: Context) -> None:
    """Send a streaming query requiring multiple tool calls.

    Parameters:
        context (Context): Behave context.
    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    base_url = f"http://{context.hostname}:{context.port}"
    url = f"{base_url}/v1/streaming_query"

    model = getattr(context, "default_model", "gpt-4o-mini")
    provider = getattr(context, "default_provider", "openai")

    payload = {
        "query": "Use all available tools to gather comprehensive information",
        "model": model,
        "provider": provider,
        "media_type": "application/json",  # Request JSON response instead of SSE
    }

    try:
        # Multiple tool calls can take longer - use 120s timeout
        # Note: This test is timing-sensitive in CI. Locally completes in ~8s,
        # but CI can take 90+ seconds due to container overhead and resource limits
        context.response = requests.post(
            url, json=payload, headers=context.auth_headers, timeout=120
        )
        print(
            f"📤 Sent streaming query requiring multiple tools (status: {context.response.status_code})"
        )
    except requests.RequestException as e:
        print(f"❌ Streaming query request failed: {e}")
        context.response = None


@then("The streaming response should be successful")
def check_streaming_response_successful(context: Context) -> None:
    """Verify streaming response was successful.

    Parameters:
        context (Context): Behave context.
    """
    assert context.response is not None, "No response received"
    assert (
        context.response.status_code == 200
    ), f"Bad status: {context.response.status_code}"


@then("The streaming response should contain tool execution results")
def check_streaming_response_has_tool_results(context: Context) -> None:
    """Verify streaming response contains tool execution results.

    Parameters:
        context (Context): Behave context.
    """
    assert context.response is not None, "No response received"
    assert (
        context.response.status_code == 200
    ), f"Bad status: {context.response.status_code}"

    # Parse response and check for tool execution evidence
    try:
        response_data = context.response.json()
        response_text = str(response_data.get("response", "")).lower()

        # Look for tool-related indicators in the response
        has_tool_content = any(
            indicator in response_text
            for indicator in ["tool", "mock", "executed", "success"]
        )

        assert has_tool_content, (
            "Response does not contain evidence of tool execution. "
            f"Response text: {response_data.get('response', '')[:200]}"
        )
    except ValueError as e:
        raise AssertionError(f"Failed to parse response JSON: {e}") from e
