"""Accounting for the LLM calls conversation compaction makes (LCORE-3910).

Compaction summarizes older turns with an LLM call of its own, and folds the
summaries with another. The provider bills both, so they are counted: in the
LLM metrics, in the quota of the user, and in the token counts the client is
told. :class:`SummarizationCalls` does the first two and adds the usage up for
the third.
"""

from dataclasses import dataclass, field
from typing import Optional

from metrics import recording
from utils.compaction import CallCounter
from utils.query import extract_provider_and_model_from_model_id
from utils.token_counter import TokenCounter


@dataclass
class SummarizationCalls:
    """The LLM calls compaction makes for one request (LCORE-3910).

    The provider bills them. So each call is recorded in the LLM metrics under
    the endpoint that triggered it, and handed to ``charge``. Both happen as
    soon as the response of the call arrived, and do not depend on what
    becomes of the request afterwards.

    Attributes:
        endpoint_path: Path of the endpoint serving the request, the label of
            the metrics. No metrics are recorded without it.
        charge: Charges one call to whoever pays for the request. Nobody is
            charged without it.
        usage: The usage of the calls counted so far, added up.
    """

    endpoint_path: Optional[str] = None
    charge: Optional[CallCounter] = None
    usage: TokenCounter = field(default_factory=TokenCounter)

    def count(self, model: str, usage: TokenCounter) -> None:
        """Record one call in the metrics, charge it, and add it to the total.

        Parameters:
            model: Fully-qualified identifier of the model that was called.
            usage: The token usage the provider reported for the call.

        Raises:
            HTTPException: When charging the call fails.
        """
        self.usage = self.usage + usage
        if self.endpoint_path is not None:
            provider_id, model_id = extract_provider_and_model_from_model_id(model)
            if usage.input_tokens or usage.output_tokens:
                recording.record_llm_token_usage(
                    provider_id,
                    model_id,
                    usage.input_tokens,
                    usage.output_tokens,
                    self.endpoint_path,
                )
            recording.record_llm_call(provider_id, model_id, self.endpoint_path)
        if self.charge is not None:
            self.charge(model, usage)
