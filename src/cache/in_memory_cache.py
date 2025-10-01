"""In-memory cache implementation."""

from cache.cache import Cache
from models.cache_entry import CacheEntry, ConversationData
from models.config import InMemoryCacheConfig
from log import get_logger
from utils.connection_decorator import connection

logger = get_logger("cache.in_memory_cache")


class InMemoryCache(Cache):
    """In-memory cache implementation."""

    def __init__(self, config: InMemoryCacheConfig) -> None:
        """Create a new instance of in-memory cache."""
        self.cache_config = config

    def connect(self) -> None:
        """Initialize connection to database."""
        logger.info("Connecting to storage")

    def connected(self) -> bool:
        """Check if connection to cache is alive."""
        return True

    def initialize_cache(self) -> None:
        """Initialize cache."""

    @connection
    def get(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> list[CacheEntry]:
        """Get the value associated with the given key.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            Empty list.
        """
        # just check if user_id and conversation_id are UUIDs
        super().construct_key(user_id, conversation_id, skip_user_id_check)
        return []

    @connection
    def insert_or_append(
        self,
        user_id: str,
        conversation_id: str,
        cache_entry: CacheEntry,
        skip_user_id_check: bool = False,
    ) -> None:
        """Set the value associated with the given key.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            cache_entry: The `CacheEntry` object to store.
            skip_user_id_check: Skip user_id suid check.

        """
        # just check if user_id and conversation_id are UUIDs
        super().construct_key(user_id, conversation_id, skip_user_id_check)

    @connection
    def delete(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> bool:
        """Delete conversation history for a given user_id and conversation_id.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            bool: True in all cases.

        """
        # just check if user_id and conversation_id are UUIDs
        super().construct_key(user_id, conversation_id, skip_user_id_check)
        return True

    @connection
    def list(
        self, user_id: str, skip_user_id_check: bool = False
    ) -> list[ConversationData]:
        """List all conversations for a given user_id.

        Args:
            user_id: User identification.
            skip_user_id_check: Skip user_id suid check.

        Returns:
            An empty list.

        """
        super()._check_user_id(user_id, skip_user_id_check)
        return []

    @connection
    def set_topic_summary(
        self,
        user_id: str,
        conversation_id: str,
        topic_summary: str,
        skip_user_id_check: bool = False,
    ) -> None:
        """Set the topic summary for the given conversation.

        Args:
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            topic_summary: The topic summary to store.
            skip_user_id_check: Skip user_id suid check.
        """
        # just check if user_id and conversation_id are UUIDs
        super().construct_key(user_id, conversation_id, skip_user_id_check)

    def ready(self) -> bool:
        """Check if the cache is ready.

        Returns:
            True in all cases.
        """
        return True
