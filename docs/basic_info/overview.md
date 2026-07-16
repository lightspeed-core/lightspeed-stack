# Overview

## Introduction

### What is Lightspeed Core Stack?

**Lightspeed Core Stack (LCore)** is an enterprise-grade middleware service that provides a robust layer between client applications and AI Large Language Model (LLM) backends. It adds essential enterprise features such as authentication, authorization, quota management, caching, and observability to LLM interactions.

Current version of LCore is built on **Llama Stack** - open-source framework that provides standardized APIs for building LLM applications. Llama Stack offers a unified interface for models, RAG (vector stores), tools, and safety (shields) across different providers. LCore communicates with Llama Stack to orchestrate all LLM operations.

To enhance LLM responses, LCore leverages **RAG (Retrieval-Augmented Generation)**, which retrieves relevant context from vector databases before generating answers. Llama Stack manages the vector stores, and LCore queries them to inject relevant documentation, knowledge bases, or previous conversations into the LLM prompt.

### Key Features

- **Multi-Provider Support**: Works with multiple LLM providers (Ollama, OpenAI, Watsonx, etc.)
- **Enterprise Security**: Authentication, authorization (RBAC), and secure credential management
- **Resource Management**: Token-based quota limits and usage tracking
- **Conversation Management**: Multi-turn conversations with history and caching
- **RAG Integration**: Retrieval-Augmented Generation for context-aware responses
- **Tool Orchestration**: Model Context Protocol (MCP) server integration
- **Observability**: Prometheus metrics, structured logging, and health checks
- **Agent-to-Agent**: A2A protocol support for multi-agent collaboration

### Components Overview

![Overview Stack as service](./overview.svg)

