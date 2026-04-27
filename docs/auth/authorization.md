# Authorization System

Authorization in Lightspeed Core Stack is controlled through role-based access
control (RBAC). Once a user is authenticated, the authorization system
determines what actions they can perform.

## Overview

```
Authentication → Role Resolution → Access Resolution → Action Allowed/Denied
```

1. **Authentication**: User identity extracted (user_id, username)
2. **Role Resolution**: Determine user's roles based on auth method
3. **Access Resolution**: Check if any role grants the requested action

## Role Resolution

Determines user roles based on the authentication method used.

### No-op/K8s Authentication

Uses a no-op role resolver:
- All users get the special `*` (everyone) role only
- No additional roles assigned
- Future versions may expand K8s role resolution

### JWK Token Authentication

Uses JWT claims to determine user roles through JSONPath expressions.
See [JWK Token - Role Extraction](jwk-token.md#role-extraction) for configuration.

If no role rules are configured, falls back to the no-op resolver.

### Red Hat Identity Authentication

Currently uses no-op role resolution:
- All users get the `*` (everyone) role
- Future versions may support org-based or entitlement-based roles

## Access Resolution

Once roles are determined, access resolvers check whether any role grants the
requested action.

### No-op Resolver

Grants all users access to all actions. Used when:
- No access rules are configured
- No-op authentication is configured
- K8s authentication is configured (currently)

### Rule-based Resolver

Checks user's roles against configured access rules. Also grants admin users
unrestricted access - any user with the `admin` action can perform all other
actions.

## Configuring Access Rules

Define which roles can perform which actions in the `authorization` section:

```yaml
authorization:
  access_rules:
    # Everyone can query and get info
    - role: "*"
      actions: ["query", "info"]
    
    # Managers have full admin access
    - role: "manager"
      actions: ["admin"]
    
    # Employees can list their conversations
    - role: "employee"
      actions: ["list_conversations"]
    
    # Developers have extended access
    - role: "developer"
      actions: ["query", "get_config", "list_conversations"]
```

### Special Roles

| Role | Description |
|------|-------------|
| `*` | Everyone - matches all authenticated users |

### Special Actions

| Action | Description |
|--------|-------------|
| `admin` | Grants unrestricted access to ALL other actions |

## Available Actions

| Action | Description | Endpoints |
|--------|-------------|-----------|
| `admin` | Full administrative access | All endpoints |
| `query` | Submit queries | `/v1/query` |
| `streaming_query` | Submit streaming queries | `/v1/streaming_query` |
| `info` | Access service info | `/`, `/info`, `/readiness`, `/liveness` |
| `get_config` | View configuration | `/config` |
| `get_models` | List available models | `/models` |
| `get_tools` | List available tools | `/tools`, `/mcp-auth/client-options` |
| `get_shields` | List safety shields | `/shields` |
| `list_providers` | List providers | `/providers` |
| `get_provider` | Get provider details | `/providers/{provider_id}` |
| `get_metrics` | Access metrics | `/metrics` |
| `feedback` | Submit feedback | `/feedback` |
| `model_override` | Override model in queries | N/A (permission flag) |
| `read_prompts` | List and get prompts | `/v1/prompts`, `/v1/prompts/{prompt_id}` |
| `manage_prompts` | Manage prompts | `/v1/prompts`, `/v1/prompts/{prompt_id}` |

### Conversation Actions

| Action | Description |
|--------|-------------|
| `list_conversations` | List own conversations |
| `list_other_conversations` | List other users' conversations |
| `get_conversation` | Get own conversation details |
| `read_other_conversations` | Read other users' conversations |
| `delete_conversation` | Delete own conversations |
| `delete_other_conversations` | Delete other users' conversations |
| `query_other_conversations` | Query other users' conversations |

## Example Configurations

### Minimal (Everyone Can Query)

```yaml
authorization:
  access_rules:
    - role: "*"
      actions: ["query", "streaming_query", "info"]
```

### Admin + Regular Users

```yaml
authorization:
  access_rules:
    - role: "*"
      actions: ["query", "info"]
    - role: "admin"
      actions: ["admin"]
```

### Team-based Access

```yaml
authorization:
  access_rules:
    # Everyone gets basic access
    - role: "*"
      actions: ["info"]
    
    # Developers can query and see config
    - role: "developer"
      actions: ["query", "streaming_query", "get_config", "list_conversations"]
    
    # SRE team gets metrics access
    - role: "sre"
      actions: ["get_metrics", "info"]
    
    # Team leads get admin access
    - role: "team_lead"
      actions: ["admin"]
```

### Read-only Access Pattern

```yaml
authorization:
  access_rules:
    - role: "*"
      actions: ["info", "get_models", "get_tools"]
    - role: "user"
      actions: ["query"]
    - role: "viewer"
      actions: ["list_conversations", "get_conversation"]
```

## Authorization Flow

```
1. Request arrives
   ↓
2. Authentication extracts user identity
   ↓
3. Role resolver determines user's roles
   (e.g., ["*", "developer", "team_lead"])
   ↓
4. Endpoint requires specific action (e.g., "query")
   ↓
5. Access resolver checks:
   - Does any user role have "admin" action? → Allow all
   - Does any user role have "query" action? → Allow
   - No matching rules? → Deny (403)
   ↓
6. Request proceeds or is rejected
```

## Controlling Model Overrides

By default, clients may specify `model` and `provider` in query requests.
This can be restricted using the `model_override` action:

```yaml
authorization:
  access_rules:
    - role: "*"
      actions: ["query", "info"]
    - role: "power_user"
      actions: ["model_override"]
```

Requests that include `model` or `provider` without the `model_override`
permission are rejected with HTTP 403.

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 403 on all requests | No access rules configured | Add `access_rules` section |
| 403 for specific action | Role doesn't have action | Add action to role's actions list |
| Admin can't access endpoint | Using wrong role name | Use `admin` action, not role |

### Debugging

Check which roles a user has:
1. Enable debug logging
2. Look for role resolution logs
3. Verify JWT claims (for jwk-token) or identity header (for rh-identity)
