"""Unit tests for safety.granite_guardian.utils."""

import math
from typing import Any

import pytest
from openai.types.chat.chat_completion_token_logprob import (
    ChatCompletionTokenLogprob,
    TopLogprob,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior

from safety.granite_guardian.utils import (
    _clean_up_candidates,
    _extract_tokens_inside_score_tag,
    _get_risky_probability,
    _search_tag,
    build_guardian_block,
    is_safe,
)


def _make_logprob(
    token: str,
    logprob: float = 0.0,
    top_logprobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a raw logprob dict matching ChatCompletionTokenLogprob."""
    return {
        "token": token,
        "logprob": logprob,
        "bytes": None,
        "top_logprobs": top_logprobs or [],
    }


def _make_token_logprob(
    token: str,
    logprob: float = 0.0,
    top_logprobs: list[tuple[str, float]] | None = None,
) -> ChatCompletionTokenLogprob:
    """Build a ChatCompletionTokenLogprob instance."""
    tops = [
        TopLogprob(token=top_token, logprob=top_logprob, bytes=None)
        for top_token, top_logprob in (top_logprobs or [])
    ]
    return ChatCompletionTokenLogprob(
        token=token,
        logprob=logprob,
        bytes=None,
        top_logprobs=tops,
    )


def _score_logprobs(safe_prob: float, risky_prob: float) -> list[dict[str, Any]]:
    """Build logprobs for a no-think response with one score token."""
    return [
        _make_logprob("<think>"),
        _make_logprob("\n"),
        _make_logprob("</think>"),
        _make_logprob("<score>"),
        _make_logprob(
            "no",
            logprob=math.log(safe_prob),
            top_logprobs=[
                {"token": "no", "logprob": math.log(safe_prob), "bytes": None},
                {"token": "yes", "logprob": math.log(risky_prob), "bytes": None},
            ],
        ),
        _make_logprob("</score>"),
    ]


class TestBuildGuardianBlock:
    """Tests for build_guardian_block."""

    def test_nothink_mode_contains_the_no_think_preamble(self) -> None:
        """Test that no-think mode asks for an empty think block."""
        result = build_guardian_block("test criteria", think=False)

        assert "<guardian><no-think>" in result
        assert "### Criteria: test criteria" in result
        assert "### Scoring Schema:" in result
        assert "return 'yes'" in result

    def test_think_mode_contains_the_think_preamble(self) -> None:
        """Test that think mode asks the judge to reason before scoring."""
        result = build_guardian_block("test criteria", think=True)

        assert "<guardian><think>" in result
        assert "<no-think>" not in result
        assert "### Criteria: test criteria" in result

    def test_default_is_nothink(self) -> None:
        """Test that think defaults to False."""
        assert "<no-think>" in build_guardian_block("criteria")


class TestSearchTag:
    """Tests for _search_tag."""

    def test_finds_a_complete_tag(self) -> None:
        """Test that a complete tag clears the buffer and reports a match."""
        remaining, found = _search_tag("<think>", "<think>")

        assert found is True
        assert remaining == ""

    def test_keeps_a_partial_tag(self) -> None:
        """Test that a partial tag stays in the buffer."""
        remaining, found = _search_tag("<think>", "<thi")

        assert found is False
        assert remaining == "<thi"

    def test_clears_non_tag_content(self) -> None:
        """Test that content which cannot be a tag clears the buffer."""
        remaining, found = _search_tag("<think>", "hello")

        assert found is False
        assert remaining == ""

    def test_finds_a_tag_inside_a_longer_buffer(self) -> None:
        """Test that a tag is detected when more text follows it."""
        remaining, found = _search_tag("<think>", "<think>some content")

        assert found is True
        assert remaining == ""

    def test_empty_buffer(self) -> None:
        """Test that an empty buffer is not a tag."""
        remaining, found = _search_tag("<think>", "")

        assert found is False
        assert remaining == ""

    def test_whitespace_only_buffer_clears(self) -> None:
        """Test that whitespace which is not a tag clears the buffer."""
        remaining, found = _search_tag("<think>", "   ")

        assert found is False
        assert remaining == ""

    def test_leading_whitespace_is_accepted(self) -> None:
        """Test that whitespace before a tag still counts as a match."""
        remaining, found = _search_tag("<think>", "  <think>")

        assert found is True
        assert remaining == ""


class TestCleanUpCandidates:
    """Tests for _clean_up_candidates."""

    def test_removes_a_split_end_tag(self) -> None:
        """Test that tokens forming the end tag are removed."""
        candidates = [
            _make_token_logprob("No"),
            _make_token_logprob("</"),
            _make_token_logprob("score>"),
        ]

        _clean_up_candidates(candidates)

        assert len(candidates) == 1
        assert candidates[0].token == "No"

    def test_removes_a_single_end_tag_token(self) -> None:
        """Test removal when the end tag arrives as one token."""
        candidates = [
            _make_token_logprob("yes"),
            _make_token_logprob("</score>"),
        ]

        _clean_up_candidates(candidates)

        assert [candidate.token for candidate in candidates] == ["yes"]

    def test_empty_candidates_do_not_raise(self) -> None:
        """Test that an empty candidate list is left empty."""
        candidates: list[ChatCompletionTokenLogprob] = []

        _clean_up_candidates(candidates)

        assert not candidates

    def test_drops_tokens_when_the_end_tag_is_absent(self) -> None:
        """Test that every candidate is removed when the end tag never appears."""
        candidates = [_make_token_logprob("No"), _make_token_logprob("maybe")]

        _clean_up_candidates(candidates)

        assert not candidates


class TestExtractTokensInsideScoreTag:
    """Tests for _extract_tokens_inside_score_tag."""

    def test_extracts_a_nothink_score_token(self) -> None:
        """Test extraction from a no-think response."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("\n"),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob("No"),
            _make_logprob("</score>"),
        ]

        assert _extract_tokens_inside_score_tag(logprobs).token == "No"

    def test_extracts_a_score_token_after_reasoning(self) -> None:
        """Test extraction from a think-mode response with reasoning text."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("The user is asking about pods."),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob("yes"),
            _make_logprob("</score>"),
        ]

        assert _extract_tokens_inside_score_tag(logprobs).token == "yes"

    def test_raises_when_the_format_is_missing(self) -> None:
        """Test that plain text raises UnexpectedModelBehavior."""
        with pytest.raises(UnexpectedModelBehavior, match="did not generate"):
            _extract_tokens_inside_score_tag([_make_logprob("This is plain text.")])

    def test_raises_when_the_score_tag_is_empty(self) -> None:
        """Test that an empty score tag raises UnexpectedModelBehavior."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob("</score>"),
        ]

        with pytest.raises(UnexpectedModelBehavior, match="No token found"):
            _extract_tokens_inside_score_tag(logprobs)

    def test_raises_when_the_score_has_multiple_tokens(self) -> None:
        """Test that a split score token raises UnexpectedModelBehavior."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob("y"),
            _make_logprob("es"),
            _make_logprob("</score>"),
        ]

        with pytest.raises(UnexpectedModelBehavior, match="More than one token"):
            _extract_tokens_inside_score_tag(logprobs)

    def test_extracts_a_score_when_tags_are_split(self) -> None:
        """Test extraction when each tag is split across tokens."""
        logprobs = [
            _make_logprob("<"),
            _make_logprob("think>"),
            _make_logprob("</"),
            _make_logprob("think>"),
            _make_logprob("<"),
            _make_logprob("score>"),
            _make_logprob("no"),
            _make_logprob("</"),
            _make_logprob("score>"),
        ]

        assert _extract_tokens_inside_score_tag(logprobs).token == "no"

    def test_extracts_a_score_when_the_think_start_tag_is_missing(self) -> None:
        """Test extraction when the model starts at the closing think tag."""
        logprobs = [
            _make_logprob("</think>"),
            _make_logprob("\n"),
            _make_logprob("<"),
            _make_logprob("score"),
            _make_logprob(">"),
            _make_logprob(" no"),
            _make_logprob(" </"),
            _make_logprob("score"),
            _make_logprob(">"),
        ]

        assert _extract_tokens_inside_score_tag(logprobs).token == " no"


class TestGetRiskyProbability:
    """Tests for _get_risky_probability."""

    def test_returns_the_normalized_risky_probability(self) -> None:
        """Test that safe and risky mass is normalized to the risky share."""
        token = _make_token_logprob(
            "no",
            top_logprobs=[("no", math.log(0.8)), ("yes", math.log(0.2))],
        )

        assert _get_risky_probability(token) == pytest.approx(0.2)

    def test_all_safe(self) -> None:
        """Test that only safe tokens produce a risky probability of zero."""
        token = _make_token_logprob(
            "no",
            top_logprobs=[("no", math.log(0.99)), ("No", math.log(0.01))],
        )

        assert _get_risky_probability(token) == pytest.approx(0.0)

    def test_all_risky(self) -> None:
        """Test that only risky tokens produce a risky probability of one."""
        token = _make_token_logprob(
            "yes",
            top_logprobs=[("yes", math.log(0.95)), ("Yes", math.log(0.05))],
        )

        assert _get_risky_probability(token) == pytest.approx(1.0)

    def test_raises_on_underflow(self) -> None:
        """Test that missing yes and no tokens raise UnexpectedModelBehavior."""
        token = _make_token_logprob(
            "maybe",
            top_logprobs=[("maybe", -1.0), ("perhaps", -2.0)],
        )

        with pytest.raises(UnexpectedModelBehavior, match="underflow"):
            _get_risky_probability(token)

    def test_strips_and_lowercases_candidate_tokens(self) -> None:
        """Test that token matching ignores case and surrounding whitespace."""
        token = _make_token_logprob(
            "No",
            top_logprobs=[(" No ", math.log(0.6)), ("YES", math.log(0.4))],
        )

        assert _get_risky_probability(token) == pytest.approx(0.4)


class TestIsSafe:
    """Tests for is_safe."""

    def test_safe_when_below_the_threshold(self) -> None:
        """Test that a risky probability below the threshold is safe."""
        assert is_safe(0.5, _score_logprobs(0.9, 0.1)) is True

    def test_unsafe_when_above_the_threshold(self) -> None:
        """Test that a risky probability above the threshold is unsafe."""
        assert is_safe(0.5, _score_logprobs(0.3, 0.7)) is False

    def test_unsafe_when_equal_to_the_threshold(self) -> None:
        """Test that a risky probability equal to the threshold is unsafe."""
        assert is_safe(0.5, _score_logprobs(0.5, 0.5)) is False

    def test_raises_when_the_format_is_missing(self) -> None:
        """Test that a response without the score format is an error."""
        with pytest.raises(UnexpectedModelBehavior, match="did not generate"):
            is_safe(0.5, [_make_logprob("plain text")])

    def test_raises_on_logprob_underflow(self) -> None:
        """Test that a score token without yes or no logprobs is an error."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob(
                "maybe",
                top_logprobs=[{"token": "maybe", "logprob": -0.1, "bytes": None}],
            ),
            _make_logprob("</score>"),
        ]

        with pytest.raises(UnexpectedModelBehavior, match="underflow"):
            is_safe(0.5, logprobs)
