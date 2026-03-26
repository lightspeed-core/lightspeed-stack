"""Unit tests for SSL context builder defined in src/utils/ssl_context.py."""

import ssl
from pathlib import Path

from pytest_mock import MockerFixture

from utils.ssl_context import build_ssl_context
from utils.tls import TLSProfiles, TLSProtocolVersion


class TestBuildSslContext:
    """Tests for build_ssl_context function."""

    def test_modern_profile_sets_tls13(self, mocker: MockerFixture) -> None:
        """Test that ModernType profile sets minimum version to TLS 1.3."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(TLSProfiles.MODERN_TYPE)

        assert mock_ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_intermediate_profile_sets_tls12(self, mocker: MockerFixture) -> None:
        """Test that IntermediateType profile sets minimum version to TLS 1.2."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(TLSProfiles.INTERMEDIATE_TYPE)

        assert mock_ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_explicit_version_overrides_profile(self, mocker: MockerFixture) -> None:
        """Test that explicit min_tls_version overrides profile default."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(
            TLSProfiles.OLD_TYPE,
            min_tls_version=TLSProtocolVersion.VERSION_TLS_13,
        )

        assert mock_ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_hostname_verification_enabled(self, mocker: MockerFixture) -> None:
        """Test that hostname verification is always enabled."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(TLSProfiles.MODERN_TYPE)

        assert mock_ctx.check_hostname is True
        assert mock_ctx.verify_mode == ssl.CERT_REQUIRED

    def test_ca_cert_loaded(self, mocker: MockerFixture) -> None:
        """Test that CA certificate is loaded when path is provided."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        ca_path = Path("/path/to/ca.crt")
        build_ssl_context(TLSProfiles.MODERN_TYPE, ca_cert_path=ca_path)

        mock_ctx.load_verify_locations.assert_called_once_with(cafile=str(ca_path))

    def test_no_ca_cert_not_loaded(self, mocker: MockerFixture) -> None:
        """Test that no CA certificate loading when path is None."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(TLSProfiles.MODERN_TYPE)

        mock_ctx.load_verify_locations.assert_not_called()

    def test_ciphers_set_for_intermediate(self, mocker: MockerFixture) -> None:
        """Test that ciphers are set for IntermediateType profile."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(TLSProfiles.INTERMEDIATE_TYPE)

        # IntermediateType has both TLS 1.3 and 1.2 ciphers — only 1.2 are set
        mock_ctx.set_ciphers.assert_called_once()
        cipher_arg = mock_ctx.set_ciphers.call_args[0][0]
        # Should not contain TLS 1.3 cipher prefixes
        assert "TLS_AES" not in cipher_arg
        # Should contain TLS 1.2 ciphers
        assert "ECDHE-" in cipher_arg

    def test_modern_profile_skips_set_ciphers(self, mocker: MockerFixture) -> None:
        """Test that ModernType (TLS 1.3 only ciphers) does not call set_ciphers."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(TLSProfiles.MODERN_TYPE)

        # ModernType has only TLS 1.3 ciphers — set_ciphers should not be called
        mock_ctx.set_ciphers.assert_not_called()

    def test_custom_ciphers_override(self, mocker: MockerFixture) -> None:
        """Test that explicit ciphers override profile defaults."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        build_ssl_context(
            TLSProfiles.CUSTOM_TYPE,
            ciphers=["ECDHE-RSA-AES128-GCM-SHA256"],
        )

        mock_ctx.set_ciphers.assert_called_once_with("ECDHE-RSA-AES128-GCM-SHA256")

    def test_cipher_error_handled_gracefully(self, mocker: MockerFixture) -> None:
        """Test that SSLError from invalid ciphers is handled without raising."""
        mock_ctx = mocker.MagicMock()
        mock_ctx.set_ciphers.side_effect = ssl.SSLError("No cipher can be selected.")
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        # Should not raise — handled with warning
        ctx = build_ssl_context(
            TLSProfiles.CUSTOM_TYPE,
            ciphers=["INVALID_CIPHER"],
        )
        assert ctx is mock_ctx

    def test_returns_ssl_context(self, mocker: MockerFixture) -> None:
        """Test that the function returns the constructed context."""
        mock_ctx = mocker.MagicMock()
        mocker.patch(
            "utils.ssl_context.ssl.create_default_context", return_value=mock_ctx
        )

        result = build_ssl_context(TLSProfiles.MODERN_TYPE)
        assert result is mock_ctx
