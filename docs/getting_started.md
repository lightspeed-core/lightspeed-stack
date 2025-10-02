# Getting Started

### Llama Stack used as a library

It is possible to run Lightspeed Core Stack service with Llama Stack "embedded" as a Python library. This means that just one process will be running and only one port (for example 8080) will be accessible.




#### Prerequisites

1. Python 3.12 or 3.13
1. `pip` tool installed
1. `jq` and `curl` tools installed

#### Installation of all required tools

1. `pip install --user uv`
1. `sudo dnf install curl jq`

#### Installing dependencies for Llama Stack

1. Clone LCS repository
1. Add and install all required dependencies
    ```bash
    uv add \
    "llama-stack==0.2.22" \
    "fastapi>=0.115.12" \
    "opentelemetry-sdk>=1.34.0" \
    "opentelemetry-exporter-otlp>=1.34.0" \
    "opentelemetry-instrumentation>=0.55b0" \
    "aiosqlite>=0.21.0" \
    "litellm>=1.72.1" \
    "uvicorn>=0.34.3" \
    "blobfile>=3.0.0" \
    "datasets>=3.6.0" \
    "sqlalchemy>=2.0.41" \
    "faiss-cpu>=1.11.0" \
    "mcp>=1.9.4" \
    "autoevals>=0.0.129" \
    "psutil>=7.0.0" \
    "torch>=2.7.1" \
    "peft>=0.15.2" \
    "trl>=0.18.2"
    ```
1. Check if all dependencies are really installed
    ```text
    Resolved 195 packages in 1.19s
          Built lightspeed-stack @ file:///tmp/ramdisk/lightspeed-stack
    Prepared 12 packages in 1.72s
    Installed 60 packages in 4.47s
     + accelerate==1.9.0
     + autoevals==0.0.129
     + blobfile==3.0.0
     + braintrust-core==0.0.59
     + chevron==0.14.0
     + datasets==4.0.0
     + dill==0.3.8
     + faiss-cpu==1.11.0.post1
     + fsspec==2025.3.0
     + greenlet==3.2.3
     + grpcio==1.74.0
     + httpx-sse==0.4.1
     ~ lightspeed-stack==0.2.0 (from file:///tmp/ramdisk/lightspeed-stack)
     + litellm==1.74.9.post1
     + lxml==6.0.0
     + mcp==1.12.2
     + mpmath==1.3.0
     + multiprocess==0.70.16
     + networkx==3.5
     + nvidia-cublas-cu12==12.6.4.1
     + nvidia-cuda-cupti-cu12==12.6.80
     + nvidia-cuda-nvrtc-cu12==12.6.77
     + nvidia-cuda-runtime-cu12==12.6.77
     + nvidia-cudnn-cu12==9.5.1.17
     + nvidia-cufft-cu12==11.3.0.4
     + nvidia-cufile-cu12==1.11.1.6
     + nvidia-curand-cu12==10.3.7.77
     + nvidia-cusolver-cu12==11.7.1.2
     + nvidia-cusparse-cu12==12.5.4.2
     + nvidia-cusparselt-cu12==0.6.3
     + nvidia-nccl-cu12==2.26.2
     + nvidia-nvjitlink-cu12==12.6.85
     + nvidia-nvtx-cu12==12.6.77
     + opentelemetry-api==1.36.0
     + opentelemetry-exporter-otlp==1.36.0
     + opentelemetry-exporter-otlp-proto-common==1.36.0
     + opentelemetry-exporter-otlp-proto-grpc==1.36.0
     + opentelemetry-exporter-otlp-proto-http==1.36.0
     + opentelemetry-instrumentation==0.57b0
     + opentelemetry-proto==1.36.0
     + opentelemetry-sdk==1.36.0
     + opentelemetry-semantic-conventions==0.57b0
     + peft==0.16.0
     + polyleven==0.9.0
     + psutil==7.0.0
     + pyarrow==21.0.0
     + pycryptodomex==3.23.0
     + pydantic-settings==2.10.1
     + safetensors==0.5.3
     + setuptools==80.9.0
     + sqlalchemy==2.0.42
     + sse-starlette==3.0.2
     + sympy==1.14.0
     + tokenizers==0.21.4
     + torch==2.7.1
     + transformers==4.54.1
     + triton==3.3.1
     + trl==0.20.0
     + wrapt==1.17.2
     + xxhash==3.5.0
    ```

