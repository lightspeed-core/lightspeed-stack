# Authentication and Authorization

Lightspeed Core Stack implements a modular authentication and authorization
system with multiple authentication methods. Authorization is configurable
through role-based access control.

## Authentication configuration

The authentication system is configured via the `authentication` section in
the configuration file.

## Authentication Modules

Authentication is handled through selectable modules configured via the
`module` field in the authentication configuration.

### No-op (`noop`)

Development-only authentication that bypasses security checks.

**Configuration:**
```yaml
authentication:
  module: noop
```

**Behavior:**
- Accepts any request without token validation
- Extracts `user_id` from query parameters (defaults to `00000000-0000-0000-0000-000`)
- Uses fixed username `lightspeed-user`

### No-op with Token (`noop-with-token`)

Development authentication that requires tokens but doesn't validate them.

**Configuration:**
```yaml
authentication:
  module: noop-with-token
```

**Behavior:**
- Extracts bearer token from the `Authorization` header
- Same user ID and username handling as `noop`
- Token is passed through unvalidated for downstream use

### Kubernetes (`k8s`)

K8s based authentication is suitable for running the Lightspeed Stack in
Kubernetes environments. The user accessing the service must have a valid
Kubernetes token and the appropriate RBAC permissions to access the service.
The user must have the `get` permission on the Kubernetes RBAC non-resource URL
`/ls-access`. Here is an example of granting `get` on `/ls-access` via a
ClusterRole’s nonResourceURLs rule:

```yaml
# Allow GET on non-resource URL /ls-access
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: lightspeed-access
rules:
  - nonResourceURLs: ["/ls-access"]
    verbs: ["get"]
---
# Bind to a user, group, or service account
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: lightspeed-access-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: lightspeed-access
subjects:
  - kind: User            # or ServiceAccount, Group
    name: SOME_USER_OR_SA
    apiGroup: rbac.authorization.k8s.io
```

**Configuration:**

When deploying Lightspeed Stack in a Kubernetes cluster, it is not required to
specify cluster connection details, it automatically picks up the in-cluster
configuration or through a kubeconfig file. 

When running outside a kubernetes cluster or connecting to external Kubernetes
clusters, Lightspeed Stack requires the cluster connection details in the
configuration file: 

- `k8s_cluster_api` Kubernetes Cluster API URL. The URL of the k8s/OCP API server where tokens are validated.
- `k8s_ca_cert_path` Path to the CA certificate file for clusters with self-signed certificates.
- `skip_tls_verification` Whether to skip TLS verification.

For example:

```yaml
authentication:
  module: k8s
  k8s_cluster_api: https://kubernetes.default.svc  # optional, will be auto-detected
  k8s_ca_cert_path: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt  # optional, will be auto-detected
  skip_tls_verification: false  # optional, insecure
```

**Behavior:**
- Validates bearer tokens via the Kubernetes TokenReview API
- Performs authorization checks using SubjectAccessReview (SAR)
- Checks access to configured virtual path (default: `/ls-access`) with `get` verb
- Extracts user ID and username from token claims
- Special handling for the `kube:admin` user (uses cluster ID as user ID)

**Requirements:**
- Valid Kubernetes service account token in the `Authorization` header
- RBAC rules granting access to the virtual path
- Cluster access or kubeconfig file

### JWK Token (`jwk-token`)

JWK (JSON Web Keyset) based authentication is suitable for scenarios where you
need to authenticate users based on tokens. This method is commonly used in web
applications and APIs.

Users provide a JWT (JSON Web Token) in the `Authorization` header of their
requests. This JWT is validated against the JWK set fetched from the configured
URL.

**Configuration:**
```yaml
authentication:
  module: jwk-token
  jwk_config:
    url: https://auth.example.com/.well-known/jwks.json
    jwt_configuration:
      user_id_claim: sub      # optional, defaults to 'sub'
      username_claim: name    # optional, defaults to 'preferred_username'
      role_rules: []          # optional role extraction rules. See Authorization section for details.
```

**Behavior:**
- Fetches JWK set from configured URL (cached for 1 hour)
- Validates JWT signature against JWK set
- Extracts user ID and username from configurable JWT claims
- Returns default credentials (guest-like) if no `Authorization` header present (guest access)

### API Key Token (`api-key-token`)

Authentication that checks a given API Key token is present as a Bearer token

**Configuration:**
```yaml
  module: "api-key-token"
  api_key_config:
    api_key: "some-api-key"
```

**Behavior:**
- Extracts bearer token from the `Authorization` header
- Same user ID and username handling as `noop`
- Token is passed through and validated against the API Key given from configuration, for downstream use

### Red Hat Identity (`rh-identity`)

Red Hat Identity header authentication is suitable for deployments behind Red Hat
Hybrid Cloud Console infrastructure (e.g., console.redhat.com, Insights). This
method validates the `x-rh-identity` header provided by Red Hat's authentication
proxy, supporting both User (console users) and System (RHEL systems) identity types.

**Configuration:**
```yaml
authentication:
  module: rh-identity
  rh_identity_config:
    required_entitlements: ["rhel"]  # optional, validates service entitlements
```

The `required_entitlements` field accepts a list of service names. When configured,
ALL listed entitlements must be present in the identity header. Omit this field
to disable entitlement validation entirely.

**Identity Types:**

