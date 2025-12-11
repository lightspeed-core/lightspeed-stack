# TLS Security Profile Configuration

This document describes how to configure and test the TLS security profile for outgoing connections to the Llama Stack provider.

## Overview

The TLS security profile allows you to enforce specific TLS security settings for connections from Lightspeed Stack to the Llama Stack server. This includes:

- **Profile Type**: Predefined security profiles (OldType, IntermediateType, ModernType, Custom)
- **Minimum TLS Version**: Enforce minimum TLS protocol version (TLS 1.0 - 1.3)
- **Cipher Suites**: Specify allowed cipher suites
- **CA Certificate**: Custom CA certificate for server verification
- **Skip Verification**: Option to skip TLS verification (testing only)

## Configuration

Add the `tls_security_profile` section under `llama_stack` in your configuration file:

```yaml
llama_stack:
  url: https://llama-stack-server:8321
  use_as_library_client: false
  tls_security_profile:
    type: ModernType
    minTLSVersion: VersionTLS13
    caCertPath: /path/to/ca-certificate.crt
```

### Configuration Options

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Profile type: `OldType`, `IntermediateType`, `ModernType`, or `Custom` |
| `minTLSVersion` | string | Minimum TLS version: `VersionTLS10`, `VersionTLS11`, `VersionTLS12`, `VersionTLS13` |
| `ciphers` | list[string] | List of allowed cipher suites (optional, uses profile defaults) |
| `caCertPath` | string | Path to CA certificate file for server verification |
| `skipTLSVerification` | boolean | Skip TLS certificate verification (default: false, **testing only**) |

### Profile Types

| Profile | Min TLS Version | Description |
|---------|-----------------|-------------|
| `OldType` | TLS 1.0 | Legacy compatibility, wide cipher support |
| `IntermediateType` | TLS 1.2 | Balanced security and compatibility |
| `ModernType` | TLS 1.3 | Maximum security, TLS 1.3 only |
| `Custom` | Configurable | User-defined settings |
