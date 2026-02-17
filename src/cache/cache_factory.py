"""Cache factory class."""

import constants
from models.config import ConversationHistoryConfiguration
from cache.cache import Cache
from cache.noop_cache import NoopCache
from cache.in_memory_cache import InMemoryCache
from cache.postgres_cache import PostgresCache
from cache.sqlite_cache import SQLiteCache
from log import get_logger

logger = get_logger(__name__)


# pylint: disable=R0903
class CacheFactory:
    """Cache factory class."""

    @staticmethod
    def conversation_cache(config: ConversationHistoryConfiguration) -> Cache:
        """Create an instance of Cache based on loaded configuration.

        Returns:
            An instance of `Cache` (either `SQLiteCache`, `PostgresCache` or `InMemoryCache`).

        Raises:
            ValueError: If `config.type` is None, if required type-specific
            configuration is missing, or if `config.type` is not a recognized
            cache type.
        """
        logger.info("Creating cache instance of type %s", config.type)
        match config.type:
            case constants.CACHE_TYPE_NOOP:
                return NoopCache()
            case constants.CACHE_TYPE_MEMORY:
                if config.memory is not None:
                    return InMemoryCache(config.memory)
                raise ValueError("Expecting configuration for in-memory cache")
            case constants.CACHE_TYPE_SQLITE:
                if config.sqlite is not None:
                    return SQLiteCache(config.sqlite)
                raise ValueError("Expecting configuration for SQLite cache")
            case constants.CACHE_TYPE_POSTGRES:
                if config.postgres is not None:
                    return PostgresCache(config.postgres)
                raise ValueError("Expecting configuration for PostgreSQL cache")
            case None:
                raise ValueError("Cache type must be set")
            case _:
                raise ValueError(
                    f"Invalid cache type: {config.type}. "
                    f"Use '{constants.CACHE_TYPE_POSTGRES}' '{constants.CACHE_TYPE_SQLITE}' "
                    f"'{constants.CACHE_TYPE_MEMORY}' or '{constants.CACHE_TYPE_NOOP}' options."
                )
