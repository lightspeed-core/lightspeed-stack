"""Unit tests for certificate utilities defined in src/utils/certificates.py."""

import datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pytest_mock import MockerFixture

from utils.certificates import (
    CERTIFICATE_STORAGE_FILENAME,
    CertAddResult,
    add_ca_to_store,
    generate_ca_bundle,
)


def _generate_self_signed_cert(cn: str) -> bytes:
    """Generate a self-signed PEM certificate with the given common name."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        )
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


@pytest.fixture(name="sample_cert_pem")
def sample_cert_pem_fixture() -> bytes:
    """Return a self-signed PEM certificate for testing."""
    return _generate_self_signed_cert("Test CA")


@pytest.fixture(name="another_cert_pem")
def another_cert_pem_fixture() -> bytes:
    """Return a different self-signed PEM certificate for testing."""
    return _generate_self_signed_cert("Another Test CA")


class TestAddCaToStore:
    """Tests for add_ca_to_store function."""

    def test_adds_new_cert(
        self, tmp_path: Path, sample_cert_pem: bytes, another_cert_pem: bytes
    ) -> None:
        """Test adding a new certificate to the store."""
        cert_file = tmp_path / "new-ca.pem"
        cert_file.write_bytes(sample_cert_pem)

        store_file = tmp_path / "store.pem"
        store_file.write_bytes(another_cert_pem)

        result = add_ca_to_store(cert_file, store_file)
        assert result == CertAddResult.ADDED

        # Verify cert was appended
        store_content = store_file.read_bytes()
        assert sample_cert_pem in store_content
        assert another_cert_pem in store_content

    def test_detects_duplicate(self, tmp_path: Path, sample_cert_pem: bytes) -> None:
        """Test that duplicate certificate is detected."""
        cert_file = tmp_path / "ca.pem"
        cert_file.write_bytes(sample_cert_pem)

        store_file = tmp_path / "store.pem"
        store_file.write_bytes(sample_cert_pem)

        result = add_ca_to_store(cert_file, store_file)
        assert result == CertAddResult.ALREADY_EXISTS

    def test_nonexistent_cert_returns_error(self, tmp_path: Path) -> None:
        """Test that nonexistent cert file returns error."""
        cert_file = tmp_path / "nonexistent.pem"
        store_file = tmp_path / "store.pem"
        store_file.write_bytes(b"")

        result = add_ca_to_store(cert_file, store_file)
        assert result == CertAddResult.ERROR

    def test_malformed_cert_returns_error(self, tmp_path: Path) -> None:
        """Test that malformed PEM data returns error."""
        cert_file = tmp_path / "bad.pem"
        cert_file.write_bytes(b"not a valid certificate")

        store_file = tmp_path / "store.pem"
        store_file.write_bytes(b"")

        result = add_ca_to_store(cert_file, store_file)
        assert result == CertAddResult.ERROR

    def test_nonexistent_store_returns_error(
        self, tmp_path: Path, sample_cert_pem: bytes
    ) -> None:
        """Test that nonexistent store file returns error."""
        cert_file = tmp_path / "ca.pem"
        cert_file.write_bytes(sample_cert_pem)

        store_file = tmp_path / "nonexistent-store.pem"

        result = add_ca_to_store(cert_file, store_file)
        assert result == CertAddResult.ERROR


class TestGenerateCaBundle:
    """Tests for generate_ca_bundle function."""

    def test_generates_bundle(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """Test basic bundle generation with no extra CAs."""
        mock_certifi = mocker.patch("utils.certificates.certifi")
        mock_shutil = mocker.patch("utils.certificates.shutil")
        mock_certifi.where.return_value = "/fake/certifi/cacert.pem"

        result = generate_ca_bundle([], tmp_path)

        assert result is not None
        assert result == tmp_path / CERTIFICATE_STORAGE_FILENAME
        mock_shutil.copyfile.assert_called_once_with("/fake/certifi/cacert.pem", result)

    def test_nonexistent_directory_returns_none(self) -> None:
        """Test that nonexistent output directory returns None."""
        result = generate_ca_bundle([], Path("/nonexistent/directory"))
        assert result is None

    def test_adds_extra_cas(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        sample_cert_pem: bytes,
        another_cert_pem: bytes,
    ) -> None:
        """Test that extra CAs are appended to the bundle."""
        # Create a real certifi-like bundle
        certifi_bundle = tmp_path / "certifi-bundle.pem"
        certifi_bundle.write_bytes(another_cert_pem)
        mock_certifi = mocker.patch("utils.certificates.certifi")
        mock_certifi.where.return_value = str(certifi_bundle)

        # Create an extra CA file
        extra_ca = tmp_path / "extra-ca.pem"
        extra_ca.write_bytes(sample_cert_pem)

        result = generate_ca_bundle([extra_ca], tmp_path)

        assert result is not None
        bundle_content = result.read_bytes()
        assert sample_cert_pem in bundle_content
        assert another_cert_pem in bundle_content
