"""Unit tests for TLS utilities defined in src/utils/tls.py."""

import ssl

import pytest

from utils.tls import (
    MIN_TLS_VERSIONS,
    TLS_CIPHERS,
    TLSProfiles,
    TLSProtocolVersion,
    ciphers_for_profile,
    ciphers_from_list,
    filter_tls12_ciphers,
    resolve_ciphers,
    resolve_min_tls_version,
    ssl_tls_version,
)


class TestTLSProfiles:
    """Tests for TLSProfiles enum."""

    def test_values(self) -> None:
        """Test that TLSProfiles has expected string values."""
        assert TLSProfiles.OLD_TYPE == "OldType"
        assert TLSProfiles.INTERMEDIATE_TYPE == "IntermediateType"
        assert TLSProfiles.MODERN_TYPE == "ModernType"
        assert TLSProfiles.CUSTOM_TYPE == "Custom"

    def test_from_string(self) -> None:
        """Test creating TLSProfiles from string values."""
        assert TLSProfiles("OldType") == TLSProfiles.OLD_TYPE
        assert TLSProfiles("Custom") == TLSProfiles.CUSTOM_TYPE

    def test_invalid_value(self) -> None:
        """Test that invalid profile name raises ValueError."""
        with pytest.raises(ValueError):
            TLSProfiles("InvalidType")


class TestTLSProtocolVersion:
    """Tests for TLSProtocolVersion enum."""

    def test_values(self) -> None:
        """Test that TLSProtocolVersion has expected string values."""
        assert TLSProtocolVersion.VERSION_TLS_10 == "VersionTLS10"
        assert TLSProtocolVersion.VERSION_TLS_11 == "VersionTLS11"
        assert TLSProtocolVersion.VERSION_TLS_12 == "VersionTLS12"
        assert TLSProtocolVersion.VERSION_TLS_13 == "VersionTLS13"

    def test_from_string(self) -> None:
        """Test creating TLSProtocolVersion from string values."""
        assert TLSProtocolVersion("VersionTLS12") == TLSProtocolVersion.VERSION_TLS_12

    def test_invalid_value(self) -> None:
        """Test that invalid version string raises ValueError."""
        with pytest.raises(ValueError):
            TLSProtocolVersion("VersionTLS14")


class TestMinTLSVersionsMapping:
    """Tests for the MIN_TLS_VERSIONS mapping."""

    def test_old_type_requires_tls10(self) -> None:
        """Test OldType minimum version is TLS 1.0."""
        assert (
            MIN_TLS_VERSIONS[TLSProfiles.OLD_TYPE] == TLSProtocolVersion.VERSION_TLS_10
        )

    def test_intermediate_type_requires_tls12(self) -> None:
        """Test IntermediateType minimum version is TLS 1.2."""
        assert (
            MIN_TLS_VERSIONS[TLSProfiles.INTERMEDIATE_TYPE]
            == TLSProtocolVersion.VERSION_TLS_12
        )

    def test_modern_type_requires_tls13(self) -> None:
        """Test ModernType minimum version is TLS 1.3."""
        assert (
            MIN_TLS_VERSIONS[TLSProfiles.MODERN_TYPE]
            == TLSProtocolVersion.VERSION_TLS_13
        )

    def test_custom_type_not_in_mapping(self) -> None:
        """Test Custom type has no default minimum version."""
        assert TLSProfiles.CUSTOM_TYPE not in MIN_TLS_VERSIONS


class TestTLSCiphersMapping:
    """Tests for the TLS_CIPHERS mapping."""

    def test_profiles_have_ciphers(self) -> None:
        """Test that all predefined profiles have cipher definitions."""
        for profile in (
            TLSProfiles.OLD_TYPE,
            TLSProfiles.INTERMEDIATE_TYPE,
            TLSProfiles.MODERN_TYPE,
        ):
            assert profile in TLS_CIPHERS
            assert len(TLS_CIPHERS[profile]) > 0

    def test_modern_has_fewer_ciphers_than_old(self) -> None:
        """Test that ModernType is more restrictive than OldType."""
        assert len(TLS_CIPHERS[TLSProfiles.MODERN_TYPE]) < len(
            TLS_CIPHERS[TLSProfiles.OLD_TYPE]
        )

    def test_cipher_tuples_are_immutable(self) -> None:
        """Test that cipher definitions are tuples (immutable)."""
        for ciphers in TLS_CIPHERS.values():
            assert isinstance(ciphers, tuple)

    def test_custom_type_not_in_ciphers(self) -> None:
        """Test Custom type has no predefined ciphers."""
        assert TLSProfiles.CUSTOM_TYPE not in TLS_CIPHERS


