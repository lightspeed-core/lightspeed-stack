"""Unit tests for functions defined in utils.suid module."""

from utils import suid


class TestSUID:
    """Unit tests for functions defined in utils.suid module."""

    def test_get_suid(self):
        """Test that get_suid generates a valid UUID."""
        suid_value = suid.get_suid()
        assert suid.check_suid(suid_value), "Generated SUID is not valid"
        assert isinstance(suid_value, str), "SUID should be a string"

    def test_check_suid_valid(self):
        """Test that check_suid returns True for a valid UUID."""
        valid_suid = "123e4567-e89b-12d3-a456-426614174000"
        assert suid.check_suid(
            valid_suid
        ), "check_suid should return True for a valid SUID"

    def test_check_suid_invalid(self):
        """Test that check_suid returns False for an invalid UUID."""
        invalid_suid = "invalid-uuid"
        assert not suid.check_suid(
            invalid_suid
        ), "check_suid should return False for an invalid SUID"
