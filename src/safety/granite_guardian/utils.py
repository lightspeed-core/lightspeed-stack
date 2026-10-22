"""Prompt construction and logprob parsing for Granite Guardian risk checks.

Granite Guardian is judged via a structured `<think>...</think><score>yes|no</score>`
completion rather than free text: `build_guardian_block` builds the instructions that ask
for that shape, and `is_safe` parses the model's response logprobs back out of it into a
risky/safe verdict. Both are used by
:class:`~lightspeed.core.agent.safety.granite_guardian.capability.GraniteGuardianRisk`.
"""

from __future__ import annotations

from enum import Enum, StrEnum, auto
from math import exp
from typing import Any

from openai.types.chat.chat_completion_token_logprob import ChatCompletionTokenLogprob
from pydantic_ai.exceptions import UnexpectedModelBehavior


class _ParsingStatus(Enum):
    """State machine states for parsing a Granite Guardian response's tokens."""

    BEFORE_THINK = auto()
    INSIDE_THINK = auto()
    POST_THINK = auto()
    INSIDE_SCORE = auto()


class _Token(StrEnum):
    """Granite Guardian verdict tokens indicating safe or risky content."""

    SAFE = "no"
    RISKY = "yes"


_THINK_START_TAG = "<think>"
_THINK_END_TAG = "</think>"
_SCORE_START_TAG = "<score>"
_SCORE_END_TAG = "</score>"

_JUDGE_PREAMBLE_NOTHINK = (
    "<guardian><no-think>As a judge agent, assess whether the provided text "
    "meets the given judging criteria using all available information, "
    "including conversations, documents, and tools. Provide your score "
    "immediately without explanation. Output empty <think>\n</think> tags "
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


def build_guardian_block(criteria: str, *, think: bool = False) -> str:
    """Build the instructions sent alongside a risk check, asking Granite Guardian to judge `criteria`."""
    preamble = _JUDGE_PREAMBLE_THINK if think else _JUDGE_PREAMBLE_NOTHINK
    return (
        f"{preamble}\n\n"
        f"### Criteria: {criteria}\n\n"
        f"### Scoring Schema: {_SCORING_SCHEMA_PROMPT_ONLY}"
    )


def _search_tag(tag: str, buffer: str) -> tuple[str, bool]:
    """Search for a complete XML tag in the buffer.

    Returns:
        A tuple of (remaining_buffer, found). The buffer is cleared when the content isn't
        tag-like, or once the tag is found.

    """
    if not buffer.strip().startswith("<"):
        return "", False
    if tag in buffer:
        return "", True
    return buffer, False


def _clean_up_candidates(candidates: list[ChatCompletionTokenLogprob]) -> None:
    """Pop trailing candidates that are part of the `</score>` tag, in place."""
    buffer = ""
    while len(candidates) != 0:
        cur_candidate = candidates.pop()
        buffer = cur_candidate.token + buffer
        if _SCORE_END_TAG in buffer:
            return


def _extract_tokens_inside_score_tag(
    logprobs: list[dict[str, Any]],
) -> ChatCompletionTokenLogprob:
    """Walk a Granite Guardian response's tokens to the one scored inside `<score>`.

    Raises:
        UnexpectedModelBehavior: If the response doesn't contain the expected tag
            structure, or the score tag has zero or multiple tokens.

    """
    cur_buffer = ""
    cur_status = _ParsingStatus.BEFORE_THINK
    candidates: list[ChatCompletionTokenLogprob] = []

    for _logprob in logprobs:
        logprob = ChatCompletionTokenLogprob.model_validate(_logprob)
        cur_buffer += logprob.token

        match cur_status:
            case _ParsingStatus.BEFORE_THINK:
                # The model sometimes starts with the closing think tag when thinking is
                # disabled, so check for that before the opening tag.
                cur_buffer, found_end = _search_tag(_THINK_END_TAG, cur_buffer)
                if found_end:
                    cur_status = _ParsingStatus.POST_THINK
                    continue

                cur_buffer, found_tag = _search_tag(_THINK_START_TAG, cur_buffer)
                if found_tag:
                    cur_status = _ParsingStatus.INSIDE_THINK
            case _ParsingStatus.INSIDE_THINK:
                cur_buffer, found_tag = _search_tag(_THINK_END_TAG, cur_buffer)
                if found_tag:
                    cur_status = _ParsingStatus.POST_THINK
            case _ParsingStatus.POST_THINK:
                cur_buffer, found_tag = _search_tag(_SCORE_START_TAG, cur_buffer)
                if found_tag:
                    cur_status = _ParsingStatus.INSIDE_SCORE
            case _ParsingStatus.INSIDE_SCORE:
                cur_buffer, found_tag = _search_tag(_SCORE_END_TAG, cur_buffer)
                candidates.append(logprob)
                if found_tag:
                    _clean_up_candidates(candidates)

                    # In practice there should be exactly one token inside the score tag;
                    # 'yes'/'no' being split across two tokens is extremely unlikely.
                    # Raising here surfaces it clearly if it ever happens.
                    candidates_num = len(candidates)
                    if candidates_num == 0:
                        raise UnexpectedModelBehavior("No token found inside score tag")
                    if candidates_num > 1:
                        raise UnexpectedModelBehavior(
                            "More than one token found inside score tag"
                        )
                    return candidates[0]

    raise UnexpectedModelBehavior("Model did not generate the required format")


def _get_risky_probability(token: ChatCompletionTokenLogprob) -> float:
    """Compute the normalized probability of the risky (`yes`) outcome.

    Raises:
        UnexpectedModelBehavior: If neither the safe nor risky token appears in the top
            logprobs (underflow).

    """
    safe_prob, risky_prob = 0.0, 0.0
    for candidate_token in token.top_logprobs:
        match candidate_token.token.strip().lower():
            case _Token.SAFE:
                safe_prob += exp(candidate_token.logprob)
            case _Token.RISKY:
                risky_prob += exp(candidate_token.logprob)
    total_prob = safe_prob + risky_prob

    if total_prob == 0:
        raise UnexpectedModelBehavior("Logprob underflow")

    return risky_prob / total_prob


def is_safe(threshold: float, logprobs: list[dict[str, Any]]) -> bool:
    """Determine whether a Granite Guardian response's verdict is safe.

    Parameters:
        threshold: The risky probability at or above which the input is considered unsafe.
        logprobs: Raw logprob dictionaries from the model response's provider details.

    Returns:
        `True` if the risky probability is below `threshold` (safe).

    """
    score_token = _extract_tokens_inside_score_tag(logprobs)
    return _get_risky_probability(score_token) < threshold
