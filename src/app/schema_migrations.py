"""Startup schema migrations for existing deployments.

``Base.metadata.create_all`` creates missing tables but never alters existing
ones, so schema changes to tables that already exist in production databases
must be handled here. Each migration is a detect-then-apply step: it checks
whether the target state is already present (making repeated runs idempotent)
and applies a minimal ``ALTER TABLE`` plus backfill otherwise.

The SQL used here must work on both supported dialects (SQLite and
PostgreSQL): column presence is detected through the dialect-agnostic
SQLAlchemy inspector, and the backfill uses a correlated subquery rather
than the ``UPDATE ... FROM`` form that differs between dialects.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from log import get_logger

logger = get_logger(__name__)

_ADD_POSITION_COLUMN_SQL = "ALTER TABLE saved_prompt ADD COLUMN position INTEGER"

_BACKFILL_POSITION_SQL = """
WITH user_max AS (
    SELECT user_id, COALESCE(MAX(position), 0) AS max_position
    FROM saved_prompt
    GROUP BY user_id
),
numbered AS (
    SELECT prompt.id,
           ROW_NUMBER() OVER (
               PARTITION BY prompt.user_id
               ORDER BY prompt.created_at DESC, prompt.id
           ) + user_max.max_position AS rn
    FROM saved_prompt AS prompt
    JOIN user_max ON user_max.user_id = prompt.user_id
    WHERE prompt.position IS NULL
)
UPDATE saved_prompt
SET position = (SELECT rn FROM numbered WHERE numbered.id = saved_prompt.id)
WHERE position IS NULL
"""


def _is_duplicate_column_error(exc: OperationalError) -> bool:
    """Check whether an ALTER failure means another worker added the column.

    Parameters:
        exc: The OperationalError raised by the ALTER TABLE.

    Returns:
        True on the duplicate-column errors of either supported dialect:
        SQLite's ``duplicate column name: position`` and PostgreSQL's
        ``column "position" of relation "saved_prompt" already exists``.

    """
    message = str(getattr(exc, "orig", exc)).lower()
    return "duplicate column name" in message or (
        'column "position"' in message and "already exists" in message
    )


def run_startup_migrations(engine: Engine) -> None:
    """Bring an existing saved_prompt table up to the current schema.

    Detects whether the ``saved_prompt`` table exists and whether it is
    missing the ``position`` column. When the column is missing, adds it.
    Then, on every boot, backfills rows with a NULL position: when the
    column was just added, each user's prompts are numbered 1..N by
    ``created_at`` descending (preserving the pre-migration newest-first
    list order), with ties broken by ``id``; when only some rows are NULL
    (rows written by old-code pods during a rolling update), they are
    appended after the user's current maximum position. The backfill is a
    no-op when no NULL rows exist, so the call is safe on every boot.

    Concurrent replicas booting simultaneously can both observe the
    pre-migration schema; the worker whose ALTER loses the race sees a
    duplicate-column error, which is tolerated (the migration is
    idempotent) so startup continues with the backfill.

    Parameters:
        engine: Database engine to migrate (from ``app.database.get_engine``).

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If the ALTER or backfill fails for
            any reason other than a lost duplicate-column race; the service
            should fail startup rather than serve queries against a schema
            the ORM cannot read.

    """
    inspector = inspect(engine)
    if "saved_prompt" not in inspector.get_table_names():
        logger.debug("saved_prompt table absent; nothing to migrate")
        return

    columns = {column["name"] for column in inspector.get_columns("saved_prompt")}
    column_added = "position" not in columns
    if column_added:
        with engine.begin() as connection:
            try:
                connection.execute(text(_ADD_POSITION_COLUMN_SQL))
            except OperationalError as exc:
                if not _is_duplicate_column_error(exc):
                    raise
                logger.info(
                    "saved_prompt.position was added concurrently by another "
                    "worker; continuing with backfill"
                )
    else:
        logger.debug("saved_prompt.position already present")

    # Run on every boot: heals NULL positions written by old-code pods
    # during a rolling update, not only the one-time column addition.
    with engine.begin() as connection:
        result = connection.execute(text(_BACKFILL_POSITION_SQL))
        healed = result.rowcount
    if column_added:
        logger.info(
            "Migrated saved_prompt: added position column and backfilled %s rows",
            healed,
        )
    elif healed:
        logger.info("Healed %s saved_prompt rows with NULL position", healed)