#### Llama Stack configuration

Llama Stack needs to be configured properly. For using the default runnable Llama Stack a file named `run.yaml` with following content needs to be created:

```yaml
version: '2'
image_name: minimal-viable-llama-stack-configuration

apis:
  - agents
  - datasetio
  - eval
  - inference
  - post_training
  - safety
  - scoring
  - telemetry
  - tool_runtime
  - vector_io
benchmarks: []
container_image: null
datasets: []
external_providers_dir: null
inference_store:
  db_path: .llama/distributions/ollama/inference_store.db
  type: sqlite
logging: null
metadata_store:
  db_path: .llama/distributions/ollama/registry.db
  namespace: null
  type: sqlite
providers:
  agents:
  - config:
      persistence_store:
        db_path: .llama/distributions/ollama/agents_store.db
        namespace: null
        type: sqlite
      responses_store:
        db_path: .llama/distributions/ollama/responses_store.db
        type: sqlite
    provider_id: meta-reference
    provider_type: inline::meta-reference
  datasetio:
  - config:
      kvstore:
        db_path: .llama/distributions/ollama/huggingface_datasetio.db
        namespace: null
        type: sqlite
    provider_id: huggingface
    provider_type: remote::huggingface
  - config:
      kvstore:
        db_path: .llama/distributions/ollama/localfs_datasetio.db
        namespace: null
        type: sqlite
    provider_id: localfs
    provider_type: inline::localfs
  eval:
  - config:
      kvstore:
        db_path: .llama/distributions/ollama/meta_reference_eval.db
        namespace: null
        type: sqlite
    provider_id: meta-reference
    provider_type: inline::meta-reference
  inference:
    - provider_id: openai
      provider_type: remote::openai
      config:
        api_key: ${env.OPENAI_API_KEY}
  post_training:
  - config:
      checkpoint_format: huggingface
      device: cpu
      distributed_backend: null
    provider_id: huggingface
    provider_type: inline::huggingface
  safety:
  - config:
      excluded_categories: []
    provider_id: llama-guard
    provider_type: inline::llama-guard
  scoring:
  - config: {}
    provider_id: basic
    provider_type: inline::basic
  - config: {}
    provider_id: llm-as-judge
    provider_type: inline::llm-as-judge
  - config:
      openai_api_key: '********'
    provider_id: braintrust
    provider_type: inline::braintrust
  telemetry:
  - config:
      service_name: 'lightspeed-stack'
      sinks: sqlite
      sqlite_db_path: .llama/distributions/ollama/trace_store.db
    provider_id: meta-reference
    provider_type: inline::meta-reference
  tool_runtime:
    - provider_id: model-context-protocol
      provider_type: remote::model-context-protocol
      config: {}
  vector_io:
  - config:
      kvstore:
        db_path: .llama/distributions/ollama/faiss_store.db
        namespace: null
        type: sqlite
    provider_id: faiss
    provider_type: inline::faiss
scoring_fns: []
server:
  auth: null
  host: null
  port: 8321
  quota: null
  tls_cafile: null
  tls_certfile: null
  tls_keyfile: null
shields: []
vector_dbs: []

models:
  - model_id: gpt-4-turbo
    provider_id: openai
    model_type: llm
    provider_model_id: gpt-4-turbo
```

#### LCS configuration to use Llama Stack in library mode

Create a file named lightspeed-stack.yaml with this content.

```yaml
name: Lightspeed Core Service (LCS)
service:
  host: localhost
  port: 8080
  auth_enabled: false
  workers: 1
  color_log: true
  access_log: true
llama_stack:
  use_as_library_client: true
  library_client_config_path: run.yaml
user_data_collection:
  feedback_enabled: true
  feedback_storage: "/tmp/data/feedback"
  transcripts_enabled: true
  transcripts_storage: "/tmp/data/transcripts"

authentication:
  module: "noop"
```

#### Start LCS

1. Export OpenAI key by using the following command:
    ```bash
    export OPENAI_API_KEY="sk-foo-bar-baz"
    ```
1. Run the following command
    ```bash
    make run
    ```
