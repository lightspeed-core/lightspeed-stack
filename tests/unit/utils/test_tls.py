"""Unit tests for TLS utilities defined in src/utils/tls.py."""

import ssl

import pytest

from utils.tls import (
    TLSProfiles,
    TLSProtocolVersion,
    MIN_TLS_VERSIONS,
    TLS_CIPHERS,
    ssl_tls_version,
    min_tls_version,
    ciphers_from_list,
    ciphers_for_tls_profile,
    ciphers_as_string,
)


class TestTLSProfiles:
    """Tests for TLSProfiles enum."""

    def test_tls_profiles_values(self) -> None:
        """Test that TLSProfiles has expected values."""
        assert TLSProfiles.OLD_TYPE == "OldType"
        assert TLSProfiles.INTERMEDIATE_TYPE == "IntermediateType"
        assert TLSProfiles.MODERN_TYPE == "ModernType"
        assert TLSProfiles.CUSTOM_TYPE == "Custom"

    def test_tls_profiles_from_string(self) -> None:
        """Test creating TLSProfiles from string."""
        assert TLSProfiles("OldType") == TLSProfiles.OLD_TYPE
        assert TLSProfiles("IntermediateType") == TLSProfiles.INTERMEDIATE_TYPE
        assert TLSProfiles("ModernType") == TLSProfiles.MODERN_TYPE
        assert TLSProfiles("Custom") == TLSProfiles.CUSTOM_TYPE

    def test_tls_profiles_invalid(self) -> None:
        """Test invalid TLS profile raises error."""
        with pytest.raises(ValueError):
            TLSProfiles("InvalidType")


class TestTLSProtocolVersion:
    """Tests for TLSProtocolVersion enum."""

    def test_tls_protocol_version_values(self) -> None:
        """Test that TLSProtocolVersion has expected values."""
        assert TLSProtocolVersion.VERSION_TLS_10 == "VersionTLS10"
        assert TLSProtocolVersion.VERSION_TLS_11 == "VersionTLS11"
        assert TLSProtocolVersion.VERSION_TLS_12 == "VersionTLS12"
        assert TLSProtocolVersion.VERSION_TLS_13 == "VersionTLS13"

    def test_tls_protocol_version_from_string(self) -> None:
        """Test creating TLSProtocolVersion from string."""
        assert TLSProtocolVersion("VersionTLS10") == TLSProtocolVersion.VERSION_TLS_10
        assert TLSProtocolVersion("VersionTLS11") == TLSProtocolVersion.VERSION_TLS_11
        assert TLSProtocolVersion("VersionTLS12") == TLSProtocolVersion.VERSION_TLS_12
        assert TLSProtocolVersion("VersionTLS13") == TLSProtocolVersion.VERSION_TLS_13

    def test_tls_protocol_version_invalid(self) -> None:
        """Test invalid TLS version raises error."""
        with pytest.raises(ValueError):
            TLSProtocolVersion("VersionTLS14")


class TestMinTLSVersionsMapping:
    """Tests for MIN_TLS_VERSIONS mapping."""

    def test_old_type_min_version(self) -> None:
        """Test OldType has TLS 1.0 as minimum."""
        assert MIN_TLS_VERSIONS[TLSProfiles.OLD_TYPE] == TLSProtocolVersion.VERSION_TLS_10

    def test_intermediate_type_min_version(self) -> None:
        """Test IntermediateType has TLS 1.2 as minimum."""
        assert (
            MIN_TLS_VERSIONS[TLSProfiles.INTERMEDIATE_TYPE]
            == TLSProtocolVersion.VERSION_TLS_12
        )

    def test_modern_type_min_version(self) -> None:
        """Test ModernType has TLS 1.3 as minimum."""
        assert MIN_TLS_VERSIONS[TLSProfiles.MODERN_TYPE] == TLSProtocolVersion.VERSION_TLS_13


class TestTLSCiphersMapping:
    """Tests for TLS_CIPHERS mapping."""

    def test_old_type_has_ciphers(self) -> None:
        """Test OldType has ciphers defined."""
        assert TLSProfiles.OLD_TYPE in TLS_CIPHERS
        assert len(TLS_CIPHERS[TLSProfiles.OLD_TYPE]) > 0

    def test_intermediate_type_has_ciphers(self) -> None:
        """Test IntermediateType has ciphers defined."""
        assert TLSProfiles.INTERMEDIATE_TYPE in TLS_CIPHERS
        assert len(TLS_CIPHERS[TLSProfiles.INTERMEDIATE_TYPE]) > 0

    def test_modern_type_has_ciphers(self) -> None:
        """Test ModernType has ciphers defined."""
        assert TLSProfiles.MODERN_TYPE in TLS_CIPHERS
        assert len(TLS_CIPHERS[TLSProfiles.MODERN_TYPE]) > 0

    def test_modern_type_has_fewer_ciphers_than_old(self) -> None:
        """Test ModernType has fewer ciphers than OldType (more restrictive)."""
        assert len(TLS_CIPHERS[TLSProfiles.MODERN_TYPE]) < len(
            TLS_CIPHERS[TLSProfiles.OLD_TYPE]
        )


