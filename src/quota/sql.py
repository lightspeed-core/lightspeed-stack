"""SQL commands used by quota management package."""

CREATE_QUOTA_TABLE_PG = """
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


CREATE_QUOTA_TABLE_SQLITE = """
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

INIT_QUOTA_SQLITE = """
    INSERT INTO quota_limits (id, subject, quota_limit, available, revoked_at)
    VALUES (?, ?, ?, ?, ?)
    """

SELECT_QUOTA_PG = """
    SELECT available
      FROM quota_limits
     WHERE id=%s AND subject=%s LIMIT 1
    """

SELECT_QUOTA_SQLITE = """
    SELECT available
      FROM quota_limits
     WHERE id=? AND subject=? LIMIT 1
    """

SET_AVAILABLE_QUOTA_PG = """
    UPDATE quota_limits
       SET available=%s, revoked_at=%s
     WHERE id=%s AND subject=%s
    """

SET_AVAILABLE_QUOTA_SQLITE = """
    UPDATE quota_limits
       SET available=?, revoked_at=?
     WHERE id=? AND subject=?
    """

UPDATE_AVAILABLE_QUOTA_PG = """
    UPDATE quota_limits
       SET available=available+%s, updated_at=%s
     WHERE id=%s AND subject=%s
    """

UPDATE_AVAILABLE_QUOTA_SQLITE = """
    UPDATE quota_limits
       SET available=available+?, updated_at=?
     WHERE id=? AND subject=?
    """

CREATE_TOKEN_USAGE_TABLE = """
    CREATE TABLE IF NOT EXISTS token_usage (
        user_id         text NOT NULL,
        provider        text NOT NULL,
        model           text NOT NULL,
        input_tokens    int,
        output_tokens   int,
        updated_at      timestamp with time zone,
        PRIMARY KEY(user_id, provider, model)
    );
    """  # noqa: S105

INIT_TOKEN_USAGE_FOR_USER = """
    INSERT INTO token_usage (user_id, provider, model, input_tokens, output_tokens, updated_at)
    VALUES (%s, %s, %s, 0, 0, %s)
    """  # noqa: S105

CONSUME_TOKENS_FOR_USER_SQLITE = """
    INSERT INTO token_usage (user_id, provider, model, input_tokens, output_tokens, updated_at)
    VALUES (:user_id, :provider, :model, :input_tokens, :output_tokens, :updated_at)
    ON CONFLICT (user_id, provider, model)
    DO UPDATE
       SET input_tokens=token_usage.input_tokens+:input_tokens,
           output_tokens=token_usage.output_tokens+:output_tokens,
           updated_at=:updated_at
     WHERE token_usage.user_id=:user_id
       AND token_usage.provider=:provider
       AND token_usage.model=:model
    """  # noqa: E501

CONSUME_TOKENS_FOR_USER_PG = """
    INSERT INTO token_usage (user_id, provider, model, input_tokens, output_tokens, updated_at)
    VALUES (%(user_id)s, %(provider)s, %(model)s, %(input_tokens)s, %(output_tokens)s, %(updated_at)s)
    ON CONFLICT (user_id, provider, model)
    DO UPDATE
       SET input_tokens=token_usage.input_tokens+%(input_tokens)s,
           output_tokens=token_usage.output_tokens+%(output_tokens)s,
           updated_at=%(updated_at)s
     WHERE token_usage.user_id=%(user_id)s
       AND token_usage.provider=%(provider)s
       AND token_usage.model=%(model)s
    """  # noqa: E501
