"""TLS security profile definitions and utilities.

Implements OpenShift-compatible TLS security profiles for outgoing connections.
Profile definitions are sourced from the OpenShift API specification:
https://github.com/openshift/api/blob/master/config/v1/types_tlssecurityprofile.go

Each profile defines a minimum TLS version and a set of allowed cipher suites.
The profiles are:

- **OldType**: Maximum backward compatibility (TLS 1.0+, 29 ciphers including
  legacy suites). Use only when connecting to systems that cannot be upgraded.
- **IntermediateType**: Recommended for most deployments (TLS 1.2+, 11 ciphers).
  Balances security with broad compatibility.
- **ModernType**: Maximum security (TLS 1.3 only, 3 ciphers). Use when all
  endpoints support TLS 1.3.
- **Custom**: User-defined minimum TLS version and cipher list.
"""

import ssl
from enum import StrEnum


class TLSProfiles(StrEnum):
    """TLS profile type names matching the OpenShift API specification."""

    OLD_TYPE = "OldType"
    INTERMEDIATE_TYPE = "IntermediateType"
    MODERN_TYPE = "ModernType"
    CUSTOM_TYPE = "Custom"


class TLSProtocolVersion(StrEnum):
    """TLS protocol version identifiers matching the OpenShift API specification."""

    VERSION_TLS_10 = "VersionTLS10"
    VERSION_TLS_11 = "VersionTLS11"
    VERSION_TLS_12 = "VersionTLS12"
    VERSION_TLS_13 = "VersionTLS13"


# Mapping from protocol version identifiers to ssl.TLSVersion values.
_TLS_VERSION_MAP: dict[TLSProtocolVersion, ssl.TLSVersion] = {
    TLSProtocolVersion.VERSION_TLS_10: ssl.TLSVersion.TLSv1,
    TLSProtocolVersion.VERSION_TLS_11: ssl.TLSVersion.TLSv1_1,
    TLSProtocolVersion.VERSION_TLS_12: ssl.TLSVersion.TLSv1_2,
    TLSProtocolVersion.VERSION_TLS_13: ssl.TLSVersion.TLSv1_3,
}

# Minimum TLS versions required for each predefined profile.
MIN_TLS_VERSIONS: dict[TLSProfiles, TLSProtocolVersion] = {
    TLSProfiles.OLD_TYPE: TLSProtocolVersion.VERSION_TLS_10,
    TLSProfiles.INTERMEDIATE_TYPE: TLSProtocolVersion.VERSION_TLS_12,
    TLSProfiles.MODERN_TYPE: TLSProtocolVersion.VERSION_TLS_13,
}

# Cipher suites defined for each predefined profile.
# Note: TLS 1.3 ciphers (TLS_AES_*) are automatically negotiated by OpenSSL
# and cannot be restricted via ssl.SSLContext.set_ciphers(). They are included
# here for documentation and validation purposes only.
TLS_CIPHERS: dict[TLSProfiles, tuple[str, ...]] = {
    TLSProfiles.OLD_TYPE: (
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-CHACHA20-POLY1305",
        "ECDHE-RSA-CHACHA20-POLY1305",
        "DHE-RSA-AES128-GCM-SHA256",
        "DHE-RSA-AES256-GCM-SHA384",
        "DHE-RSA-CHACHA20-POLY1305",
        "ECDHE-ECDSA-AES128-SHA256",
        "ECDHE-RSA-AES128-SHA256",
        "ECDHE-ECDSA-AES128-SHA",
        "ECDHE-RSA-AES128-SHA",
        "ECDHE-ECDSA-AES256-SHA384",
        "ECDHE-RSA-AES256-SHA384",
        "ECDHE-ECDSA-AES256-SHA",
        "ECDHE-RSA-AES256-SHA",
        "DHE-RSA-AES128-SHA256",
        "DHE-RSA-AES256-SHA256",
        "AES128-GCM-SHA256",
        "AES256-GCM-SHA384",
        "AES128-SHA256",
        "AES256-SHA256",
        "AES128-SHA",
        "AES256-SHA",
        "DES-CBC3-SHA",
    ),
    TLSProfiles.INTERMEDIATE_TYPE: (
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
        "ECDHE-ECDSA-AES128-GCM-SHA256",
        "ECDHE-RSA-AES128-GCM-SHA256",
        "ECDHE-ECDSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-ECDSA-CHACHA20-POLY1305",
        "ECDHE-RSA-CHACHA20-POLY1305",
        "DHE-RSA-AES128-GCM-SHA256",
        "DHE-RSA-AES256-GCM-SHA384",
    ),
    TLSProfiles.MODERN_TYPE: (
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
        "TLS_CHACHA20_POLY1305_SHA256",
    ),
}

