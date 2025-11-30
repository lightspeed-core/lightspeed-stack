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

    Returns True if the string is a valid UUID or a llama-stack conversation ID.

    Parameters:
        suid (str | bytes): UUID value to validate — accepts a UUID string,
        its byte representation, or a llama-stack conversation ID (conv_xxx),
        or a plain hex string (database format).

    Notes:
        Validation is performed by:
        1. For llama-stack conversation IDs starting with 'conv_':
           - Strips the 'conv_' prefix
           - Validates at least 32 hex characters follow (may have additional suffix)
           - Extracts first 32 hex chars as the UUID part
           - Converts to UUID format by inserting hyphens at standard positions
           - Validates the resulting UUID structure
        2. For plain hex strings (database format, 32+ chars without conv_ prefix):
           - Validates it's a valid hex string
           - Extracts first 32 chars as UUID part
           - Converts to UUID format and validates
        3. For standard UUIDs: attempts to construct uuid.UUID(suid)
        Invalid formats or types result in False.
    """
    try:
        # Accept llama-stack conversation IDs (conv_<hex> format)
        if isinstance(suid, str) and suid.startswith("conv_"):
            # Extract the hex string after 'conv_'
            hex_part = suid[5:]  # Remove 'conv_' prefix

            # Verify it's a valid hex string
            # llama-stack may use 32 hex chars (UUID) or 36 hex chars (UUID + suffix)
            if len(hex_part) < 32:
                return False

            # Verify all characters are valid hex
            try:
                int(hex_part, 16)
            except ValueError:
                return False

            # Extract the first 32 hex characters (the UUID part)
            uuid_hex = hex_part[:32]

            # Convert to UUID format with hyphens: 8-4-4-4-12
            uuid_str = (
                f"{uuid_hex[:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                f"{uuid_hex[16:20]}-{uuid_hex[20:]}"
            )

            # Validate it's a proper UUID
            uuid.UUID(uuid_str)
            return True

        # Check if it's a plain hex string (database format without conv_ prefix)
        if isinstance(suid, str) and len(suid) >= 32:
            try:
                int(suid, 16)
                # Extract the first 32 hex characters (the UUID part)
                uuid_hex = suid[:32]

                # Convert to UUID format with hyphens: 8-4-4-4-12
                uuid_str = (
                    f"{uuid_hex[:8]}-{uuid_hex[8:12]}-{uuid_hex[12:16]}-"
                    f"{uuid_hex[16:20]}-{uuid_hex[20:]}"
                )

                # Validate it's a proper UUID
                uuid.UUID(uuid_str)
                return True
            except ValueError:
                pass  # Not a valid hex string, try standard UUID validation

        # accepts strings and bytes only for UUID validation
        uuid.UUID(suid)
        return True
    except (ValueError, TypeError):
        return False


def normalize_conversation_id(conversation_id: str) -> str:
    """
    Normalize a conversation ID for database storage.

    Strips the 'conv_' prefix if present to store just the UUID part.
    This keeps IDs shorter and database-agnostic.

    Args:
        conversation_id: The conversation ID, possibly with 'conv_' prefix.

    Returns:
        str: The normalized ID without 'conv_' prefix.

    Examples:
        >>> normalize_conversation_id('conv_abc123')
        'abc123'
        >>> normalize_conversation_id('550e8400-e29b-41d4-a716-446655440000')
        '550e8400-e29b-41d4-a716-446655440000'
    """
    if conversation_id.startswith("conv_"):
        return conversation_id[5:]  # Remove 'conv_' prefix
    return conversation_id


def to_llama_stack_conversation_id(conversation_id: str) -> str:
    """
    Convert a database conversation ID to llama-stack format.

    Adds the 'conv_' prefix if not already present.

    Args:
        conversation_id: The conversation ID from database.

    Returns:
        str: The conversation ID in llama-stack format (conv_xxx).

    Examples:
        >>> to_llama_stack_conversation_id('abc123')
        'conv_abc123'
        >>> to_llama_stack_conversation_id('conv_abc123')
        'conv_abc123'
    """
    if not conversation_id.startswith("conv_"):
        return f"conv_{conversation_id}"
    return conversation_id