class TestSslTlsVersion:
    """Tests for ssl_tls_version function."""

    def test_ssl_tls_version_tls10(self) -> None:
        """Test conversion of TLS 1.0."""
        result = ssl_tls_version(TLSProtocolVersion.VERSION_TLS_10)
        assert result == ssl.TLSVersion.TLSv1

    def test_ssl_tls_version_tls11(self) -> None:
        """Test conversion of TLS 1.1."""
        result = ssl_tls_version(TLSProtocolVersion.VERSION_TLS_11)
        assert result == ssl.TLSVersion.TLSv1_1

    def test_ssl_tls_version_tls12(self) -> None:
        """Test conversion of TLS 1.2."""
        result = ssl_tls_version(TLSProtocolVersion.VERSION_TLS_12)
        assert result == ssl.TLSVersion.TLSv1_2

    def test_ssl_tls_version_tls13(self) -> None:
        """Test conversion of TLS 1.3."""
        result = ssl_tls_version(TLSProtocolVersion.VERSION_TLS_13)
        assert result == ssl.TLSVersion.TLSv1_3

    def test_ssl_tls_version_none(self) -> None:
        """Test conversion of None returns None."""
        result = ssl_tls_version(None)
        assert result is None


class TestMinTlsVersion:
    """Tests for min_tls_version function."""

    def test_min_tls_version_specified(self) -> None:
        """Test that specified version overrides profile default."""
        result = min_tls_version("VersionTLS13", TLSProfiles.OLD_TYPE)
        assert result == TLSProtocolVersion.VERSION_TLS_13

    def test_min_tls_version_from_profile(self) -> None:
        """Test that profile default is used when no version specified."""
        result = min_tls_version(None, TLSProfiles.MODERN_TYPE)
        assert result == TLSProtocolVersion.VERSION_TLS_13

    def test_min_tls_version_invalid_falls_back_to_profile(self) -> None:
        """Test that invalid version falls back to profile default."""
        result = min_tls_version("InvalidVersion", TLSProfiles.INTERMEDIATE_TYPE)
        assert result == TLSProtocolVersion.VERSION_TLS_12


class TestCiphersFromList:
    """Tests for ciphers_from_list function."""

    def test_ciphers_from_list_with_ciphers(self) -> None:
        """Test conversion of cipher list to string."""
        ciphers = ["CIPHER1", "CIPHER2", "CIPHER3"]
        result = ciphers_from_list(ciphers)
        assert result == "CIPHER1:CIPHER2:CIPHER3"

    def test_ciphers_from_list_single(self) -> None:
        """Test conversion of single cipher."""
        ciphers = ["CIPHER1"]
        result = ciphers_from_list(ciphers)
        assert result == "CIPHER1"

    def test_ciphers_from_list_empty(self) -> None:
        """Test conversion of empty list."""
        result = ciphers_from_list([])
        assert result == ""

    def test_ciphers_from_list_none(self) -> None:
        """Test conversion of None returns None."""
        result = ciphers_from_list(None)
        assert result is None


class TestCiphersForTlsProfile:
    """Tests for ciphers_for_tls_profile function."""

    def test_ciphers_for_old_type(self) -> None:
        """Test getting ciphers for OldType profile."""
        result = ciphers_for_tls_profile(TLSProfiles.OLD_TYPE)
        assert result is not None
        assert ":" in result  # Should be colon-separated

    def test_ciphers_for_modern_type(self) -> None:
        """Test getting ciphers for ModernType profile."""
        result = ciphers_for_tls_profile(TLSProfiles.MODERN_TYPE)
        assert result is not None
        # Modern type should have TLS 1.3 ciphers
        assert "TLS_AES_128_GCM_SHA256" in result

    def test_ciphers_for_custom_type(self) -> None:
        """Test Custom type returns None (no predefined ciphers)."""
        result = ciphers_for_tls_profile(TLSProfiles.CUSTOM_TYPE)
        assert result is None


class TestCiphersAsString:
    """Tests for ciphers_as_string function."""

    def test_ciphers_as_string_custom_list(self) -> None:
        """Test that custom cipher list is used when provided."""
        custom_ciphers = ["CUSTOM1", "CUSTOM2"]
        result = ciphers_as_string(custom_ciphers, TLSProfiles.MODERN_TYPE)
        assert result == "CUSTOM1:CUSTOM2"

    def test_ciphers_as_string_profile_default(self) -> None:
        """Test that profile ciphers are used when no custom list."""
        result = ciphers_as_string(None, TLSProfiles.MODERN_TYPE)
        assert result is not None
        assert "TLS_AES_128_GCM_SHA256" in result

    def test_ciphers_as_string_empty_list_uses_profile(self) -> None:
        """Test that empty list results in empty string (not profile default)."""
        result = ciphers_as_string([], TLSProfiles.MODERN_TYPE)
        assert result == ""