# TLS 1.3 cipher prefixes — these cannot be set via set_ciphers() and are
# always available when TLS 1.3 is negotiated.
_TLS_13_CIPHER_PREFIX = "TLS_"


def ssl_tls_version(
    tls_protocol_version: TLSProtocolVersion,
) -> ssl.TLSVersion:
    """Convert a TLS protocol version identifier to its ssl.TLSVersion equivalent.

    Parameters:
        tls_protocol_version: The TLS protocol version identifier.

    Returns:
        The corresponding ssl.TLSVersion value.

    Raises:
        KeyError: If the protocol version is not recognized.
    """
    return _TLS_VERSION_MAP[tls_protocol_version]


def resolve_min_tls_version(
    specified_version: TLSProtocolVersion | None,
    profile: TLSProfiles,
) -> TLSProtocolVersion:
    """Determine the minimum TLS version from explicit config or profile default.

    If a version is explicitly specified, it takes precedence. Otherwise the
    profile's default minimum version is used. For Custom profiles without an
    explicit version, TLS 1.2 is used as a safe default.

    Parameters:
        specified_version: Explicitly configured TLS version, or None.
        profile: The TLS profile type.

    Returns:
        The resolved minimum TLS protocol version.
    """
    if specified_version is not None:
        return specified_version
    return MIN_TLS_VERSIONS.get(profile, TLSProtocolVersion.VERSION_TLS_12)


def ciphers_from_list(ciphers: list[str] | tuple[str, ...]) -> str:
    """Join a sequence of cipher names into an OpenSSL cipher string.

    Parameters:
        ciphers: Sequence of cipher suite names.

    Returns:
        Colon-separated cipher string suitable for ssl.SSLContext.set_ciphers().
    """
    return ":".join(ciphers)


def ciphers_for_profile(profile: TLSProfiles) -> tuple[str, ...] | None:
    """Retrieve the cipher suite tuple for a predefined TLS profile.

    Parameters:
        profile: The TLS profile type.

    Returns:
        Tuple of cipher names, or None for Custom profiles.
    """
    return TLS_CIPHERS.get(profile)


def resolve_ciphers(
    custom_ciphers: list[str] | None,
    profile: TLSProfiles,
) -> str | None:
    """Determine the cipher string from explicit config or profile default.

    Custom ciphers take precedence over profile defaults. Returns None only
    for Custom profiles with no explicit cipher list.

    Parameters:
        custom_ciphers: Explicitly configured cipher list, or None.
        profile: The TLS profile type.

    Returns:
        Colon-separated cipher string, or None if no ciphers are configured.
    """
    if custom_ciphers is not None:
        return ciphers_from_list(custom_ciphers)
    profile_ciphers = ciphers_for_profile(profile)
    if profile_ciphers is not None:
        return ciphers_from_list(profile_ciphers)
    return None


def filter_tls12_ciphers(cipher_string: str) -> str | None:
    """Filter out TLS 1.3 ciphers from a cipher string.

    TLS 1.3 ciphers (prefixed with 'TLS_') are automatically negotiated by
    OpenSSL and cannot be set via ssl.SSLContext.set_ciphers(). This function
    removes them, returning only TLS 1.2 and below ciphers.

    Parameters:
        cipher_string: Colon-separated cipher string.

    Returns:
        Filtered cipher string with only TLS 1.2 ciphers, or None if all
        ciphers were TLS 1.3.
    """
    tls12_ciphers = [
        c for c in cipher_string.split(":") if not c.startswith(_TLS_13_CIPHER_PREFIX)
    ]
    return ":".join(tls12_ciphers) if tls12_ciphers else None
