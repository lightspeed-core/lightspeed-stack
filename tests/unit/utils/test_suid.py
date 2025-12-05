"""Unit tests for functions defined in utils.suid module."""

from typing import Any

import pytest

from utils import suid


class TestSUID:
    """Unit tests for functions defined in utils.suid module."""

    def test_get_suid(self) -> None:
        """Test that get_suid generates a valid UUID."""
        suid_value = suid.get_suid()
        assert suid.check_suid(suid_value), "Generated SUID is not valid"
        assert isinstance(suid_value, str), "SUID should be a string"

    def test_check_suid_valid_uuid(self) -> None:
        """Test that check_suid returns True for a valid UUID."""
        valid_suid = "123e4567-e89b-12d3-a456-426614174000"
        assert suid.check_suid(valid_suid), "check_suid should return True for UUID"

    def test_check_suid_valid_48char_hex(self) -> None:
        """Test that check_suid returns True for a 48-char hex string."""
        valid_hex = "e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
        assert len(valid_hex) == 48
        assert suid.check_suid(
            valid_hex
        ), "check_suid should return True for 48-char hex"

    def test_check_suid_valid_conv_prefix(self) -> None:
        """Test that check_suid returns True for conv_ + 48-char hex string."""
        valid_conv = "conv_e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c"
        assert len(valid_conv) == 53
        assert suid.check_suid(
            valid_conv
        ), "check_suid should return True for conv_ prefixed hex"

    def test_check_suid_invalid_string(self) -> None:
        """Test that check_suid returns False for an invalid string."""
        assert not suid.check_suid("invalid-uuid")

    def test_check_suid_valid_32char_hex_uuid(self) -> None:
        """Test that check_suid returns True for 32-char hex (valid UUID format)."""
        # 32-char hex is a valid UUID format (without hyphens)
        assert suid.check_suid("e6afd7aaa97b49ce8f4f96a801b07893")

    def test_check_suid_invalid_hex_wrong_length(self) -> None:
        """Test that check_suid returns False for hex string with wrong length."""
        # 47 chars (not 48, not valid UUID)
        assert not suid.check_suid("e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3")
        # 49 chars (not 48, not valid UUID)
        assert not suid.check_suid("e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c1")

    def test_check_suid_invalid_conv_prefix_wrong_length(self) -> None:
        """Test that check_suid returns False for conv_ with wrong hex length."""
        # conv_ + 47 chars (not 48)
        assert not suid.check_suid(
            "conv_e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3"
        )
        # conv_ + 49 chars (not 48)
        assert not suid.check_suid(
            "conv_e6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53e3c1"
        )

    def test_check_suid_invalid_non_hex_chars(self) -> None:
        """Test that check_suid returns False for strings with non-hex characters."""
        # 48 chars but contains 'g' and 'z'
        invalid_hex = "g6afd7aaa97b49ce8f4f96a801b07893d9cb784d72e53ezz"
        assert len(invalid_hex) == 48
        assert not suid.check_suid(invalid_hex)

    @pytest.mark.parametrize("invalid_type", [None, 123, [], {}])
    def test_check_suid_invalid_type(self, invalid_type: Any) -> None:
        """Test that check_suid returns False for non-string types."""
        assert not suid.check_suid(invalid_type)
