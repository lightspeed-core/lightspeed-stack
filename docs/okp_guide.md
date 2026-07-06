# OKP Deployment and Configuration Guide

This document explains how to deploy the Offline Knowledge Portal (OKP) as a
RAG source and configure Lightspeed Stack and Llama Stack to use it. You will:

* Deploy and verify the OKP Solr service
* Configure Lightspeed Stack for OKP (inline or tool RAG)
* Install dependencies and launch Lightspeed Stack
* Confirm the end-to-end stack with a sample query

For general RAG concepts, BYOK vector stores, and manual Llama Stack
configuration, see the [RAG Configuration Guide](rag_guide.md).

---

## Table of Contents

* [Introduction](#introduction)
* [Prerequisites](#prerequisites)
* [Step 1: Launch OKP](#step-1-launch-okp)
* [Step 2: Install Dependencies and Set Environment Variables](#step-2-install-dependencies-and-set-environment-variables)
* [Step 3: Configure Lightspeed Stack](#step-3-configure-lightspeed-stack)
* [Step 4: Launch Lightspeed Stack](#step-4-launch-lightspeed-stack)
* [Step 5: Verify the Stack](#step-5-verify-the-stack)

---

## Introduction

OKP (Offline Knowledge Portal) provides a Solr-backed RAG source that
Lightspeed Stack can use for both **Inline RAG** (context injected before the
LLM request) and **Tool RAG** (context retrieved on demand via the
`file_search` tool). This guide walks through deploying the OKP container,
configuring Lightspeed Stack for OKP, and
validating that queries return referenced chunks.

---

## Prerequisites

* [lightspeed-stack repository](https://github.com/lightspeed-core/lightspeed-stack) cloned **with submodules**:
  ```bash
  git clone --recursive https://github.com/lightspeed-core/lightspeed-stack.git
  ```
  If you already cloned without `--recursive`, run: `git submodule update --init`
* [Podman](https://podman.io/) (or Docker) to run the OKP image
* [uv](https://docs.astral.sh/uv/) for Python dependency management
* An OpenAI API key (for inference when using OpenAI in your run config)

---

## Step 1: Launch OKP

Start the OKP RAG service with Podman:

```bash
podman run --rm -d -p 8081:8080 registry.redhat.io/offline-knowledge-portal/rhokp-rhel9:latest
```

> **Note:** Remove `-d` to run in the foreground.

* The service listens on **port 8081** on the host (mapped from 8080 in the container).  Lightspeed Stack itself listens on `8080`, so this avoids port conflicts.
* Confirm it is running by opening in a browser or with `curl`:

  ```bash
  curl -s http://localhost:8081
  ```

  Or visit: **http://localhost:8081**

> **Note:** The default OKP URL is configured via the `RH_SERVER_OKP` environment variable
> (see Step 2). You can override this by setting a different value for
> `RH_SERVER_OKP`, or by changing the `okp.rhokp_url` field in
> `lightspeed-stack.yaml`.
---

## Step 2: Install Dependencies and Set Environment Variables

Install dependencies:

```bash
uv sync --group dev --group llslibdev
```

Set required environment variables:

```bash
export OPENAI_API_KEY=<your-openai-api-key>

# Set OKP URL env var, using special hostname for container-to-host networking
# when running locally
# Podman:
export RH_SERVER_OKP=http://host.containers.internal:8081
# Docker:
# export RH_SERVER_OKP=http://host.docker.internal:8081
```

---

## Step 3: Configure Lightspeed Stack

### Enable OKP in Lightspeed Stack

Edit your Lightspeed Stack config file (e.g. `lightspeed-stack.yaml`) and add
the following top-level sections so that OKP is used for either inline or tool
RAG:

Inline RAG:

```yaml
# RAG configuration
rag:
  inline:
  - okp
okp:
  rhokp_url: ${env.RH_SERVER_OKP}
  offline: true
```

Tool RAG:

```yaml
# RAG configuration
rag:
  tool:
  - okp
okp:
  rhokp_url: ${env.RH_SERVER_OKP}
  offline: true
```

* **`rag.inline`** and **`rag.tool`**: Enable OKP as the RAG source for inline context injection and for the RAG tool.  Tool rag means the LLM will be provided a search tool it can choose to invoke to find relevant content and augment the user prompt.  The tool may or may not be invoked.  Inline means a rag search and prompt augmentation will always occur.
* **`okp.offline`**: When `true`, source URLs use `parent_id` (offline/Mimir-style). When `false`, use `reference_url` (online).

If you want to filter the docs to a specific product, you can include a static query filter such as:

```yaml
okp:
  offline: true
  chunk_filter_query: "product:*openshift* AND product_version:4.21"
```

When you launch Lightspeed stack it will augment the Llamastack run.yaml with
configuration for OKP.

### Dynamic Metadata Filtering

In addition to static filters configured in `lightspeed-stack.yaml`, you can apply **dynamic filters** per query using structured filter objects in the request. Dynamic filters are combined with static filters using AND logic.

#### Supported Filter Operations

**Comparison Filters:**
- `eq` - Equal to (exact match)
- `ne` - Not equal to
- `in` - Value in list
- `nin` - Value not in list

**Compound Filters:**
- `and` - All filters must match
- `or` - Any filter must match

> **Note:** Range operators (`gt`, `gte`, `lt`, `lte`) are not supported because they use lexicographic comparison on string fields, which can produce unexpected results.

#### Dynamic Filter Examples

**Simple equality filter:**

```bash
curl -sX POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to install ansible?",
    "solr": {
      "mode": "hybrid",
      "filters": {
        "filters": {
          "type": "eq",
          "key": "product",
          "value": "ansible_automation_platform"
        }
      }
    }
  }'
```

**Multiple values with 'in' filter:**

```bash
curl -sX POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Security best practices",
    "solr": {
      "mode": "semantic",
      "filters": {
        "filters": {
          "type": "in",
          "key": "product",
          "value": ["openshift_container_platform", "ansible_automation_platform", "red_hat_enterprise_linux"]
        }
      }
    }
  }'
```

**Compound filters (AND/OR):**

```bash
curl -sX POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Advanced configuration",
    "solr": {
      "mode": "hybrid",
      "filters": {
        "filters": {
          "type": "and",
          "filters": [
            {"type": "eq", "key": "product", "value": "openshift_container_platform"},
            {"type": "eq", "key": "product_version", "value": "4.21"}
          ]
        }
      }
    }
  }'
```

**Nested compound filters:**

```bash
curl -sX POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Troubleshooting guide",
    "solr": {
      "mode": "hybrid",
      "filters": {
        "filters": {
          "type": "and",
          "filters": [
            {"type": "eq", "key": "doc_type", "value": "guide"},
            {
              "type": "or",
              "filters": [
                {"type": "eq", "key": "product", "value": "openshift_container_platform"},
                {"type": "eq", "key": "product", "value": "ansible_automation_platform"}
              ]
            }
          ]
        }
      }
    }
  }'
```

#### Filter Behavior

- **Static filters preserved:** The configured `chunk_filter_query` (e.g., `"product:*openshift*"`) is always applied
- **Dynamic filters added:** Request filters are combined with static filters using AND logic
- **String escaping:** Special Solr characters in filter values are automatically escaped
- **Works with all search modes:** Filters apply to `semantic`, `hybrid`, and `lexical` search modes

---

## Step 4: Launch Lightspeed Stack

Then launch Lightspeed Stack using your Lightspeed Stack
config(`lightspeed-stack.yaml`) which references the provided default
Llamastack config file (`run.yaml`):

```bash
make run
```

Lightspeed Stack has launched successfully and is available when you see this
log output:

```log
INFO     2026-03-17 11:20:31,347 uvicorn.error:62 uncategorized: Application startup complete.
INFO     2026-03-17 11:20:31,349 uvicorn.error:224 uncategorized: Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

---

## Step 5: Verify the Stack

Confirm that the full stack (Lightspeed Stack + Llama Stack + OKP) is working
by sending a query and checking that the response includes referenced chunks
from OKP:

```bash
curl -sX POST http://localhost:8080/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "configure remote desktop using gnome"}' | jq .
```

* Adjust the URL and port if your Lightspeed Stack API is exposed elsewhere.
* In the JSON response, look for `rag_chunks` that indicate OKP/Solr results were retrieved.

Example response excerpt:
```json
"rag_chunks": [
{
    "content": "You can connect from a Red Hat Enterprise Linux client to a remote desktop server by using the\n**Connections**\napplication. The connection depends on the remote server configuration.\n**Prerequisites**\n- Desktop sharing or remote login is enabled on the server. For more information, see [Enabling desktop sharing on the server by using GNOME](#enabling-desktop-sharing-on-the-server-by-using-gnome) or [Configuring GNOME remote login](#configuring-gnome-remote-login) .\n- For desktop sharing, a user is logged in to the GNOME graphical session on the server.\n- The `gnome-connections` package is installed on the client.\n**Procedure**\n1. On the client, launch the **Connections** application.\n2. Click the + button in the top bar to open a new connection.\n4. Enter the IP address of the server.\n5. Choose the connection type based on the operating system you want to connect to: Remote Desktop Protocol (RDP) Use RDP for connecting to Windows and RHEL 10 servers. Virtual Network Computing (VNC) Use VNC for connecting to servers with RHEL 9 and previous versions.\n6. Click Connect .\n**Verification**\n1. On the client, check that you can see the shared server desktop.\n2. On the server, a screen sharing indicator appears on the right side of the top panel: You can control screen sharing in the **System** menu of the server.",
    "source": "okp",
    "score": 826.40784,
    "attributes": {
    "doc_url": "https://mimir.corp.redhat.com/documentation/en-us/red_hat_enterprise_linux/10/html-single/administering_rhel_by_using_the_gnome_desktop_environment/index",
    "document_id": "/documentation/en-us/red_hat_enterprise_linux/10/html-single/administering_rhel_by_using_the_gnome_desktop_environment/index"
    }
}
],
```

> **Note:** The first time you query the system the response may take
> additional time because it must first download the necessary embedding model
> to perform the vector search.

If you see no RAG context, verify:

1. OKP is up at http://localhost:8081
2. `lightspeed-stack.yaml` has `okp` under `rag.inline` and/or `rag.tool` as in Step 4

---
