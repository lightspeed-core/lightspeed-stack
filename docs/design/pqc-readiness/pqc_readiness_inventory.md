# PQC Readiness: Cryptographic Inventory

<!-- vim-markdown-toc GFM -->

* [Introduction](#introduction)
    * [PQC families](#pqc-families)
    * [Why it matters](#why-it-matters)
* [Practical strategy](#practical-strategy)
    * [PQC in Python ecosystem](#pqc-in-python-ecosystem)
    * [Strategy](#strategy)
* [Dependencies check](#dependencies-check)
    * [Focus areas](#focus-areas)
    * [Scope and checklist](#scope-and-checklist)
        * [All uv.lock packages](#all-uvlock-packages)
        * [Direct and transitive crypto-relevant dependencies](#direct-and-transitive-crypto-relevant-dependencies)
        * [Every TLS/HTTPS origin and termination path in src/](#every-tlshttps-origin-and-termination-path-in-src)
        * [Deployment surfaces that carry TLS](#deployment-surfaces-that-carry-tls)
        * [Classical-algorithm dependencies and gaps](#classical-algorithm-dependencies-and-gaps)
    * [Package inventory](#package-inventory)
        * [System-policy-governed](#system-policy-governed)
        * [Vendored](#vendored)
        * [Crypto-adjacent / inspect if used](#crypto-adjacent--inspect-if-used)
    * [TLS/HTTPS paths in `src/`](#tlshttps-paths-in-src)
        * [Outbound HTTPS / TLS clients](#outbound-https--tls-clients)
        * [Database TLS paths](#database-tls-paths)
        * [Inbound TLS / termination paths](#inbound-tls--termination-paths)
    * [Deployment surfaces](#deployment-surfaces)
    * [Classical algorithm dependencies](#classical-algorithm-dependencies)
    * [Gaps](#gaps)
    * [Acceptance](#acceptance)
* [Links](#links)

<!-- vim-markdown-toc -->

# Introduction

Post-quantum cryptography (PQC) is the field of designing cryptographic
algorithms that are intended to stay secure even if attackers have a powerful
quantum computer. It exists because the long-term security assumptions behind
much of today’s internet security may not hold forever.

Today’s widely used public-key systems, like RSA and elliptic-curve
cryptography, rely on math problems that are hard for classical computers but
would become much easier for a sufficiently large quantum computer. PQC aims to
replace those vulnerable systems with new ones based on different hard
problems, so encrypted data, digital signatures, and secure key exchange can
keep working in the future.

This transition matters most for anything that depends on public-key
cryptography. That includes TLS connections, software updates, signed
documents, identity systems, and certificates. If those systems are built on
algorithms that quantum computers can eventually break, then data protected
today could be exposed later.

The main idea is not that quantum computers break all cryptography. Symmetric
ciphers and hash functions are less affected; they mainly need larger security
margins, such as longer keys. The biggest concern is public-key cryptography,
because quantum algorithms could undermine the math behind key exchange and
signatures.

PQC is therefore less about inventing a completely new kind of security and
more about swapping out the weak links in current systems before they become a
real problem. In practice, that means planning migrations early, testing new
algorithms, and making software flexible enough to adopt them without major
redesign.



## PQC families

Common PQC families include:

* Lattice-based cryptography: currently the leading approach in many standards efforts.
* Code-based cryptography: based on error-correcting codes.
* Hash-based signatures: strong for signing, though often less flexible.
* Multivariate cryptography: based on systems of polynomial equations.
* Isogeny-based cryptography: once promising, but many schemes were broken, so it’s less central now.

## Why it matters

* Data encrypted now may be stored and decrypted later, once quantum computers exist.
* Software, hardware, certificates, and protocols need time to migrate.
* The transition is hard because cryptography is embedded everywhere: browsers, VPNs, messaging apps, devices, and infrastructure.

# Practical strategy

* A practical strategy is often “crypto-agility,” meaning systems are built so
* cryptographic algorithms can be swapped out without redesigning everything.

## PQC in Python ecosystem

To make a Lightspeed Core, which is a larger Python, project PQC-ready, it is
essential to focus on making crypto replaceable, not on “adding quantum-safe
crypto everywhere” all at once.

## Strategy

1. Inventory all cryptography use
    * TLS/API connections
    * JWTs, cookies, session signing
    * Password hashing
    * File/database encryption
    * Message signatures
    * Key exchange
    * Any third-party SDKs that do crypto internally

1. Separate crypto behind interfaces
    * Don’t scatter RSA/ECDSA/AES calls throughout the codebase
    * Wrap them in one module/service so algorithms can be swapped later

1. Use crypto-agile design
    * Store algorithm names with keys/certificates
    * Make key formats versioned
    * Avoid hardcoding one public-key algorithm anywhere

1. Prepare for hybrid migration
    * For key exchange, plan for hybrid schemes (classical + PQC) where supported
    * This is the safest transition path for internet protocols

1. Check your dependencies
    * Update libraries that handle TLS, SSH, signing, or certificate parsing
    * Make sure your stack can accept new algorithms when they appear

1. Use modern symmetric crypto already
    * AES-256 and SHA-384/512 are fine choices
    * PQC mostly changes public-key crypto, not symmetric encryption

1. Build migration hooks
    * Config flags for algorithm selection
    * Key rotation support
    * Backward compatibility for old ciphertext/signatures
    * Versioned envelopes for encrypted data

1. Plan for signatures
    * If your app verifies long-lived signatures, design for larger PQC signatures and certificates
    * Size/performance changes can be significant

1. Test interoperability
    * Ensure your protocol/message formats can handle larger keys, signatures, and certificates.

1. Track standards

1. Prefer standardized PQC algorithms from recognized standards bodies instead of experimental ones.



# Dependencies check

Lightspeed Core is built on FastAPI, which means it runs as a modern Python web
application and depends on several surrounding systems to function correctly.
It does not operate in isolation. Instead, it handles incoming requests,
processes application logic, reads from and writes to databases, and exchanges
data with other internal or external services.

Because of that, the security and reliability of the platform are shaped not
just by the FastAPI code itself, but also by the components it connects to.
Database access, service-to-service communication, authentication, encryption,
and dependency management all become important parts of the system’s overall
posture.

This means the main focus should be on the application boundaries: how data
enters the system, how it is stored, how it is transmitted, and how it is
shared with other services. Those are the areas where bugs, misconfigurations,
or weak cryptographic choices are most likely to create risk.

It also means that any upgrade or migration effort should be evaluated end to
end. A change in one layer, such as a database driver, a token format, or a TLS
configuration, can affect the whole service. For that reason, the most
effective approach is to review the full request path rather than treating the
application, database, and integrations as separate concerns.

In practice, the areas to focus on include API authentication, database
encryption, secrets management, transport security, dependency auditing, and
secure integration with downstream services. Those are the parts of the system
that will determine whether Lightspeed Core stays secure, maintainable, and
ready for future changes.

## Focus areas

* JWT libraries
    - Check whether the library supports multiple signing algorithms, key rotation, JWK/JWKS,
      and larger signatures. We need to know if we can keep verifying old tokens while issuing
      new ones with different algorithms later.
* cryptography
    - this is the core Python crypto library. We have to review whether LCore code relies on
      only RSA/ECDSA primitives, where the dependency is used, and whether its wrapped it
      behind our own interface so we can swap algorithms without touching the app logic.
* OAuth/OIDC client libs
    - these handle login flows, token validation, and public key discovery. We have to check if
      they can consume changing key sets, support future algorithm updates, and handle larger
      ID/access token payloads or signatures. 
* reverse proxy / ingress TLS stack
    - this is the layer terminating HTTPS before LCore (FastAPI). Check whether the proxy/load
      balancer can support future PQC-capable TLS settings or hybrid modes, and whether
      certificate/key sizes or handshake limits could become a problem.
* database drivers
	- applicable only when LCore encrypt data before storing it. In this case
      it is needed to review whether the driver, ORM, or schema can handle larger
      ciphertexts, versioned envelopes, and key metadata. Also check whether your app
      can re-encrypt rows over time.



## Scope and checklist

This inventory covers:
- all `uv.lock` packages
- direct and transitive crypto-relevant dependencies
- every TLS/HTTPS origin and termination path in `src/`
- deployment surfaces that carry TLS
- classical-algorithm dependencies and gaps

### All uv.lock packages

Review every locked dependency, not just the ones you import directly. A
transitive package may be the one handling hashing, signatures, certificates,
HTTP transport, or token parsing.

### Direct and transitive crypto-relevant dependencies

Include anything that touches crypto even indirectly: auth libraries, HTTP
clients, SDKs, certificate tools, ORM plugins, and cloud integrations. The goal
is to catch hidden crypto assumptions in packages your code depends on.

### Every TLS/HTTPS origin and termination path in src/

Find where requests start or end over HTTPS: API clients, callback handlers,
webhook consumers, internal service calls, and any code that configures
certificates, URLs, or trust roots. We need to have a map of every place TLS is
used or assumed.

### Deployment surfaces that carry TLS

Check infrastructure outside the code too: reverse proxies, ingress
controllers, load balancers, API gateways, service meshes, sidecars, and
container entrypoints. These are often where TLS is actually terminated or
re-encrypted.

### Classical-algorithm dependencies and gaps

Identify where your system still depends on RSA, ECDSA, Ed25519, or other
current algorithms, and where PQC support is missing. This shows what must be
abstracted, replaced, or kept temporarily for backward compatibility. 



## Package inventory

### System-policy-governed

| Package                                  | Why it matters                 | Notes                               |
|------------------------------------------|--------------------------------|-------------------------------------|
| `aiohttp`                                | HTTPS client/server            | stdlib `ssl` path unless overridden |
| `asyncpg`                                | PostgreSQL client              | TLS via libpq/OpenSSL               |
| `authlib`                                | OAuth/OIDC/JWT helpers         | protocol crypto only                |
| `azure-core`                             | Azure HTTP transport           | HTTPS path                          |
| `azure-identity`                         | Azure auth/token flows         | auth crypto only                    |
| `boto3`                                  | AWS API client                 | HTTPS path                          |
| `botocore`                               | AWS signing + transport        | classical signing + HTTPS           |
| `cffi`                                   | crypto FFI support             | dependency enabler                  |
| `cryptography`                           | X.509 / asymmetric crypto      | OpenSSL-backed                      |
| `datasets`                               | network transport/checksums    | HTTPS path                          |
| `dnspython`                              | DNS/DNSSEC-capable library     | crypto-adjacent                     |
| `fastapi`                                | web framework                  | not TLS itself                      |
| `google-auth`                            | auth/signing                   | classical crypto                    |
| `google-api-core`                        | Google API transport support   | HTTPS path                          |
| `google-cloud-*`                         | cloud clients                  | HTTPS path                          |
| `grpcio`                                 | gRPC transport                 | may negotiate TLS                   |
| `httpcore`                               | HTTP transport core            | underlying TLS path                 |
| `httpx`                                  | HTTP/HTTPS client              | stdlib `ssl` path                   |
| `httpx-sse`                              | SSE over HTTP                  | inherits HTTPX TLS                  |
| `joserfc`                                | JWS/JWE/JWK/JWKS               | classical crypto                    |
| `kubernetes`                             | Kubernetes API client          | HTTPS path                          |
| `msal`                                   | OAuth/OpenID client            | auth crypto                         |
| `msal-extensions`                        | auth helpers                   | auth-adjacent                       |
| `oauthlib`                               | OAuth helpers                  | auth crypto                         |
| `openai`                                 | API client                     | HTTPS path                          |
| `opentelemetry-exporter-otlp`            | telemetry export               | HTTP or gRPC TLS path               |
| `opentelemetry-exporter-otlp-proto-grpc` | OTLP/gRPC export               | TLS via gRPC                        |
| `opentelemetry-exporter-otlp-proto-http` | OTLP/HTTP export               | TLS via HTTP                        |
| `psycopg2-binary`                        | PostgreSQL client              | TLS via libpq/OpenSSL               |
| `pyasn1`                                 | ASN.1 parsing                  | cert/auth parsing                   |
| `pyasn1-modules`                         | ASN.1 modules                  | cert/auth parsing                   |
| `pyjwt`                                  | JWT signing/verification       | classical crypto                    |
| `requests`                               | HTTPS client                   | urllib3/ssl path                    |
| `requests-oauthlib`                      | OAuth over requests            | auth crypto                         |
| `s3transfer`                             | AWS transfer helper            | HTTPS path                          |
| `sentry-sdk`                             | telemetry transport            | HTTPS path                          |
| `sqlalchemy`                             | DB abstraction                 | indirect TLS via drivers            |
| `starlette`                              | ASGI framework                 | not TLS itself                      |
| `truststore`                             | system trust store integration | system-rooted trust                 |
| `urllib3`                                | HTTP/HTTPS transport           | stdlib `ssl` path                   |
| `uvicorn`                                | ASGI server                    | TLS termination via cert/key        |
| `websocket-client`                       | WSS client                     | stdlib `ssl` path                   |
| `websockets`                             | WS/WSS client/server           | stdlib `ssl` path                   |

### Vendored

| Package   | Why it matters   | Notes                |
|-----------|------------------|----------------------|
| `certifi` | bundled CA roots | vendored trust store |

### Crypto-adjacent / inspect if used

| Package                                                 | Why it matters            | Notes              |
|---------------------------------------------------------|---------------------------|--------------------|
| `bandit`                                                | security linting          | not runtime crypto |
| `google-resumable-media`                                | upload/download transport | HTTPS path         |
| `google-cloud-storage`                                  | API transport             | HTTPS path         |
| `google-cloud-aiplatform`                               | API transport             | HTTPS path         |
| `google-cloud-bigquery`                                 | API transport             | HTTPS path         |
| `google-cloud-core`                                     | API transport support     | HTTPS path         |
| `google-cloud-resource-manager`                         | API transport             | HTTPS path         |
| `google-crc32c`                                         | checksum                  | integrity, not TLS |
| `grpcio-status`                                         | gRPC support              | transport-adjacent |
| `h2`, `hpack`, `hyperframe`                             | HTTP/2 stack              | TLS-adjacent       |
| `httpx2`, `httpcore2`, `httpx2-jsfetch`, `fastmcp-slim` | alternate transport stack | inspect usage      |
| `opentelemetry-instrumentation-httpx`                   | transport instrumentation | not crypto itself  |
| `opentelemetry-util-http`                               | helpers                   | not crypto itself  |
| `requests-toolbelt`                                     | requests helpers          | not crypto itself  |
| `sse-starlette`                                         | streaming transport       | TLS via ASGI stack |
| `trustme`                                               | test CA/cert generation   | test-only crypto   |

## TLS/HTTPS paths in `src/`

### Outbound HTTPS / TLS clients

| File                                                                      | Path                         | Mechanism                                | Classification         | Notes                                |
|---------------------------------------------------------------------------|------------------------------|------------------------------------------|------------------------|--------------------------------------|
| `src/providers/inference/watsonx/pai_provider.py`                         | outbound to Watsonx          | `httpx.AsyncClient(...)`                 | system-policy-governed | relies on HTTPX/stdlib TLS           |
| `src/providers/inference/watsonx/auth.py`                                 | token refresh / auth request | `httpx.AsyncClient()`                    | system-policy-governed | HTTPS auth flow                      |
| `src/pydantic_ai_lightspeed/ogx/_provider.py`                             | outbound OGX HTTP            | `httpx.AsyncClient(...)`                 | system-policy-governed | default HTTPX TLS                    |
| `src/pydantic_ai_lightspeed/capabilities/granite_guardian/_capability.py` | outbound HTTP                | `httpx.AsyncClient(verify=...)`          | system-policy-governed | explicit TLS verification toggle     |
| `src/observability/splunk.py`                                             | outbound telemetry           | `aiohttp.ClientSession(...)`             | system-policy-governed | `TCPConnector(ssl=...)` controls TLS |
| `src/observability/sentry.py`                                             | outbound telemetry           | Sentry SDK                               | system-policy-governed | CA bundle path supported             |
| `src/authentication/jwk_token.py`                                         | JWKS retrieval               | `aiohttp.ClientSession()`                | system-policy-governed | HTTPS fetch of keys                  |
| `src/utils/mcp/mcp_tools.py`                                              | MCP HTTP client              | `httpx.Timeout(...)` / HTTPX client path | system-policy-governed | inspect callsites for URL transport  |
| `src/client/ogx.py`                                                       | OGX request client           | HTTP request path                        | system-policy-governed | inspect implementation for transport |
| `src/authentication/k8s.py`                                               | Kubernetes API requests      | `k8s_config.verify_ssl`, `ssl_ca_cert`   | system-policy-governed | explicit CA and verify controls      |

### Database TLS paths

| File                                      | Path                  | Mechanism                         | Classification         | Notes                           |
|-------------------------------------------|-----------------------|-----------------------------------|------------------------|---------------------------------|
| `src/quota/connect_pg.py`                 | PostgreSQL connection | `sslmode=...`                     | system-policy-governed | TLS policy controlled by config |
| `src/cache/postgres_cache.py`             | PostgreSQL connection | `sslmode=...`, `sslrootcert=...`  | system-policy-governed | possible custom CA bundle       |
| `src/telemetry/configuration_snapshot.py` | config surface only   | `database.postgres.ssl_mode` etc. | system-policy-governed | records TLS settings            |

### Inbound TLS / termination paths

| File                                      | Path                          | Mechanism                                                        | Classification                     | Notes                               |
|-------------------------------------------|-------------------------------|------------------------------------------------------------------|------------------------------------|-------------------------------------|
| `src/telemetry/configuration_snapshot.py` | server TLS config surface     | `server.tls_cafile`, `server.tls_certfile`, `server.tls_keyfile` | system-policy-governed             | config-only evidence of termination |
| `src/constants.py`                        | Sentry CA bundle path env var | CA bundle path                                                   | vendored if file-bundled           | path-based trust override           |
| `src/observability/sentry.py`             | CA bundle config              | CA certificate bundle path                                       | vendored or system-policy-governed | depends on path source              |

## Deployment surfaces

| Surface                             | TLS role            | Classification         | Notes                       |
|-------------------------------------|---------------------|------------------------|-----------------------------|
| app API server                      | inbound termination | system-policy-governed | cert/key driven by config   |
| outbound inference providers        | outbound client     | system-policy-governed | HTTPX/aiohttp-based         |
| observability exporters             | outbound client     | system-policy-governed | Sentry/Splunk/OTLP          |
| PostgreSQL-backed services          | outbound DB TLS     | system-policy-governed | `sslmode` / CA cert         |
| Kubernetes-authenticated components | outbound client     | system-policy-governed | verify CA / skip TLS toggle |

## Classical algorithm dependencies

These packages/paths rely on classical algorithms:

- `cryptography`
- `pyjwt`
- `pyasn1`
- `pyasn1-modules`
- `authlib`
- `oauthlib`
- `joserfc`
- `msal`
- `google-auth`
- `botocore`
- `requests-oauthlib`
- TLS stacks using RSA/ECDSA/ECDH, SHA-256/SHA-384, HMAC, X.509, PKCS#7/PKCS#12

## Gaps

- `uv.lock` package names are confirmed, but version-level transitive audit still needs the full lock metadata.
- `certifi` is the only obvious vendored trust bundle.
- `src/` contains multiple TLS policy knobs, but file-level termination/origin lines should be finalized with exact line references.
- Any use of `verify=False`, bundled CA files, or pinned certificates should be treated as exceptions requiring explicit rationale.

## Acceptance

- Every crypto-relevant package in `uv.lock` is classified at package-name level.
- Vendored trust material is identified.
- TLS/HTTPS origin and termination paths are enumerated from `src/`.
- Classical algorithm dependencies are documented.

# Links

- [NIST PQC overview](https://csrc.nist.gov/projects/post-quantum-cryptography)
- [NIST migration to PQC](https://www.nccoe.nist.gov/applied-cryptography/migration-to-pqc)
- [IETF migration guidance draft](https://www.ietf.org/archive/id/draft-kwiatkowski-pquip-pqc-migration-00.html)
- [RFC 9954, hybrid key exchange in TLS 1.3](https://www.rfc-editor.org/info/rfc9954/)

