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
        * [Exceptions and CA trust](#exceptions-and-ca-trust)
    * [Deployment surfaces](#deployment-surfaces)
    * [Classical algorithm dependencies](#classical-algorithm-dependencies)
    * [Focus-area findings](#focus-area-findings)
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

Versions are pinned from `uv.lock` (as off commit 4d2db67cab20f8ae4ce9e88847f7f0d111cad7b3).

| Package                                  | Version      | Why it matters                 | Notes                               |
|------------------------------------------|--------------|--------------------------------|-------------------------------------|
| `aiohttp`                                | 3.14.5       | HTTPS client/server            | stdlib `ssl` path unless overridden |
| `asyncpg`                                | 0.32.0       | PostgreSQL client              | TLS via libpq/OpenSSL               |
| `authlib`                                | 1.9.5        | OAuth/OIDC/JWT helpers         | protocol crypto only                |
| `azure-core`                             | 1.41.0       | Azure HTTP transport           | HTTPS path                          |
| `azure-identity`                         | 1.27.0       | Azure auth/token flows         | auth crypto only                    |
| `boto3`                                  | 1.44.0       | AWS API client                 | HTTPS path                          |
| `botocore`                               | 1.44.0       | AWS signing + transport        | classical signing + HTTPS           |
| `cffi`                                   | 2.1.1        | crypto FFI support             | dependency enabler                  |
| `cryptography`                           | 50.0.2       | X.509 / asymmetric crypto      | OpenSSL-backed; transitive-only (not imported in `src/`) |
| `datasets`                               | 5.2.0        | network transport/checksums    | HTTPS path                          |
| `dnspython`                              | 2.9.2        | DNS/DNSSEC-capable library     | crypto-adjacent                     |
| `fastapi`                                | 0.162.4      | web framework                  | not TLS itself                      |
| `google-auth`                            | 2.62.2       | auth/signing                   | classical crypto                    |
| `google-api-core`                        | 2.44.0       | Google API transport support   | HTTPS path                          |
| `google-cloud-*`                         | (see below)  | cloud clients                  | HTTPS path; per-package versions in crypto-adjacent table |
| `grpcio`                                 | 1.85.1       | gRPC transport                 | may negotiate TLS                   |
| `httpcore`                               | 1.0.9        | HTTP transport core            | underlying TLS path                 |
| `httpx`                                  | 0.28.1       | HTTP/HTTPS client              | stdlib `ssl` path                   |
| `httpx-sse`                              | 0.4.3        | SSE over HTTP                  | inherits HTTPX TLS                  |
| `joserfc`                                | 1.8.0        | JWS/JWE/JWK/JWKS               | classical crypto                    |
| `kubernetes`                             | 36.0.3       | Kubernetes API client          | HTTPS path                          |
| `msal`                                   | 1.39.0       | OAuth/OpenID client            | auth crypto                         |
| `msal-extensions`                        | 1.3.1        | auth helpers                   | auth-adjacent                       |
| `oauthlib`                               | 4.0.1        | OAuth helpers                  | auth crypto                         |
| `openai`                                 | 3.49.0       | API client                     | HTTPS path                          |
| `opentelemetry-exporter-otlp`            | 1.45.2       | telemetry export               | HTTP or gRPC TLS path               |
| `opentelemetry-exporter-otlp-proto-grpc` | 1.45.2       | OTLP/gRPC export               | TLS via gRPC                        |
| `opentelemetry-exporter-otlp-proto-http` | 1.45.2       | OTLP/HTTP export               | TLS via HTTP                        |
| `psycopg2-binary`                        | 2.9.13       | PostgreSQL client              | TLS via libpq/OpenSSL               |
| `pyasn1`                                 | 0.6.5        | ASN.1 parsing                  | cert/auth parsing; transitive-only  |
| `pyasn1-modules`                         | 0.4.2        | ASN.1 modules                  | cert/auth parsing; transitive-only  |
| `pyjwt`                                  | 2.15.1       | JWT signing/verification       | classical crypto; transitive-only (JWT handled via `authlib`) |
| `requests`                               | 2.34.2       | HTTPS client                   | urllib3/ssl path                    |
| `requests-oauthlib`                      | 2.0.0        | OAuth over requests            | auth crypto; transitive-only        |
| `s3transfer`                             | 0.19.3       | AWS transfer helper            | HTTPS path                          |
| `sentry-sdk`                             | 2.74.0       | telemetry transport            | HTTPS path                          |
| `sqlalchemy`                             | 2.1.8        | DB abstraction                 | indirect TLS via drivers            |
| `starlette`                              | 1.10.0       | ASGI framework                 | not TLS itself                      |
| `truststore`                             | 0.10.5       | system trust store integration | system-rooted trust                 |
| `urllib3`                                | 2.8.0        | HTTP/HTTPS transport           | stdlib `ssl` path                   |
| `uvicorn`                                | 0.54.0       | ASGI server                    | TLS termination via cert/key        |
| `websocket-client`                       | 1.9.2        | WSS client                     | stdlib `ssl` path                   |
| `websockets`                             | 17.4         | WS/WSS client/server           | stdlib `ssl` path                   |

### Vendored

| Package   | Version      | Why it matters   | Notes                |
|-----------|--------------|------------------|----------------------|
| `certifi` | 2026.10.23   | bundled CA roots | vendored trust store — **the only vendored CA bundle in the dependency set** |

### Crypto-adjacent / inspect if used

| Package                               | Version       | Why it matters            | Notes              |
|---------------------------------------|---------------|---------------------------|--------------------|
| `bandit`                              | 1.9.4         | security linting          | not runtime crypto |
| `google-resumable-media`              | 2.11.0        | upload/download transport | HTTPS path         |
| `google-cloud-storage`                | 3.17.1        | API transport             | HTTPS path         |
| `google-cloud-aiplatform`             | 2.8.0         | API transport             | HTTPS path         |
| `google-cloud-bigquery`               | 3.47.0        | API transport             | HTTPS path         |
| `google-cloud-core`                   | 2.8.0         | API transport support     | HTTPS path         |
| `google-cloud-resource-manager`       | 1.19.0        | API transport             | HTTPS path         |
| `google-crc32c`                       | 1.9.0         | checksum                  | integrity, not TLS |
| `grpcio-status`                       | 1.85.1        | gRPC support              | transport-adjacent |
| `h2`, `hpack`, `hyperframe`           | not locked    | HTTP/2 stack              | **not present in `uv.lock`** — HTTP/2 stack is not a dependency |
| `httpx2`, `httpcore2`                 | 2.16.0        | alternate transport stack | inspect usage      |
| `httpx2-jsfetch`                      | 1.0           | alternate transport stack | inspect usage      |
| `fastmcp-slim`                        | 3.4.11        | alternate transport stack | inspect usage      |
| `opentelemetry-instrumentation-httpx` | 0.66b2        | transport instrumentation | not crypto itself  |
| `opentelemetry-util-http`             | 0.66b2        | helpers                   | not crypto itself  |
| `requests-toolbelt`                   | 1.0.0         | requests helpers          | not crypto itself  |
| `sse-starlette`                       | 3.7.0         | streaming transport       | TLS via ASGI stack |
| `trustme`                             | 1.2.1         | test CA/cert generation   | test-only crypto   |

## TLS/HTTPS paths in `src/`

### Outbound HTTPS / TLS clients

Exact `file:line` references verified against the tree as off commit 4d2db67cab20f8ae4ce9e88847f7f0d111cad7b3.

| File:line                                                                      | Path                         | Mechanism                                                   | Classification         | Notes                                              |
|--------------------------------------------------------------------------------|------------------------------|-------------------------------------------------------------|------------------------|----------------------------------------------------|
| `src/providers/inference/watsonx/auth.py:94`                                   | IBM IAM token request        | `httpx.AsyncClient()` (default verify) → `IAM_TOKEN_URL` (`auth.py:16`) | system-policy-governed | HTTPS auth flow; certifi trust                     |
| `src/providers/inference/watsonx/pai_provider.py:63`                           | outbound to Watsonx ML       | `httpx.AsyncClient(auth=WatsonxIAMAuth(...))` → `AsyncOpenAI` | system-policy-governed | default verify=True                                |
| `src/pydantic_ai_lightspeed/ogx/_provider.py:140`                             | outbound OGX (service mode)  | `create_async_http_client()` → `AsyncOpenAI(base_url=...)`  | system-policy-governed | default HTTPX/certifi TLS                           |
| `src/pydantic_ai_lightspeed/ogx/_provider.py:122-124`                         | in-process OGX library        | `httpx.AsyncClient(transport=..., base_url="http://ogx-library")` | N/A (loopback)          | **plaintext loopback transport, no network TLS**   |
| `src/pydantic_ai_lightspeed/ogx/_transport.py:117`                            | OGX server transport wrapper | `httpx.AsyncClient(transport=OgxServerTransport, ...)`      | system-policy-governed | inherits parent client TLS                         |
| `src/client/ogx.py:155`                                                        | OGX request client           | `AsyncOgxClient(base_url=..., api_key=..., timeout=...)`    | system-policy-governed | underlying client default verify=True              |
| `src/pydantic_ai_lightspeed/capabilities/granite_guardian/_capability.py:395` | Granite Guardian inference   | `httpx.AsyncClient(verify=self.config.verify_ssl, ...)`     | system-policy-governed | **configurable verify** — see Exceptions           |
| `src/observability/splunk.py:74`                                             | Splunk HEC telemetry         | `aiohttp.TCPConnector(ssl=splunk_config.verify_ssl)`       | system-policy-governed | **configurable verify** — see Exceptions           |
| `src/observability/sentry.py:106`                                            | Sentry ingest telemetry      | `sentry_sdk.init(ca_certs=ca_certs)` (`sentry.py:85-106`)  | system-policy-governed | optional custom CA via env — see Exceptions         |
| `src/authentication/jwk_token.py:52`                                         | JWKS retrieval               | `aiohttp.ClientSession()` (default) → `session.get` (`:54`) | system-policy-governed | HTTPS fetch of keys; system trust                  |
| `src/utils/mcp/mcp_tools.py:72`                                              | MCP streamable HTTP          | `httpx.AsyncClient(...)` → `streamable_http_client`        | system-policy-governed | default verify=True                                |
| `src/utils/mcp/mcp_tools.py:89`                                              | MCP SSE fallback             | `sse_client(endpoint, headers=...)` (MCP SDK default httpx) | system-policy-governed | SDK-default TLS context                            |
| `src/utils/mcp/mcp_oauth_probe.py:110`                                       | MCP OAuth 401 probe          | `aiohttp.ClientSession(timeout=...)` (default)             | system-policy-governed | default verify=True                                |
| `src/authentication/k8s.py:127-138`                                          | Kubernetes API requests      | `k8s_config.verify_ssl`, `ssl_ca_cert` → `ApiClient`       | system-policy-governed | **configurable verify + custom CA** — see Exceptions |

### Database TLS paths

| File:line                                    | Path                  | Mechanism                                              | Classification         | Notes                                                        |
|----------------------------------------------|-----------------------|-------------------------------------------------------|------------------------|--------------------------------------------------------------|
| `src/app/database.py:134,143-144`            | Primary Postgres DB   | `?sslmode={ssl_mode}&gssencmode=...`; `sslrootcert` (if set) | system-policy-governed | SQLAlchemy/psycopg2; custom CA honored                       |
| `src/cache/postgres_cache.py:216-217`        | Postgres conv. cache  | `psycopg2.connect(sslmode=..., sslrootcert=...)`      | system-policy-governed | custom CA bundle honored                                     |
| `src/quota/connect_pg.py:44-45`              | Postgres quota store  | `psycopg2.connect(sslmode=...)`; `sslrootcert` **commented out** | system-policy-governed | **custom CA silently ignored here** — see Exceptions         |
| `src/telemetry/configuration_snapshot.py`    | config surface only   | `database.postgres.ssl_mode` etc.                     | system-policy-governed | records TLS settings (masking/telemetry)                     |

Default `ssl_mode` is `"prefer"` (`src/constants.py:194`): TLS is **opportunistic and
unverified** — `prefer`/`allow` negotiate TLS when available but do **not** validate the
server certificate; only `verify-ca`/`verify-full` check the CA.

### Inbound TLS / termination paths

| File:line                                    | Path                          | Mechanism                                                        | Classification         | Notes                                                       |
|----------------------------------------------|-------------------------------|------------------------------------------------------------------|------------------------|-------------------------------------------------------------|
| `src/runners/uvicorn.py:44-46`               | inbound HTTPS listener        | `uvicorn.run(ssl_keyfile=..., ssl_certfile=..., ssl_keyfile_password=...)` | system-policy-governed | **only** cert/key/password — no TLS min-version, cipher, or curve/group pinning; falls back to plain HTTP when unset |
| `src/telemetry/configuration_snapshot.py`    | server TLS config surface     | `server.tls_certfile`, `server.tls_keyfile`, `server.tls_cafile` | system-policy-governed | config-only evidence of termination (masking/telemetry)     |
| `src/constants.py:384`                        | Sentry CA bundle env var      | `SENTRY_CA_CERTS_ENV_VAR = "SENTRY_CA_CERTS"`                    | system-policy-governed | path-based trust **override**, not vendored material         |
| `src/observability/sentry.py:85-106`          | Sentry CA bundle config       | `ca_certs` from env, else system trust                          | system-policy-governed | custom path overrides system CA; not a bundled trust store   |

### Exceptions and CA trust

**Verification-disable switches — all default to secure (verification ON):**

| Switch | Call site | Config field | Default |
|--------|-----------|--------------|---------|
| Granite Guardian verify | `_capability.py:395` (`verify=self.config.verify_ssl`) | `GraniteGuardianConfig.verify_ssl` (`src/models/config.py:3638`, `bool \| str`) | `True` (a `str` value = custom CA bundle path) |
| Splunk HEC verify | `splunk.py:74` (`ssl=splunk_config.verify_ssl`) | `SplunkConfiguration.verify_ssl` (`src/models/config.py:1285`, `bool`) | `True` |
| Kubernetes verify | `k8s.py:127-128` (`verify_ssl = not skip_tls_verification`) | `AuthenticationConfiguration.skip_tls_verification` (`src/models/config.py:1769`, `bool`) | `False` (i.e. verify ON) |

Each is an operator-controlled escape hatch for self-signed/internal
endpoints; all ship secure-by-default. Any deployment setting one insecurely is the
exception that needs sign-off.

**Custom / bundled CA usage (trust override, not disable):**

- Kubernetes `ssl_ca_cert` — `k8s.py:130-135`, field `src/models/config.py:1783` (`k8s_ca_cert_path`).
- Postgres `sslrootcert` — `app/database.py:143-144` and `cache/postgres_cache.py:217`, field `src/models/config.py:255` (`ca_cert_path`).
- Sentry `ca_certs` — `sentry.py:85-106` via env `SENTRY_CA_CERTS` (`constants.py:384`).

**No certificate pinning** anywhere in `src/`, and **no `verify=False` literal** — the
only ways to disable verification are the three config switches above.

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

Note: of the above, `cryptography`, `pyjwt`, `pyasn1(-modules)`, `oauthlib`,
`requests-oauthlib` are **transitive-only** — never imported directly in `src/` (see
Focus-area findings). They are pulled in by `authlib`, `msal`, `google-auth`, and `boto*`.

## Focus-area findings

Resolves the review items listed under [Focus areas](#focus-areas) using the verified
`src/` audit (2026-11-11).

* **JWT libraries.** Token verification runs through `authlib.jose`
  (`src/authentication/jwk_token.py:241`, `jwt.decode(...)`). `pyjwt` is present only
  transitively and is **not** used by LCS code. The accepted signature algorithm is
  **not** a hardcoded string and there is **no `algorithms=` allowlist** — the accepted
  `alg` is driven by the JWK set, with the resolver enforcing `key.alg == header.alg`
  (`jwk_token.py:107-143`), which mitigates algorithm-confusion attacks. Key selection is
  abstracted into `key_resolver_func`, but algorithm *policy* is inline rather than
  configuration-driven. JWKS is re-fetched over HTTPS at runtime
  (`jwk_token.py:52-54`), so rotating/expanding key sets — and larger PQ signatures —
  are consumed without code change. **Crypto-agility gap:** there is no central place to
  restrict or select signature-algorithm families; a PQ-signature migration would be
  driven by whatever the JWKS publisher advertises.

* **`cryptography` library.** No direct `import cryptography` / `from cryptography ...`
  anywhere in `src/` — it is purely transitive. There is **no direct RSA / ECDSA /
  Ed25519 / X25519 / ECDH usage in application code**, so there is nothing to wrap behind
  an interface for key exchange or signatures today.

* **In-code cipher / group / curve selection.** **None.** No `SSLContext`,
  `set_ciphers`, `set_ecdh_curve`, or `ssl.TLSVersion` anywhere in `src/`. Every TLS
  surface is a config pass-through (cert/key paths, `sslmode`/`sslrootcert`, verify
  booleans, CA paths). **This is the core crypto-agility finding:** key-exchange group
  negotiation (including ML-KEM / hybrid) is entirely delegated to OpenSSL and the system
  crypto policy, so PQC key-exchange readiness lights up at the platform layer with no
  change to this repo — and conversely the app offers no hook to enforce PQ groups.

* **OAuth/OIDC client libs.** `oauthlib` / `requests-oauthlib` / `msal` are transitive
  only; the active OIDC path is the JWKS flow above, which already consumes changing key
  sets at runtime.

* **Reverse proxy / ingress TLS stack.** Out of repo — a **platform / deployment-owned**
  surface (ingress controller, load balancer, service mesh). PQC/hybrid-TLS capability
  there is a platform concern, not an LCS code concern.
  
* **Database drivers.** **N/A for at-rest crypto** — LCS stores no application-encrypted
  ciphertext, versioned envelopes, or key metadata. Postgres usage is transport TLS only
  (see Database TLS paths), so driver ciphertext-size / re-encryption concerns do not apply.

## Gaps

- **OpenSSL / system crypto-policy build capability** — whether the shipped build
  negotiates ML-KEM / hybrid groups. Owner: platform.
- **Peer PQ support** — LLM backends, Postgres, Splunk HEC, JWKS/OIDC, Kubernetes API.
  Owner: respective service owners.
- **Reverse-proxy / ingress TLS stack** — PQC/hybrid capability at the termination layer.
  Owner: platform/deployment.

These are platform/peer-owned, outside this repo's code

# Links

- [NIST PQC overview](https://csrc.nist.gov/projects/post-quantum-cryptography)
- [NIST migration to PQC](https://www.nccoe.nist.gov/applied-cryptography/migration-to-pqc)
- [IETF migration guidance draft](https://www.ietf.org/archive/id/draft-kwiatkowski-pquip-pqc-migration-00.html)
- [RFC 9954, hybrid key exchange in TLS 1.3](https://www.rfc-editor.org/info/rfc9954/)