1. Check the output
    ```text
    uv run src/lightspeed_stack.py
    Using config run.yaml:
    apis:
    - agents
    - datasetio
    - eval
    - inference
    - post_training
    - safety
    - scoring
    - telemetry
    - tool_runtime
    - vector_io
    [07/30/25 20:01:53] INFO     Initializing app                                                                                 main.py:19
    [07/30/25 20:01:54] INFO     Including routers                                                                                main.py:68
                        INFO     Registering MCP servers                                                                          main.py:81
                        DEBUG    No MCP servers configured, skipping registration                                               common.py:36
                        INFO     Setting up model metrics                                                                         main.py:84
    [07/30/25 20:01:54] DEBUG    Set provider/model configuration for openai/openai/chatgpt-4o-latest to 0                       utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-3.5-turbo to 0                           utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-3.5-turbo-0125 to 0                      utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-3.5-turbo-instruct to 0                  utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-4 to 0                                   utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-4-turbo to 0                             utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-4o to 0                                  utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-4o-2024-08-06 to 0                       utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-4o-audio-preview to 0                    utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/gpt-4o-mini to 0                             utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/o1 to 0                                      utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/o1-mini to 0                                 utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/o3-mini to 0                                 utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/o4-mini to 0                                 utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/text-embedding-3-large to 0                  utils.py:45
                        DEBUG    Set provider/model configuration for openai/openai/text-embedding-3-small to 0                  utils.py:45
                        INFO     App startup complete                                                                             main.py:86
    ```

#### Check if service runs

```bash
curl localhost:8080/v1/models | jq .
```

```json
{
  "models": [
    {
      "identifier": "gpt-4-turbo",
      "metadata": {},
      "api_model_type": "llm",
      "provider_id": "openai",
      "type": "model",
      "provider_resource_id": "gpt-4-turbo",
      "model_type": "llm"
    }
  ]
}
```

### Configuring MCP Servers

Lightspeed developers can quickly enable external tool calling using MCP servers in LCS. MCP (Model Context Protocol) is a standard for exposing external tools in a structured way so AI agents can call them reliably. An MCP server hosts one or more tools and exposes them over a network endpoint. In LCS, the AI agent can leverage these servers to execute tools: LCS routes tool calls to the appropriate MCP server and uses the tool output to generate more accurate responses.

Each MCP server provides a list of tools along with structured metadata, including name, description, and inputSchema. Using the standard `tools/list` method, LCS automatically fetches this metadata so the AI agent can evaluate user prompts and dynamically select the appropriate tool for a given request. For more details, see the [MCP documentation](https://modelcontextprotocol.io/docs/learn/architecture#how-this-works-in-ai-applications).

The following step-by-step guide shows how to set up and integrate MCP servers into LCS:

#### Step 1: Run your MCP servers
MCP servers host one or more tools and expose them over a network endpoint. They can be run locally for development or hosted externally for production.

#### Step 2: Configure LCS to know about your MCP servers
MCP servers must be defined in the `mcp_servers` section of your `lightspeed-stack.yaml`.
Example (all MCP servers running locally):

```yaml
mcp_servers:
  - name: "filesystem-tools"
    provider_id: "model-context-protocol"
    url: "http://localhost:3000"
  - name: "git-tools"
    provider_id: "model-context-protocol"
    url: "http://localhost:3001"
  - name: "database-tools"
    provider_id: "model-context-protocol"
    url: "http://localhost:3002"
```

**Important**: Only MCP servers defined in the `lightspeed-stack.yaml` configuration are available to the AI agents. Tools configured in the llama-stack `run.yaml` are not accessible to LCS agents.

#### Step 3: Pass authentication or metadata via MCP headers (optional)

Some MCP servers require authentication tokens, API keys, or other metadata. These can be passed **per request** using the `MCP-HEADERS` HTTP header. LCS will forward these headers when invoking the tool, allowing the MCP server to authenticate requests or receive additional context.
Example:

```bash
curl -X POST "http://localhost:8080/v1/query" \
  -H "Content-Type: application/json" \
  -H "MCP-HEADERS: {\"filesystem-tools\": {\"Authorization\": \"Bearer token123\"}}" \
  -d '{"query": "List files in /tmp"}'
```

#### Step 4: Verify connectivity
After starting the MCP servers and updating `lightspeed-stack.yaml`, test by sending a prompt to the AI agent. LCS evaluates the prompt against available tools’ metadata, selects the appropriate tool, calls the corresponding MCP server, and uses the result to generate more accurate agent response.
