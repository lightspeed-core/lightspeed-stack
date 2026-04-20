"""Common steps for HTTP-related operations."""

import json

import requests
from behave import (
    given,
    step,
    then,
    when,
)  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import (
    http_response_json_or_responses_sse_terminal,
    normalize_endpoint,
    replace_placeholders,
    request_with_transient_retry,
    validate_json,
    validate_json_partially,
)

# default timeout for HTTP operations
DEFAULT_TIMEOUT = 10


@step("The status code of the response is {status:d}")
def check_status_code(context: Context, status: int) -> None:
    """Check the HTTP status code for latest response from tested service."""
    assert context.response is not None, "Request needs to be performed first"
    if context.response.status_code != status:
        # Include response body in error message for debugging
        try:
            error_body = context.response.json()
        except Exception:
            error_body = context.response.text
        assert False, (
            f"Status code is {context.response.status_code}, expected {status}. "
            f"Response: {error_body}"
        )


@then('Content type of response should be set to "{content_type}"')
def check_content_type(context: Context, content_type: str) -> None:
    """Check the HTTP content type for latest response from tested service."""
    assert context.response is not None, "Request needs to be performed first"
    headers = context.response.headers
    assert "content-type" in headers, "Content type is not specified"
    actual = headers["content-type"]
    assert actual.startswith(content_type), f"Improper content type {actual}"


@then("The body of the response has the following schema")
def check_response_body_schema(context: Context) -> None:
    """Check that response body is compliant with a given schema.

    Asserts that a response has been received and that a schema is
    present in `context.text` attribute. Loads the schema from
    `context.text` attribute and validates the response body.
    """
    assert context.response is not None, "Request needs to be performed first"
    assert context.text is not None, "Response does not contain any payload"
    schema = json.loads(context.text)
    body = context.response.json()

    validate_json(schema, body)


@then("The body of the response contains {substring}")
def check_response_body_contains(context: Context, substring: str) -> None:
    """Check that response body contains a substring.

    Supports {MODEL} and {PROVIDER} placeholders in the substring so
    assertions work with any configured provider (e.g. unknown-provider
    error message includes the actual model id).

    Matching is case-insensitive so LLM replies (e.g. ``Hello`` vs ``hello``)
    do not fail otherwise-identical scenarios.
    """
    assert context.response is not None, "Request needs to be performed first"
    expected = replace_placeholders(context, substring)
    response_text_lower = context.response.text.lower()
    expected_substring_lower = expected.lower()
    assert (
        expected_substring_lower in response_text_lower
    ), f"The response text '{context.response.text}' doesn't contain '{expected}'"


@then("The body of the response does not contain {substring}")
def check_response_body_does_not_contain(context: Context, substring: str) -> None:
    """Check that response body does not contain a substring."""
    assert context.response is not None, "Request needs to be performed first"
    assert (
        substring not in context.response.text
    ), f"The response text '{context.response.text}' contains '{substring}'"


@then("The body of the response is the following")
def check_prediction_result(context: Context) -> None:
    """Check the content of the response to be exactly the same.

    Raises an assertion error if the response is missing, the
    expected payload is not provided, or if the actual and expected
    JSON objects differ.
    """
    assert context.response is not None, "Request needs to be performed first"
    assert context.text is not None, "Response does not contain any payload"

    # Replace {MODEL} and {PROVIDER} placeholders with actual values
    json_str = replace_placeholders(context, context.text or "{}")

    expected_body = json.loads(json_str)
    result = context.response.json()

    # compare both JSONs and print actual result in case of any difference
    assert result == expected_body, f"got:\n{result}\nwant:\n{expected_body}"


@then('The headers of the response contains the following header "{header_name}"')
def check_response_headers_contains(context: Context, header_name: str) -> None:
    """Check that response contains a header whose name matches."""
    assert context.response is not None, "Request needs to be performed first"
    assert (
        header_name in context.response.headers.keys()
    ), f"The response headers '{context.response.headers}' doesn't contain header '{header_name}'"


@then('The body of the response, ignoring the "{field}" field, is the following')
def check_prediction_result_ignoring_field(context: Context, field: str) -> None:
    """Check the content of the response to be exactly the same.

    Asserts that the JSON response body matches the expected JSON
    payload, ignoring a specified field.

    Parameters:
    ----------
        field (str): The name of the field to exclude from both the actual and expected JSON objects during comparison.
    """
    assert context.response is not None, "Request needs to be performed first"
    assert context.text is not None, "Response does not contain any payload"
    expected_body = json.loads(context.text).copy()
    result = context.response.json().copy()

    expected_body.pop(field, None)
    result.pop(field, None)

    # compare both JSONs and print actual result in case of any difference
    assert result == expected_body, f"got:\n{result}\nwant:\n{expected_body}"


