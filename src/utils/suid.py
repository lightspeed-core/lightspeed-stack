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
    Check if given string is a proper session ID.

    Returns True if the string is a valid UUID, False otherwise.

    Parameters:
        suid (str | bytes): UUID value to validate — accepts a UUID string or
        its byte representation.

    Notes:
        Validation is performed by attempting to construct uuid.UUID(suid);
        invalid formats or types result in False.
    """
    try:
        # accepts strings and bytes only
        uuid.UUID(suid)
        return True
    except (ValueError, TypeError):
        return False
