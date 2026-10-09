"""Implementation of common test steps."""

import base64
import json

import requests
from behave import given, when  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import normalize_endpoint


def _encode_rh_identity(identity_data: dict) -> str:
    """Encode identity dict to base64 for x-rh-identity header.

    Args:
        identity_data: JSON-serializable identity payload to encode.

    Returns:
        Base64-encoded UTF-8 string representation of the JSON payload.

    """
    json_str = json.dumps(identity_data)
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


@given("I set the Authorization header to {header_value}")
def set_authorization_header_custom(context: Context, header_value: str) -> None:
    """Set a custom Authorization header value.

    Parameters:
    ----------
        header_value (str): The value to set for the `Authorization` header.

    """
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}
    context.auth_headers["Authorization"] = header_value
    print(f"🔑 Set Authorization header to: {header_value}")


@given("I remove the auth header")  # type: ignore[reportCallIssue]
def remove_authorization_header(context: Context) -> None:
    """Remove Authorization header."""
    if hasattr(context, "auth_headers") and "Authorization" in context.auth_headers:
        del context.auth_headers["Authorization"]


@when("I access endpoint {endpoint} using HTTP POST method with user_id {user_id}")
def access_rest_api_endpoint_post(
    context: Context, endpoint: str, user_id: str
) -> None:
    """Send POST HTTP request with payload in the endpoint as parameter to tested service.

    The response is stored in `context.response` attribute.

    Parameters:
    ----------
        endpoint (str): Endpoint path to call; will be normalized.
        user_id (str): Value used for the `user_id` query parameter (surrounding quotes are removed).

    """
    endpoint = normalize_endpoint(endpoint)
    user_id = user_id.replace('"', "")
    base = f"http://{context.hostname}:{context.port}"
    path = f"{endpoint}?user_id={user_id}".replace("//", "/")
    url = base + path

    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    # perform REST API call
    context.response = requests.post(
        url, json="", headers=context.auth_headers, timeout=10
    )


@when("I access endpoint {endpoint} using HTTP POST method without user_id")
def access_rest_api_endpoint_post_without_param(
    context: Context, endpoint: str
) -> None:
    """Send POST HTTP request without user_id payload.

    The response is stored in `context.response` attribute.
    """
    endpoint = normalize_endpoint(endpoint)
    base = f"http://{context.hostname}:{context.port}"
    path = f"{endpoint}".replace("//", "/")
    url = base + path

    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    # perform REST API call
    context.response = requests.post(
        url, json="", headers=context.auth_headers, timeout=10
    )


@given('I set the x-rh-identity header to raw value "{header_value}"')
def set_rh_identity_header_raw(context: Context, header_value: str) -> None:
    """Set x-rh-identity header with a raw string value for testing invalid base64."""
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}
    context.auth_headers["x-rh-identity"] = header_value
    print(f"Set x-rh-identity header to raw value: {header_value[:50]}...")


@given('I set the x-rh-identity header with base64 encoded value "{raw_value}"')
def set_rh_identity_header_base64_raw(context: Context, raw_value: str) -> None:
    """Set x-rh-identity header with base64-encoded raw string for testing invalid JSON."""
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}
    encoded = base64.b64encode(raw_value.encode("utf-8")).decode("utf-8")
    context.auth_headers["x-rh-identity"] = encoded
    print(f"Set x-rh-identity header with base64-encoded: {raw_value}")


@given("I set the x-rh-identity header with JSON")
def set_rh_identity_header_json(context: Context) -> None:
    """Set x-rh-identity header with base64-encoded JSON from context.text."""
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}
    assert context.text is not None, "JSON payload required"
    identity_data = json.loads(context.text)
    context.auth_headers["x-rh-identity"] = _encode_rh_identity(identity_data)
    print(f"Set x-rh-identity header with JSON: {identity_data}")


@given("I set the x-rh-identity header with valid User identity")
def set_rh_identity_user(context: Context) -> None:
    """Set x-rh-identity header with User identity from table."""
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    assert context.table is not None, "Table with identity fields required"

    fields = {row["field"]: row["value"] for row in context.table}

    entitlements = {}
    if "entitlements" in fields:
        for ent in fields["entitlements"].split(","):
            ent = ent.strip()
            if not ent:
                continue
            entitlements[ent] = {"is_entitled": True, "is_trial": False}

    identity_data = {
        "identity": {
            "account_number": fields.get("account_number", "123"),
            "org_id": fields.get("org_id", "321"),
            "type": "User",
            "user": {
                "user_id": fields.get("user_id", "test-user"),
                "username": fields.get("username", "test@redhat.com"),
                "is_org_admin": fields.get("is_org_admin", "false").lower() == "true",
            },
        },
        "entitlements": entitlements,
    }

    context.auth_headers["x-rh-identity"] = _encode_rh_identity(identity_data)
    print(f"Set x-rh-identity header with User identity: {fields.get('user_id')}")


@given("I set the x-rh-identity header with valid System identity")
def set_rh_identity_system(context: Context) -> None:
    """Set x-rh-identity header with System identity from table."""
    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    assert context.table is not None, "Table with identity fields required"

    fields = {row["field"]: row["value"] for row in context.table}

    entitlements = {}
    if "entitlements" in fields:
        for ent in fields["entitlements"].split(","):
            ent = ent.strip()
            if not ent:
                continue
            entitlements[ent] = {"is_entitled": True, "is_trial": False}

    identity_data = {
        "identity": {
            "account_number": fields.get("account_number", "123"),
            "org_id": fields.get("org_id", "321"),
            "type": "System",
            "system": {
                "cn": fields.get("cn", "default-cn-uuid"),
            },
        },
        "entitlements": entitlements,
    }

    context.auth_headers["x-rh-identity"] = _encode_rh_identity(identity_data)
    print(f"Set x-rh-identity header with System identity: {fields.get('cn')}")
