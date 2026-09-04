"""Unit tests for pydantic_ai_lightspeed.capabilities.granite_guardian.utils module."""

import math

import pytest
from openai.types.chat.chat_completion_token_logprob import (
    ChatCompletionTokenLogprob,
    TopLogprob,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior

from pydantic_ai_lightspeed.capabilities.granite_guardian.utils import (
    _clean_up_candidates,
    _extract_tokens_inside_score_tag,
    _get_risky_probabilities,
    _search_tag,
    build_guardian_block,
    is_safe,
)


def _make_logprob(token: str, logprob: float = 0.0, top_logprobs=None):
    """Build a raw logprob dict matching the ChatCompletionTokenLogprob schema."""
    return {
        "token": token,
        "logprob": logprob,
        "bytes": None,
        "top_logprobs": top_logprobs or [],
    }


def _make_token_logprob(token: str, logprob: float = 0.0, top_logprobs=None):
    """Build a ChatCompletionTokenLogprob instance."""
    tops = [
        TopLogprob(token=t, logprob=lp, bytes=None) for t, lp in (top_logprobs or [])
    ]
    return ChatCompletionTokenLogprob(
        token=token, logprob=logprob, bytes=None, top_logprobs=tops
    )


class TestBuildGuardianBlock:
    """Tests for build_guardian_block."""

    def test_nothink_mode_contains_no_think_tag(self) -> None:
        """Test that no-think mode uses the no-think preamble."""
        result = build_guardian_block("test criteria", think=False)
        assert "<guardian><no-think>" in result
        assert "### Criteria: test criteria" in result
        assert "### Scoring Schema:" in result

    def test_think_mode_contains_think_tag(self) -> None:
        """Test that think mode uses the think preamble."""
        result = build_guardian_block("test criteria", think=True)
        assert "<guardian><think>" in result
        assert "<no-think>" not in result

    def test_criteria_embedded_in_output(self) -> None:
        """Test that the criteria text appears in the output."""
        result = build_guardian_block("harmful content detection")
        assert "### Criteria: harmful content detection" in result

    def test_default_is_nothink(self) -> None:
        """Test that think defaults to False."""
        result = build_guardian_block("criteria")
        assert "<no-think>" in result


class TestSearchTag:
    """Tests for _search_tag."""

    def test_finds_complete_tag(self) -> None:
        """Test that a complete tag is detected."""
        remaining, found = _search_tag("<think>", "<think>")
        assert found is True
        assert remaining == ""

    def test_partial_tag_keeps_buffer(self) -> None:
        """Test that a partial tag keeps the buffer intact."""
        remaining, found = _search_tag("<think>", "<thi")
        assert found is False
        assert remaining == "<thi"

    def test_non_tag_content_clears_buffer(self) -> None:
        """Test that non-tag content clears the buffer."""
        remaining, found = _search_tag("<think>", "hello")
        assert found is False
        assert remaining == ""

    def test_tag_embedded_in_longer_string(self) -> None:
        """Test detection when tag is part of a longer string."""
        remaining, found = _search_tag("<think>", "<think>some content")
        assert found is True
        assert remaining == ""

    def test_empty_buffer(self) -> None:
        """Test empty buffer is treated as non-tag content."""
        remaining, found = _search_tag("<think>", "")
        assert found is False
        assert remaining == ""

    def test_whitespace_before_tag(self) -> None:
        """Test that leading whitespace before a tag is accepted."""
        remaining, found = _search_tag("<think>", "  <think>")
        assert found is True
        assert remaining == ""


class TestCleanUpCandidates:
    """Tests for _clean_up_candidates."""

    def test_removes_end_tag_tokens(self) -> None:
        """Test that tokens forming the end tag are removed."""
        candidates = [
            _make_token_logprob("No"),
            _make_token_logprob("</"),
            _make_token_logprob("score>"),
        ]
        _clean_up_candidates(candidates)
        assert len(candidates) == 1
        assert candidates[0].token == "No"

    def test_single_end_tag_token(self) -> None:
        """Test removal when end tag is a single token."""
        candidates = [
            _make_token_logprob("yes"),
            _make_token_logprob("</score>"),
        ]
        _clean_up_candidates(candidates)
        assert len(candidates) == 1
        assert candidates[0].token == "yes"

    def test_empty_candidates(self) -> None:
        """Test that empty list does not raise."""
        candidates = []
        _clean_up_candidates(candidates)
        assert not candidates


class TestExtractTokensInsideScoreTag:
    """Tests for _extract_tokens_inside_score_tag."""

    def test_extracts_score_token_nothink(self) -> None:
        """Test extraction from a no-think response format."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("\n"),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob("No", top_logprobs=[]),
            _make_logprob("</score>"),
        ]
        result = _extract_tokens_inside_score_tag(logprobs)
        assert result.token == "No"

    def test_extracts_score_token_with_think(self) -> None:
        """Test extraction from a think-mode response with reasoning content."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("The user is asking about pods."),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob("yes", top_logprobs=[]),
            _make_logprob("</score>"),
        ]
        result = _extract_tokens_inside_score_tag(logprobs)
        assert result.token == "yes"

    def test_raises_when_no_tags_present(self) -> None:
        """Test that missing tag structure raises UnexpectedModelBehavior."""
        logprobs = [
            _make_logprob("This is just plain text."),
        ]
        with pytest.raises(UnexpectedModelBehavior, match="did not generate"):
            _extract_tokens_inside_score_tag(logprobs)

    def test_raises_when_score_tag_empty(self) -> None:
        """Test that an empty score tag raises UnexpectedModelBehavior."""
        logprobs = [
            _make_logprob("<think>"),
            _make_logprob("</think>"),
            _make_logprob("<score>"),
            _make_logprob("</score>"),
        ]
        with pytest.raises(UnexpectedModelBehavior, match="No token found"):
            _extract_tokens_inside_score_tag(logprobs)

    def test_raises_when_multiple_tokens_in_score(self) -> None:
        """Test that multiple content tokens in score raises UnexpectedModelBehavior."""
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

    def test_split_tags_across_tokens(self) -> None:
        """Test extraction when tags are split across multiple tokens."""
        logprobs = [
            _make_logprob("<"),
            _make_logprob("think>"),
            _make_logprob("</"),
            _make_logprob("think>"),
            _make_logprob("<"),
            _make_logprob("score>"),
            _make_logprob("no", top_logprobs=[]),
            _make_logprob("</"),
            _make_logprob("score>"),
        ]
        result = _extract_tokens_inside_score_tag(logprobs)
        assert result.token == "no"

    def test_extracts_score_when_think_start_tag_missing(self) -> None:
        """Test extraction when model omits <think> and starts with </think>."""
        logprobs = [
            _make_logprob("</think>"),
            _make_logprob("\n"),
            _make_logprob("<"),
            _make_logprob("score"),
            _make_logprob(">"),
            _make_logprob(" no", top_logprobs=[]),
            _make_logprob(" </"),
            _make_logprob("score"),
            _make_logprob(">"),
        ]
        result = _extract_tokens_inside_score_tag(logprobs)
        assert result.token == " no"


