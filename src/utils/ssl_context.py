"""SSL context construction from TLS security profiles.

Provides a single entry point for building ssl.SSLContext instances configured
with the appropriate TLS version, cipher suites, and CA certificates based on
a TLS security profile configuration.
"""

import ssl
from pathlib import Path

from log import get_logger
from utils.tls import (
    TLSProfiles,
    TLSProtocolVersion,
    filter_tls12_ciphers,
    resolve_ciphers,
    resolve_min_tls_version,
    ssl_tls_version,
)

logger = get_logger(__name__)


def build_ssl_context(
    profile_type: TLSProfiles,
    min_tls_version: TLSProtocolVersion | None = None,
    ciphers: list[str] | None = None,
    ca_cert_path: Path | None = None,
) -> ssl.SSLContext:
    """Build an SSL context from TLS security profile settings.

    Constructs an ssl.SSLContext with the minimum TLS version and cipher
    suites determined by the profile type and optional overrides. Hostname
    verification is always enabled.

    Parameters:
        profile_type: The TLS profile type (Old, Intermediate, Modern, Custom).
        min_tls_version: Override for minimum TLS version, or None to use
            the profile default.
        ciphers: Override cipher list, or None to use the profile default.
        ca_cert_path: Path to a CA certificate file for verifying server
            certificates, or None to use the system default trust store.

    Returns:
        A configured ssl.SSLContext ready for use with HTTP clients.

    Raises:
        ssl.SSLError: If the cipher string is invalid or cannot be applied.
        FileNotFoundError: If the CA certificate file does not exist.
    """
    context = ssl.create_default_context()

    # Hostname verification stays ON — this is a deliberate improvement over
    # road-core, which silently disabled it when using custom CA certs.
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    # Resolve and set minimum TLS version
    resolved_version = resolve_min_tls_version(min_tls_version, profile_type)
    ssl_version = ssl_tls_version(resolved_version)
    context.minimum_version = ssl_version
    logger.info("SSL context minimum TLS version: %s", ssl_version.name)

    # Resolve and set cipher suites
    cipher_string = resolve_ciphers(ciphers, profile_type)
    if cipher_string is not None:
        # TLS 1.3 ciphers are auto-negotiated and cannot be set via
        # set_ciphers(). Filter them out to avoid SSLError.
        tls12_ciphers = filter_tls12_ciphers(cipher_string)
        if tls12_ciphers:
            try:
                context.set_ciphers(tls12_ciphers)
                logger.info("SSL context ciphers set: %s", tls12_ciphers)
            except ssl.SSLError:
                logger.warning(
                    "Could not set ciphers '%s'. Falling back to OpenSSL defaults.",
                    tls12_ciphers,
                )
        else:
            logger.info(
                "All configured ciphers are TLS 1.3 — cipher selection "
                "is handled automatically by OpenSSL."
            )

    # Load custom CA certificate if specified
    if ca_cert_path is not None:
        context.load_verify_locations(cafile=str(ca_cert_path))
        logger.info("Loaded CA certificate from: %s", ca_cert_path)

    return context