class TestSslTlsVersion:
    """Tests for ssl_tls_version function."""

    @pytest.mark.parametrize(
        ("protocol_version", "expected"),
        [
            (TLSProtocolVersion.VERSION_TLS_10, ssl.TLSVersion.TLSv1),
            (TLSProtocolVersion.VERSION_TLS_11, ssl.TLSVersion.TLSv1_1),
            (TLSProtocolVersion.VERSION_TLS_12, ssl.TLSVersion.TLSv1_2),
            (TLSProtocolVersion.VERSION_TLS_13, ssl.TLSVersion.TLSv1_3),
        ],
    )
    def test_conversion(
        self, protocol_version: TLSProtocolVersion, expected: ssl.TLSVersion
    ) -> None:
        """Test conversion of all protocol versions."""
        assert ssl_tls_version(protocol_version) == expected

    def test_returns_ssl_tls_version_type(self) -> None:
        """Test that return type is ssl.TLSVersion."""
        result = ssl_tls_version(TLSProtocolVersion.VERSION_TLS_12)
        assert isinstance(result, ssl.TLSVersion)


class TestResolveMinTlsVersion:
    """Tests for resolve_min_tls_version function."""

    def test_explicit_version_takes_precedence(self) -> None:
        """Test that explicitly specified version overrides profile default."""
        result = resolve_min_tls_version(
            TLSProtocolVersion.VERSION_TLS_13, TLSProfiles.OLD_TYPE
        )
        assert result == TLSProtocolVersion.VERSION_TLS_13

    def test_none_uses_profile_default(self) -> None:
        """Test that None falls back to profile default."""
        result = resolve_min_tls_version(None, TLSProfiles.MODERN_TYPE)
        assert result == TLSProtocolVersion.VERSION_TLS_13

    def test_custom_profile_with_none_uses_safe_default(self) -> None:
        """Test that Custom profile without explicit version uses TLS 1.2."""
        result = resolve_min_tls_version(None, TLSProfiles.CUSTOM_TYPE)
        assert result == TLSProtocolVersion.VERSION_TLS_12


class TestCiphersFromList:
    """Tests for ciphers_from_list function."""

    def test_joins_with_colon(self) -> None:
        """Test that cipher list is joined with colons."""
        result = ciphers_from_list(["CIPHER1", "CIPHER2", "CIPHER3"])
        assert result == "CIPHER1:CIPHER2:CIPHER3"

    def test_single_cipher(self) -> None:
        """Test conversion of single-element list."""
        assert ciphers_from_list(["CIPHER1"]) == "CIPHER1"

    def test_empty_list(self) -> None:
        """Test conversion of empty list."""
        assert ciphers_from_list([]) == ""


class TestCiphersForProfile:
    """Tests for ciphers_for_profile function."""

    def test_returns_ciphers_for_predefined_profile(self) -> None:
        """Test that predefined profiles return their cipher tuples."""
        result = ciphers_for_profile(TLSProfiles.MODERN_TYPE)
        assert result is not None
        assert "TLS_AES_128_GCM_SHA256" in result

    def test_returns_none_for_custom(self) -> None:
        """Test that Custom profile returns None."""
        assert ciphers_for_profile(TLSProfiles.CUSTOM_TYPE) is None


class TestResolveCiphers:
    """Tests for resolve_ciphers function."""

    def test_custom_ciphers_take_precedence(self) -> None:
        """Test that explicit cipher list overrides profile."""
        result = resolve_ciphers(["CUSTOM1", "CUSTOM2"], TLSProfiles.MODERN_TYPE)
        assert result == "CUSTOM1:CUSTOM2"

    def test_none_uses_profile_default(self) -> None:
        """Test that None falls back to profile ciphers."""
        result = resolve_ciphers(None, TLSProfiles.MODERN_TYPE)
        assert result is not None
        assert "TLS_AES_128_GCM_SHA256" in result

    def test_custom_profile_with_none_returns_none(self) -> None:
        """Test that Custom profile with no ciphers returns None."""
        assert resolve_ciphers(None, TLSProfiles.CUSTOM_TYPE) is None


class TestFilterTls12Ciphers:
    """Tests for filter_tls12_ciphers function."""

    def test_filters_tls13_ciphers(self) -> None:
        """Test that TLS 1.3 ciphers are removed."""
        cipher_str = "TLS_AES_128_GCM_SHA256:ECDHE-RSA-AES128-GCM-SHA256"
        result = filter_tls12_ciphers(cipher_str)
        assert result == "ECDHE-RSA-AES128-GCM-SHA256"

    def test_returns_none_when_all_tls13(self) -> None:
        """Test that all-TLS-1.3 cipher string returns None."""
        cipher_str = "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384"
        assert filter_tls12_ciphers(cipher_str) is None

    def test_preserves_tls12_only(self) -> None:
        """Test that TLS 1.2 ciphers are preserved."""
        cipher_str = "ECDHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384"
        assert filter_tls12_ciphers(cipher_str) == cipher_str
