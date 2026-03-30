# Hybrid MCP Architecture: Server Tools + Client Tools

## Overview

The Lightspeed Stack (LCS) `/v1/responses` API supports a hybrid architecture where **server-configured tools** (RAG, MCP knowledge services) run centrally in the cluster while **client-provided tools** (oc/kubectl, local MCP servers) run on the developer's workstation under their own identity.

This design reflects a fundamental separation: **knowledge is shared, but actions are scoped**.

- **RAG, OKP, errata, Bugzilla** -- the same data for everyone on the cluster. LCS serves it once with auth, quotas, and moderation.
- **oc, kubectl** -- run from the Goose agent pod under a locked-down service account with read-only cluster access.

## Architecture

```
OpenShift Cluster
┌────────────────────────────────────────────────────────────────────────────┐
│                                                                            │
│  namespace: foo-staging                                                    │
│  ┌─────────────────────────────────────┐                                   │
│  │       Goose Agent (Pod)             │                                   │
│  │                                     │                                   │
│  │  ServiceAccount: goose-readonly     │                                   │
│  │  (read-only, limited k8s/OCP access)│                                   │
│  │                                     │    HTTPS POST /v1/responses       │
│  │  LLM reasoning loop                 │                                   │
│  │  ├─ LCS /v1/responses ──────────────┼─────────────────────┐             │
│  │  │  (knowledge queries)             │                     │             │
│  │  │                                  │                     ▼             │
│  │  ├─ Local MCP tools                 │  namespace: lightspeed-stack      │
│  │  │  (cluster read-only operations)  │  ┌─────────────────────────┐      │
│  │  │  ├─ oc get pods                  │  │  Lightspeed Stack (LCS) │      │
│  │  │  ├─ oc logs                      │  │                         │      │
│  │  │  └─ oc describe                  │  │  Llama Stack Engine     │      │
│  │  └──────────────────────────────────┘  │  ├─ file_search (RAG)   │      │
│  └──────────┬───────────────────────────  │  ├─ mcp: OKP/Solr       │      │
│             │ ServiceAccount token        │  ├─ mcp: errata         │      │
│             │ (read-only RBAC)            │  └─ mcp: bugzilla       │      │
│             │                             └───────────┬─────────────┘      │
│             │                                   ┌─────┴──────┐             │
│             │                                   │FAISS / Solr│             │
│             │                                   └────────────┘             │
│             │                                                              │
│             │  namespace: foo-staging                                      │
│             │  ┌───────────────────────────┐                               │
│             └─▶│  pods, deployments, ...   │                               │
│                │  (read-only RBAC enforced)│                               │
│                └───────────────────────────┘                               │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Server-Tool Merging

When a client (e.g. Goose) sends a `/v1/responses` request with its own tools, LCS needs to combine them with server-configured tools. This is controlled by the `X-LCS-Merge-Server-Tools: true` request header.

### Behavior

| Scenario | Result |
|---|---|
| No tools in request | LCS uses all server-configured tools (RAG, MCP) |
| Tools in request, **no merge header** | Client tools used as-is (original behavior) |
| Tools in request, **merge header set** | Client tools merged with server-configured tools |
| `tool_choice: "none"` | All tools disabled |

### Conflict Detection

When merging, LCS rejects conflicts with HTTP 409:

- **MCP conflict**: Client provides an MCP tool with the same `server_label` as a server-configured MCP tool.
- **file_search conflict**: Client provides a `file_search` tool when the server also configures one.

Non-conflicting tools are combined: client tools first, then server tools.

## Server-Tool Filtering in Responses

Clients like Goose may not understand server-side MCP item types (`mcp_call`, `mcp_list_tools`, `mcp_approval_request`). LCS filters these from streamed responses so clients only see standard item types (`message`, `function_call`, etc.).

### Streaming Filters

During SSE streaming, LCS suppresses events for server-deployed MCP tools:

1. **`response.output_item.added`** -- If the item is an `mcp_call`/`mcp_list_tools`/`mcp_approval_request` with a `server_label` matching a configured MCP server, the event is dropped and the `output_index` is tracked.
2. **`response.mcp_call.*` / `response.mcp_list_tools.*`** -- Events with a tracked `output_index` are dropped.
3. **`response.output_item.done`** -- Matching items are dropped and the index tracking is cleared.
4. **`response.completed`** -- The final `output` array is cleaned to remove server MCP items.

Client-provided MCP tools (with `server_label` values not matching any server config) pass through unfiltered.

### Turn Summary

Only server-deployed tool outputs are included in turn summaries, metrics, and storage. Client tool outputs (`function_call` items or MCP items with unrecognized `server_label`) are returned to the caller but not processed internally by LCS.

## Conversation Flow

```
Goose                     LCS /v1/responses        Llama Stack        MCP/RAG
  │                             │                       │                │
  │  "pod api-7f8b9 is crash-   │                       │                │
  │   looping in foo-staging,   │                       │                │
  │   help me diagnose it"      │                       │                │
  │                             │                       │                │
  │  POST {input, tools,        │                       │                │
  │   X-LCS-Merge-Server-Tools} │                       │                │
  │────────────────────────────▶│                       │                │
  │                             │ merge client +        │                │
  │                             │ server tools          │                │
  │                             │                       │                │
  │                             │ responses.create()    │                │
  │                             │──────────────────────▶│                │
  │                             │                       │ LLM: search RAG│
  │                             │                       │───────────────▶│
  │                             │                       │◀── RAG chunks: │
  │                             │                       │  known OOM fix │
  │                             │                       │  for api image │
  │                             │                       │                │
  │                             │                       │ LLM: query OKP │
  │                             │                       │───────────────▶│
  │                             │                       │◀── KB article: │
  │                             │                       │  memory limits │
  │                             │                       │  best practice │
  │                             │                       │                │
  │                             │◀──────────────────────│ answer with    │
  │                             │                       │ RAG + KB ctx   │
  │  SSE: response.completed    │                       │                │
  │  (server MCP items filtered)│                       │                │
  │◀────────────────────────────│                       │                │
  │                             │                       │                │
  │  Goose combines LCS knowledge with live cluster data:                │
  │                             │                       │                │
  │──▶ LOCAL MCP: oc get pods -n foo-staging                             │
  │◀── pod/api-7f8b9  CrashLoopBackOff                                   │
  │──▶ LOCAL MCP: oc logs pod/api-7f8b9                                  │
  │◀── OOMKilled                                                         │
  │──▶ LOCAL MCP: oc describe pod/api-7f8b9                              │
  │◀── events, resource limits                                           │
  │                                                                      │
  │  Goose correlates live cluster state with RAG/OKP                    │
  │  knowledge to produce a diagnosis:                                   │
  │  "Pod is OOMKilled. RAG docs confirm a known fix                     │
  │   for this image -- raise memory limit to 512Mi.                     │
  │   See KB article for memory tuning best practices."                  │
```
