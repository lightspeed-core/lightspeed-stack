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

from log import get_logger

logger = get_logger(__name__)

_ADD_POSITION_COLUMN_SQL = "ALTER TABLE saved_prompt ADD COLUMN position INTEGER"

_BACKFILL_POSITION_SQL = """
WITH numbered AS (
    SELECT id, ROW_NUMBER() OVER (
        PARTITION BY user_id ORDER BY created_at DESC, id
    ) AS rn
    FROM saved_prompt
    WHERE position IS NULL
)
UPDATE saved_prompt
SET position = (SELECT rn FROM numbered WHERE numbered.id = saved_prompt.id)
WHERE position IS NULL
"""


def run_startup_migrations(engine: Engine) -> None:
    """Bring an existing saved_prompt table up to the current schema.

    Detects whether the ``saved_prompt`` table exists and whether it is
    missing the ``position`` column. When the column is missing, adds it and
    backfills deterministic per-user positions: each user's prompts are
    numbered 1..N by ``created_at`` descending (preserving the pre-migration
    newest-first list order), with ties broken by ``id`` so the result is
    deterministic. Databases where the table or column is already present
    are left untouched, so the call is safe on every boot.

    Parameters:
        engine: Database engine to migrate (from ``app.database.get_engine``).

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If the ALTER or backfill fails; the
            service should fail startup rather than serve queries against a
            schema the ORM cannot read.

    """
    inspector = inspect(engine)
    if "saved_prompt" not in inspector.get_table_names():
        logger.debug("saved_prompt table absent; nothing to migrate")
        return

    columns = {column["name"] for column in inspector.get_columns("saved_prompt")}
    if "position" in columns:
        logger.debug("saved_prompt.position already present; nothing to migrate")
        return

    with engine.begin() as connection:
        connection.execute(text(_ADD_POSITION_COLUMN_SQL))
        row_count = connection.execute(
            text("SELECT COUNT(*) FROM saved_prompt")
        ).scalar_one()
        connection.execute(text(_BACKFILL_POSITION_SQL))
    logger.info(
        "Migrated saved_prompt: added position column and backfilled %s rows",
        row_count,
    )
