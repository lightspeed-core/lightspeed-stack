# Lightspeed Core

![LCORE](images/lcore.jpg)

---

Vladimír Kadlec, 
vkadlec@redhat.com

Pavel Tišnovský,
ptisnovs@redhat.com

---

## Agenda

* Llama Stack
* Lightspeed Core
* Evaluation

---

## Llama Stack

![LCORE](images/llama_stack_logo.png)

---

## What is Llama Stack?

* Framework to create applications with AI
    - chat bots
    - generative AI
    - training and evaluation tools
* It's a real framework independent on programming language
    - providers
    - RAG, quota control, guardrails, metrics

---

![LS1](images/llama_stack.png)

---

### Easiest usage of Llama Stack

* LLM call
* Processing answer from LLM
* "chatbot v.0.0.1"

---

### In reality, the requirements are larger

![confusion](images/notation_traffic.jpg)

---

### In reality, the requirements are larger

* RAG
* Conversation history
* Conversation forking
* Conversation summary
* Facts about user
* MCP calls
* Quota handling
* Answers validation
* Responses validation
* Multiple LLM calls
* Responses evaluation

---

### 🤖 LLM Inference
* Generates AI responses (streaming and non-streaming)
* Handles complex streaming with tool calls and content interleaving

---

### 🛡️  Safety & Content Filtering
* Retrieves input/output shields for content filtering
* Provides safety mechanisms for AI responses

---

## 🔧 Tools & Agents

* Manages agent sessions (create, retrieve, delete)
* Supports tool-augmented AI interactions
* Enables agents to call external tools/functions

---

### 📚 RAG Support
* Integration with vector databases
* Enables Retrieval-Augmented Generation for better context

---
### 🎯 Model & Provider Management
* Lists available models and providers
* Allows runtime switching between different LLM providers (OpenAI, Azure, etc.)

---

### API and providers

* Fully configurable
* It is possible to retrieve list of APIs
* It is possible to retrieve list of providers
* Warning: more dependencies for providers

---

### Providers (1/2)

<table>
<tr><th>Name</th><th>Meaning</th></tr>
<tr><td>Agents</td><td>interacting with agents</td></tr>
<tr><td>Inference</td><td>interface to LLMs and embedding models</td></tr>
<tr><td>VectorIO</td><td>originally vector DB I/O but now support fulltext search</td></tr>
</table>

---

### Providers (2/2)

<table>
<tr><th>Name</th><th>Meaning</th></tr>
<tr><td>Safety</td><td>questions with improper content detection</td></tr>
<tr><td>Telemetry</td><td>telemetry (OpenTelemetry etc.)</td></tr>
<tr><td>Eval</td><td>evaluation of model answers etc.</td></tr>
<tr><td>DatasetIO</td><td>file I/O (datasets etc.)</td></tr>
</table>

---

![LS-providers](images/llama_stack_providers.svg)

---

### Communication with Llama Stack

* CLI
* REST API
* As a common library (Python etc.)
* Llama Stack client
    - supports REST API
    - support running as a library (async)

---

### Llama Stack client

* Python
* Swift
* Kotlin
* Node.js

---

### Llama Stack as a library

![LS1](images/llama_stack_as_library.svg)

---

### Llama Stack as a service

![LS1](images/llama_stack_as_service.svg)

---

### Run inside container

![LS1](images/llama_stack_in_container.svg)

---

### Llama Stack installation

---

Python ecosystem

```
pdm init
pdm add llama-stack fastapi opentelemetry-sdk \
opentelemetry-exporter-otlp opentelemetry-instrumentation \
aiosqlite litellm uvicorn blobfile
```

---

### Generated project file

```toml
[project]
name = "llama-stack-demo"
version = "0.1.0"
description = "Default template for PDM package"
authors = []
dependencies = [
    "llama-stack==0.2.20",
    "llama-stack-client==0.2.20",
    "opentelemetry-sdk>=1.34.0",
    "opentelemetry-exporter-otlp>=1.34.0",
    "opentelemetry-instrumentation>=0.55b0",
    ...
    ...
    ...
]
requires-python = "==3.12.*"
readme = "README.md"
license = {text = "MIT"}


[tool.pdm]
distribution = false
```

---

### Starting Llama Stack

```bash
uv run llama stack
```

---

### List of Llama Stack API

```bash
uv run llama stack list-apis
```

---

