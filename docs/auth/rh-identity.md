# Red Hat Identity Authentication (`rh-identity`)

Red Hat Identity header authentication for deployments behind Red Hat Hybrid
Cloud Console infrastructure (e.g., console.redhat.com, Insights). This module
validates the `x-rh-identity` header provided by Red Hat's authentication proxy.

## Overview

The `rh-identity` module:
1. Extracts the `x-rh-identity` header from incoming requests
2. Base64 decodes and parses the JSON payload
3. Validates the identity structure based on type (User, System, or ServiceAccount)
4. Optionally validates service entitlements
5. Extracts user identity for downstream use

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│   Client/RHEL   │──────▶  Red Hat Auth    │──────▶  Lightspeed Stack   │
│     System      │      │     Proxy        │      │   (rh-identity)     │
└─────────────────┘      └──────────────────┘      └─────────────────────┘
                               │                           │
                               │ Adds x-rh-identity        │ Validates header
                               │ header to request         │ Extracts identity
                               ▼                           ▼
```

The authentication proxy (part of Red Hat's infrastructure) authenticates users
via SSO or systems via certificate authentication, then injects the
`x-rh-identity` header containing the verified identity information.

## Configuration

### Basic Configuration

```yaml
authentication:
  module: rh-identity
```

### With Entitlement Validation

```yaml
authentication:
  module: rh-identity
  rh_identity_config:
    required_entitlements:
      - rhel
      - insights
```

### Configuration Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `required_entitlements` | No | `[]` | List of service entitlements to require |

When `required_entitlements` is configured, **ALL** listed entitlements must be
present and entitled in the identity header. Omit this field to disable
entitlement validation entirely.

## Identity Types

The `x-rh-identity` header supports three identity types, each with different
structure and use cases.

### User Identity

Console users authenticated via Red Hat SSO. Used when humans access services
through the Hybrid Cloud Console.

**Identity extraction:**
- `user_id`: From `identity.user.user_id`
- `username`: From `identity.user.username`

**Header structure:**
```json
{
  "identity": {
    "account_number": "123456",
    "org_id": "654321",
    "type": "User",
    "user": {
      "user_id": "abc123",
      "username": "user@example.com",
      "is_org_admin": false,
      "is_internal": false,
      "locale": "en_US"
    }
  },
  "entitlements": {
    "rhel": {"is_entitled": true, "is_trial": false},
    "insights": {"is_entitled": true, "is_trial": false},
    "ansible": {"is_entitled": false, "is_trial": false}
  }
}
```

**Available User fields:**

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | string | Unique user identifier |
| `username` | string | User's email or username |
| `is_org_admin` | boolean | Whether user is an organization admin |
| `is_internal` | boolean | Whether user is a Red Hat internal user |
| `locale` | string | User's locale preference |

### System Identity

Certificate-authenticated RHEL systems. Used when RHEL hosts access services
directly (e.g., Insights client, subscription-manager).

**Identity extraction:**
- `user_id`: From `identity.system.cn` (certificate Common Name)
- `username`: From `identity.account_number` when present and non-empty,
  otherwise falls back to `identity.system.cn`

`org_id` is the required organizational identifier for System identities.
`account_number` is optional: no-cost RHEL developer subscriptions send an
empty `account_number` with a populated `org_id`. A System identity is rejected
only when `org_id` or `system.cn` is empty or absent.

**Header structure:**
```json
{
  "identity": {
    "account_number": "123456",
    "org_id": "654321",
    "type": "System",
    "system": {
      "cn": "c87dcb4c-8af1-40dd-878e-60c744edddd0",
      "cert_type": "system"
    }
  },
  "entitlements": {
    "rhel": {"is_entitled": true, "is_trial": false}
  }
}
```

A developer-subscription System identity omits the account number:
```json
{
  "identity": {
    "account_number": "",
    "org_id": "18939564",
    "type": "System",
    "auth_type": "cert-auth",
    "system": {
      "cn": "14b75b86-6f99-411d-b41d-f400268b5807",
      "cert_type": "system"
    }
  }
}
```

**Available System fields:**

| Field | Type | Description |
|-------|------|-------------|
| `cn` | string | Certificate Common Name (system UUID) |
| `cert_type` | string | Certificate type (usually "system") |

### ServiceAccount Identity

OAuth service accounts authenticated via JWT. Used when automated services or
integrations access APIs using client credentials.

**Identity extraction:**
- `user_id`: From `identity.service_account.client_id`
- `username`: From `identity.service_account.username`

**Header structure:**
```json
{
  "identity": {
    "account_number": "123456",
    "org_id": "654321",
    "type": "ServiceAccount",
    "auth_type": "jwt-auth",
    "service_account": {
      "client_id": "b69eaf9e-e6a6-4f9e-805e-02987daddfbd",
      "username": "service-account-b69eaf9e-e6a6-4f9e-805e-02987daddfbd"
    }
  },
  "entitlements": {
    "rhel": {"is_entitled": true, "is_trial": false}
  }
}
```

**Available ServiceAccount fields:**

| Field | Type | Description |
|-------|------|-------------|
| `client_id` | string | OAuth client identifier (used as user_id) |
| `username` | string | Service account username |

## Common Identity Fields

All identity types share these top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `account_number` | string | Red Hat account number (optional for System identities; may be empty for developer subscriptions) |
| `org_id` | string | Organization ID (required for System identities) |
| `type` | string | Identity type: "User", "System", or "ServiceAccount" |

## Entitlements

Entitlements represent service subscriptions. Each entitlement has:

| Field | Type | Description |
|-------|------|-------------|
| `is_entitled` | boolean | Whether the account has this entitlement |
| `is_trial` | boolean | Whether this is a trial entitlement |

**Common entitlement names:**
- `rhel` - Red Hat Enterprise Linux
- `insights` - Red Hat Insights
- `ansible` - Ansible Automation Platform
- `openshift` - OpenShift Container Platform

## Accessing Identity Data in Application

The module stores the parsed identity data in `request.state.rh_identity_data`
for downstream access:

```python
from fastapi import Request

