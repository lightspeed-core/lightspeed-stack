"""Token counting utilities using tiktoken.

This module provides utilities for counting tokens in text and conversation messages
using the tiktoken library. It supports automatic model-specific encoding detection
with fallback to a default tokenizer, and includes conversation-level token tracking
for Agent conversations.
"""

from functools import lru_cache
import logging
from typing import Sequence

from cachetools import TTLCache  # type: ignore

from llama_stack_client.types import (
    UserMessage,
    SystemMessage,
    ToolResponseMessage,
    CompletionMessage,
)
import tiktoken

from configuration import configuration, AppConfig
from constants import DEFAULT_ESTIMATION_TOKENIZER

logger = logging.getLogger(__name__)

# Class-level cache to track cumulative input tokens for each conversation
_conversation_cache: TTLCache[str, int] = TTLCache(maxsize=1000, ttl=3600)


class TokenCounter:
    """A utility class for counting tokens in text and conversation messages.

    This class provides methods to count tokens in plain text and structured
    conversation messages. It automatically handles model-specific tokenization
    using tiktoken, with fallback to a default tokenizer if the model is not
    recognized. It also tracks cumulative input tokens for Agent conversations.

    Attributes:
        _encoder: The tiktoken encoding object used for tokenization
    """

    def __init__(self, model_id: str):
        """Initialize the TokenCounter with a specific model.

        Args:
            model_id: The identifier of the model to use for tokenization.
                     This is used to determine the appropriate tiktoken encoding.

        Note:
            If the model_id is not recognized by tiktoken, the system will
            fall back to the default estimation tokenizer specified in the
            configuration.
        """
        self._encoder = None

        try:
            # Use tiktoken's encoding_for_model function which handles GPT models automatically
            self._encoder = tiktoken.encoding_for_model(model_id)
            logger.debug("Initialized tiktoken encoding for model: %s", model_id)
        except KeyError as e:
            fallback_encoding = get_default_estimation_tokenizer(configuration)
            logger.warning(
                "Failed to get encoding for model %s: %s, using %s",
                model_id,
                e,
                fallback_encoding,
            )
            self._encoder = tiktoken.get_encoding(fallback_encoding)

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a given text string.

        Args:
            text: The text string to count tokens for.

        Returns:
            The number of tokens in the text. Returns 0 if text is empty or None.
        """
        if not text or not self._encoder:
            return 0
        return len(self._encoder.encode(text))

    def count_turn_tokens(
        self, system_prompt: str, query: str, response: str = ""
    ) -> dict[str, int]:
        """Count tokens for a complete conversation turn.

        This method estimates token usage for a typical conversation turn,
        including system prompt, user query, and optional response. It accounts
        for message formatting overhead and conversation structure.

        Args:
            system_prompt: The system prompt message content.
            query: The user's query message content.
            response: The assistant's response message content (optional).

        Returns:
            A dictionary containing:
                - 'input_tokens': Total tokens in the input messages (system + query)
                - 'output_tokens': Total tokens in the response message
        """
        # Estimate token usage
        input_messages: list[SystemMessage | UserMessage] = []
        if system_prompt:
            input_messages.append(
                SystemMessage(role="system", content=str(system_prompt))
            )
        input_messages.append(UserMessage(role="user", content=query))

        input_tokens = self.count_message_tokens(input_messages)
        output_tokens = self.count_tokens(response)

        logger.debug("Estimated tokens in/out: %d / %d", input_tokens, output_tokens)

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def count_conversation_turn_tokens(
        self, conversation_id: str, system_prompt: str, query: str, response: str = ""
    ) -> dict[str, int]:
        """Count tokens for a conversation turn with cumulative tracking.

        This method estimates token usage for a conversation turn and tracks
        cumulative input tokens across the conversation. It accounts for the
        fact that Agent conversations include the entire message history in
        each turn.

        Args:
            conversation_id: The conversation ID to track tokens for.
            system_prompt: The system prompt message content.
            query: The user's query message content.
            response: The assistant's response message content (optional).

        Returns:
            A dictionary containing:
                - 'input_tokens': Cumulative input tokens for the conversation
                - 'output_tokens': Total tokens in the response message
        """
        # Get the current turn's token usage
        turn_token_usage = self.count_turn_tokens(system_prompt, query, response)

        # Get cumulative input tokens for this conversation
        cumulative_input_tokens = _conversation_cache.get(conversation_id, 0)

        # Add this turn's input tokens to the cumulative total
        new_cumulative_input_tokens = (
            cumulative_input_tokens + turn_token_usage["input_tokens"]
        )
        _conversation_cache[conversation_id] = new_cumulative_input_tokens

        # TODO(csibbitt) - Add counting for MCP and RAG content

        logger.debug(
            "Token usage for conversation %s: turn input=%d, cumulative input=%d, output=%d",
            conversation_id,
            turn_token_usage["input_tokens"],
            new_cumulative_input_tokens,
            turn_token_usage["output_tokens"],
        )

        return {
            "input_tokens": new_cumulative_input_tokens,
            "output_tokens": turn_token_usage["output_tokens"],
        }

    def count_message_tokens(
        self,
        messages: Sequence[
            UserMessage | SystemMessage | ToolResponseMessage | CompletionMessage
        ],
    ) -> int:
        """Count tokens for a list of conversation messages.

        This method counts tokens for structured conversation messages, including
        the message content and formatting overhead for roles and conversation
        structure.

        Args:
            messages: A list of message objects (e.g., SystemMessage, UserMessage)

        Returns:
            The total number of tokens across all messages, including formatting overhead.
        """
        total_tokens = 0

        for message in messages:
            total_tokens += self.count_tokens(str(message.content))
            # Add role overhead (varies by model, 4 is typical for OpenAI models)
            role_formatting_overhead = 4
            total_tokens += role_formatting_overhead

        # Add conversation formatting overhead
        if messages:
            total_tokens += self._get_conversation_overhead(len(messages))

        return total_tokens

    def _get_conversation_overhead(self, message_count: int) -> int:
        """Calculate the token overhead for conversation formatting.

        This method estimates the additional tokens needed for conversation
        structure, including start/end tokens and message separators.

        Args:
            message_count: The number of messages in the conversation.

        Returns:
            The estimated token overhead for conversation formatting.
        """
        base_overhead = 3  # Start of conversation tokens (based on OpenAI chat format)
        separator_overhead = max(0, (message_count - 1) * 1)  # Message separator tokens
        return base_overhead + separator_overhead


@lru_cache(maxsize=8)
def get_token_counter(model_id: str) -> TokenCounter:
    """Get a cached TokenCounter instance for the specified model.

    This function provides a cached TokenCounter instance to avoid repeated
    initialization of the same model's tokenizer.

    Args:
        model_id: The identifier of the model to get a token counter for.

    Returns:
        A TokenCounter instance configured for the specified model.
    """
    return TokenCounter(model_id)


def get_default_estimation_tokenizer(config: AppConfig) -> str:
    """Get the default estimation tokenizer."""
    if (
        config.customization is not None
        and config.customization.default_estimation_tokenizer is not None
    ):
        return config.customization.default_estimation_tokenizer

    # default system prompt has the lowest precedence
    return DEFAULT_ESTIMATION_TOKENIZER
