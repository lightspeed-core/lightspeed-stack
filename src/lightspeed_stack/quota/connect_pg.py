"""PostgreSQL connection handler."""

from typing import Any

import psycopg2

from log import get_logger
from models.config import PostgreSQLDatabaseConfiguration

logger = get_logger(__name__)


def connect_pg(config: PostgreSQLDatabaseConfiguration) -> Any:
    """
    Create and return a psycopg2 connection to the configured PostgreSQL database.

    Parameters:
    ----------
        config (PostgreSQLDatabaseConfiguration): Configuration containing
        host, port, user, password (accessible via `get_secret_value()`),
        database name, and SSL/GSS options used to establish the connection.

    Returns:
    -------
        connection: A psycopg2 database connection

    Raises:
    ------
        psycopg2.Error: If establishing the database connection fails.
    """
    logger.info("Connecting to PostgreSQL storage")
    namespace = "public"
    if config.namespace is not None:
        namespace = config.namespace

    try:
        connection = psycopg2.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password.get_secret_value(),
            dbname=config.db,
            sslmode=config.ssl_mode,
            # sslrootcert=config.ca_cert_path,
            gssencmode=config.gss_encmode,
            options=f"-c search_path={namespace}",
        )
        if connection is not None:
            connection.autocommit = True
        return connection
    except psycopg2.Error as e:
        logger.exception("Error connecting to PostgreSQL database:\n%s", e)
        raise
