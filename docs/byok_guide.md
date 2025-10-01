# BYOK (Bring Your Own Knowledge) Feature Documentation

## Overview

The BYOK (Bring Your Own Knowledge) feature in Lightspeed Core enables users to integrate their own knowledge sources into the AI system through Retrieval-Augmented Generation (RAG) functionality. This feature allows the AI to access and utilize custom knowledge bases to provide more accurate, contextual, and domain-specific responses.

---

## Table of Contents

* [What is BYOK?](#what-is-byok)
* [How BYOK Works](#how-byok-works)
* [Prerequisites](#prerequisites)
* [Configuration Guide](#configuration-guide)
  * [Step 1: Prepare Your Knowledge Sources](#step-1-prepare-your-knowledge-sources)
  * [Step 2: Create Vector Database](#step-2-create-vector-database)
  * [Step 3: Configure Embedding Model](#step-3-configure-embedding-model)
  * [Step 4: Configure Llama Stack](#step-4-configure-llama-stack)
  * [Step 5: Enable RAG Tools](#step-5-enable-rag-tools)
* [Supported Vector Database Types](#supported-vector-database-types)
* [Configuration Examples](#configuration-examples)
* [Conclusion](#conclusion)

---

## What is BYOK?

BYOK (Bring Your Own Knowledge) is Lightspeed Core's implementation of Retrieval-Augmented Generation (RAG) that allows you to:

- **Integrate custom knowledge sources**: Add your organization's documentation, manuals, FAQs, or any text-based knowledge
- **Enhance AI responses**: Provide contextual, accurate answers based on your specific domain knowledge
- **Maintain data control**: Keep your knowledge sources within your infrastructure
- **Improve relevance**: Get responses that are tailored to your organization's context and terminology

## How BYOK Works

The BYOK system operates through a sophisticated chain of components:

1. **Agent Orchestrator**: The AI agent acts as the central coordinator, using the LLM as its reasoning engine
2. **RAG Tool**: When the agent needs external information, it queries your custom vector database
3. **Vector Database**: Your indexed knowledge sources, stored as vector embeddings for semantic search
4. **Embedding Model**: Converts queries and documents into vector representations for similarity matching
5. **Context Integration**: Retrieved knowledge is integrated into the AI's response generation process

```mermaid
graph TD
    A[User Query] --> B[AI Agent]
    B --> C{Need External Knowledge?}
    C -->|Yes| D[RAG Tool]
    C -->|No| E[Generate Response]
    D --> F[Vector Database]
    F --> G[Retrieve Relevant Context]
    G --> H[Integrate Context]
    H --> E
    E --> I[Response to User]
```

---

## Prerequisites

Before implementing BYOK, ensure you have:

### Required Tools
- **rag-content tool**: For creating compatible vector databases
  - Repository: https://github.com/lightspeed-core/rag-content
  - Used for indexing your knowledge sources

### System Requirements
- **Embedding Model**: Local or downloadable embedding model
- **LLM Provider**: OpenAI, vLLM, or other supported inference provider

### Knowledge Sources
- **Directly supported**: Markdown (.md) and plain text (.txt) files
- **Requires conversion**: PDFs, AsciiDoc, HTML, and other formats must be converted to markdown or TXT
- Documentation, manuals, FAQs, knowledge bases (after format conversion)

---

## Configuration Guide

### Step 1: Prepare Your Knowledge Sources

1. **Collect your documents**: Gather all knowledge sources you want to include
2. **Convert formats**: Convert non-supported formats to markdown (.md) or plain text (.txt)
   - **PDF conversion**: Use tools like [docling](https://github.com/DS4SD/docling) to convert PDFs to markdown
   - **Adoc conversion**: Use [custom scripts](https://github.com/openshift/lightspeed-rag-content/blob/main/scripts/asciidoctor-text/convert-it-all.py) to convert AsciiDoc to plain text
3. **Organize content**: Structure your converted documents for optimal indexing
4. **Format validation**: Ensure all documents are in supported formats (.md or .txt)

### Step 2: Create Vector Database

Use the `rag-content` tool to create a compatible vector database:
Please refer https://github.com/lightspeed-core/rag-content to create your vector database

**Metadata Configuration:**
When using the `rag-content` tool, you need to create a `custom_processor.py` script to handle document metadata:

1. **Document URL References**: Implement the `url_function` in your `custom_processor.py` to add URL metadata to each document chunk
2. **Title Extraction**: The system automatically extracts the document title from the first line of each file
3. **Custom Metadata**: You can add additional metadata fields as needed for your use case

Example `custom_processor.py` structure:
```python
class CustomMetadataProcessor(MetadataProcessor):

    def __init__(self, url):
        self.url = url

    def url_function(self, file_path: str) -> str:
        # Return a URL for the file, so it can be referenced when used
        # in an answer
        return self.url
```

**Important Notes:**
- The vector database must be compatible with Llama Stack
- Supported formats: 
  - Llama-Stack Faiss Vector-IO
  - Llama-Stack SQLite-vec Vector-IO
- The same embedding model must be used for both creation and querying

### Step 3: Configure Embedding Model

You have two options for configuring your embedding model:

#### Option 1: Use rag-content Download Script (Optional)
You can use the embedding generation step mentioned in the rag-content repo:

```bash
mkdir ./embeddings_model
pdm run python ./scripts/download_embeddings_model.py -l ./embeddings_model/ -r sentence-transformers/all-mpnet-base-v2 
```

#### Option 2: Manual Download and Configuration
Alternatively, you can download your own embedding model and update the path in your YAML configuration:

1. **Download your preferred embedding model** from Hugging Face or other sources
2. **Place the model** in your desired directory (e.g., `/path/to/your/embedding_models/`)
3. **Update the YAML configuration** to point to your model path:

```yaml
models:
  - model_id: sentence-transformers/all-mpnet-base-v2
    metadata:
        embedding_dimension: 768
    model_type: embedding
    provider_id: sentence-transformers
    provider_model_id: /path/to/your/embedding_models/all-mpnet-base-v2
```

**Note**: Ensure the same embedding model is used for both vector database creation and querying.

### Step 4: Configure Llama Stack

Edit your `run.yaml` file to include BYOK configuration:

```yaml
version: 2
image_name: byok-configuration

# Required APIs for BYOK
apis:
- agents
- inference
- vector_io
- tool_runtime
- safety

models:
  # Your LLM model
  - model_id: your-llm-model
    provider_id: openai  # or your preferred provider
    model_type: llm
    provider_model_id: gpt-4o-mini

  # Embedding model for BYOK
  - model_id: sentence-transformers/all-mpnet-base-v2
    metadata:
        embedding_dimension: 768
    model_type: embedding
    provider_id: sentence-transformers
    provider_model_id: /path/to/embedding_models/all-mpnet-base-v2

providers:
  inference:
  # Embedding model provider
  - provider_id: sentence-transformers
    provider_type: inline::sentence-transformers
    config: {}

  # LLM provider (example: OpenAI)
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

  # Vector database configuration
  vector_io:
  - provider_id: your-knowledge-base
    provider_type: inline::faiss  # or remote::pgvector
    config:
      kvstore:
        type: sqlite
        db_path: /path/to/vector_db/faiss_store.db
        namespace: null

  tool_runtime:
  - provider_id: rag-runtime
    provider_type: inline::rag-runtime
    config: {}

# Enable RAG tools
tool_groups:
- provider_id: rag-runtime
  toolgroup_id: builtin::rag

# Vector database configuration
vector_dbs:
- embedding_dimension: 768
  embedding_model: sentence-transformers/all-mpnet-base-v2
  provider_id: your-knowledge-base
  vector_db_id: your-index-id  # ID used during index generation
```

**⚠️ Important**: The `vector_db_id` value must exactly match the ID you provided when creating the vector database using the rag-content tool. This identifier links your Llama Stack configuration to the specific vector database index you created.

### Step 5: Enable RAG Tools

The configuration above automatically enables the RAG tools. The system will:

1. **Detect RAG availability**: Automatically identify when RAG is available
2. **Enhance prompts**: Encourage the AI to use RAG tools

---

## Supported Vector Database Types

### 1. FAISS (Recommended)
- **Type**: Local vector database with SQLite metadata
- **Best for**: Small to medium-sized knowledge bases
- **Configuration**: `inline::faiss`
- **Storage**: SQLite database file

```yaml
vector_io:
- provider_id: faiss-knowledge
  provider_type: inline::faiss
  config:
    kvstore:
      type: sqlite
      db_path: /path/to/faiss_store.db
      namespace: null
```

### 2. pgvector (PostgreSQL)
- **Type**: PostgreSQL with pgvector extension
- **Best for**: Large-scale deployments, shared knowledge bases
- **Configuration**: `remote::pgvector`
- **Requirements**: PostgreSQL with pgvector extension

```yaml
vector_io:
- provider_id: pgvector-knowledge
  provider_type: remote::pgvector
  config:
    host: localhost
    port: 5432
    db: knowledge_db
    user: lightspeed_user
    password: ${env.DB_PASSWORD}
    kvstore:
      type: sqlite
      db_path: .llama/distributions/pgvector/registry.db
```

**pgvector Table Schema:**
- `id` (text): UUID identifier of the chunk
- `document` (jsonb): JSON containing content and metadata
- `embedding` (vector(n)): The embedding vector (n = embedding dimension)

---

## Configuration Examples

### Example 1: OpenAI + FAISS
Complete configuration for OpenAI LLM with local FAISS knowledge base:

```yaml
version: 2
image_name: openai-faiss-byok

apis:
- agents
- inference
- vector_io
- tool_runtime
- safety

models:
- model_id: gpt-4o-mini
  provider_id: openai
  model_type: llm
  provider_model_id: gpt-4o-mini

- model_id: sentence-transformers/all-mpnet-base-v2
  metadata:
      embedding_dimension: 768
  model_type: embedding
  provider_id: sentence-transformers
  provider_model_id: /home/user/embedding_models/all-mpnet-base-v2

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
  - provider_id: company-docs
    provider_type: inline::faiss
    config:
      kvstore:
        type: sqlite
        db_path: /home/user/vector_dbs/company_docs/faiss_store.db
        namespace: null

  tool_runtime:
  - provider_id: rag-runtime
    provider_type: inline::rag-runtime
    config: {}

tool_groups:
- provider_id: rag-runtime
  toolgroup_id: builtin::rag

vector_dbs:
- embedding_dimension: 768
  embedding_model: sentence-transformers/all-mpnet-base-v2
  provider_id: company-docs
  vector_db_id: company-knowledge-index
```

### Example 2: vLLM + pgvector
Configuration for local vLLM inference with PostgreSQL knowledge base:

```yaml
version: 2
image_name: vllm-pgvector-byok

apis:
- agents
- inference
- vector_io
- tool_runtime
- safety

models:
- model_id: meta-llama/Llama-3.1-8B-Instruct
  provider_id: vllm
  model_type: llm
  provider_model_id: null

- model_id: sentence-transformers/all-mpnet-base-v2
  metadata:
      embedding_dimension: 768
  model_type: embedding
  provider_id: sentence-transformers
  provider_model_id: sentence-transformers/all-mpnet-base-v2

providers:
  inference:
  - provider_id: sentence-transformers
    provider_type: inline::sentence-transformers
    config: {}
  - provider_id: vllm
    provider_type: remote::vllm
    config:
      url: http://localhost:8000/v1/
      api_token: your-token-here

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
  - provider_id: enterprise-knowledge
    provider_type: remote::pgvector
    config:
      host: postgres.company.com
      port: 5432
      db: enterprise_kb
      user: rag_user
      password: ${env.POSTGRES_PASSWORD}
      kvstore:
        type: sqlite
        db_path: .llama/distributions/pgvector/registry.db

  tool_runtime:
  - provider_id: rag-runtime
    provider_type: inline::rag-runtime
    config: {}

tool_groups:
- provider_id: rag-runtime
  toolgroup_id: builtin::rag
  args: null
  mcp_endpoint: null

vector_dbs:
- embedding_dimension: 768
  embedding_model: sentence-transformers/all-mpnet-base-v2
  provider_id: enterprise-knowledge
  vector_db_id: enterprise-docs
```

---

## Conclusion

The BYOK (Bring Your Own Knowledge) feature in Lightspeed Core provides powerful capabilities for integrating custom knowledge sources through RAG technology. By following this guide, you can successfully implement and configure BYOK to enhance your AI system with domain-specific knowledge.

For additional support and advanced configurations, refer to:
- [RAG Configuration Guide](rag_guide.md)
- [Llama Stack Documentation](https://llama-stack.readthedocs.io/)
- [rag-content Tool Repository](https://github.com/lightspeed-core/rag-content)

Remember to regularly update your knowledge sources and monitor system performance to maintain optimal BYOK functionality.