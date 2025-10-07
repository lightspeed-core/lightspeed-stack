"""Helper classes to count tokens sent and received by the LLM."""

import logging
from dataclasses import dataclass
from typing import cast

from llama_stack.models.llama.datatypes import RawMessage
from llama_stack.models.llama.llama3.chat_format import ChatFormat
from llama_stack.models.llama.llama3.tokenizer import Tokenizer
from llama_stack_client.types.agents.turn import Turn

import metrics

logger = logging.getLogger(__name__)


@dataclass
class TokenCounter:
    """Model representing token counter.

    Attributes:
        input_tokens: number of tokens sent to LLM
        output_tokens: number of tokens received from LLM
        input_tokens_counted: number of input tokens counted by the handler
        llm_calls: number of LLM calls
    """

    input_tokens: int = 0
    output_tokens: int = 0
    input_tokens_counted: int = 0
    llm_calls: int = 0

    def __str__(self) -> str:
        """Textual representation of TokenCounter instance."""
        return (
            f"{self.__class__.__name__}: "
            + f"input_tokens: {self.input_tokens} "
            + f"output_tokens: {self.output_tokens} "
            + f"counted: {self.input_tokens_counted} "
            + f"LLM calls: {self.llm_calls}"
        )


def extract_token_usage_from_turn(turn: Turn, system_prompt: str = "") -> TokenCounter:
    """Extract token usage information from a turn.

    This function uses the same tokenizer and logic as the metrics system
    to ensure consistency between API responses and Prometheus metrics.

    Args:
        turn: The turn object containing token usage information
        system_prompt: The system prompt used for the turn

    Returns:
        TokenCounter: Token usage information
    """
    token_counter = TokenCounter()

    try:
        # Use the same tokenizer as the metrics system for consistency
        tokenizer = Tokenizer.get_instance()
        formatter = ChatFormat(tokenizer)

        # Count output tokens (same logic as metrics.utils.update_llm_token_count_from_turn)
        if hasattr(turn, "output_message") and turn.output_message:
            raw_message = cast(RawMessage, turn.output_message)
            encoded_output = formatter.encode_dialog_prompt([raw_message])
            token_counter.output_tokens = (
                len(encoded_output.tokens) if encoded_output.tokens else 0
            )

        # Count input tokens (same logic as metrics.utils.update_llm_token_count_from_turn)
        if hasattr(turn, "input_messages") and turn.input_messages:
            input_messages = cast(list[RawMessage], turn.input_messages)
            if system_prompt:
                input_messages = [
                    RawMessage(role="system", content=system_prompt)
                ] + input_messages
            encoded_input = formatter.encode_dialog_prompt(input_messages)
            token_counter.input_tokens = (
                len(encoded_input.tokens) if encoded_input.tokens else 0
            )
            token_counter.input_tokens_counted = token_counter.input_tokens

        token_counter.llm_calls = 1

    except (AttributeError, TypeError, ValueError) as e:
        logger.warning("Failed to extract token usage from turn: %s", e)
        # Fallback to default values if token counting fails
        token_counter.input_tokens = 100  # Default estimate
        token_counter.output_tokens = 50  # Default estimate
        token_counter.llm_calls = 1

    return token_counter


def extract_and_update_token_metrics(
    turn: Turn, model: str, provider: str, system_prompt: str = ""
) -> TokenCounter:
    """Extract token usage and update Prometheus metrics in one call.

    This function combines the token counting logic with the metrics system
    to ensure both API responses and Prometheus metrics are updated consistently.

    Args:
        turn: The turn object containing token usage information
        model: The model identifier for metrics labeling
        provider: The provider identifier for metrics labeling
        system_prompt: The system prompt used for the turn

    Returns:
        TokenCounter: Token usage information
    """
    token_counter = extract_token_usage_from_turn(turn, system_prompt)

    # Update Prometheus metrics with the same token counts
    try:
        # Update the metrics using the same token counts we calculated
        metrics.llm_token_sent_total.labels(provider, model).inc(
            token_counter.input_tokens
        )
        metrics.llm_token_received_total.labels(provider, model).inc(
            token_counter.output_tokens
        )
        metrics.llm_calls_total.labels(provider, model).inc()

    except (AttributeError, TypeError, ValueError) as e:
        logger.warning("Failed to update token metrics: %s", e)

    return token_counter