@step("REST API service hostname is {hostname:w}")
def set_service_hostname(context: Context, hostname: str) -> None:
    """Set REST API hostname to be used in following steps."""
    context.hostname = hostname


@step("REST API service port is {port:d}")
def set_service_port(context: Context, port: int) -> None:
    """Set REST API port to be used in following steps."""
    context.port = port


@step("REST API service prefix is {prefix}")
def set_rest_api_prefix(context: Context, prefix: str) -> None:
    """Set REST API prefix to be used in following steps."""
    context.api_prefix = prefix


@when("I access endpoint {endpoint} using HTTP GET method")
def access_non_rest_api_endpoint_get(context: Context, endpoint: str) -> None:
    """Send GET HTTP request to tested service."""
    endpoint = normalize_endpoint(endpoint)
    base = f"http://{context.hostname}:{context.port}"
    path = f"{endpoint}".replace("//", "/")
    url = base + path
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(url, timeout=DEFAULT_TIMEOUT)
    assert context.response is not None, "Response is None"


@when("I access endpoint {endpoint} using HTTP POST method")
def access_non_rest_api_endpoint_post(context: Context, endpoint: str) -> None:
    """Send POST HTTP request with JSON payload to tested service.

    The JSON payload is retrieved from `context.text` attribute,
    which must not be None. The response is stored in
    `context.response` attribute.
    """
    endpoint = normalize_endpoint(endpoint)
    base = f"http://{context.hostname}:{context.port}"
    path = f"{endpoint}".replace("//", "/")
    url = base + path

    assert context.text is not None, "Payload needs to be specified"
    data = json.loads(context.text)
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.post(
        url, json=data, headers=headers, timeout=DEFAULT_TIMEOUT
    )


@when("I access REST API endpoint {endpoint} using HTTP {method} method")
def access_rest_api_endpoint(context: Context, endpoint: str, method: str) -> None:
    """Send HTTP request with JSON payload to tested service.

    The JSON payload is retrieved from `context.text` attribute,
    which must not be None. The response is stored in
    `context.response` attribute.
    """
    endpoint = normalize_endpoint(endpoint)
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path
    headers = context.auth_headers if hasattr(context, "auth_headers") else {}
    # initial value
    context.response = None

    # GET/DELETE: do not pass json= (even None); some stacks mishandle it.
    # All methods: retry transient RST/connection errors after restarts in CI.
    if method in ("GET", "DELETE"):
        context.response = request_with_transient_retry(
            method=method, url=url, headers=headers, timeout=DEFAULT_TIMEOUT
        )
    else:
        assert context.text is not None, "Payload needs to be specified"
        data = json.loads(context.text)
        context.response = request_with_transient_retry(
            method=method, url=url, json=data, headers=headers, timeout=DEFAULT_TIMEOUT
        )


@then('The status message of the response is "{expected_message}"')
def check_status_of_response(context: Context, expected_message: str) -> None:
    """Check the actual message/value in status attribute."""
    assert context.response is not None, "Send request to service first"

    # try to parse response body as JSON
    body = context.response.json()
    assert body is not None, "Improper format of response body"

    assert "status" in body, "Response does not contain status message"
    actual_message = body["status"]

    assert (
        actual_message == expected_message
    ), f"Improper status message {actual_message}"


@then("the body of the response has the following structure")
def check_response_partially(context: Context) -> None:
    """Validate that the response body matches the expected JSON structure.

    Compares the actual response JSON against the expected structure defined
    in `context.text`, ignoring extra keys or values not specified.
    """
    assert context.response is not None, "Request needs to be performed first"
    body = http_response_json_or_responses_sse_terminal(context.response)
    json_str = replace_placeholders(context, context.text or "{}")
    expected = json.loads(json_str)
    validate_json_partially(body, expected)


@given('I set the "{header_name}" header to')
def set_header(context: Context, header_name: str) -> None:
    """Set a header in the request.

    For ``MCP-HEADERS``, normalizes JSON to a single line. Multi-line or
    indented docstrings from Gherkin must not be sent as raw header values:
    HTTP forbids newlines in field values, which can cause proxies or clients
    to drop or truncate the header so the server sees no MCP client auth.
    """
    assert context.text is not None, "Header value needs to be specified"

    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}
    value = context.text.strip()
    if header_name.upper() == "MCP-HEADERS":
        try:
            parsed = json.loads(value)
            value = json.dumps(parsed, separators=(",", ":"))
        except json.JSONDecodeError:
            pass
    context.auth_headers[header_name] = value
