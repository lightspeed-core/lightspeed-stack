# Lightspeed Core Providers

Lightspeed Core Stack (LCS) builds on top of llama-stack and its provider system.  
Any llama-stack provider can be enabled in LCS with minimal effort by installing the required dependencies and updating llama-stack configuration in `run.yaml` file.  

This document catalogs all available llama-stack providers and indicates which ones are officially supported in the current LCS version. It also provides a step-by-step guide on how to enable any llama-stack provider in LCS.  


- [Inference Providers](#inference-providers)
- [Agent Providers](#agent-providers)
- [Evaluation Providers](#evaluation-providers)
- [DatasetIO Providers](#datasetio-providers)
- [Safety Providers](#safety-providers)
- [Scoring Providers](#scoring-providers)
- [Telemetry Providers](#telemetry-providers)
- [Post Training Providers](#post-training-providers)
- [VectorIO Providers](#vectorio-providers)
- [Tool Runtime Providers](#tool-runtime-providers)
- [Files Providers](#files-providers)
- [Batches Providers](#batches-providers)
- [How to Enable a Provider](#enabling-a-llama-stack-provider)

The tables below summarize each provider category, containing the following atributes:

- **Name** – Provider identifier in llama-stack  
- **Type** – `inline` (runs inside LCS) or `remote` (external service)  
- **Pip Dependencies** – Required Python packages  
- **Supported in LCS** – Current support status (`✅` / `❌`)  
 


## Inference Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| meta-reference | inline | `accelerate`, `fairscale`, `torch`, `torchvision`, `transformers`, `zmq`, `lm-format-enforcer`, `sentence-transformers`, `torchao==0.8.0`, `fbgemm-gpu-genai==1.1.2` | ❌ |
| sentence-transformers | inline | `torch torchvision torchao>=0.12.0 --extra-index-url https://download.pytorch.org/whl/cpu`, `sentence-transformers --no-deps` | ❌ |
| anthropic | remote | `litellm` | ❌ |
| azure | remote | `litellm` | ✅ |
| bedrock | remote | `boto3` | ❌ |
| cerebras | remote | `cerebras_cloud_sdk` | ❌ |
| databricks | remote | — | ❌ |
| fireworks | remote | `fireworks-ai<=0.17.16` | ❌ |
| gemini | remote | `litellm` | ❌ |
| groq | remote | `litellm` | ❌ |
| hf::endpoint | remote | `huggingface_hub`, `aiohttp` | ❌ |
| hf::serverless | remote | `huggingface_hub`, `aiohttp` | ❌ |
| llama-openai-compat | remote | `litellm` | ❌ |
| nvidia | remote | — | ❌ |
| ollama | remote | `ollama`, `aiohttp`, `h11>=0.16.0` | ❌ |
| openai | remote | `litellm` | ✅ |
| passthrough | remote | — | ❌ |
| runpod | remote | — | ❌ |
| sambanova | remote | `litellm` | ❌ |
| tgi | remote | `huggingface_hub`, `aiohttp` | ❌ |
| together | remote | `together` | ❌ |
| vertexai | remote | `litellm`, `google-cloud-aiplatform` | ❌ |
| watsonx | remote | `ibm_watsonx_ai` | ❌ |

Red Hat providers:

| Name | Version Tested | Type | Pip Dependencies | Supported in LCS |
|---|---|---|---|:---:|
| RHAIIS (vllm) | 3.2.3 (on RHEL 9.20250429.0.4) | remote | `openai` | ✅ |
| RHEL AI (vllm) | 1.5.2 | remote | `openai` | ✅ |

### Azure Provider - Entra ID Authentication Guide

Lightspeed Core supports secure authentication using Microsoft Entra ID (formerly Azure Active Directory) for the Azure Inference Provider. This allows you to connect to Azure OpenAI without using API keys, by authenticating through your organization’s Azure identity.

#### Lightspeed Core configuration requirements

To enable Entra ID authentication, the `azure_entra_id` block must be included in your LCS configuration, and all three attributes — `tenant_id`, `client_id`, and `client_secret` — are required. The authentication will not work if any of them is missing:

```yaml
azure_entra_id:
  tenant_id: ${env.AZURE_TENANT_ID}
  client_id: ${env.AZURE_CLIENT_ID}
  client_secret: ${env.AZURE_CLIENT_SECRET}
```
**Note:** We strongly recommend to load the secrets from environment variables or secrets.

#### Llama Stack Configuration Requirements

Because Lightspeed builds on top of Llama Stack, certain configuration fields are required to satisfy the base Llama Stack schema — even though they are not used when Entra ID authentication is enabled. Specifically, the config block for the Azure provider must include `api_key`, `api_base`, and `api_version`.

While `api_key` is not used in Entra ID mode, it must still be set to a dummy value because Llama Stack validates its presence. The `api_base` and `api_version` fields remain required and are used in Entra ID authentication.

```yaml
inference:
  - provider_id: azure
    provider_type: remote::azure
    config:
      api_key: ${AZURE_API_KEY:=}       # Required but not used for Entra ID
      api_base: ${AZURE_API_BASE}
      api_version: 2025-01-01-preview
```
**Note:** Llama Stack currently supports only static API key authentication through the LiteLLM SDK. Lightspeed extends this behavior by dynamically injecting Entra ID access tokens into each request, enabling full compatibility while maintaining schema compliance with the Llama Stack configuration.

#### Access Token Lifecycle and Managment
When the service starts or an inference request is made:
1. The system reads your Entra ID configuration.
1. It checks whether a valid access token already exists:
    - If the token does not exist or the current token has expired, the system automatically requests a new token from Microsoft Entra ID using your credentials.
    - If a valid token is still active, it is reused — no new request is made.
1. The access token grants access to Azure OpenAI Services.
1. Tokens are automatically refreshed as needed before they expire. Access tokens are typically valid for 1 hour, and this process happens entirely in the background without any manual action.

---

## Agent Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| meta-reference | inline | `matplotlib`, `pillow`, `pandas`, `scikit-learn`, `mcp>=1.8.1` `aiosqlite`, `psycopg2-binary`, `redis`, `pymongo` | ✅ |

---

## Evaluation Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| meta-reference | inline | `tree_sitter`, `pythainlp`, `langdetect`, `emoji`, `nltk` | ✅ |
| meta-reference | remote | `requests` | ❌ |

---

## Datasetio Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| localfs | inline | `pandas` | ✅ |
| huggingface | remote | `datasets>=4.0.0` | ✅ |
| nvidia | remote | `datasets>=4.0.0` | ❌ |

---

## Safety Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| code-scanner | inline | `codeshield` | ❌ |
| llama-guard | inline | — | ✅ |
| prompt-guard | inline | `transformers[accelerate]`, `torch --index-url https://download.pytorch.org/whl/cpu` | ❌ |
| bedrock | remote | `boto3` | ❌ |
| nvidia | remote | `requests` | ❌ |
| sambanova | remote | `litellm`, `requests` | ❌ |

---

## Scoring Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| basic | inline | `requests` | ✅ |
| llm-as-judge | inline | — | ✅ |
| braintrust | inline | `autoevals` | ✅ |

---

## Telemetry Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| meta-reference | inline | `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` | ✅ |

---
## Post Training Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| torchtune-cpu | inline | `numpy`, `torch torchtune>=0.5.0`, `torchao>=0.12.0 --extra-index-url https://download.pytorch.org/whl/cpu`| ❌ |
| torchtune-gpu | inline | `numpy`,`torch torchtune>=0.5.0`, `torchao>=0.12.0` | ❌ |
| huggingface-gpu | inline | `trl`, `transformers`, `peft`, `datasets>=4.0.0`, `torch` | ✅ |
| nvidia | remote | `requests`, `aiohttp` | ❌ |

---
## VectorIO Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| meta-reference | inline | `faiss-cpu` | ❌ |
| chromadb | inline | `chromadb` | ❌ |
| faiss | inline | `faiss-cpu` | ✅ |
| milvus | inline | `pymilvus>=2.4.10` | ❌ |
| qdrant | inline | `qdrant-client` | ❌ |
| sqlite-vec | inline | `sqlite-vec` | ❌ |
| chromadb | remote | `chromadb-client` | ❌ |
| milvus | remote | `pymilvus>=2.4.10` | ❌ |
| pgvector | remote | `psycopg2-binary` | ❌ |
| qdrant | remote | `qdrant-client` | ❌ |
| weaviate | remote | `weaviate-client` | ❌ |

---

## Tool Runtime Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| rag-runtime | inline | `chardet`,`pypdf`, `tqdm`, `numpy`, `scikit-learn`, `scipy`, `nltk`, `sentencepiece`, `transformers` | ❌ |
| bing-search | remote | `requests` | ❌ |
| brave-search | remote | `requests` | ❌ |
| model-context-protocol | remote | `mcp>=1.8.1` | ✅ |
| tavily-search | remote | `requests` | ❌ |
| wolfram-alpha | remote | `requests` | ❌ |

---

## Files Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| localfs | inline | `sqlalchemy[asyncio]`, `aiosqlite`, `asyncpg` | ❌ |
| s3 | remote | `sqlalchemy[asyncio]`, `aiosqlite`, `asyncpg`, `boto3` | ❌ |

---

## Batches Providers

| Name | Type | Pip Dependencies | Supported in LCS |
|---|---|---|:---:|
| reference | inline | `openai` | ❌ |

---

## Enabling a Llama Stack Provider

1. **Add provider dependencies** 

    Run the following command to find out required dependencies for the desired provider (or check the tables above):
    ```bash
    uv run llama stack list-providers
    ```
    Edit your `pyproject.toml` and add the required pip packages for the provider into `llslibdev` section:
   ```toml
   llslibdev = [
     "openai>=1.0.0",
     "pymilvus>=2.4.10",
     
     # add your dependencies here
   ]
   ```

1. **Update project dependencies**

    Run the following command to update project dependencies:
    ```bash
    uv sync --group llslibdev
    ```
1. **Update llama-stack configuration**
    
    Update the llama-stack configuration in `run.yaml` as follows:
    
    Check if the corresponding API of added provider is listed in `apis` section.
    ```yaml
    apis:
        - inference
        - agents
        - eval
        ...
        # add api here if not served
    ```
    Add the provider instance under the **corresponding**       providers section:
    ```yaml
    providers:
        inference:
            - provider_id: openai
            provider_type: remote::openai
            config:
                api_key: ${env.OPENAI_API_KEY}

        agents:
            ...

        eval:
            ...       
    ```
    **Note:** The `provider_type` attribute uses schema `<type>::<name>` and comes from the deffinition on upstream.
    The `provider_id` is your local label.

    Some of APIs are associated with a set of **Resources**. Here is the mapping of APIs to resources:

    - **Inference**, **Eval** and **Post Training** are associated with **Model** resources.
    - **Safety** is associated with **Shield** resources.
    - **Tool Runtime** is associated with **ToolGroup** resources.
    - **DatasetIO** is associated with **Dataset** resources.
    - **VectorIO** is associated with **VectorDB** resources.
    - **Scoring** is associated with **ScoringFunction** resources.
    - **Eval** is associated with **Benchmark** resources.

    Update corresponding resources of the added provider in dedicated section.
    ```yaml
    providers:
        ...

    models:
    - model_id: gpt-4-turbo  # local label
        provider_id: openai
        model_type: llm
        provider_model_id: gpt-4-turbo  # provider label
    
    shields:
        ...
    ```
    **Note** It is necessary for llama-stack to know which resources to use for a given provider. This means you need to explicitly register resources (including models) before you can use them with the associated APIs.

1. **Provide credentials / secrets**  
   Make sure any required API keys or tokens are available to the stack. For example, export environment variables or configure them in your secret manager:
   ```bash
   export OPENAI_API_KEY="sk_..."
    ```
    Llama Stack supports environment variable substitution in configuration values using the `${env.VARIABLE_NAME}` syntax. 

1. **Rerun your llama-stack service**

    If you are running llama-stack as a standalone service, restart it with:
    ```bash
    uv run llama stack run run.yaml
    ```
    If you are running it within Lightspeed Core, use:
    ```bash
    make run
    ```

1. **Verify the provider**

    Check the logs to ensure the provider initialized successfully.  
    Then make a simple API call to confirm it is active and responding as expected.  

---

For a deeper understanding, see the [official llama-stack providers documentation](https://llamastack.github.io/docs/providers).
