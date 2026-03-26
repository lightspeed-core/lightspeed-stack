"""Certificate handling utilities for custom CA certificate management.

Provides functions to merge custom CA certificates with the system trust store
(certifi bundle) into a single combined certificate file. This is useful for
environments with interception proxies or internal CAs that need to be trusted
for outgoing HTTPS connections.
"""

import shutil
from enum import StrEnum
from pathlib import Path

import certifi
from cryptography import x509

from log import get_logger

logger = get_logger(__name__)

# Default filename for the merged certificate bundle.
CERTIFICATE_STORAGE_FILENAME = "ca-bundle.crt"


class CertAddResult(StrEnum):
    """Result of adding a certificate to the store."""

    ADDED = "added"
    ALREADY_EXISTS = "already_exists"
    ERROR = "error"


def add_ca_to_store(cert_path: Path, store_path: Path) -> CertAddResult:
    """Append a CA certificate to an existing certificate store file.

    Loads the certificate from cert_path, checks for duplicates against
    the existing certificates in store_path, and appends it if not already
    present.

    Parameters:
        cert_path: Path to the PEM-encoded CA certificate to add.
        store_path: Path to the certificate store file to append to.

    Returns:
        CertAddResult indicating whether the certificate was added,
        already existed, or caused an error.
    """
    try:
        new_cert_data = cert_path.read_bytes()
        new_cert = x509.load_pem_x509_certificate(new_cert_data)
    except (OSError, ValueError) as e:
        logger.error("Failed to load certificate from '%s': %s", cert_path, e)
        return CertAddResult.ERROR

    try:
        existing_data = store_path.read_bytes()
        existing_certs = x509.load_pem_x509_certificates(existing_data)
    except (OSError, ValueError) as e:
        logger.error("Failed to read certificate store '%s': %s", store_path, e)
        return CertAddResult.ERROR

    if new_cert in existing_certs:
        logger.info("Certificate '%s' already exists in store, skipping.", cert_path)
        return CertAddResult.ALREADY_EXISTS

    try:
        with open(store_path, "ab") as store_file:
            store_file.write(new_cert_data)
        logger.info(
            "Added certificate '%s' to store (%d bytes).",
            cert_path,
            len(new_cert_data),
        )
        return CertAddResult.ADDED
    except OSError as e:
        logger.error("Failed to write certificate to store '%s': %s", store_path, e)
        return CertAddResult.ERROR


def generate_ca_bundle(
    extra_ca_paths: list[Path],
    output_directory: Path,
    filename: str = CERTIFICATE_STORAGE_FILENAME,
) -> Path | None:
    """Generate a merged CA bundle from the system trust store and extra CAs.

    Copies the certifi CA bundle to the output directory, then appends each
    extra CA certificate. Certificates that already exist in the bundle or
    that fail to load are skipped with appropriate logging.

    Parameters:
        extra_ca_paths: List of paths to additional PEM-encoded CA certificates.
        output_directory: Directory where the merged bundle will be written.
        filename: Name of the output file (default: ca-bundle.crt).

    Returns:
        Path to the generated bundle file, or None if the output directory
        does not exist or is not writable.
    """
    if not output_directory.is_dir():
        logger.error(
            "Certificate output directory does not exist: %s", output_directory
        )
        return None

    destination = output_directory / filename

    # Start with the system certifi bundle
    certifi_location = certifi.where()
    logger.info("Copying certifi bundle from %s to %s", certifi_location, destination)
    shutil.copyfile(certifi_location, destination)

    # Append each extra CA
    added = 0
    errors = 0
    for cert_path in extra_ca_paths:
        result = add_ca_to_store(cert_path, destination)
        if result == CertAddResult.ADDED:
            added += 1
        elif result == CertAddResult.ERROR:
            errors += 1

    logger.info(
        "CA bundle generated: %d extra CAs added, %d errors, %d total extra CAs.",
        added,
        errors,
        len(extra_ca_paths),
    )

    if errors > 0:
        logger.warning(
            "%d certificate(s) failed to load. Check logs for details.", errors
        )

    return destination
