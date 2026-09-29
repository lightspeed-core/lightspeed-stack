"""Helper classes to count tokens sent and received by the LLM."""

from dataclasses import dataclass

from log import get_logger

logger = get_logger(__name__)


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

    def __add__(self, other: "TokenCounter") -> "TokenCounter":
        """Return the usage of two sets of LLM calls taken together.

        Parameters:
            other: The token counter to add.

        Returns:
            A new counter holding the sums; neither operand is changed.
        """
        return TokenCounter(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            input_tokens_counted=self.input_tokens_counted + other.input_tokens_counted,
            llm_calls=self.llm_calls + other.llm_calls,
        )

    def __str__(self) -> str:
        """
        Return a human-readable summary of the token usage stored in this TokenCounter.

        Returns:
            summary (str): A formatted string containing `input_tokens`,
                           `output_tokens`, `input_tokens_counted`, and `llm_calls`.
        """
        return (
            f"{self.__class__.__name__}: "
            + f"input_tokens: {self.input_tokens} "
            + f"output_tokens: {self.output_tokens} "
            + f"counted: {self.input_tokens_counted} "
            + f"LLM calls: {self.llm_calls}"
        )
