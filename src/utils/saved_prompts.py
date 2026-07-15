"""Validation helpers for saved prompts."""


class SavedPromptValidationError(Exception):
    """Invalid saved-prompt field values."""


class SavedPromptLimitExceededError(SavedPromptValidationError):
    """Per-user saved-prompt count would exceed the configured maximum."""


def validate_saved_prompt_quota(
    current_count: int,
    max_prompts_per_user: int,
) -> None:
    """Raise if creating another saved prompt would exceed the per-user maximum.

    The maximum is inclusive so a configured limit of N means the user may hold
    N prompts (create is rejected only when they already have N). Call when
    ``current_count`` is the number of prompts the user already has.

    Parameters:
        current_count: Number of saved prompts the user currently has.
        max_prompts_per_user: Configured maximum prompts allowed per user.

    Raises:
        SavedPromptLimitExceededError: If ``current_count >= max_prompts_per_user``.
    """
    if current_count >= max_prompts_per_user:
        raise SavedPromptLimitExceededError(
            f"Saved prompt limit exceeded: {current_count} existing prompts, "
            f"maximum is {max_prompts_per_user}"
        )


def validate_saved_prompt_name(
    name: str,
    max_display_name_length: int,
) -> str:
    """Validate and normalize a saved-prompt name.

    Strips leading/trailing whitespace before checks because names are labels:
    padding is not meaningful and would otherwise create near-duplicate names
    under uniqueness constraints. Requires a non-empty stripped value whose
    length does not exceed ``max_display_name_length``.

    Parameters:
        name: Prompt display name.
        max_display_name_length: Maximum allowed length for the stripped name.

    Returns:
        The stripped ``name``.

    Raises:
        SavedPromptValidationError: If the name fails validation.
    """
    stripped_name = name.strip()
    if not stripped_name:
        raise SavedPromptValidationError("Saved prompt name must not be empty")
    if len(stripped_name) > max_display_name_length:
        raise SavedPromptValidationError(
            f"Saved prompt name length {len(stripped_name)} exceeds maximum "
            f"{max_display_name_length}"
        )
    return stripped_name


def validate_saved_prompt_content(
    content: str,
    max_content_length: int,
) -> None:
    """Validate a saved-prompt content body.

    Uses ``strip()`` only to detect blank prompts (empty or whitespace-only).
    Non-blank content is left unchanged so intentional leading/trailing
    whitespace in the prompt body is preserved; length is measured on that
    original string.

    Parameters:
        content: Prompt body.
        max_content_length: Maximum allowed length for the original content.

    Raises:
        SavedPromptValidationError: If the content fails validation.
    """
    if not content.strip():
        raise SavedPromptValidationError("Saved prompt content must not be empty")
    if len(content) > max_content_length:
        raise SavedPromptValidationError(
            f"Saved prompt content length {len(content)} exceeds maximum "
            f"{max_content_length}"
        )
