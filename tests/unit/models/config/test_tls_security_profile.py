"""Unit tests for TLSSecurityProfile configuration model."""

import pytest

from models.config import TLSSecurityProfile, LlamaStackConfiguration


class TestTLSSecurityProfileInit:
    """Tests for TLSSecurityProfile initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization with no parameters."""
        profile = TLSSecurityProfile()
        assert profile.profile_type is None
        assert profile.min_tls_version is None
        assert profile.ciphers is None

    def test_initialization_with_profile_type(self) -> None:
        """Test initialization with profile type."""
        profile = TLSSecurityProfile(profile_type="ModernType")
        assert profile.profile_type == "ModernType"
        assert profile.min_tls_version is None
        assert profile.ciphers is None

    def test_initialization_with_alias(self) -> None:
        """Test initialization using YAML-style aliases."""
        profile = TLSSecurityProfile(type="IntermediateType", minTLSVersion="VersionTLS12")
        assert profile.profile_type == "IntermediateType"
        assert profile.min_tls_version == "VersionTLS12"

    def test_initialization_with_all_fields(self) -> None:
        """Test initialization with all fields."""
        ciphers = ["TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384"]
        profile = TLSSecurityProfile(
            profile_type="Custom",
            min_tls_version="VersionTLS13",
            ciphers=ciphers,
        )
        assert profile.profile_type == "Custom"
        assert profile.min_tls_version == "VersionTLS13"
        assert profile.ciphers == ciphers


class TestTLSSecurityProfileValidation:
    """Tests for TLSSecurityProfile validation."""

    def test_valid_old_type_profile(self) -> None:
        """Test valid OldType profile."""
        profile = TLSSecurityProfile(profile_type="OldType")
        assert profile.profile_type == "OldType"

    def test_valid_intermediate_type_profile(self) -> None:
        """Test valid IntermediateType profile."""
        profile = TLSSecurityProfile(profile_type="IntermediateType")
        assert profile.profile_type == "IntermediateType"

    def test_valid_modern_type_profile(self) -> None:
        """Test valid ModernType profile."""
        profile = TLSSecurityProfile(profile_type="ModernType")
        assert profile.profile_type == "ModernType"

    def test_valid_custom_profile(self) -> None:
        """Test valid Custom profile."""
        profile = TLSSecurityProfile(profile_type="Custom")
        assert profile.profile_type == "Custom"

    def test_invalid_profile_type(self) -> None:
        """Test invalid profile type raises error."""
        with pytest.raises(ValueError, match="Invalid TLS profile type"):
            TLSSecurityProfile(profile_type="InvalidType")

    def test_valid_tls_versions(self) -> None:
        """Test all valid TLS versions."""
        for version in ["VersionTLS10", "VersionTLS11", "VersionTLS12", "VersionTLS13"]:
            profile = TLSSecurityProfile(min_tls_version=version)
            assert profile.min_tls_version == version

    def test_invalid_tls_version(self) -> None:
        """Test invalid TLS version raises error."""
        with pytest.raises(ValueError, match="Invalid minimal TLS version"):
            TLSSecurityProfile(min_tls_version="VersionTLS14")

    def test_cipher_validation_non_custom_profile(self) -> None:
        """Test that ciphers must be valid for non-Custom profiles."""
        # Using a cipher not in the ModernType profile
        with pytest.raises(ValueError, match="Unsupported cipher"):
            TLSSecurityProfile(
                profile_type="ModernType",
                ciphers=["INVALID_CIPHER"],
            )

    def test_cipher_validation_custom_profile_allows_any(self) -> None:
        """Test that Custom profile allows any ciphers."""
        profile = TLSSecurityProfile(
            profile_type="Custom",
            ciphers=["ANY_CIPHER_ALLOWED"],
        )
        assert profile.ciphers == ["ANY_CIPHER_ALLOWED"]

    def test_valid_ciphers_for_profile(self) -> None:
        """Test valid ciphers for IntermediateType profile."""
        profile = TLSSecurityProfile(
            profile_type="IntermediateType",
            ciphers=["TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384"],
        )
        assert profile.ciphers == ["TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384"]


class TestTLSSecurityProfileExtraFields:
    """Tests for extra field handling."""

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields are rejected."""
        with pytest.raises(ValueError):
            TLSSecurityProfile(
                profile_type="ModernType",
                unknown_field="value",
            )


class TestLlamaStackConfigurationWithTLS:
    """Tests for LlamaStackConfiguration with TLS security profile."""

    def test_llama_stack_config_without_tls_profile(self) -> None:
        """Test LlamaStackConfiguration without TLS profile."""
        config = LlamaStackConfiguration(
            url="https://llama-stack:8321",
            use_as_library_client=False,
        )
        assert config.tls_security_profile is None

    def test_llama_stack_config_with_tls_profile(self) -> None:
        """Test LlamaStackConfiguration with TLS profile."""
        tls_profile = TLSSecurityProfile(
            profile_type="ModernType",
            min_tls_version="VersionTLS13",
        )
        config = LlamaStackConfiguration(
            url="https://llama-stack:8321",
            use_as_library_client=False,
            tls_security_profile=tls_profile,
        )
        assert config.tls_security_profile is not None
        assert config.tls_security_profile.profile_type == "ModernType"
        assert config.tls_security_profile.min_tls_version == "VersionTLS13"

    def test_llama_stack_config_with_custom_ciphers(self) -> None:
        """Test LlamaStackConfiguration with custom TLS ciphers."""
        ciphers = [
            "TLS_AES_128_GCM_SHA256",
            "TLS_AES_256_GCM_SHA384",
        ]
        tls_profile = TLSSecurityProfile(
            profile_type="Custom",
            min_tls_version="VersionTLS13",
            ciphers=ciphers,
        )
        config = LlamaStackConfiguration(
            url="https://llama-stack:8321",
            use_as_library_client=False,
            tls_security_profile=tls_profile,
        )
        assert config.tls_security_profile is not None
        assert config.tls_security_profile.ciphers == ciphers

