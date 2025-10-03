"""Session ID utility functions."""

import uuid


def get_suid() -> str:
    """
    Generate a unique session ID (SUID) using UUID4.

    The value is a canonical RFC 4122 UUID (hex groups separated by
    hyphens) generated with uuid.uuid4().

    Returns:
        str: A UUID4 string suitable for use as a session identifier.
    """
    return str(uuid.uuid4())


def check_suid(suid: str) -> bool:
    """
    Check if given string is a proper session ID or response ID.

    Returns True if the string is a valid UUID or if it starts with resp-/resp_
    and it follows a valid UUID string, False otherwise.

    Parameters:
        suid (str | bytes): UUID value to validate — accepts a UUID string or
        its byte representation.

    Notes:
        Validation is performed by attempting to construct uuid.UUID(suid);
        invalid formats or types result in False.
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
