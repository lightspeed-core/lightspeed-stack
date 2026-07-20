# Sentry Error Tracking Integration

Sentry integration is **completely optional** and **disabled by default**. Most deployments will not use it. The service starts and runs normally with no Sentry configuration present.

When enabled, Sentry captures unhandled exceptions and performance traces from the FastAPI application and sends them to your Sentry project for monitoring and alerting.

## Overview

Enabling Sentry gives you:

- **Error tracking** - unhandled exceptions are captured and reported with full stack traces
- **Performance tracing** - a sample of POST requests are traced end-to-end
- **Release tagging** - errors are tagged with the running service version for easier triage

The integration is initialized at service startup and flushes any pending events on shutdown (2-second timeout).

## Configuration

Sentry is configured entirely through environment variables. No changes to `lightspeed-stack.yaml` are required.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN` | Yes (to enable) | - | Data Source Name from your Sentry project. Setting this variable enables Sentry. The DSN value is never written to logs to prevent credential exposure. |
| `SENTRY_ENVIRONMENT` | No | `development` | Environment tag attached to all events. Set this explicitly in production deployments. Use values like `production`, `stage`, or `dev` to distinguish clusters or deployment stages. |
| `SENTRY_CA_CERTS` | No | - | Path to a CA certificate bundle file. Only needed when your Sentry instance uses a private or internal CA. If the file is missing at startup, the SDK proceeds without custom certificates and logs a warning. |

### Enabling Sentry

Set `SENTRY_DSN` to the DSN string from your Sentry project settings:

```bash
export SENTRY_DSN="https://examplePublicKey@o0.ingest.sentry.io/0"
```

The service logs `Sentry initialized` on startup when the DSN is present, or `Sentry DSN not configured, skipping initialization` when it is not.

## Behavior Details

### FastAPI Integration

The Sentry FastAPI integration is configured to capture only `POST` requests. `GET` requests (health checks, model listings, etc.) are not traced.

### Trace Sampling

Of the captured POST requests, the following routes are always excluded from tracing regardless of the sample rate:

- `/readiness`
- `/liveness`
- `/metrics`
- `/` (root)

The remaining eligible requests are sampled at 25% for performance tracing. This keeps trace volume low and avoids noise from health check and metrics scrape traffic.

### Privacy

`send_default_pii` is set to `False`. Sentry will not attach user IP addresses, HTTP headers, or other personally identifiable information to events.

### Release Tagging

Every event is tagged with the running service version in the format `lightspeed-stack@{version}` (for example, `lightspeed-stack@0.5.0`). This makes it straightforward to correlate errors with specific releases in the Sentry UI.

### Shutdown Behavior

When the service shuts down, it flushes any buffered Sentry events before exiting. The flush has a 2-second timeout to avoid delaying shutdown.

## OpenShift Deployment

### Setting the DSN via a Secret

Store the Sentry DSN in an OpenShift Secret rather than hardcoding it in a Deployment manifest:

```bash
oc create secret generic sentry-credentials \
  --from-literal=dsn="https://examplePublicKey@o0.ingest.sentry.io/0"
```

Reference the Secret in your Deployment or Pod spec:

```yaml
env:
  - name: SENTRY_DSN
    valueFrom:
      secretKeyRef:
        name: sentry-credentials
        key: dsn
```

### Setting the Environment Tag

Use `SENTRY_ENVIRONMENT` to label events by cluster or deployment stage. This makes it easy to filter events in the Sentry UI:

```yaml
env:
  - name: SENTRY_DSN
    valueFrom:
      secretKeyRef:
        name: sentry-credentials
        key: dsn
  - name: SENTRY_ENVIRONMENT
    value: "production"
```

Set this to `stage`, `dev`, or any label that matches your deployment topology.

### Private CA Certificates (Enterprise Sentry Instances)

Most deployers will not need this. If your Sentry instance is hosted internally and uses a certificate signed by a private CA, the SDK will fail to connect without the CA bundle.

Mount the CA bundle into the pod using a ConfigMap or Secret, then point `SENTRY_CA_CERTS` at the mount path.

**Using a ConfigMap:**

```bash
oc create configmap sentry-ca --from-file=ca-bundle.crt=/path/to/your/ca-bundle.crt
```

```yaml
volumes:
  - name: sentry-ca
    configMap:
      name: sentry-ca

containers:
  - name: lightspeed-stack
    volumeMounts:
      - name: sentry-ca
        mountPath: /etc/sentry-ca
        readOnly: true
    env:
      - name: SENTRY_DSN
        valueFrom:
          secretKeyRef:
            name: sentry-credentials
            key: dsn
      - name: SENTRY_CA_CERTS
        value: "/etc/sentry-ca/ca-bundle.crt"
```

If the file is not present at the path specified by `SENTRY_CA_CERTS`, the service logs a warning and continues without custom CA certificates. It will not fail to start.

## Troubleshooting

### Events Not Appearing in Sentry

1. Confirm `SENTRY_DSN` is set and the value is correct. Check the service logs for `Sentry initialized` at startup.
2. Verify network connectivity from the pod to the Sentry ingest endpoint. DNS resolution failures and firewall rules are common causes.
3. If using a private Sentry instance, confirm `SENTRY_CA_CERTS` points to a valid CA bundle and the file is readable by the service process.
4. Check that the DSN belongs to the correct Sentry project and organization.

### Warning: CA Cert File Not Found

```text
CA cert file specified by SENTRY_CA_CERTS not found at /etc/sentry-ca/ca-bundle.crt; proceeding without custom CA certs
```

The path set in `SENTRY_CA_CERTS` does not exist. Verify the ConfigMap or Secret is mounted correctly and the mount path matches the environment variable value.

### Events Appear in Wrong Environment

Check the value of `SENTRY_ENVIRONMENT`. If it is not set, events are tagged as `development` by default. Set the variable explicitly to match your deployment stage.
