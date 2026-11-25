# OKP Deployment and Configuration Guide

This document explains how to deploy the Offline Knowledge Portal (OKP) as a
RAG source and configure Lightspeed Stack and OGX to use it. You will:

* Deploy and verify the OKP Solr service
* Configure Lightspeed Stack for OKP (inline or tool RAG)
* Install dependencies and launch Lightspeed Stack
* Confirm the end-to-end stack with a sample query

For general RAG concepts, BYOK vector stores, and manual OGX
configuration, see the [RAG Configuration Guide](rag_guide.md).

---

## Table of Contents

* [Introduction](#introduction)
* [Prerequisites](#prerequisites)
* [Step 1: Launch OKP](#step-1-launch-okp)
* [Step 2: Install Dependencies and Set Environment Variables](#step-2-install-dependencies-and-set-environment-variables)
  * [EnMaaS (OpenAI-compatible remote LLM)](#enmaas-openai-compatible-remote-llm)
* [Step 3: Configure Lightspeed Stack](#step-3-configure-lightspeed-stack)
* [Step 4: Launch Lightspeed Stack](#step-4-launch-lightspeed-stack)
  * [Library mode (embedded OGX)](#library-mode-embedded-ogx)
  * [Server mode (separate OGX process)](#server-mode-separate-ogx-process)
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
* An API key for your LLM backend (OpenAI or an OpenAI-compatible gateway such as
  EnMaaS)

---

## Step 1: Launch OKP

Start the OKP RAG service with Podman or Docker:

**Using Podman:**

```bash
podman login registry.redhat.io
podman run --rm -d -p 8081:8080 registry.redhat.io/offline-knowledge-portal/rhokp-rhel9:latest
```

**Using Docker:**

```bash
docker login registry.redhat.io
docker run --rm -d -p 8081:8080 registry.redhat.io/offline-knowledge-portal/rhokp-rhel9:latest
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
uv sync --group dev --group ogxlibdev
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

### EnMaaS (OpenAI-compatible remote LLM)

Use EnMaaS (or similar) by exporting your token as `OPENAI_API_KEY`, the
gateway as `OPENAI_BASE_URL`, and the model as `E2E_OPENAI_MODEL`, and add
`inference.providers[].config` (on the provider entry, not at file root):

```bash
export OPENAI_API_KEY=<your-enmaas-api-key>
export OPENAI_BASE_URL=https://api.enmaas.devshift.net/v1
export E2E_OPENAI_MODEL=rits/zai-org/glm-5-3
```

```yaml
inference:
  default_provider: openai
  default_model: ${env.E2E_OPENAI_MODEL:=rits/zai-org/glm-5-3}
  providers:
    - type: openai
      config:
        api_key: ${env.OPENAI_API_KEY} #EnMaaS token
        base_url: ${env.OPENAI_BASE_URL:=} #EnMaaS base url (https://api.enmaas.devshift.net/v1 )
      allowed_models:
        - ${env.E2E_OPENAI_MODEL:=rits/zai-org/glm-5-3}
```

In **library mode**, add `api_key_env: OPENAI_API_KEY` and
`extra.base_url` on the same provider so OGX synthesis picks up the EnMaaS
URL and key (synthesis does not read `config` today).

---

## Step 3: Configure Lightspeed Stack

### Enable OKP in Lightspeed Stack

Edit your Lightspeed Stack config file (e.g. `lightspeed-stack.yaml`) and add
the following top-level sections so that OKP is used for either inline or tool
RAG:

**Inline RAG:**

```yaml
# RAG configuration
rag:
  retrieval:
    inline:
      sources:
        - okp
      max_chunks: 3      # Final tight cap on chunks returned to user
  okp:
    rhokp_url: ${env.RH_SERVER_OKP}
    offline: true
    max_chunks: 5        # Initial generous fetch from OKP
```

**Tool RAG:**

```yaml
# RAG configuration
rag:
  retrieval:
    tool:
      sources:
        - okp
      max_chunks: 10     # Tool RAG limit
  okp:
    rhokp_url: ${env.RH_SERVER_OKP}
    offline: true
    max_chunks: 5
```

* **`rag.retrieval.inline`** and **`rag.retrieval.tool`**: Enable OKP as the RAG source for inline context injection and for the RAG tool. Tool RAG means the LLM will be provided a search tool it can choose to invoke to find relevant content and augment the user prompt. The tool may or may not be invoked. Inline RAG means a RAG search and prompt augmentation will always occur.
* **`okp.offline`**: When `true`, source URLs use `parent_id` (offline/Mimir-style). When `false`, use `reference_url` (online).
* **`okp.search_mode`**: Default Solr search strategy for OKP queries. Controls *how* Solr ranks chunks, not *which* documents are eligible (that is `chunk_filter_query` and per-request `solr.filters`). Allowed values:
  - **`hybrid`** (default when the field is omitted): combines vector similarity with keyword (BM25) text search. Requires an embedding model. This is the global default.
  - **`semantic`**: pure vector search against Solr embeddings. Requires an embedding model. Best when the query is conceptual rather than matching document wording.
  - **`keyword`**: BM25 text search only. No embedding model is needed, so it is the right choice for air-gapped or embedding-free deployments, and it is typically faster than hybrid.
* **`max_chunks` behavior**:
  - **Inline RAG**: `rag.retrieval.inline.max_chunks` is the final tight cap on chunks returned in the response, while `rag.okp.max_chunks` is the initial generous fetch from OKP before filtering and ranking.
  - **Tool RAG**: `rag.retrieval.tool.max_chunks` sets the limit on chunks available to the tool.

If you want to filter the docs to a specific product, you can include a static query filter such as:

```yaml
okp:
  offline: true
  search_mode: keyword
  chunk_filter_query: "product:*openshift* AND product_version:4.21"
```

A per-request `solr.mode` on `/v1/query` (or streaming/responses) overrides this YAML default for that call. Per-request `lexical` is treated as `keyword`.

> **Important:** When running OGX in **Server mode**, changes to static OKP settings such as `chunk_filter_query` and `search_mode` require an OGX restart to take effect. They are applied when Lightspeed Stack enriches OGX configuration at startup and will not propagate automatically during runtime.

When you launch Lightspeed Stack it will augment the OGX configuration (the synthesized run.yaml in unified mode, or your external run.yaml in the deprecated legacy mode) with
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
- **Works with all search modes:** Filters apply whether the search mode is `semantic`, `hybrid`, or `keyword` (per-request `lexical` is an alias of `keyword`).

---

## Step 4: Launch Lightspeed Stack

Use either **library mode** (one process, OGX embedded) or **server mode**
(Lightspeed Stack on port 8080 plus a separate OGX process, often on 8321).
OKP enrichment (Solr vector store, `external_providers_dir`) is applied
automatically when `okp` is listed under `rag.retrieval.inline.sources`
and/or `rag.retrieval.tool.sources`.

### Library mode (embedded OGX)

One process on port **8080**; OGX config is synthesized at startup (no separate
`ogx run`). In `lightspeed-stack.yaml`, set `ogx.use_as_library_client: true`,
`ogx.config.baseline: byo-llm`, OKP `rag` (Step 3), and `inference` (Step 2).

```bash
git submodule update --init providers
export PYTHONPATH="$(pwd)/providers${PYTHONPATH:+:$PYTHONPATH}"
export EXTERNAL_PROVIDERS_DIR="$(pwd)/providers/resources/external_providers"
export RH_SERVER_OKP=http://localhost:8081/solr
# Plus OPENAI_* / EnMaaS vars from Step 2

make run-ogx CONFIG=lightspeed-stack.yaml
```

### Server mode (separate OGX process)

Use `make run` (compose), or follow
[Running OKP RAG tests locally — server mode](../testing/e2e_testing.md#running-okp-rag-tests-locally-server-mode).

Lightspeed Stack has launched successfully when you see this log output:

```log
INFO     2026-03-17 11:20:31,347 uvicorn.error:62 uncategorized: Application startup complete.
INFO     2026-03-17 11:20:31,349 uvicorn.error:224 uncategorized: Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

---

## Step 5: Verify the Stack

Confirm that the full stack (Lightspeed Stack + OGX + OKP) is working
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

> **Note:** The first time you query the system, `hybrid` or `semantic` search may take
> additional time because OGX must download the embedding model used for vector
> search. `keyword` search skips that download.

If you see no RAG context, verify:

1. OKP is up at http://localhost:8081
2. `lightspeed-stack.yaml` lists `okp` under `rag.retrieval.inline.sources` and/or `rag.retrieval.tool.sources` as in Step 3

Local Behave: [Running OKP RAG tests locally](../testing/e2e_testing.md#running-okp-rag-tests-locally).

---
