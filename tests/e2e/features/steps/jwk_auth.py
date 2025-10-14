"""JWK auth steps - reusing unit test primitives."""

from pathlib import Path
import sys

from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context


from authlib.jose import JsonWebToken

sys.path.append(str(Path(__file__).resolve().parents[4]))

# Import at runtime to avoid module load issues
from tests.unit.authentication.test_jwk_token import (
    create_token_header,
    create_token_payload,
)


@given("I have a valid JWT token with the {role} role")
def create_role_token(context: Context, role: str) -> None:
    """Create token with role using the shared test key."""
    test_key = context.test_key

    header = create_token_header(test_key["kid"])
    payload = create_token_payload()

    # This works thanks to the definitions in lightspeed-stack-auth-jwk.yaml
    payload["roles"] = [role]  # Add role to existing payload

    token = (
        JsonWebToken(algorithms=["RS256"])
        .encode(header, payload, test_key["private_key"])
        .decode()
    )

    if not hasattr(context, "auth_headers"):
        context.auth_headers = {}

    context.auth_headers["Authorization"] = f"Bearer {token}"
