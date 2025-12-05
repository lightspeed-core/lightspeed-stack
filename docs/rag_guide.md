# RAG Configuration Guide

This document explains how to configure and customize your RAG pipeline using the `llama-stack` configuration YAML file. You will:

* Initialize a vector store
* Download and point to a local embedding model
* Configure an inference provider (LLM)
* Enable Agent-based RAG querying

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

RAG in Lightspeed Core Stack (LCS) is yet only supported via the Agents API. The agent is responsible for planning and deciding when to query the vector index.

The system operates a chain of command. The **Agent** is the orchestrator, using the LLM as its reasoning engine. When a plan requires external information, the Agent queries the **Vector Store**. This is your database of indexed knowledge, which you are responsible for creating before running the stack. The **Embedding Model** is used to convert the queries to vectors. 

> [!NOTE]
> The same Embedding Model should be used to both create the store and to query it.

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
models:
- model_id: <embedding-model-name> # e.g. sentence-transformers/all-mpnet-base-v2
  metadata:
      embedding_dimension: <embedding-dimension> # e.g. 768
  model_type: embedding
  provider_id: sentence-transformers
  provider_model_id: <path-to-embedding-model> # e.g. /home/USER/embedding_model

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
      kvstore:
        type: sqlite
        db_path: <path-to-vector-index> # e.g. /home/USER/vector_db/faiss_store.db
        namespace: null

vector_dbs:
- embedding_dimension: <embedding-dimension> # e.g. 768
  embedding_model: <embedding-model-name> # e.g. sentence-transformers/all-mpnet-base-v2
  provider_id: custom-index
  vector_db_id: <index-id> 
```

Where:
- `provider_model_id` is the path to the folder of the embedding model (or alternatively, the supported embedding model to download)
- `db_path` is the path to the vector index (.db file in this case)
- `vector_db_id` is the index ID used to generate the db

See the full working [config example](examples/openai-faiss-run.yaml) for more details.

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
> The `vector_db_id` (e.g. `rhdocs`) is used to point to the table named `vector_store_rhdocs` in the specified database, which stores the vector embeddings.


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

vector_dbs:
- embedding_dimension: 768
  embedding_model: sentence-transformers/all-mpnet-base-v2
  provider_id: pgvector-example 
  # A unique ID that becomes the PostgreSQL table name, prefixed with 'vector_store_'.
  # e.g., 'rhdocs' will create the table 'vector_store_rhdocs'.
  # If the table was already created, this value must match the ID used at creation.
  vector_db_id: rhdocs
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

models:
- model_id: gpt-test 
  provider_id: openai # This ID is a reference to 'providers.inference'
  model_type: llm
  provider_model_id: gpt-4o-mini

- model_id: sentence-transformers/all-mpnet-base-v2
  metadata:
      embedding_dimension: 768
  model_type: embedding
  provider_id: sentence-transformers # This ID is a reference to 'providers.inference'
  provider_model_id: /home/USER/lightspeed-stack/embedding_models/all-mpnet-base-v2 
  
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
      persistence_store:
        type: sqlite
        db_path: .llama/distributions/ollama/agents_store.db
      responses_store:
        type: sqlite
        db_path: .llama/distributions/ollama/responses_store.db

  safety:
  - provider_id: llama-guard
    provider_type: inline::llama-guard
    config:
      excluded_categories: []

  vector_io:
  - provider_id: ocp-docs 
    provider_type: inline::faiss
    config:
      kvstore:
        type: sqlite
        db_path: /home/USER/lightspeed-stack/vector_dbs/ocp_docs/faiss_store.db
        namespace: null

  tool_runtime:
  - provider_id: rag-runtime 
    provider_type: inline::rag-runtime
    config: {}

# Enable the RAG tool
tool_groups:
- provider_id: rag-runtime
  toolgroup_id: builtin::rag
  args: null
  mcp_endpoint: null

vector_dbs:
- embedding_dimension: 768
  embedding_model: sentence-transformers/all-mpnet-base-v2 
  provider_id: ocp-docs # This ID is a reference to 'providers.vector_io'
  vector_db_id: openshift-index  # This ID was defined during index generation
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
