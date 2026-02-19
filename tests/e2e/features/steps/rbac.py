"""Step definitions for RBAC E2E tests."""

import os
import requests
from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context


def get_test_tokens() -> dict[str, str]:
    """Fetch test tokens from the mock JWKS server.

    In Prow environment, mock-jwks is port-forwarded to localhost:8000.
    """
    jwks_host = os.getenv("E2E_JWKS_HOSTNAME", "localhost")
    jwks_port = os.getenv("E2E_JWKS_PORT", "8000")
    tokens_url = f"http://{jwks_host}:{jwks_port}/tokens"

    response = requests.get(tokens_url, timeout=5)
    response.raise_for_status()
    return response.json()


@given('I authenticate as "{role}" user')
def authenticate_as_role(context: Context, role: str) -> None:
    """Set the Authorization header with a token for the specified role.

    Fetches pre-generated test tokens from the mock JWKS server
    and sets the appropriate Authorization header for the given role.

    Available roles: admin, user, viewer, query_only, no_role
    """
    tokens = get_test_tokens()

    if role not in tokens:
        raise ValueError(
            f"Unknown role '{role}'. Available roles: {list(tokens.keys())}"
        )

    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    context.auth_headers["Authorization"] = f"Bearer {tokens[role]}"
    print(f"🔑 Authenticated as '{role}' user")
