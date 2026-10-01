# Mock OTEL collector

A minimal OTLP/HTTP collector used by the OpenTelemetry E2E scenario
(`tests/e2e/features/opentelemetry.feature`) to verify that the Lightspeed Core
Stack delivers spans/events to a telemetry backend.

It is a stdlib-only `http.server` that buffers the raw OTLP export bodies in
memory and exposes a small control API so Behave steps can assert what was
received. See `server.py` for the full endpoint list.

## Endpoints

| Method & path        | Purpose                                                        |
| -------------------- | ------------------------------------------------------------- |
| `POST /v1/*`         | Receive an OTLP export (traces/logs/metrics); body buffered.  |
| `GET /received`      | Report the count of buffered exports.                         |
| `GET /received?contains=<text>` | Report whether `<text>` appears in any payload.   |
| `POST /reset`        | Clear the buffer (called at scenario start).                  |
| `GET /health`        | Liveness probe (`{"status": "ok"}`).                         |

Substring queries search the raw request bytes. OTLP protobuf encodes string
fields as UTF-8, so a plaintext marker embedded in a span attribute value is
found without decoding protobuf.

## Running

Locally:

```bash
python server.py [port]   # default port 4318
```

In E2E it runs as the `mock-otel` Docker Compose service on the `lightspeednet`
network. It starts with the rest of the stack (`docker compose up -d`) and
`lightspeed-stack` lists it under `depends_on` (waiting for it to become
healthy), so telemetry is delivered from startup. The
`An OpenTelemetry service is running and listening for OTLP data` step only waits
for it to become healthy and resets its buffer.

## Pointing the service at it

The Lightspeed Core Stack exports via HTTP/protobuf when launched with the OTEL
SDK enabled. The Compose files set these by default so export is always on in
E2E (override or set `OTEL_SDK_DISABLED=true` to change or disable it):

```bash
OTEL_SDK_DISABLED=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://mock-otel:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

The `scripts/entrypoint.sh` gate launches the service under
`opentelemetry-instrument` whenever `OTEL_SDK_DISABLED=false`.
