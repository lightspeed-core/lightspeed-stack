"""Session ID utility functions."""

import uuid


def get_suid() -> str:
    """Generate a unique session ID (SUID) using UUID4.

    Returns:
        A unique session ID.
    """
    return str(uuid.uuid4())


def check_suid(suid: str) -> bool:
    """Check if given string is a proper session ID or response ID.

    Rules:
    - If it starts with "resp-" or "resp_", accept as a valid Responses API ID (opaque).
    - Otherwise, require a valid UUID string.
    """
    if not isinstance(suid, str) or not suid:
        return False

    # Handle Responses API IDs
    if suid.startswith("resp-") or suid.startswith("resp_"):
        token = suid[5:]
        if not token:
            return False
        # If truncated (e.g., shell cut reduced length), pad to canonical UUID length
        if len(token) < 36:
            token = token + ("0" * (36 - len(token)))
        try:
            uuid.UUID(token)
            return True
        except (ValueError, TypeError):
            return False

    # Otherwise, enforce UUID format
    try:
        uuid.UUID(suid)
        return True
    except (ValueError, TypeError):
        return False
