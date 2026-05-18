"""Abstract class that is parent for all cache implementations."""

from abc import ABC, abstractmethod

from cache.cache_entry import CacheEntry
from models.common import ConversationData
from utils.suid import check_suid


class Cache(ABC):
    """Abstract class that is parent for all cache implementations.

    Cache entries are identified by compound key that consists of
    user ID and conversation ID. Application logic must ensure that
    user will be able to store and retrieve values that have the
    correct user ID only. This means that user won't be able to
    read or modify other users conversations.
    """

    # separator between parts of compound key
    COMPOUND_KEY_SEPARATOR = ":"

    @staticmethod
    def _check_user_id(user_id: str, skip_user_id_check: bool) -> None:
        """Check if given user ID is valid.

        Validate a user identifier unless validation is explicitly skipped.

        Parameters:
        ----------
            user_id (str): The user identifier to validate.
            skip_user_id_check (bool): If True, skip validation and return immediately.

        Raises:
        ------
            ValueError: If validation is not skipped and `user_id` is invalid.
        """
        if skip_user_id_check:
            return
        if not check_suid(user_id):
            raise ValueError(f"Invalid user ID {user_id}")

    @staticmethod
    def _check_conversation_id(conversation_id: str) -> None:
        """Check if given conversation ID is a valid UUID (including optional dashes).

        Parameters:
        ----------
            conversation_id (str): Conversation identifier to validate.

        Raises:
        ------
            ValueError: If `conversation_id` is not a valid SUID (UUID-format
            string; dashes are optional).
        """
        if not check_suid(conversation_id):
            raise ValueError(f"Invalid conversation ID {conversation_id}")

    @staticmethod
    def construct_key(
        user_id: str, conversation_id: str, skip_user_id_check: bool
    ) -> str:
        """Construct key to cache.

        Construct the compound cache key for a user and conversation.

        Parameters:
        ----------
            user_id (str): User identifier; validated unless `skip_user_id_check` is True.
            conversation_id (str): Conversation identifier; always validated.
            skip_user_id_check (bool): When True, skip validation of `user_id`.

        Returns:
        -------
            str: Compound key in the form "user_id:conversation_id".
        """
        Cache._check_user_id(user_id, skip_user_id_check)
        Cache._check_conversation_id(conversation_id)
        return f"{user_id}{Cache.COMPOUND_KEY_SEPARATOR}{conversation_id}"

    @abstractmethod
    def get(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool
    ) -> list[CacheEntry]:
        """Abstract method to retrieve a value from the cache.

        Retrieve cache entries for a given user and conversation.

        Parameters:
        ----------
            user_id (str): User identifier.
            conversation_id (str): Conversation identifier scoped to the user.
            skip_user_id_check (bool): If True, skip validation of `user_id`.

        Returns:
        -------
            list[CacheEntry]: List of cache entries for the specified key;
            empty list if no entries exist.
        """

    @abstractmethod
    def insert_or_append(
        self,
        user_id: str,
        conversation_id: str,
        cache_entry: CacheEntry,
        skip_user_id_check: bool,
    ) -> None:
        """Abstract method to store a value in the cache.

        Store or append a cache entry for the specified user and conversation.

        Parameters:
        ----------
            user_id (str): Identifier of the user; may be validated unless
            skip_user_id_check is True.
            conversation_id (str): Identifier of the conversation within the user's scope.
            cache_entry (CacheEntry): Cache entry to store or append.
            skip_user_id_check (bool): If True, skip validation of `user_id`.
        """

    @abstractmethod
    def delete(
        self, user_id: str, conversation_id: str, skip_user_id_check: bool
    ) -> bool:
        """Delete all entries for a given conversation.

        Parameters:
        ----------
            user_id: User identification.
            conversation_id: Conversation ID unique for given user.
            skip_user_id_check: Skip user_id suid check.

        Returns:
        -------
            `True` if entries were deleted, `False` if no key was found.
        """

    @abstractmethod
    def list(self, user_id: str, skip_user_id_check: bool) -> list[ConversationData]:
        """List all conversations for a given user_id.

        Parameters:
        ----------
            user_id (str): User identifier.
            skip_user_id_check (bool): If True, skip validation of `user_id` before lookup.

        Returns:
        -------
            list[ConversationData]: A list of ConversationData objects for the
                        user's conversations, each containing `conversation_id`,
                        `topic_summary`, and `last_message_timestamp`.
        """

    @abstractmethod
    def set_topic_summary(
        self,
        user_id: str,
        conversation_id: str,
        topic_summary: str,
        skip_user_id_check: bool,
    ) -> None:
        """Abstract method to store topic summary in the cache.

        Parameters:
        ----------
            user_id (str): User identifier used as part of the compound cache key.
            conversation_id (str): Conversation identifier used as part of the compound cache key.
            topic_summary (str): Text summary of the conversation topic to store.
            skip_user_id_check (bool): If True, skip validation of `user_id` before storing.
        """

    @abstractmethod
    def ready(self) -> bool:
        """Check if the cache is ready.

        Returns:
            True if the cache is ready, False otherwise.
        """
