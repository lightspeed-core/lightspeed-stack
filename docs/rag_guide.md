# RAG Configuration Guide

This document explains how to configure and customize your RAG pipeline using the `llama-stack` configuration YAML file. You will:

* Initialize a vector store
* Download and point to a local embedding model
* Configure an inference provider (LLM)
* Choose a RAG strategy (Always RAG or Tool RAG)

---

## Table of Contents

* [Introduction](#introduction)
* [Prerequisites](#prerequisites)
   * [Set Up the Vector Database](#set-up-the-vector-database)
   * [Download an Embedding Model](#download-an-embedding-model)
* [Configure Vector Store and Embedding Model](#configure-vector-store-and-embedding-model)
* [Add an Inference Model (LLM)](#add-an-inference-model-llm)
* [Complete Configuration Reference](#complete-configuration-reference)
* [System Prompt Guidance for RAG (as a tool)](#system-prompt-guidance-for-rag-as-a-tool)
* [References](#references)


---

# Introduction

Lightspeed Core Stack (LCS) supports two complementary RAG strategies:

- **Always RAG**: context is fetched from Solr and/or BYOK vector stores and injected into every query before the LLM responds. No tool calls are required.
- **Tool RAG**: the LLM can call the `file_search` tool during generation to retrieve context on demand from BYOK vector stores.

Both strategies can be enabled independently via the `rag` section of `lightspeed-stack.yaml`. See [BYOK Feature Documentation](byok_guide.md) for configuration details.

The **Embedding Model** is used to convert queries and documents into vector representations for similarity matching.

> [!NOTE]
> The same Embedding Model should be used to both create the vector store and to query it.

---

# Prerequisites

## Set Up the Vector Database

Use the [`rag-content`](https://github.com/lightspeed-core/rag-content) repository to build a compatible vector database.

> [!IMPORTANT]
> The resulting DB must be compatible with Llama Stack (e.g., FAISS with SQLite metadata, SQLite-vec). This can be configured when using the tool to generate the index.

---

## Download an Embedding Model

Download a local embedding model such as `sentence-transformers/all-mpnet-base-v2` by using the script in [`rag-content`](https://github.com/lightspeed-core/rag-content) or manually download and place in your desired path.

> [!NOTE]
> Llama Stack can also download a model for you, which will make the first start-up slower. In the YAML configuration file `run.yaml` specify a supported model name as `provider_model_id` instead of a path. LLama Stack will then download the model to the `~/.cache/huggingface/hub` folder.

---

## Configure Vector Store and Embedding Model

Update the `run.yaml` file used by Llama Stack to point to:

* Your downloaded **embedding model**
* Your generated **vector database**

### FAISS example

```yaml
providers:
  inference:
  - provider_id: sentence-transformers
    provider_type: inline::sentence-transformers
    config: {}

  # FAISS vector store
  vector_io:
  - provider_id: custom-index
    provider_type: inline::faiss
    config:
      persistence:
        namespace: vector_io::faiss
        backend: rag_backend  # References storage.backends.rag_backend

storage:
  backends:
    rag_backend:
      type: kv_sqlite
      db_path: <path-to-vector-index>  # e.g. /home/USER/vector_db/faiss_store.db

registered_resources:
  models:
  - model_id: <embedding-model-name> # e.g. sentence-transformers/all-mpnet-base-v2
    metadata:
        embedding_dimension: <embedding-dimension> # e.g. 768
    model_type: embedding
    provider_id: sentence-transformers
    provider_model_id: <path-to-embedding-model> # e.g. /home/USER/embedding_model

  vector_stores:
  - embedding_dimension: <embedding-dimension> # e.g. 768
    embedding_model: <embedding-model-name> # e.g. sentence-transformers/all-mpnet-base-v2
    provider_id: custom-index
    vector_store_id: <index-id> 
```

Where:
- `provider_model_id` is the path to the folder of the embedding model (or alternatively, the supported embedding model to download)
- `db_path` is the path to the vector index (.db file in this case)
- `vector_store_id` is the index ID used to generate the db

See the full working [config example](examples/run.yaml) for more details.

### pgvector example

This example shows how to configure a remote PostgreSQL database with the [pgvector](https://github.com/pgvector/pgvector) extension for storing embeddings.

> You will need to install PostgreSQL with a matching version to pgvector, then log in with `psql` and enable the extension with:
> ```sql
> CREATE EXTENSION IF NOT EXISTS vector;
> ```

Update the connection details (`host`, `port`, `db`, `user`, `password`) to match your PostgreSQL setup.

Each pgvector-backed table follows this schema:

- `id` (`text`): UUID identifier of the chunk
- `document` (`jsonb`): json containing content and metadata associated with the embedding  
- `embedding` (`vector(n)`): the embedding vector, where `n` is the embedding dimension and will match the model's output size (e.g. 768 for `all-mpnet-base-v2`) 

> [!NOTE]
> The `vector_store_id` (e.g. `rhdocs`) is used to point to the table named `vector_store_rhdocs` in the specified database, which stores the vector embeddings.


```yaml
[...]
providers:
  [...]
  vector_io:
  - provider_id: pgvector-example 
    provider_type: remote::pgvector
    config:
      host: localhost
      port: 5432
      db: pgvector_example # PostgreSQL database (psql -d pgvector_example)
      user: lightspeed # PostgreSQL user
      password: password123
      kvstore:
        type: sqlite
        db_path: .llama/distributions/pgvector/pgvector_registry.db

vector_stores:
- embedding_dimension: 768
  embedding_model: sentence-transformers/all-mpnet-base-v2
  provider_id: pgvector-example 
  # A unique ID that becomes the PostgreSQL table name, prefixed with 'vector_store_'.
  # e.g., 'rhdocs' will create the table 'vector_store_rhdocs'.
  # If the table was already created, this value must match the ID used at creation.
  vector_store_id: rhdocs
```

See the full working [config example](examples/openai-pgvector-run.yaml) for more details.

---

## Add an Inference Model (LLM)

### vLLM on RHEL AI (Llama 3.1) example

> [!NOTE]
> The following example assumes that podman's CDI has been properly configured to [enable GPU support](https://podman-desktop.io/docs/podman/gpu).

The [`vllm-openai`](https://hub.docker.com/r/vllm/vllm-openai) Docker image is used to serve the Llama-3.1-8B-Instruct model.  
The following example shows how to run it on **RHEL AI** with `podman`:  

```bash
podman run \
  --device "${CONTAINER_DEVICE}" \
  --gpus ${GPUS} \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  --env "HUGGING_FACE_HUB_TOKEN=${HF_TOKEN}" \
  -p ${EXPORTED_PORT}:8000 \
  --ipc=host \
  docker.io/vllm/vllm-openai:latest \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --enable-auto-tool-choice \
  --tool-call-parser llama3_json --chat-template examples/tool_chat_template_llama3.1_json.jinja
```

> The example command above enables tool calling for Llama 3.1 models.
> For other supported models and configuration options, see the vLLM documentation:
> [vLLM: Tool Calling](https://docs.vllm.ai/en/stable/features/tool_calling.html)

After starting the container edit your `run.yaml` file, matching `model_id` with the model provided in the `podman run` command.

```yaml
[...]
models:
[...]
- model_id: meta-llama/Llama-3.1-8B-Instruct # Same as the model name in the 'podman run' command
  provider_id: vllm
  model_type: llm
  provider_model_id: null

providers:
  [...]
  inference:
  - provider_id: vllm
    provider_type: remote::vllm
    config:
      url: http://localhost:${env.EXPORTED_PORT:=8000}/v1/ # Replace localhost with the url of the vLLM instance
      api_token: <your-key-here> # if any
```

See the full working [config example](examples/vllm-llama-faiss-run.yaml) for more details.

### OpenAI example

Add a provider for your language model (e.g., OpenAI):

```yaml
models:
[...]
- model_id: my-model 
  provider_id: openai
  model_type: llm
  provider_model_id: <model-name> # e.g. gpt-4o-mini

providers:
[...]
  inference:
  - provider_id: openai
    provider_type: remote::openai
    config:
      api_key: ${env.OPENAI_API_KEY}
```

Make sure to export your API key:

```bash
export OPENAI_API_KEY=<your-key-here>
```

> [!NOTE]
> When experimenting with different `models`, `providers` and `vector_dbs`, you might need to manually unregister the old ones with the Llama Stack client CLI (e.g. `llama-stack-client vector_dbs list`)


See the full working [config example](examples/openai-faiss-run.yaml) for more details.

### Azure OpenAI

Not yet supported.

### Ollama

The `remote::ollama` provider can be used for inference. However, it does not support tool calling, including RAG.  
While Ollama also exposes an OpenAI compatible endpoint that supports tool calling, it cannot be used with `llama-stack` due to current limitations in the `remote::openai` provider. 

There is an [ongoing discussion](https://github.com/meta-llama/llama-stack/discussions/3034) about enabling tool calling with Ollama.  
Currently, tool calling is not supported out of the box. Some experimental patches exist (including internal workarounds), but these are not officially released.  

### vLLM Mistral

The RAG tool calls where not working properly when experimenting with `mistralai/Mistral-7B-Instruct-v0.3` on vLLM.

### Solr Vector IO

The OKP (Offline Knowledge Portal) Solr Vector IO is a read-only vector search provider that integrates with Apache Solr for enhanced vector search capabilities. It enables retrieving contextual information from Solr-indexed Red Hat documents to enhance query responses with support for hybrid search and chunk window expansion.


#### How to Enable Solr Vector IO

**1. Configure Llama Stack (`run.yaml`):**

```yaml
providers:
  vector_io:
  - provider_id: solr-vector
    provider_type: remote::solr_vector_io
    config:
      solr_url: http://localhost:8983/solr
      collection_name: portal-rag
      vector_field: chunk_vector
      content_field: chunk
      embedding_dimension: 384
      embedding_model: ${env.EMBEDDING_MODEL_DIR}
      chunk_window_config:
        chunk_parent_id_field: "parent_id"
        chunk_content_field: "chunk_field"
        chunk_index_field: "chunk_index"
        chunk_token_count_field: "num_tokens"
        parent_total_chunks_field: "total_chunks"
        parent_total_tokens_field: "total_tokens"
        chunk_filter_query: "is_chunk:true" 
      persistence:
        namespace: portal-rag
        backend: kv_default

registered_resources:
  vector_stores:
  - vector_store_id: portal-rag
    provider_id: solr-vector
    embedding_model: granite-embedding-30m
    embedding_dimension: 384
```

Note: if the vector database (portal-rag) is not in the persistent data store within the vector_io provider
(e.g. after deleting the llama stack cache) you will need to register the vector database under registered resources:


```yaml
  vector_stores:
    - embedding_dimension: 384
      embedding_model: sentence-transformers/${env.EMBEDDING_MODEL_DIR}
      provider_id: solr-vector
      vector_store_id: portal-rag
```


**2. Configure Lightspeed Stack (`lightspeed-stack.yaml`):**

```yaml
rag:
  always:
    solr:
      enabled: true     # Enable Solr vector IO (Always RAG - pre-query injection)
      offline: true     # Use parent_id for document URLs (offline mode)
                        # Set to false to use reference_url (online mode)
```

**Query Request Example:**
```
curl -sX POST http://localhost:8080/v1/query \
    -H "Content-Type: application/json" \
    -d '{"query" : "how do I secure a nodejs application with keycloak?"}' | jq .
```


**Query Processing:**

1. When Solr is enabled, queries use the `portal-rag` vector store
2. Vector search is performed with configurable parameters:
   - `k`: Number of results (default: 5)
   - `score_threshold`: Minimum similarity score (default: 0.0)  
   - `mode`: Search mode (default: "hybrid")
3. Results include document metadata and source URLs
4. Document URLs are built based on the `offline` setting:
   - **Offline mode**: Uses `parent_id` with Mimir base URL
   - **Online mode**: Uses `reference_url` from document metadata

**Query Filtering:**

To filter the Solr context edit the *chunk_filter_query* field in the
Solr **vector_io** provider in the `run.yaml`. Filters should follow the key:value format:
ex. `"product:*openshift*"`

Note: This static filter is a temporary work-around. 

**Prerequisites:**

- Solr must be running and accessible at the configured URL
  for instructions on how to pull and run the OKP Solr image visit: https://github.com/lightspeed-core/lightspeed-providers/lightspeed_stack_providers/providers/remote/solr_vector_io/solr_vector_io/README.md


**Limitations:**

- This is a **read-only** provider - no insert/delete operations

---

# Complete Configuration Reference

To enable RAG functionality, make sure the `agents`, `tool_runtime`, and `safety` APIs are included and properly configured in your YAML. 

Below is a real example of a working config, with:

* A local `all-mpnet-base-v2` embedding model
* A `FAISS`-based vector store
* `OpenAI` as the inference provider
* Agent-based RAG setup

> [!TIP]
> We recommend starting with a minimal working configuration (one is automatically generated by the `rag-content` tool when generating the database) and extending it as needed by adding more APIs and providers.

```yaml
version: 2
image_name: rag-configuration

apis:
- agents
- inference
- vector_io
- tool_runtime
- safety

providers:
  inference:
  - provider_id: sentence-transformers
    provider_type: inline::sentence-transformers
    config: {}
  - provider_id: openai
    provider_type: remote::openai
    config:
      api_key: ${env.OPENAI_API_KEY}

  agents:
  - provider_id: meta-reference
    provider_type: inline::meta-reference
    config:
      persistence:
        agent_state:
          namespace: agents_state
          backend: kv_default
        responses:
          table_name: agents_responses
          backend: sql_default

  safety:
  - provider_id: llama-guard
    provider_type: inline::llama-guard
    config:
      excluded_categories: []

  vector_io:
  - provider_id: ocp-docs
    provider_type: inline::faiss
    config:
      persistence:
        namespace: vector_io::faiss
        backend: ocp_docs_backend  # References storage.backends

  tool_runtime:
  - provider_id: rag-runtime
    provider_type: inline::rag-runtime
    config: {}

storage:
  backends:
    kv_default:
      type: kv_sqlite
      db_path: ~/.llama/storage/kv_store.db
    sql_default:
      type: sql_sqlite
      db_path: ~/.llama/storage/sql_store.db
    ocp_docs_backend:
      type: kv_sqlite
      db_path: /home/USER/lightspeed-stack/vector_dbs/ocp_docs/faiss_store.db

registered_resources:
  models:
  - model_id: gpt-test
    provider_id: openai
    model_type: llm
    provider_model_id: gpt-4o-mini
  - model_id: sentence-transformers/all-mpnet-base-v2
    model_type: embedding
    provider_id: sentence-transformers
    provider_model_id: /home/USER/lightspeed-stack/embedding_models/all-mpnet-base-v2
    metadata:
      embedding_dimension: 768
  vector_stores:
  - vector_store_id: openshift-index  # This ID was defined during index generation
    provider_id: ocp-docs  # References providers.vector_io
    embedding_model: sentence-transformers/all-mpnet-base-v2
    embedding_dimension: 768
  tool_groups:
  - toolgroup_id: builtin::rag
    provider_id: rag-runtime
```

---

# System Prompt Guidance for RAG (as a tool)

When using RAG, the `knowledge_search` tool must be explicitly referenced in your system prompt. Without clear instructions, models may inconsistently use the tool.

**Tool-Aware sample instruction**:
```text
You are a helpful assistant with access to a 'knowledge_search' tool. When users ask questions, ALWAYS use the knowledge_search tool first to find accurate information from the documentation before answering.
```
---

# References

* [Llama Stack - RAG](https://llama-stack.readthedocs.io/en/latest/building_applications/rag.html)
* [Llama Stack - Configuring a “Stack"](https://llama-stack.readthedocs.io/en/latest/distributions/configuration.html)
* [Llama Stack - Sample configurations](https://github.com/meta-llama/llama-stack/tree/main/llama_stack/distributions)
