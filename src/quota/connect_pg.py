"""PostgreSQL connection handler."""

from typing import Any
import psycopg2

from log import get_logger
from models.config import PostgreSQLDatabaseConfiguration

logger = get_logger(__name__)


def connect_pg(config: PostgreSQLDatabaseConfiguration) -> Any:
    """Initialize connection to PostgreSQL database."""
    logger.info("Connecting to PostgreSQL storage")
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
        )
        if connection is not None:
            connection.autocommit = True
        return connection
    except psycopg2.Error as e:
        logger.exception("Error connecting to PostgreSQL database:\n%s", e)
        raise
