"""rlsapi v1 endpoint test steps."""

from behave import then, step  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context


@then("The rlsapi response should have valid structure")
def check_rlsapi_response_structure(context: Context) -> None:
    """Check that rlsapi v1 response has valid structure.

    Validates that the response contains:
    - data.text (non-empty string)
    - data.request_id (non-empty string)
    """
    assert context.response is not None, "Request needs to be performed first"
    response_json = context.response.json()

    assert "data" in response_json, "Response missing 'data' field"
    data = response_json["data"]

    assert "text" in data, "Response data missing 'text' field"
    assert isinstance(data["text"], str), "data.text must be a string"
    assert len(data["text"]) > 0, "data.text must not be empty"

    assert "request_id" in data, "Response data missing 'request_id' field"
    assert isinstance(data["request_id"], str), "data.request_id must be a string"
    assert len(data["request_id"]) > 0, "data.request_id must not be empty"


@step("I store the rlsapi request_id")
def store_rlsapi_request_id(context: Context) -> None:
    """Store the request_id from rlsapi response for later comparison."""
    assert context.response is not None, "Request needs to be performed first"
    response_json = context.response.json()

    assert "data" in response_json, "Response missing 'data' field"
    assert "request_id" in response_json["data"], "Response data missing 'request_id'"
    assert isinstance(
        response_json["data"]["request_id"], str
    ), "data.request_id must be a string"
    assert (
        len(response_json["data"]["request_id"]) > 0
    ), "data.request_id must not be empty"

    context.stored_request_id = response_json["data"]["request_id"]


@then("The rlsapi request_id should be different from the stored one")
def check_rlsapi_request_id_different(context: Context) -> None:
    """Verify that the current request_id differs from the stored one."""
    assert context.response is not None, "Request needs to be performed first"
    assert hasattr(context, "stored_request_id"), "No request_id was stored previously"

    response_json = context.response.json()
    assert "data" in response_json, "Response missing 'data' field"
    assert "request_id" in response_json["data"], "Response data missing 'request_id'"

    current_request_id = response_json["data"]["request_id"]
    assert isinstance(current_request_id, str), "data.request_id must be a string"
    assert len(current_request_id) > 0, "data.request_id must not be empty"
    stored_request_id = context.stored_request_id

    assert (
        current_request_id != stored_request_id
    ), f"request_id should be unique, but got same value: {current_request_id}"