```text
┏━━━━━━━━━━━━━━━━━━━┓
┃ API               ┃
┡━━━━━━━━━━━━━━━━━━━┩
│ providers         │
├───────────────────┤
│ inference         │
├───────────────────┤
│ safety            │
├───────────────────┤
│ agents            │
├───────────────────┤
│ batches           │
├───────────────────┤
│ vector_io         │
├───────────────────┤
│ datasetio         │
├───────────────────┤
│ scoring           │
├───────────────────┤
│ eval              │
├───────────────────┤
│ post_training     │
├───────────────────┤
│ tool_runtime      │
├───────────────────┤
│ telemetry         │
├───────────────────┤
│ models            │
├───────────────────┤
│ shields           │
├───────────────────┤
│ vector_dbs        │
├───────────────────┤
│ datasets          │
├───────────────────┤
│ scoring_functions │
├───────────────────┤
│ benchmarks        │
├───────────────────┤
│ tool_groups       │
├───────────────────┤
│ files             │
├───────────────────┤
│ inspect           │
└───────────────────┘
```

---

### List of providers

```bash
uv run llama stack list-providers
```

---

```text
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ API Type      ┃ Provider Type                  ┃ PIP Package Dependencies                                                                                   ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ agents        │ inline::meta-reference         │ matplotlib,pillow,pandas,scikit-learn,mcp>=1.8.1,aiosqlite,psycopg2-binary,redis,pymongo                   │
├───────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ batches       │ inline::reference              │ openai                                                                                                     │
├───────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ datasetio     │ inline::localfs                │ pandas                                                                                                     │
├───────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ datasetio     │ remote::huggingface            │ datasets                                                                                                   │
├───────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ datasetio     │ remote::nvidia                 │ datasets                                                                                                   │
├───────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ eval          │ inline::meta-reference         │ tree_sitter,pythainlp,langdetect,emoji,nltk                                                                │
├───────────────┼────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
```

---

## Lightspeed Core

![LCORE](images/lcore.jpg)

---

## Why Lightspeed core?

---
![LCORE](images/journey.png)

---

### Lightspeed Core

* It's own REST API (stable, standard)
* Llama Stack as backed
    - more modules as LC plugins
    - supports Llama Stack in service mode
    - supports Llama Stack in library mode
* Implemented as async Python code

---

![Python](images/python.png)

---

![LS1](images/llama_stack_arch.svg)

---

* Authentication + authorization
* RBAC
* Quota management
* MCP/Agents
* Question validators
* Answers redactors
* System prompt
* Summarization
* Storage
* Metrics
* Plugins
* UI specification
* User data collection (feedback + history)

---

## Summary

* AI world is similar to JS world 10 years ago
    - every week new framework is created
    - Llama Stack is a nice fit to this world
    - Lightspeed Core as stable layer to keep developers sane

---

## Evaluation

---

## Why Evaluate an LLM System?

* Measure performance
* Ensure good user experience
* Detect bias & harm
* Comply with ethical & legal standards

---

## Benefits of Evaluation

* Improvement:
  - Pinpoints weaknesses (e.g., hallucinations)
  - Enables data-driven model tuning

* Benchmarking:
  - Compare models (GPT, Gemini, Granite, etc.)
  - Ensures reliability over time

---
### Lightspeed Evaluation Framework

<font size="10">[https://github.com/lightspeed-core/lightspeed-evaluation/](https://github.com/lightspeed-core/lightspeed-evaluation)</font>
---

### Lightspeed Evaluation Framework

* Multi-Framework LLM as a Judge
  - Ragas, DeepEval and custom implementations
* Turn & Conversation-Level
  - Individual queries and multi-turn conversations
* Tools/Agents Support
* LLM Providers
  - OpenAI, Watsonx, Gemini, vLLM and others
* Setup/Cleanup Scripts
* Statistical Analysis

---
```yaml
- conversation_group_id: "test_conversation"
  description: "Sample evaluation"
  
  # Optional: Environment setup/cleanup scripts, when API is enabled
  setup_script: "scripts/setup_env.sh"      # Run before conversation
  cleanup_script: "scripts/cleanup_env.sh"  # Run after conversation
  
  # Conversation-level metrics   
  conversation_metrics:
    - "deepeval:conversation_completeness"
  
  conversation_metrics_metadata:
    "deepeval:conversation_completeness":
      threshold: 0.8
  
  turns:
    - turn_id: id1
      query: What is OpenShift Virtualization?
      response: null                    # Populated by API if enabled, otherwise provide
      contexts:
        - OpenShift Virtualization is an extension of the OpenShift ...
      attachments: []                   # Attachments (Optional)
      expected_response: OpenShift Virtualization is an extension of the OpenShift Container Platform that allows running virtual machines alongside containers
      expected_intent: "explain a concept"  # Expected intent for intent evaluation
      
      # Per-turn metrics (overrides system defaults)
      turn_metrics:
        - "ragas:faithfulness"
        - "custom:answer_correctness"
        - "custom:intent_eval"
```
---

## Demo

---

## Thank you

