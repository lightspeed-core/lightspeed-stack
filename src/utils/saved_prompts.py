"""Validation helpers and data access for saved prompts."""

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import constants
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


def _next_position(session: Session, user_id: str) -> int:
    """Compute the next per-user position for a new saved prompt.

    Positions are append-only on create: the next value is one past the
    user's current maximum, so deletions leave gaps that are never backfilled.

    Parameters:
        session: DAL session to query within.
        user_id: Owner whose maximum position is looked up.

    Returns:
        The next position value (1 for a user with no prompts).

    """
    max_position = (
        session.query(func.max(SavedPrompt.position))
        .filter_by(user_id=user_id)
        .scalar()
    )
    return (max_position or 0) + 1


def _is_position_conflict(exc: IntegrityError) -> bool:
    """Check whether an IntegrityError comes from the position unique constraint.

    Parameters:
        exc: The IntegrityError raised by a commit.

    Returns:
        True if the error references the per-user position constraint.

    """
    message = str(getattr(exc, "orig", exc)).lower()
    return "position" in message


def create_saved_prompt(
    user_id: str,
    name: str,
    content: str,
    max_prompts_per_user: int,
) -> SavedPrompt:
    """Create a saved prompt for a user after enforcing the per-user quota.

    Caller is responsible for validating ``name`` and ``content``. This function
    counts existing prompts for ``user_id``, enforces ``max_prompts_per_user``,
    inserts a new row with a generated id and the user's next append position,
    and returns the persisted entity with timestamps loaded. If a concurrent
    create wins the same position (unique constraint violation), the insert is
    retried once with a freshly computed position.

    Parameters:
        user_id: Owner of the saved prompt.
        name: Display name as provided by the caller (not stripped here).
        content: Prompt body as provided by the caller.
        max_prompts_per_user: Maximum prompts the user may hold.

    Returns:
        The created ``SavedPrompt`` with id, position, and timestamps populated.

    Raises:
        SavedPromptLimitExceededError: If the user is already at the limit.
        SavedPromptConflictError: If insert violates a unique constraint
            (practically always duplicate ``(user_id, name)``).

    """
    with get_session() as session:
        current_count = session.query(SavedPrompt).filter_by(user_id=user_id).count()
        validate_saved_prompt_quota(current_count, max_prompts_per_user)

        saved_prompt = SavedPrompt(
            id=get_suid(),
            user_id=user_id,
            name=name,
            content=content,
            position=_next_position(session, user_id),
        )
        session.add(saved_prompt)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if _is_position_conflict(exc):
                # A concurrent create took the same position; retry once
                # with a freshly computed maximum before giving up.
                logger.debug(
                    "Saved prompt position conflict for user_id=%s, retrying",
                    user_id,
                )
                saved_prompt.position = _next_position(session, user_id)
                session.add(saved_prompt)
                try:
                    session.commit()
                except IntegrityError as retry_exc:
                    session.rollback()
                    logger.debug(
                        "Saved prompt create conflict for user_id=%s",
                        user_id,
                    )
                    raise SavedPromptConflictError(
                        "Saved prompt name already exists"
                    ) from retry_exc
            else:
                logger.debug(
                    "Saved prompt create conflict for user_id=%s",
                    user_id,
                )
                raise SavedPromptConflictError(
                    "Saved prompt name already exists"
                ) from exc

        # reload server default timestamps so they remain usable after the session closes
        session.refresh(saved_prompt)
        logger.debug(
            "Created saved prompt id=%s for user_id=%s",
            saved_prompt.id,
            user_id,
        )
        return saved_prompt


def list_saved_prompts_by_user(user_id: str) -> list[SavedPrompt]:
    """List saved prompts for a user ordered by position ascending.

    Order is ``position`` ascending with ``created_at`` descending and ``id``
    as deterministic tiebreakers, so results stay stable even when duplicate
    positions exist (possible on deployments upgraded before the
    ``(user_id, position)`` unique constraint). Results are capped at
    ``SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND`` so a misconfigured or
    out-of-band insert path cannot materialize unbounded rows.

    Parameters:
        user_id: Owner whose prompts should be returned.

    Returns:
        List of ``SavedPrompt`` rows for the user. Empty list if none exist.

    """
    with get_session() as session:
        return (
            session.query(SavedPrompt)
            .filter_by(user_id=user_id)
            .order_by(
                SavedPrompt.position.asc(),
                SavedPrompt.created_at.desc(),
                SavedPrompt.id,
            )
            .limit(constants.SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND)
            .all()
        )