class TestGetRiskyProbabilities:
    """Tests for _get_risky_probabilities."""

    def test_returns_risky_probability(self) -> None:
        """Test normalized risky probability computation."""
        token = _make_token_logprob(
            "no",
            top_logprobs=[
                ("no", math.log(0.8)),
                ("yes", math.log(0.2)),
            ],
        )
        result = _get_risky_probabilities(token)
        assert result == pytest.approx(0.2, abs=1e-6)

    def test_all_safe(self) -> None:
        """Test when all probability goes to safe token."""
        token = _make_token_logprob(
            "no",
            top_logprobs=[
                ("no", math.log(0.99)),
                ("No", math.log(0.01)),
            ],
        )
        result = _get_risky_probabilities(token)
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_all_risky(self) -> None:
        """Test when all probability goes to risky token."""
        token = _make_token_logprob(
            "yes",
            top_logprobs=[
                ("yes", math.log(0.95)),
                ("Yes", math.log(0.05)),
            ],
        )
        result = _get_risky_probabilities(token)
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_raises_on_underflow(self) -> None:
        """Test that zero total probability raises UnexpectedModelBehavior."""
        token = _make_token_logprob(
            "maybe",
            top_logprobs=[
                ("maybe", -1.0),
                ("perhaps", -2.0),
            ],
        )
        with pytest.raises(UnexpectedModelBehavior, match="underflow"):
            _get_risky_probabilities(token)

    def test_handles_whitespace_in_tokens(self) -> None:
        """Test that tokens with surrounding whitespace are normalized."""
        token = _make_token_logprob(
            " no ",
            top_logprobs=[
                (" no ", math.log(0.7)),
                (" yes ", math.log(0.3)),
            ],
        )
        result = _get_risky_probabilities(token)
        assert result == pytest.approx(0.3, abs=1e-6)

    def test_handles_case_insensitive_tokens(self) -> None:
        """Test that token matching is case-insensitive."""
        token = _make_token_logprob(
            "No",
            top_logprobs=[
                ("No", math.log(0.6)),
                ("YES", math.log(0.4)),
            ],
        )
        result = _get_risky_probabilities(token)
        assert result == pytest.approx(0.4, abs=1e-6)


class TestIsSafe:
    """Tests for is_safe."""

    def _make_full_logprobs(self, safe_prob: float, risky_prob: float):
        """Build a complete logprobs list for a single-token score response."""
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

    def test_safe_when_below_threshold(self) -> None:
        """Test that input is safe when risky probability is below threshold."""
        logprobs = self._make_full_logprobs(0.9, 0.1)
        assert is_safe(0.5, logprobs) is True

    def test_unsafe_when_above_threshold(self) -> None:
        """Test that input is unsafe when risky probability exceeds threshold."""
        logprobs = self._make_full_logprobs(0.3, 0.7)
        assert is_safe(0.5, logprobs) is False

    def test_unsafe_when_at_threshold(self) -> None:
        """Test that input is unsafe when risky probability equals threshold."""
        logprobs = self._make_full_logprobs(0.5, 0.5)
        assert is_safe(0.5, logprobs) is False
