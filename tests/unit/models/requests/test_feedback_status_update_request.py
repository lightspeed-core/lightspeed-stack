"""Unit tests for FeedbackStatusUpdateRequest model."""

from lightspeed_stack.models.api.requests import FeedbackStatusUpdateRequest


class TestFeedbackStatusUpdateRequest:
    """Test cases for the FeedbackStatusUpdateRequest model."""

    def test_constructor(self) -> None:
        """Test the FeedbackStatusUpdateRequest constructor."""
        fs = FeedbackStatusUpdateRequest(status=False)
        assert fs.status is False

        fs = FeedbackStatusUpdateRequest(status=True)
        assert fs.status is True

    def test_get_value(self) -> None:
        """Test the FeedbackStatusUpdateRequest.get_value method."""
        fs = FeedbackStatusUpdateRequest(status=False)
        assert fs.get_value() is False

        fs = FeedbackStatusUpdateRequest(status=True)
        assert fs.get_value() is True
