"""Utility functions for extracting RH Identity context for telemetry.

This module provides functions to extract organization and system identifiers
from Red Hat Identity request state for telemetry and logging purposes.
"""

from typing import Final, Optional

from starlette.requests import Request

from authentication.rh_identity import RHIdentityData

# Default value when RH Identity auth is not configured
AUTH_DISABLED: Final[str] = "auth_disabled"


def get_rh_identity_context(request: Request) -> tuple[str, str]:
    """Extract org_id and system_id from RH Identity request state.

    When RH Identity authentication is configured, the auth dependency stores
    the RHIdentityData object in request.state.rh_identity_data. This function
    extracts the org_id and system_id for telemetry purposes.

    Args:
        request: The FastAPI request object.

    Returns:
        Tuple of (org_id, system_id). Returns ("auth_disabled", "auth_disabled")
        when RH Identity auth is not configured or data is unavailable.
    """
    rh_identity: Optional[RHIdentityData] = getattr(
        request.state, "rh_identity_data", None
    )
    if rh_identity is None:
        return AUTH_DISABLED, AUTH_DISABLED

    org_id = rh_identity.get_org_id() or AUTH_DISABLED
    system_id = rh_identity.get_user_id() or AUTH_DISABLED
    return org_id, system_id
