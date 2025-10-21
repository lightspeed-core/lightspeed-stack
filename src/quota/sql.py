"""SQL commands used by quota management package."""

CREATE_QUOTA_TABLE = """
    CREATE TABLE IF NOT EXISTS quota_limits (
        id              text NOT NULL,
        subject         char(1) NOT NULL,
        quota_limit     int NOT NULL,
        available       int,
        updated_at      timestamp with time zone,
        revoked_at      timestamp with time zone,
        PRIMARY KEY(id, subject)
    );
    """


INCREASE_QUOTA_STATEMENT_PG = """
    UPDATE quota_limits
       SET available=available+%s, revoked_at=NOW()
     WHERE subject=%s
       AND revoked_at < NOW() - INTERVAL %s ;
    """


INCREASE_QUOTA_STATEMENT_SQLITE = """
    UPDATE quota_limits
       SET available=available+?, revoked_at=datetime('now')
     WHERE subject=?
       AND revoked_at < datetime('now', ?);
    """


RESET_QUOTA_STATEMENT_PG = """
    UPDATE quota_limits
       SET available=%s, revoked_at=NOW()
     WHERE subject=%s
       AND revoked_at < NOW() - INTERVAL %s ;
    """


RESET_QUOTA_STATEMENT_SQLITE = """
    UPDATE quota_limits
       SET available=?, revoked_at=datetime('now')
     WHERE subject=?
       AND revoked_at < datetime('now', ?);
    """

INIT_QUOTA_PG = """
    INSERT INTO quota_limits (id, subject, quota_limit, available, revoked_at)
    VALUES (%s, %s, %s, %s, %s)
    """

SELECT_QUOTA_PG = """
    SELECT available
      FROM quota_limits
     WHERE id=%s and subject=%s LIMIT 1
    """

SET_AVAILABLE_QUOTA_PG = """
    UPDATE quota_limits
       SET available=%s, revoked_at=%s
     WHERE id=%s and subject=%s
    """

UPDATE_AVAILABLE_QUOTA_PG = """
    UPDATE quota_limits
       SET available=available+%s, updated_at=%s
     WHERE id=%s and subject=%s
    """
