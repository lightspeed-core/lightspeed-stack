"""Validation helpers and data access for saved prompts."""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, load_only

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
    and returns the persisted entity with timestamps loaded. If the insert
    violates a unique constraint, it is retried once with a freshly computed
    position (a concurrent create may have transiently taken the same
    position); a conflict that survives the retry is reported as a name
    conflict.

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
        for attempt in range(2):
            try:
                session.commit()
                break
            except IntegrityError as exc:
                session.rollback()
                if attempt > 0:
                    logger.debug(
                        "Saved prompt create conflict for user_id=%s",
                        user_id,
                    )
                    raise SavedPromptConflictError(
                        "Saved prompt name already exists"
                    ) from exc
                # A concurrent create may have transiently taken the computed
                # position; retry once with a fresh maximum. A name conflict
                # is not transient and fails again on the next commit.
                logger.debug(
                    "Saved prompt insert conflict for user_id=%s, retrying",
                    user_id,
                )
                saved_prompt.position = _next_position(session, user_id)
                session.add(saved_prompt)

        # reload server default timestamps so they remain usable after the session closes
        session.refresh(saved_prompt)
        logger.debug(
            "Created saved prompt id=%s for user_id=%s",
            saved_prompt.id,
            user_id,
        )
        return saved_prompt


def _heal_null_positions(session: Session, rows: list[SavedPrompt]) -> None:
    """Assign positions to rows written without one (lazy healing).

    Old-code pods serving during a rolling update insert rows with a NULL
    position after the new pod has already migrated. Such rows are appended
    after the user's current maximum position, newest first, so the list
    endpoint can return them instead of failing response validation.

    Parameters:
        session: DAL session the rows belong to; changes are flushed by the
            caller's commit.
        rows: The user's rows as fetched by the list query.

    """
    positioned = [row.position for row in rows if row.position is not None]
    next_position = (max(positioned) if positioned else 0) + 1
    strays = [row for row in rows if row.position is None]
    # created_at DESC with id ASC as tiebreaker, matching the startup
    # backfill rule; two stable sorts achieve the mixed direction.
    strays.sort(key=lambda row: row.id)
    strays.sort(key=lambda row: row.created_at, reverse=True)
    for stray in strays:
        stray.position = next_position
        next_position += 1
    session.flush()


def _ordered_user_prompts(
    session: Session,
    user_id: str,
    *,
    limit: Optional[int] = None,
    defer_body: bool = False,
) -> tuple[list[SavedPrompt], bool]:
    """Load a user's prompts in canonical order, healing NULL positions.

    This is the single loader shared by every saved-prompt read and
    renumber path, so the ordering contract — ``position`` ascending with
    ``created_at`` descending and ``id`` as deterministic tiebreakers
    (stable even with duplicate positions, possible on deployments upgraded
    before the ``(user_id, position)`` unique constraint) — is defined once.
    Rows with a NULL position (written by old-code pods during a rolling
    update) are healed by appending them after the user's maximum position
    and the query is re-run so the returned rows reflect the healed order.

    Parameters:
        session: DAL session to query within.
        user_id: Owner whose prompts are loaded.
        limit: Optional row cap (the list endpoint caps at
            ``SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND``).
        defer_body: Defer loading the large ``content`` column; set when the
            caller only renumbers rows and never reads the body.

    Returns:
        The ordered rows and whether NULL positions were healed (the caller
        owns committing the heal).

    """
    query = session.query(SavedPrompt).filter_by(user_id=user_id)
    if defer_body:
        query = query.options(
            load_only(SavedPrompt.id, SavedPrompt.position, SavedPrompt.created_at)
        )
    query = query.order_by(
        SavedPrompt.position.asc(),
        SavedPrompt.created_at.desc(),
        SavedPrompt.id,
    )
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
    if not any(row.position is None for row in rows):
        return rows, False
    # Heal over the user's FULL row set, not just the capped window: strays
    # beyond a cap would otherwise re-enter the window on the re-query
    # (NULLs sort first on SQLite) and collide with freshly assigned
    # positions. The uncapped recursive call performs the heal.
    if limit is not None:
        _ordered_user_prompts(session, user_id)
    else:
        _heal_null_positions(session, rows)
    return query.all(), True


