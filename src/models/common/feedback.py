"""Predefined feedback categories for AI response quality signals."""

from enum import StrEnum


class FeedbackCategory(StrEnum):
    """Enum representing predefined feedback categories for AI responses.

    These categories help provide structured feedback about AI inference quality
    when users provide negative feedback (thumbs down). Multiple categories can
    be selected to provide comprehensive feedback about response issues.
    """

    INCORRECT = "incorrect"  # "The answer provided is completely wrong"
    NOT_RELEVANT = "not_relevant"  # "This answer doesn't address my question at all"
    INCOMPLETE = "incomplete"  # "The answer only covers part of what I asked about"
    OUTDATED_INFORMATION = "outdated_information"  # "This information is from several years ago and no longer accurate"  # pylint: disable=line-too-long
    UNSAFE = "unsafe"  # "This response could be harmful or dangerous if followed"
    OTHER = "other"  # "The response has issues not covered by other categories"


class PositiveFeedbackCategory(StrEnum):
    """Enum representing predefined categories for positive AI responses.

    These categories cover qualities commonly associated with a useful answer.
    """

    HELPFUL = "helpful"  # "The response is useful"
    ACCURATE = "accurate"  # "The information provided is correct"
    CLEAR = "clear"  # "The response is easy to understand"
    RELEVANT = "relevant"  # "This answer addresses my question"
    ACTIONABLE = "actionable"  # "The response provides steps I can follow"
    RESOLVED_ISSUE = "resolved_issue"  # "This response solved my problem"
