"""Validation helpers and data access for saved prompts."""

from sqlalchemy.exc import IntegrityError

from app.database import get_session
from log import get_logger
from models.database.saved_prompts import SavedPrompt
from utils.suid import get_suid

logger = get_logger(__name__)


class SavedPromptError(Exception):
    """Base class for saved-prompt domain errors."""


class SavedPromptValidationError(SavedPromptError):
    """Invalid saved-prompt field values."""


class SavedPromptLimitExceededError(SavedPromptValidationError):
    """Per-user saved-prompt count would exceed the configured maximum."""


class SavedPromptNotFoundError(SavedPromptError):
    """No saved prompt exists for the given identifier."""


class SavedPromptAccessDeniedError(SavedPromptError):
    """The saved prompt exists but is not owned by the requesting user."""


class SavedPromptConflictError(SavedPromptError):
    """A saved prompt conflicts with an existing unique constraint."""


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


def create_saved_prompt(
    user_id: str,
    name: str,
    content: str,
    max_prompts_per_user: int,
) -> SavedPrompt:
    """Create a saved prompt for a user after enforcing the per-user quota.

    Caller is responsible for validating ``name`` and ``content``. This function
    counts existing prompts for ``user_id``, enforces ``max_prompts_per_user``,
    inserts a new row with a generated id, and returns the persisted entity with
    timestamps loaded.

    Parameters:
        user_id: Owner of the saved prompt.
        name: Display name as provided by the caller (not stripped here).
        content: Prompt body as provided by the caller.
        max_prompts_per_user: Maximum prompts the user may hold.

    Returns:
        The created ``SavedPrompt`` with id and timestamps populated.

    Raises:
        SavedPromptLimitExceededError: If the user is already at the limit.
        SavedPromptConflictError: If insert violates a unique constraint
            (typically duplicate ``(user_id, name)``).
    """
    with get_session() as session:
        current_count = session.query(SavedPrompt).filter_by(user_id=user_id).count()
        validate_saved_prompt_quota(current_count, max_prompts_per_user)

        saved_prompt = SavedPrompt(
            id=get_suid(),
            user_id=user_id,
            name=name,
            content=content,
        )
        session.add(saved_prompt)
        try:
            session.commit()
        except IntegrityError as exc:
            logger.debug(
                "Saved prompt create conflict for user_id=%s",
                user_id,
            )
            raise SavedPromptConflictError("Saved prompt name already exists") from exc

        # reload server default timestamps so they remain usable after the session closes
        session.refresh(saved_prompt)
        logger.debug(
            "Created saved prompt id=%s for user_id=%s",
            saved_prompt.id,
            user_id,
        )
        return saved_prompt


def list_saved_prompts_by_user(user_id: str) -> list[SavedPrompt]:
    """List saved prompts for a user ordered by created_at descending.

    Parameters:
        user_id: Owner whose prompts should be returned.

    Returns:
        List of ``SavedPrompt`` rows for the user. Empty list if none exist.
        Tie order when ``created_at`` values are equal is database-defined.
    """
    with get_session() as session:
        return (
            session.query(SavedPrompt)
            .filter_by(user_id=user_id)
            .order_by(SavedPrompt.created_at.desc())
            .all()
        )


def delete_saved_prompt_by_id_and_user(prompt_id: str, user_id: str) -> None:
    """Delete a saved prompt only if it belongs to the given user.

    Parameters:
        prompt_id: Primary key of the saved prompt.
        user_id: Authenticated user attempting the delete.

    Raises:
        SavedPromptNotFoundError: If no row exists for ``prompt_id``.
        SavedPromptAccessDeniedError: If the row exists but ``user_id`` does not
            match the owner.
    """
    with get_session() as session:
        saved_prompt = session.query(SavedPrompt).filter_by(id=prompt_id).first()
        if saved_prompt is None:
            logger.debug(
                "Saved prompt not found for delete prompt_id=%s user_id=%s",
                prompt_id,
                user_id,
            )
            raise SavedPromptNotFoundError("Saved prompt not found")

        if saved_prompt.user_id != user_id:
            logger.debug(
                "Saved prompt access denied for delete prompt_id=%s user_id=%s",
                prompt_id,
                user_id,
            )
            raise SavedPromptAccessDeniedError("Saved prompt access denied")

        session.delete(saved_prompt)
        session.commit()
        logger.debug(
            "Deleted saved prompt id=%s for user_id=%s",
            prompt_id,
            user_id,
        )
