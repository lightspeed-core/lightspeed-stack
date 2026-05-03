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
* [Step 2: Setup llamastack config environment variables](#step-2-setup-llamamstack-config-environment-variables)
* [Step 3: Install Lightspeed Stack Dependencies](#step-3-install-lightspeed-stack-dependencies)
* [Step 4: Configure Lightspeed Stack](#step-4-configure-lightspeed-stack)
* [Step 5: Launch Lightspeed Stack](#step-5-launch-lightspeed-stack)
* [Step 6: Verify the Stack](#step-6-verify-the-stack)

---

## Introduction

OKP (Offline Knowledge Portal) provides a Solr-backed RAG source that
Lightspeed Stack can use for both **Inline RAG** (context injected before the
LLM request) and **Tool RAG** (context retrieved on demand via the
`file_search` tool). This guide walks through deploying the OKP container,
enriching your Llama Stack config from Lightspeed Stack settings, and
validating that queries return referenced chunks.

---

## Prerequisites

* [lightspeed-stack repository](https://github.com/lightspeed-core/lightspeed-stack) cloned
* [lightspeed-providers repository](https://github.com/lightspeed-core/lightspeed-providers) cloned
* [Podman](https://podman.io/) (or Docker) to run the OKP image
* [uv](https://docs.astral.sh/uv/) for Python dependency management
* An OpenAI API key (for inference when using OpenAI in your run config)

---

## Step 1: Launch OKP

> **Warning:** The image referenced below is a **prototype**. The official OKP
> RAG image is expected in **late March / early April** of 2026.

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

> **Note:** Lightspeed stack will automatically enrich the llamastack
> configuration to add the necessary providers/resources for referencing OKP.
> This assumes your OKP instance is running on localhost:8081.  If you need a
> different OKP url, you can set the SOLR_URL environment variable with the
> correct url prior to launching Lightspeed stack and that value will be used
> instead.
---

## Step 2: Setup llamastack config environment variables

Set the required environment variables. The external providers path must point
to the `external_providers` content inside the
[lightspeed-providers](https://github.com/lightspeed-core/lightspeed-providers/tree/main/lightspeed_stack_providers/)
repository:

```bash
export EXTERNAL_PROVIDERS_DIR=../lightspeed-providers/resources/external_providers
export OPENAI_API_KEY=<your-openai-api-key>
export RH_SERVER_OKP=http://localhost:8081
```

Adjust `EXTERNAL_PROVIDERS_DIR` if your lightspeed-providers repo is in a
different location relative to your lightspeed-stack directory.

---

## Step 3: Install Lightspeed Stack Dependencies

Then install dependencies and custom providers:

```bash
uv sync --group dev --group llslibdev
uv pip install -e ../lightspeed-providers # Path to lightspeed-providers repo
```

* **`uv sync`**: Installs project and dev/llslibdev groups so that the app and tooling run correctly.
* **`uv pip install -e ../lightspeed-providers`**: Installs the lightspeed stack providers from the local clone of the repository.  Adjust the directory path as needed.

> **Note:** Running `uv sync` will remove the lightspeed-providers dependency
> installed by the `uv pip install` command, so you will need to rerun the `uv
> pip install` command if you rerun `uv sync`.

---

## Step 4: Configure Lightspeed Stack

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

If you want to filter the docs to a specific product, you can include a query
filter such as:

```yaml
okp:
  offline: true
  chunk_filter_query: "product:*openshift*"
```

When you launch Lightspeed stack it will augment the Llamastack run.yaml with
configuration for OKP.

### Configure Lightspeed Stack for library mode

For the simplest local development, configure `lightspeed-stack.yaml` to
consume Llama Stack in library mode:

```yaml
llama_stack:
  ...
  use_as_library_client: true
  library_client_config_path: run.yaml
  # Comment these lines out if present
  # url: http://lama-stack:87321
  # api_key: xyzzy
  ...
```

---

## Step 5: Launch Lightspeed Stack

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

## Step 6: Verify the Stack

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
