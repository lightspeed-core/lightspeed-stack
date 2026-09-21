"""Utility functions for Granite Guardian prompt construction and logprob parsing."""

from enum import Enum, StrEnum, auto
from math import exp
from typing import Any

from openai.types.chat.chat_completion_token_logprob import ChatCompletionTokenLogprob
from pydantic_ai.exceptions import UnexpectedModelBehavior

from log import get_logger


class ParsingStatus(Enum):
    """State machine states for parsing Granite Guardian response tokens."""

    BEFORE_THINK = auto()
    INSIDE_THINK = auto()
    POST_THINK = auto()
    INSIDE_SCORE = auto()


class Token(StrEnum):
    """Granite Guardian verdict tokens indicating safe or risky content."""

    SAFE = "no"
    RISKY = "yes"


THINK_START_TAG = "<think>"
THINK_END_TAG = "</think>"
SCORE_START_TAG = "<score>"
SCORE_END_TAG = "</score>"

# Copied the implementation of Granite Guardian guardrail from Ask Red Hat.
# Reference: https://gitlab.cee.redhat.com/ask-red-hat/backend/ask-guardrails

# =============================================================================
# Guardian Block Construction (GG 4.1 client-side prompt)
# =============================================================================

_JUDGE_PREAMBLE_NOTHINK = (
    "<guardian><no-think>As a judge agent, assess whether the provided text "
    "meets the given judging criteria using all available information, "
    "including conversations, documents, and tools. Provide your score "
    "immediately without explanation. Output empty <think>\\n</think> tags "
    "followed by your score in <score></score> tags."
)

_JUDGE_PREAMBLE_THINK = (
    "<guardian><think>As a judge agent, carefully analyze whether the provided "
    "text meets the given judging criteria. Use all available information, "
    "including conversations, documents, and tools. Reason through the "
    "evidence step by step before providing your score. Wrap your reasoning "
    "in <think></think> tags, then provide your score in <score></score> tags."
)

_SCORING_SCHEMA_PROMPT_ONLY = (
    "If the last user's text meets the criteria, return 'yes'; otherwise, return 'no'."
)

logger = get_logger(__name__)


def build_guardian_block(criteria: str, *, think: bool = False) -> str:
    """Build the guardian evaluation block sent as a second user message."""
    preamble = _JUDGE_PREAMBLE_THINK if think else _JUDGE_PREAMBLE_NOTHINK
    return (
        f"{preamble}\n\n"
        f"### Criteria: {criteria}\n\n"
        f"### Scoring Schema: {_SCORING_SCHEMA_PROMPT_ONLY}"
    )


def _search_tag(tag: str, buffer: str) -> tuple[str, bool]:
    """Search for a complete XML tag in the buffer.

    Parameters:
        tag: The XML tag to search for (e.g. ``<think>``).
        buffer: The accumulated token text to search in.

    Returns:
        A tuple of (remaining_buffer, found). The buffer is cleared when
        the content is not tag-like or when the tag is found.
    """
    if not buffer.strip().startswith("<"):
        return "", False

    if tag in buffer:
        return "", True

    return buffer, False


def _clean_up_candidates(candidates: list[ChatCompletionTokenLogprob]) -> None:
    """Remove trailing candidates that are part of the score end tag.

    Pops tokens from the end of the candidates list until the ``</score>``
    tag boundary is found, leaving only the score content tokens.

    Parameters:
        candidates: Mutable list of token logprobs to clean in place.
    """
    buffer = ""
    while len(candidates) != 0:
        cur_candidate = candidates.pop()
        buffer = cur_candidate.token + buffer
        if SCORE_END_TAG in buffer:
            return