def list_saved_prompts_by_user(user_id: str) -> list[SavedPrompt]:
    """List saved prompts for a user ordered by position ascending.

    Rows are loaded in canonical order (see ``_ordered_user_prompts``),
    capped at ``SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND`` so a misconfigured
    or out-of-band insert path cannot materialize unbounded rows. NULL
    positions, if any, are healed and committed before returning.

    Parameters:
        user_id: Owner whose prompts should be returned.

    Returns:
        List of ``SavedPrompt`` rows for the user. Empty list if none exist.

    """
    with get_session() as session:
        rows, healed = _ordered_user_prompts(
            session,
            user_id,
            limit=constants.SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND,
        )
        if healed:
            session.commit()
            # commit expires the loaded rows; re-load them fresh
            rows, _ = _ordered_user_prompts(
                session,
                user_id,
                limit=constants.SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND,
            )
        return rows


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
    rows, _healed = _ordered_user_prompts(session, user_id, defer_body=True)
    target = next(row for row in rows if row.id == target_id)
    rows.remove(target)
    insert_index = min(new_position, len(rows) + 1) - 1
    rows.insert(insert_index, target)

    # Positions are not dense: creates append max+1 and deletes never
    # renumber, so a user's max position can far exceed their row count.
    # The phase-1 offset must therefore clear the *max existing position*,
    # not the row count, or a still-present old position inside the target
    # range collides mid-renumber.
    max_existing = max((row.position or 0) for row in rows)
    offset = max(max_existing, len(rows)) + 1
    # Phase 1: shift beyond any existing value so no intermediate state
    # collides with a still-present old position.
    for sequence, row in enumerate(rows):
        row.position = sequence + 1 + offset
    session.flush()
    # Phase 2: normalize to a dense 1..N sequence.
    for sequence, row in enumerate(rows):
        row.position = sequence + 1


def _get_owned_saved_prompt(
    session: Session,
    prompt_id: str,
    user_id: str,
    action: str,
) -> SavedPrompt:
    """Fetch a saved prompt and enforce ownership for a mutating action.

    Shared by the update and delete paths so the ownership ladder (missing
    row, wrong owner) is defined once.

    Parameters:
        session: DAL session to query within.
        prompt_id: Primary key of the saved prompt.
        user_id: Authenticated user attempting the action.
        action: Action name for log messages (e.g. "update", "delete").

    Returns:
        The owned ``SavedPrompt`` row.

    Raises:
        SavedPromptNotFoundError: If no row exists for ``prompt_id``.
        SavedPromptAccessDeniedError: If the row exists but ``user_id`` does
            not match the owner.

    """
    saved_prompt = session.query(SavedPrompt).filter_by(id=prompt_id).first()
    if saved_prompt is None:
        logger.debug(
            "Saved prompt not found for %s prompt_id=%s user_id=%s",
            action,
            prompt_id,
            user_id,
        )
        raise SavedPromptNotFoundError("Saved prompt not found")

    if saved_prompt.user_id != user_id:
        logger.debug(
            "Saved prompt access denied for %s prompt_id=%s user_id=%s",
            action,
            prompt_id,
            user_id,
        )
        raise SavedPromptAccessDeniedError("Saved prompt access denied")
    return saved_prompt


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
        saved_prompt = _get_owned_saved_prompt(session, prompt_id, user_id, "update")

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
        saved_prompt = _get_owned_saved_prompt(session, prompt_id, user_id, "delete")

        session.delete(saved_prompt)
        session.commit()
        logger.debug(
            "Deleted saved prompt id=%s for user_id=%s",
            prompt_id,
            user_id,
        )