def _renumber_positions(
    session: Session,
    user_id: str,
    target_id: str,
    new_position: int,
) -> None:
    """Move one prompt to ``new_position`` and normalize the user's positions.

    The move is applied in two phases inside the caller's transaction: first
    every row of the user is shifted to values beyond any existing position,
    then all rows are normalized to a dense 1..N sequence. The two phases
    avoid transient collisions that would violate the
    ``(user_id, position)`` unique constraint on tables that enforce it.
    A ``new_position`` above the number of prompts the user holds moves the
    prompt to the end.

    Parameters:
        session: DAL session to query and update within.
        user_id: Owner whose prompts are renumbered.
        target_id: Primary key of the prompt being moved.
        new_position: Target position (1-based, clamped to the end).

    """
    rows = (
        session.query(SavedPrompt)
        .filter_by(user_id=user_id)
        .order_by(
            SavedPrompt.position.asc(),
            SavedPrompt.created_at.desc(),
            SavedPrompt.id,
        )
        .all()
    )
    ordered_ids = [row.id for row in rows]
    ordered_ids.remove(target_id)
    insert_index = min(new_position, len(ordered_ids) + 1) - 1
    ordered_ids.insert(insert_index, target_id)

    offset = len(ordered_ids) + 1
    # Phase 1: shift beyond any existing value so no intermediate state
    # collides with a still-present old position.
    for sequence, row_id in enumerate(ordered_ids):
        session.query(SavedPrompt).filter_by(id=row_id).update(
            {"position": sequence + 1 + offset}
        )
    session.flush()
    # Phase 2: normalize to a dense 1..N sequence.
    for sequence, row_id in enumerate(ordered_ids):
        session.query(SavedPrompt).filter_by(id=row_id).update(
            {"position": sequence + 1}
        )


def update_saved_prompt_by_id_and_user(
    prompt_id: str,
    user_id: str,
    name: str,
    content: str,
    position: int,
) -> SavedPrompt:
    """Update a saved prompt in place, reordering within the user's list.

    Applies full-replace semantics: ``name`` and ``content`` are set to the
    given values and the prompt is moved to ``position`` (clamped to the end
    when above the user's prompt count), with the user's remaining positions
    renormalized deterministically to 1..N. Ownership is enforced the same
    way as delete.

    Parameters:
        prompt_id: Primary key of the saved prompt.
        user_id: Authenticated user attempting the update.
        name: New display name (validated by the caller).
        content: New prompt body (validated by the caller).
        position: New position (1-based, validated by the caller).

    Returns:
        The updated ``SavedPrompt`` with refreshed timestamps.

    Raises:
        SavedPromptNotFoundError: If no row exists for ``prompt_id``.
        SavedPromptAccessDeniedError: If the row exists but ``user_id`` does
            not match the owner.
        SavedPromptConflictError: If the update violates a unique constraint
            (practically always renaming to a ``(user_id, name)`` that
            already exists).

    """
    with get_session() as session:
        saved_prompt = session.query(SavedPrompt).filter_by(id=prompt_id).first()
        if saved_prompt is None:
            logger.debug(
                "Saved prompt not found for update prompt_id=%s user_id=%s",
                prompt_id,
                user_id,
            )
            raise SavedPromptNotFoundError("Saved prompt not found")

        if saved_prompt.user_id != user_id:
            logger.debug(
                "Saved prompt access denied for update prompt_id=%s user_id=%s",
                prompt_id,
                user_id,
            )
            raise SavedPromptAccessDeniedError("Saved prompt access denied")

        saved_prompt.name = name
        saved_prompt.content = content
        try:
            _renumber_positions(session, user_id, prompt_id, position)
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            logger.debug(
                "Saved prompt update conflict for prompt_id=%s",
                prompt_id,
            )
            raise SavedPromptConflictError("Saved prompt name already exists") from exc

        # reload server-generated timestamps so they remain usable after
        # the session closes
        session.refresh(saved_prompt)
        logger.debug(
            "Updated saved prompt id=%s for user_id=%s",
            saved_prompt.id,
            user_id,
        )
        return saved_prompt


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