def _extract_tokens_inside_score_tag(
    logprobs: list[dict[str, Any]],
) -> ChatCompletionTokenLogprob:
    """Extract the single token logprob from inside the ``<score>`` tag.

    Parses the model's structured output through ``<think>`` and ``<score>``
    tags, returning the logprob of the scoring token (``yes`` or ``no``).

    Parameters:
        logprobs: Raw logprob dictionaries from the model's provider_details.

    Returns:
        The ``ChatCompletionTokenLogprob`` for the score token.

    Raises:
        UnexpectedModelBehavior: When the model output doesn't contain the
            expected tag structure, or the score tag has zero or multiple tokens.
    """
    cur_buffer = ""
    cur_status = ParsingStatus.BEFORE_THINK
    candidates: list[ChatCompletionTokenLogprob] = []

    for _logprob in logprobs:
        logprob = ChatCompletionTokenLogprob.model_validate(_logprob)
        cur_buffer += logprob.token

        match cur_status:
            case ParsingStatus.BEFORE_THINK:
                # Sometimes Granite Guardian model will start with the end thinking tag
                # if thinking is disabled
                cur_buffer, found_end = _search_tag(THINK_END_TAG, cur_buffer)
                if found_end:
                    cur_status = ParsingStatus.POST_THINK
                    continue

                cur_buffer, found_tag = _search_tag(THINK_START_TAG, cur_buffer)
                if found_tag:
                    cur_status = ParsingStatus.INSIDE_THINK
            case ParsingStatus.INSIDE_THINK:
                cur_buffer, found_tag = _search_tag(THINK_END_TAG, cur_buffer)
                if found_tag:
                    cur_status = ParsingStatus.POST_THINK
            case ParsingStatus.POST_THINK:
                cur_buffer, found_tag = _search_tag(SCORE_START_TAG, cur_buffer)
                if found_tag:
                    cur_status = ParsingStatus.INSIDE_SCORE
            case ParsingStatus.INSIDE_SCORE:
                cur_buffer, found_tag = _search_tag(SCORE_END_TAG, cur_buffer)
                candidates.append(logprob)
                if found_tag:
                    _clean_up_candidates(candidates)

                    # Theoretically, there should be only one token inside score tag because
                    # the chance that 'yes' and 'no' are split into two tokens are extremely
                    # low. Raising an error here so if it ever happens in the future, we can
                    # improve the parsing logic then.
                    candidates_num = len(candidates)
                    if candidates_num == 0:
                        raise UnexpectedModelBehavior("No token found inside score tag")
                    if candidates_num > 1:
                        raise UnexpectedModelBehavior(
                            "More than one token found inside score tag"
                        )
                    return candidates[0]

    raise UnexpectedModelBehavior("Model did not generate the required format")


def _get_risky_probabilities(token: ChatCompletionTokenLogprob) -> float:
    """Compute the normalized probability of the risky (``yes``) outcome.

    Parameters:
        token: The score token with its top logprob alternatives.

    Returns:
        The probability of the risky outcome, normalized against the sum
        of safe and risky probabilities.

    Raises:
        UnexpectedModelBehavior: When neither safe nor risky tokens appear
            in the top logprobs (underflow).
    """
    safe_prob, risky_prob = 0.0, 0.0
    for candidate_token in token.top_logprobs:
        match candidate_token.token.strip().lower():
            case Token.SAFE:
                safe_prob += exp(candidate_token.logprob)
            case Token.RISKY:
                risky_prob += exp(candidate_token.logprob)
    total_prob = safe_prob + risky_prob

    if total_prob == 0:
        raise UnexpectedModelBehavior("Logprob underflow")

    return risky_prob / total_prob


def is_safe(threshold: float, logprobs: list[dict[str, Any]]) -> bool:
    """Determine whether the input is safe based on the risky probability.

    Parameters:
        threshold: The risk threshold; the input is unsafe when the risky
            probability meets or exceeds this value.
        logprobs: Raw logprob dictionaries from the model response.

    Returns:
        True if the risky probability is below the threshold (safe).
    """
    token_for_confidence_threshold = _extract_tokens_inside_score_tag(logprobs)
    p_risky = _get_risky_probabilities(token_for_confidence_threshold)

    return p_risky < threshold
