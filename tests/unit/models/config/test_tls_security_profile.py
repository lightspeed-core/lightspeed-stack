"""Unit tests for TLSSecurityProfile configuration model."""

import pytest

from models.config import (
    NetworkingConfiguration,
    ProxyConfiguration,
    TLSSecurityProfile,
)


class TestTLSSecurityProfileInit:
    """Tests for TLSSecurityProfile initialization."""

    def test_default_all_none(self) -> None:
        """Test default initialization with no parameters."""
        profile = TLSSecurityProfile()
        assert profile.profile_type is None
        assert profile.min_tls_version is None
        assert profile.ciphers is None
        assert profile.ca_cert_path is None
        assert profile.skip_tls_verification is False

    def test_with_profile_type(self) -> None:
        """Test initialization with profile type."""
        profile = TLSSecurityProfile(profile_type="ModernType")
        assert profile.profile_type == "ModernType"

    def test_with_yaml_aliases(self) -> None:
        """Test initialization using YAML-style alias names."""
        profile = TLSSecurityProfile(
            type="IntermediateType", minTLSVersion="VersionTLS12"
        )
        assert profile.profile_type == "IntermediateType"
        assert profile.min_tls_version == "VersionTLS12"

    def test_with_all_fields(self) -> None:
        """Test initialization with all fields set."""
        ciphers = ["TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384"]
        profile = TLSSecurityProfile(
            profile_type="Custom",
            min_tls_version="VersionTLS13",
            ciphers=ciphers,
            skip_tls_verification=True,
        )
        assert profile.profile_type == "Custom"
        assert profile.min_tls_version == "VersionTLS13"
        assert profile.ciphers == ciphers
        assert profile.skip_tls_verification is True


class TestTLSSecurityProfileValidation:
    """Tests for TLSSecurityProfile validation."""

    @pytest.mark.parametrize(
        "profile_type",
        ["OldType", "IntermediateType", "ModernType", "Custom"],
    )
    def test_valid_profile_types(self, profile_type: str) -> None:
        """Test all valid profile types are accepted."""
        profile = TLSSecurityProfile(profile_type=profile_type)
        assert profile.profile_type == profile_type

    def test_invalid_profile_type(self) -> None:
        """Test that invalid profile type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid TLS profile type"):
            TLSSecurityProfile(profile_type="InvalidType")

    @pytest.mark.parametrize(
        "version",
        ["VersionTLS10", "VersionTLS11", "VersionTLS12", "VersionTLS13"],
    )
    def test_valid_tls_versions(self, version: str) -> None:
        """Test all valid TLS versions are accepted."""
        profile = TLSSecurityProfile(min_tls_version=version)
        assert profile.min_tls_version == version

    def test_invalid_tls_version(self) -> None:
        """Test that invalid TLS version raises ValueError."""
        with pytest.raises(ValueError, match="Invalid TLS version"):
            TLSSecurityProfile(min_tls_version="VersionTLS14")

    def test_unsupported_cipher_for_profile(self) -> None:
        """Test that ciphers not in profile's supported list are rejected."""
        with pytest.raises(ValueError, match="Unsupported cipher"):
            TLSSecurityProfile(profile_type="ModernType", ciphers=["INVALID_CIPHER"])

    def test_custom_profile_allows_any_ciphers(self) -> None:
        """Test that Custom profile accepts arbitrary cipher names."""
        profile = TLSSecurityProfile(profile_type="Custom", ciphers=["ANY_CIPHER"])
        assert profile.ciphers == ["ANY_CIPHER"]

    def test_valid_ciphers_for_intermediate(self) -> None:
        """Test valid ciphers for IntermediateType are accepted."""
        ciphers = ["TLS_AES_128_GCM_SHA256", "ECDHE-RSA-AES128-GCM-SHA256"]
        profile = TLSSecurityProfile(profile_type="IntermediateType", ciphers=ciphers)
        assert profile.ciphers == ciphers

    def test_extra_fields_forbidden(self) -> None:
        """Test that unknown fields are rejected."""
        with pytest.raises(ValueError):
            TLSSecurityProfile(profile_type="ModernType", unknown_field="value")


class TestProxyConfiguration:
    """Tests for ProxyConfiguration model."""

    def test_default_all_none(self) -> None:
        """Test default initialization."""
        proxy = ProxyConfiguration()
        assert proxy.http_proxy is None
        assert proxy.https_proxy is None
        assert proxy.no_proxy is None

    def test_with_all_fields(self) -> None:
        """Test initialization with all fields."""
        proxy = ProxyConfiguration(
            http_proxy="http://proxy:8080",
            https_proxy="http://proxy:8080",
            no_proxy="localhost,127.0.0.1",
        )
        assert proxy.http_proxy == "http://proxy:8080"
        assert proxy.https_proxy == "http://proxy:8080"

    def test_invalid_proxy_url_no_scheme(self) -> None:
        """Test that proxy URL without scheme is rejected."""
        with pytest.raises(ValueError, match="missing a scheme"):
            ProxyConfiguration(http_proxy="://proxy:8080")

    def test_invalid_proxy_url_no_host(self) -> None:
        """Test that proxy URL without hostname is rejected."""
        with pytest.raises(ValueError, match="missing a hostname"):
            ProxyConfiguration(https_proxy="http://")

    def test_valid_proxy_url_with_path(self) -> None:
        """Test that proxy URL with path is accepted."""
        proxy = ProxyConfiguration(https_proxy="http://proxy:8080/path")
        assert proxy.https_proxy == "http://proxy:8080/path"
        assert proxy.no_proxy is None


class TestNetworkingConfiguration:
    """Tests for NetworkingConfiguration model."""

    def test_default_all_none(self) -> None:
        """Test default initialization."""
        nc = NetworkingConfiguration()
        assert nc.proxy is None
        assert nc.tls_security_profile is None
        assert nc.extra_ca == []
        assert nc.certificate_directory is None

    def test_with_proxy(self) -> None:
        """Test initialization with proxy config."""
        nc = NetworkingConfiguration(
            proxy=ProxyConfiguration(https_proxy="http://proxy:8080")
        )
        assert nc.proxy is not None
        assert nc.proxy.https_proxy == "http://proxy:8080"  # pylint: disable=no-member

    def test_with_tls_profile(self) -> None:
        """Test initialization with TLS security profile."""
        nc = NetworkingConfiguration(
            tls_security_profile=TLSSecurityProfile(profile_type="ModernType")
        )
        assert nc.tls_security_profile is not None
        profile = nc.tls_security_profile
        assert profile.profile_type == "ModernType"  # pylint: disable=no-member
