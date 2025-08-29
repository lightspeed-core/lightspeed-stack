"""Database engine management."""

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine.base import Engine
from sqlalchemy.orm import sessionmaker, Session
from log import get_logger, logging
from configuration import configuration
from models.database.base import Base
from models.config import SQLiteDatabaseConfiguration, PostgreSQLDatabaseConfiguration

logger = get_logger(__name__)

engine: Engine | None = None
SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    """Get the database engine. Raises an error if not initialized."""
    if engine is None:
        raise RuntimeError(
            "Database engine not initialized. Call initialize_database() first."
        )
    return engine


def create_tables() -> None:
    """Create tables."""
    Base.metadata.create_all(get_engine())


def get_session() -> Session:
    """Get a database session. Raises an error if not initialized."""
    if SessionLocal is None:
        raise RuntimeError(
            "Database session not initialized. Call initialize_database() first."
        )
    return SessionLocal()


def _create_sqlite_engine(config: SQLiteDatabaseConfiguration, **kwargs: Any) -> Engine:
    """Create SQLite database engine."""
    if not Path(config.db_path).parent.exists():
        raise FileNotFoundError(
            f"SQLite database directory does not exist: {config.db_path}"
        )

    try:
        return create_engine(f"sqlite:///{config.db_path}", **kwargs)
    except Exception as e:
        logger.exception("Failed to create SQLite engine")
        raise RuntimeError(f"SQLite engine creation failed: {e}") from e


def _create_postgres_engine(
    config: PostgreSQLDatabaseConfiguration, **kwargs: Any
) -> Engine:
    """Create PostgreSQL database engine."""
    postgres_url = (
        f"postgresql://{config.user}:{config.password}@"
        f"{config.host}:{config.port}/{config.db}"
        f"?sslmode={config.ssl_mode}&gssencmode={config.gss_encmode}"
    )

    is_custom_schema = config.namespace is not None and config.namespace != "public"

    connect_args = {}
    if is_custom_schema:
        connect_args["options"] = f"-csearch_path={config.namespace}"

    if config.ca_cert_path is not None:
        connect_args["sslrootcert"] = str(config.ca_cert_path)

    try:
        postgres_engine = create_engine(
            postgres_url, connect_args=connect_args, **kwargs
        )
    except Exception as e:
        logger.exception("Failed to create PostgreSQL engine")
        raise RuntimeError(f"PostgreSQL engine creation failed: {e}") from e

    if is_custom_schema:
        try:
            with postgres_engine.connect() as connection:
                connection.execute(
                    text(f'CREATE SCHEMA IF NOT EXISTS "{config.namespace}"')
                )
                connection.commit()
                logger.info("Schema '%s' created or already exists", config.namespace)
        except Exception as e:
            logger.exception("Failed to create schema '%s'", config.namespace)
            raise RuntimeError(
                f"Schema creation failed for '{config.namespace}': {e}"
            ) from e

    return postgres_engine


def initialize_database() -> None:
    """Initialize the database engine."""
    db_config = configuration.database_configuration

    global engine, SessionLocal  # pylint: disable=global-statement

    # Debug print all SQL statements if our logger is at-least DEBUG level
    echo = bool(logger.isEnabledFor(logging.DEBUG))

    create_engine_kwargs = {
        "echo": echo,
        "pool_pre_ping": True,
    }

    match db_config.db_type:
        case "sqlite":
            sqlite_config = db_config.config
            assert isinstance(sqlite_config, SQLiteDatabaseConfiguration)
            engine = _create_sqlite_engine(sqlite_config, **create_engine_kwargs)
        case "postgres":
            postgres_config = db_config.config
            assert isinstance(postgres_config, PostgreSQLDatabaseConfiguration)
            engine = _create_postgres_engine(postgres_config, **create_engine_kwargs)

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
