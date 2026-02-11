# Splunk HEC Integration

Lightspeed Core Stack can send inference telemetry events to Splunk via the HTTP Event Collector (HEC) protocol for monitoring and analytics.

## Overview

When enabled, the service sends telemetry events for:

- **Successful inference requests** (`infer_with_llm` sourcetype)
- **Failed inference requests** (`infer_error` sourcetype)

Events are sent asynchronously in the background and never block or affect the main request flow.

## Configuration

Add the `splunk` section to your `lightspeed-stack.yaml`:

```yaml
splunk:
  enabled: true
  url: "https://splunk.corp.example.com:8088/services/collector"
  token_path: "/var/secrets/splunk-hec-token"
  index: "rhel_lightspeed"
  source: "lightspeed-stack"
  timeout: 5
  verify_ssl: true

deployment_environment: "production"
```

### Configuration Options

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | bool | No | `false` | Enable/disable Splunk integration |
| `url` | string | Yes* | - | Splunk HEC endpoint URL |
| `token_path` | string | Yes* | - | Path to file containing HEC token |
| `index` | string | Yes* | - | Target Splunk index |
| `source` | string | No | `lightspeed-stack` | Event source identifier |
| `timeout` | int | No | `5` | HTTP timeout in seconds |
| `verify_ssl` | bool | No | `true` | Verify SSL certificates |

*Required when `enabled: true`

### Token File

Store your HEC token in a file (not directly in the config):

```bash
echo "your-hec-token-here" > /var/secrets/splunk-hec-token
chmod 600 /var/secrets/splunk-hec-token
```

The token is read from file on each request, supporting rotation without service restart.

## Event Format

Events follow the rlsapi telemetry format for consistency with existing analytics.

### HEC Envelope

```json
{
    "time": 1737470400,
    "host": "pod-lcs-abc123",
    "source": "lightspeed-stack (v1.0.0)",
    "sourcetype": "infer_with_llm",
    "index": "rhel_lightspeed",
    "event": { ... }
}
```

### Event Payload

```json
{
    "question": "How do I configure SSH?",
    "refined_questions": [],
    "context": "",
    "response": "To configure SSH, edit /etc/ssh/sshd_config...",
    "inference_time": 2.34,
    "model": "granite-3-8b-instruct",
    "deployment": "production",
    "org_id": "12345678",
    "system_id": "abc-def-123",
    "total_llm_tokens": 0,
    "request_id": "req_xyz789",
    "cla_version": "CLA/0.4.1",
    "system_os": "RHEL",
    "system_version": "9.3",
    "system_arch": "x86_64"
}
```

### Field Descriptions

| Field | Description |
|-------|-------------|
| `question` | User's original question |
| `refined_questions` | Reserved for RAG (empty array) |
| `context` | Reserved for RAG (empty string) |
| `response` | LLM-generated response text |
| `inference_time` | Time in seconds for LLM inference |
| `model` | Model identifier from configuration |
| `deployment` | Value of `deployment_environment` config |
| `org_id` | Organization ID from RH Identity, or `auth_disabled` |
| `system_id` | System CN from RH Identity, or `auth_disabled` |
| `total_llm_tokens` | Reserved for token counting (currently `0`) |
| `request_id` | Unique request identifier |
| `cla_version` | Client User-Agent header |
| `system_os` | Client operating system |
| `system_version` | Client OS version |
| `system_arch` | Client CPU architecture |

## Endpoints

Currently, Splunk telemetry is enabled for:

| Endpoint | Sourcetype (Success) | Sourcetype (Error) |
|----------|---------------------|-------------------|
| `/rlsapi/v1/infer` | `infer_with_llm` | `infer_error` |

## Graceful Degradation

The Splunk client is designed for resilience:

- **Disabled by default**: No impact when not configured
- **Non-blocking**: Events sent via FastAPI BackgroundTasks
- **Fail-safe**: HTTP errors logged as warnings, never raise exceptions
- **Missing config**: Silently skips when required fields are missing

## Troubleshooting

### Events Not Appearing in Splunk

1. Verify `splunk.enabled: true` in config
2. Check token file exists and is readable
3. Verify HEC endpoint URL is correct
4. Check service logs for warning messages:
   ```text
   Splunk HEC request failed with status 403: Invalid token
   ```

### Connection Timeouts

Increase the timeout value:

```yaml
splunk:
  timeout: 10
```

### SSL Certificate Errors

For development/testing with self-signed certs:

```yaml
splunk:
  verify_ssl: false
```

**Warning**: Do not disable SSL verification in production.

## Extending to Other Endpoints

See [src/observability/README.md](../src/observability/README.md) for developer documentation on adding Splunk telemetry to additional endpoints.