- **User**: Console users authenticated via SSO. Identified by `user_id` and `username`
  from the `identity.user` object.
- **System**: Certificate-authenticated RHEL systems. Identified by `cn` (Common Name)
  from the `identity.system` object, with `account_number` used as username.

**Header Format:**

The `x-rh-identity` header contains a base64-encoded JSON payload. Below are
examples of the decoded JSON structure for each identity type.

User identity:
```json
{
  "identity": {
    "account_number": "123456",
    "org_id": "654321",
    "type": "User",
    "user": {
      "user_id": "abc123",
      "username": "user@example.com",
      "is_org_admin": false
    }
  },
  "entitlements": {
    "rhel": {"is_entitled": true, "is_trial": false}
  }
}
```

System identity:
```json
{
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
}
```

**Behavior:**
- Extracts `x-rh-identity` header from request
- Base64 decodes and parses as JSON
- Validates structure based on identity type (User or System)
- Validates service entitlements if `required_entitlements` is configured
- Extracts user_id (or cn for System) and username (or account_number for System)

**Requirements:**
- Valid `x-rh-identity` header with base64-encoded JSON
- Proper JSON structure for the identity type
- Required service entitlements (if configured)

**Error Responses:**

| Status | Condition |
|--------|-----------|
| 401 | Missing `x-rh-identity` header |
| 400 | Invalid base64 encoding, invalid JSON, or missing required fields |
| 403 | Missing required service entitlements |

## Authorization System

Authorization is controlled through role-based access control using two resolver types.

### Role Resolution

Determines user roles based on authentication method:

**No-op/K8s Authentication:**
- Uses a no-op role resolver
- All users get the special `*` (everyone) role only
- To be expanded in the future

**JWK Token Authentication:**
- Uses JWT claims to determine user roles through JSONPath expressions
- Falls back to a no-op resolver if no role rules are configured

#### JWT Role Rules

Extract roles from JWT claims using JSONPath expressions, for example:

```yaml
authentication:
  module: jwk-token
  jwk_config:
    jwt_configuration:
      role_rules:
        - jsonpath: "$.realm_access.roles[*]"
          operator: contains
          value: "manager"
          roles: ["manager"]
        - jsonpath: "$.org_id"
          operator: "equals"
          value: [["dummy_corp"]]
          roles: ["dummy_employee"]
        - jsonpath: "$.groups[*]"
          operator: in
          value: ["developers", "qa"]
          roles: ["developer"]
          negate: false
```

**Fields:**
- `jsonpath`: JSONPath expression to extract values from JWT claims. 
- `operator`: Comparison operator (see below)
- `value`: Value(s) to evaluate the extracted values and operator against
- `roles`: List of roles to assign if the rule matches
- `negate`: If true, inverts the rule match result (optional, defaults to false)

Note that the JSONPath expression always yields a list of values, even for
single-value expressions, so comparisons should be done accordingly.

**Operators:**
- `equals`: Exact match
- `contains`: Value contains the specified string
- `in`: Value is in the specified list
- `match`: Regex pattern match (uses pre-compiled patterns)

### Access Resolution

Various operations inside lightspeed require authorization checks. Those
operations are associated with actions (e.g. `query`, `info`, `admin`).

Once user roles are determined, checking whether a user is allowed to perform
an action is done through access resolvers.

**No-op resolver:**

A resolver which uses a no-op access resolver that grants all users access to
all actions, used when no access rules are configured no-op authentication is
configured, or at-least currently when k8s authentication is configured.

**Rule-based Access:**

A resolver which does the obvious thing of checking whether any of the user's
roles is allowed to perform the requested action based on the access rules in
the authorization configuration. It also grants all users which have the `admin`
action unrestricted access to all other actions.

#### Access Rules

Define which roles can perform which actions:

```yaml
authorization:
  access_rules:
    # `*` is a special role that is given to all users
    - role: "*"
      actions: ["query", "info"]
    - role: "manager"
      # admin is a special *action* that grants unrestricted access to all actions.
      # Note that only the `admin` *action* is special, there is no special `admin` role.
      actions: ["admin"]
    - role: "dummy_employee"
      actions: ["list_conversations"]
    - role: "developer"
      actions: ["query", "get_config", "list_conversations"]
```

**Available Actions:**
- `admin` - If a user has this action, they automatically can perform all other actions
- `query` - Access query endpoints
- `query_other_conversations` - Query conversations not owned by the user
- `streaming_query` - Access streaming query endpoints
- `info` - Access the `/` endpoint, `/info` endpoint, `/readiness` endpoint, and `/liveness` endpoint
- `get_config` - Access the `/config` endpoint
- `get_models` - Access the `/models` endpoint
- `list_providers` - Access the `/providers` endpoint
- `get_provider` - Access the `/providers/{provider_id}` endpoint
- `get_metrics` - Access the `/metrics` endpoint
- `list_conversations` - Access the `/conversations` endpoint
- `list_other_conversations` - Access conversations not owned by the user
- `get_conversation` - `GET` conversations from `/conversations/{conversation_id}` endpoint
- `read_other_conversations` - Read conversations not owned by the user
- `delete_conversation` - `DELETE` conversations from `/conversations/{conversation_id}` endpoint
- `delete_other_conversations` - Delete conversations not owned by the user
- `feedback` - Access the `/feedback` endpoint
- `model_override` - Allow user to choose the model when querying