async def my_endpoint(request: Request):
    rh_identity = request.state.rh_identity_data
    
    # Get organization ID
    org_id = rh_identity.get_org_id()
    
    # Check specific entitlement
    has_insights = rh_identity.has_entitlement("insights")
    
    # Get user info
    user_id = rh_identity.get_user_id()
    username = rh_identity.get_username()
```

### Available Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_user_id()` | `str` | User ID, system CN, or service account client_id |
| `get_username()` | `str` | Username, account number, or service account username |
| `get_org_id()` | `str` | Organization ID |
| `has_entitlement(service)` | `bool` | Check single entitlement |
| `has_entitlements(services)` | `bool` | Check ALL entitlements in list |

## Request Examples

### Creating a Test Header

```bash
# User identity
IDENTITY='{
  "identity": {
    "account_number": "123456",
    "org_id": "654321",
    "type": "User",
    "user": {
      "user_id": "test-user-id",
      "username": "testuser@example.com"
    }
  },
  "entitlements": {
    "rhel": {"is_entitled": true, "is_trial": false}
  }
}'

# Base64 encode
HEADER=$(echo -n "$IDENTITY" | base64)

# Make request
curl http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -H "x-rh-identity: $HEADER" \
  -d '{"query": "Hello"}'
```

### System Identity Example

```bash
# System identity
IDENTITY='{
  "identity": {
    "account_number": "123456",
    "org_id": "654321",
    "type": "System",
    "system": {
      "cn": "c87dcb4c-8af1-40dd-878e-60c744edddd0"
    }
  },
  "entitlements": {
    "rhel": {"is_entitled": true, "is_trial": false}
  }
}'

HEADER=$(echo -n "$IDENTITY" | base64)

curl http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -H "x-rh-identity: $HEADER" \
  -d '{"query": "Hello"}'
```

### ServiceAccount Identity Example

```bash
# ServiceAccount identity
IDENTITY='{
  "identity": {
    "account_number": "123456",
    "org_id": "654321",
    "type": "ServiceAccount",
    "auth_type": "jwt-auth",
    "service_account": {
      "client_id": "b69eaf9e-e6a6-4f9e-805e-02987daddfbd",
      "username": "service-account-b69eaf9e-e6a6-4f9e-805e-02987daddfbd"
    }
  },
  "entitlements": {
    "rhel": {"is_entitled": true, "is_trial": false}
  }
}'

HEADER=$(echo -n "$IDENTITY" | base64)

curl http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -H "x-rh-identity: $HEADER" \
  -d '{"query": "Hello"}'
```

## Error Responses

| Status | Condition | Response |
|--------|-----------|----------|
| 401 | Missing `x-rh-identity` header | `{"detail": "Missing x-rh-identity header"}` |
| 400 | Invalid base64 encoding | `{"detail": "Invalid base64 encoding in x-rh-identity header"}` |
| 400 | Invalid JSON | `{"detail": "Invalid JSON in x-rh-identity header"}` |
| 400 | Missing `identity` field | `{"detail": "Missing 'identity' field"}` |
| 400 | Missing identity `type` | `{"detail": "Missing identity 'type' field"}` |
| 400 | Missing `user` for User type | `{"detail": "Missing 'user' field for User type"}` |
| 400 | Missing `user_id` in user | `{"detail": "Missing 'user_id' in user data"}` |
| 400 | Missing `username` in user | `{"detail": "Missing 'username' in user data"}` |
| 400 | Missing `system` for System type | `{"detail": "Missing 'system' field for System type"}` |
| 400 | Missing `cn` in system | `{"detail": "Missing 'cn' in system data"}` |
| 400 | Missing `org_id` for System | `{"detail": "Missing 'org_id' for System type"}` |
| 400 | Missing `service_account` for ServiceAccount type | `{"detail": "Invalid identity data"}` |
| 400 | Missing `client_id` in service_account | `{"detail": "Invalid identity data"}` |
| 400 | Missing `username` in service_account | `{"detail": "Invalid identity data"}` |
| 400 | Unsupported identity type | `{"detail": "Unsupported identity type: X"}` |
| 403 | Missing required entitlements | `{"detail": "Missing required entitlement: rhel"}` |

## Deployment Considerations

### Behind the Hybrid Cloud Console

When deployed behind console.redhat.com or similar Red Hat infrastructure:
1. The authentication proxy handles all authentication
2. The `x-rh-identity` header is automatically injected
3. Configure Lightspeed Stack to trust this header

### Security Notes

- **Never expose directly to the internet** - The `x-rh-identity` header can be
  forged. Always deploy behind Red Hat's authentication proxy.
- **Validate entitlements** - Use `required_entitlements` to ensure only
  authorized accounts can access the service.
- **Log audit events** - The extracted user/system identity should be logged
  for audit purposes.

### Local Development

For local testing without the authentication proxy, you can manually create
headers using the examples above. Consider using `noop` module instead for
simpler local development.

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 401 errors | Header not being forwarded | Check proxy/ingress configuration |
| 400 errors | Malformed header | Validate JSON structure, check base64 encoding |
| 403 errors | Missing entitlements | Verify account has required subscriptions |
| Wrong user ID | Using System identity | Check identity type in header |

### Debugging

Enable debug logging to see identity extraction:
```yaml
service:
  color_log: true
  log_level: DEBUG
```

Look for log entries like:
```
RH Identity authenticated: user_id=abc123, username=user@example.com
```
