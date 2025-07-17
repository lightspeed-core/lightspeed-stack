"""Common steps for HTTP related operations."""

import json

import requests
from behave import given, then, when  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context
from tests.e2e.utils.utils import normalize_endpoint, validate_json

# default timeout for HTTP operations
DEFAULT_TIMEOUT = 10


@when(
    "I request the {endpoint} endpoint in {hostname:w}:{port:d} with {body} in the body"
)
def request_endpoint_with_body(
    context: Context, endpoint: str, hostname: str, port: int, body: str
) -> None:
    """Perform a request to the local server with a given body in the request."""
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(
        f"http://{hostname}:{port}/{endpoint}",
        data=body,
        timeout=DEFAULT_TIMEOUT,
    )


@when("I request the {endpoint} endpoint in {hostname:w}:{port:d} with JSON")
def request_endpoint_with_json(
    context: Context, endpoint: str, hostname: str, port: int
) -> None:
    """Perform a request to the local server with a given JSON in the request.

    The JSON payload is parsed from `context.text`, which must not
    be None in order for this step to succeed. The response is
    saved to `context.response` attribute.
    """
    # initial value
    context.response = None

    assert context.text is not None, "Payload needs to be specified"

    # perform REST API call
    context.response = requests.get(
        f"http://{hostname}:{port}/{endpoint}",
        json=json.loads(context.text),
        timeout=DEFAULT_TIMEOUT,
    )


@when(
    "I request the {endpoint} endpoint in {hostname:w}:{port:d} with following parameters"
)
def request_endpoint_with_url_params(
    context: Context, endpoint: str, hostname: str, port: int
) -> None:
    """Perform a request to the server defined by URL to a given endpoint.

    The function asserts that `context.table` is provided and uses
    its rows to build the query parameters for the request. The
    HTTP response is stored in `context.response` attribute.
    """
    params = {}

    assert context.table is not None, "Request parameters needs to be specified"

    for row in context.table:
        name = row["param"]
        value = row["value"]
        params[name] = value

    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(
        f"http://{hostname}:{port}/{endpoint}",
        params=params,
        timeout=DEFAULT_TIMEOUT,
    )


@when("I request the {endpoint} endpoint in {hostname:w}:{port:d} with path {path}")
def request_endpoint_with_url_path(
    context: Context, endpoint: str, hostname: str, port: int, path: str
) -> None:
    """Perform a request to the server defined by URL to a given endpoint."""
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(
        f"http://{hostname}:{port}/{endpoint}/{path}",
        timeout=DEFAULT_TIMEOUT,
    )


@when("I request the {endpoint} endpoint in {hostname:w}:{port:d}")
def request_endpoint(context: Context, endpoint: str, hostname: str, port: int) -> None:
    """Perform a request to the local server to the given endpoint."""
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(
        f"http://{hostname}:{port}/{endpoint}", timeout=DEFAULT_TIMEOUT
    )


@then("The status code of the response is {status:d}")
def check_status_code(context: Context, status: int) -> None:
    """Check the HTTP status code for latest response from tested service."""
    assert context.response is not None, "Request needs to be performed first"
    assert (
        context.response.status_code == status
    ), f"Status code is {context.response.status_code}"


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
    """Check that response body contains a substring."""
    assert context.response is not None, "Request needs to be performed first"
    assert (
        substring in context.response.text
    ), f"The response text '{context.response.text}' doesn't contain '{substring}'"


@then("The body of the response is the following")
def check_prediction_result(context: Context) -> None:
    """Check the content of the response to be exactly the same.

    Raises an assertion error if the response is missing, the
    expected payload is not provided, or if the actual and expected
    JSON objects differ.
    """
    assert context.response is not None, "Request needs to be performed first"
    assert context.text is not None, "Response does not contain any payload"
    expected_body = json.loads(context.text)
    result = context.response.json()

    # compare both JSONs and print actual result in case of any difference
    assert result == expected_body, f"got:\n{result}\nwant:\n{expected_body}"


@then('The body of the response, ignoring the "{field}" field, is the following')
def check_prediction_result_ignoring_field(context: Context, field: str) -> None:
    """Check the content of the response to be exactly the same.

    Asserts that the JSON response body matches the expected JSON
    payload, ignoring a specified field.

    Parameters:
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


@given("REST API service hostname is {hostname:w}")
@when("REST API service hostname is {hostname:w}")
def set_service_hostname(context: Context, hostname: str) -> None:
    """Set REST API hostname to be used in following steps."""
    context.hostname = hostname


@given("REST API service port is {port:d}")
@when("REST API service port is {port:d}")
def set_service_port(context: Context, port: int) -> None:
    """Set REST API port to be used in following steps."""
    context.port = port


@given("REST API service prefix is {prefix}")
@when("REST API service prefix is {prefix}")
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


@when("I access REST API endpoint {endpoint} using HTTP GET method")
def access_rest_api_endpoint_get(context: Context, endpoint: str) -> None:
    """Send GET HTTP request to tested service."""
    endpoint = normalize_endpoint(endpoint)
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.get(url, timeout=DEFAULT_TIMEOUT)


@when("I access endpoint {endpoint:w} using HTTP POST method")
def access_rest_api_endpoint_post(context: Context, endpoint: str) -> None:
    """Send POST HTTP request with JSON payload to tested service.

    The JSON payload is retrieved from `context.text` attribute,
    which must not be None. The response is stored in
    `context.response` attribute.
    """
    base = f"http://{context.hostname}:{context.port}"
    path = f"{context.api_prefix}/{endpoint}".replace("//", "/")
    url = base + path

    assert context.text is not None, "Payload needs to be specified"
    data = json.loads(context.text)
    # initial value
    context.response = None

    # perform REST API call
    context.response = requests.post(url, json=data, timeout=DEFAULT_TIMEOUT)


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


@then("I should see attribute named {attribute:w} in response")
def check_attribute_presence(context: Context, attribute: str) -> None:
    """Check if given attribute is returned in HTTP response."""
    assert context.response is not None, "Request needs to be performed first"
    json = context.response.json()
    assert json is not None

    assert attribute in json, f"Attribute {attribute} is not returned by the service"


@then("Attribute {attribute:w} should be null")
def check_for_null_attribute(context: Context, attribute: str) -> None:
    """Check if given attribute returned in HTTP response is null."""
    assert context.response is not None, "Request needs to be performed first"
    json = context.response.json()
    assert json is not None

    assert attribute in json, f"Attribute {attribute} is not returned by the service"
    value = json[attribute]
    assert (
        value is None
    ), f"Attribute {attribute} should be null, but it contains {value}"
