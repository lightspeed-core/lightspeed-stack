"""In-memory cache implementation."""

from cache.cache import Cache
from models.cache_entry import CacheEntry
from models.config import InMemoryCacheConfig
from models.responses import ConversationData
from log import get_logger
from utils.connection_decorator import connection

logger = get_logger(__name__)


class InMemoryCache(Cache):
    """In-memory cache implementation."""

    def __init__(self, config: InMemoryCacheConfig) -> None:
        """Create a new instance of in-memory cache.

        Initialize the InMemoryCache with the provided configuration.

        Parameters:
            config (InMemoryCacheConfig): Configuration options controlling cache behavior.
        """
        self.cache_config = config

    def connect(self) -> None:
        """Initialize connection to database.

        Log the start of a storage connection for the in-memory cache; does not
        establish an external connection.

        This method records (via logger) that the cache is connecting to its
        storage backend. For the in-memory implementation this is a no-op with
        respect to network or persistent connections.
        """
        logger.info("Connecting to storage")

    def connected(self) -> bool:
        """Check if connection to cache is alive.

        Report whether the cache connection is currently available.

        Returns:
            True if the cache is available, False otherwise.
        """
        return True

    def initialize_cache(self) -> None:
        """Initialize cache.

        No-op placeholder for cache initialization.

        This implementation performs no actions and exists only to satisfy the cache interface.
        """

    @connection
    def get(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool = False
    ) -> list[CacheEntry]:
        """Get the value associated with the given key.

        Validate the provided identifiers and retrieve cache entries for a user's conversation.

        Parameters:
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

        Validate and construct the cache key for a user's conversation without storing data.

        This method verifies the provided `user_id` and `conversation_id` (via
        the base class key construction/validation) and performs no persistent
        storage or mutation.

        Parameters:
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

        Validate the provided user and conversation identifiers and report deletion success.

        Parameters:
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

        Parameters:
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

        Parameters:
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
            True (`bool`): Always `True` for this in-memory cache implementation.
        """
        return True
