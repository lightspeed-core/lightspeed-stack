# Lightspeed Core Stack

[![GitHub Pages](https://img.shields.io/badge/%20-GitHub%20Pages-informational)](https://lightspeed-core.github.io/lightspeed-stack/)
[![License](https://img.shields.io/badge/license-Apache-blue)](https://github.com/lightspeed-core/lightspeed-stack/blob/main/LICENSE)

## About

**Lightspeed Core Stack (LCS)** is an enterprise-grade AI-powered assistant that provides answers to product questions using backend LLM services, agents, and RAG databases. Built on FastAPI and integrated with Llama Stack, it adds essential enterprise features like authentication, authorization, quota management, and observability to LLM interactions.

The service includes comprehensive user data collection capabilities for various types of user interaction data, which can be exported to Red Hat's Dataverse for analysis using the companion [lightspeed-to-dataverse-exporter](https://github.com/lightspeed-core/lightspeed-to-dataverse-exporter) service.

## Documentation

**📚 Complete documentation is available at: [lightspeed-core.github.io/lightspeed-stack](https://lightspeed-core.github.io/lightspeed-stack/)**

### Quick Links

| Topic | Link |
|-------|------|
| **Architecture** | [Architecture Overview](https://lightspeed-core.github.io/lightspeed-stack/ARCHITECTURE.html) |
| **Getting Started** | [Getting Started Guide](https://lightspeed-core.github.io/lightspeed-stack/getting_started.html) |
| **Installation** | [Linux](https://lightspeed-core.github.io/lightspeed-stack/installation_linux.html) \| [macOS](https://lightspeed-core.github.io/lightspeed-stack/installation_macos.html) |
| **Configuration** | [Configuration Guide](https://lightspeed-core.github.io/lightspeed-stack/config.html) |
| **Deployment** | [Deployment Guide](https://lightspeed-core.github.io/lightspeed-stack/deployment_guide.html) |
| **API Documentation** | [OpenAPI Spec](https://lightspeed-core.github.io/lightspeed-stack/openapi.html) \| [Conversations API](https://lightspeed-core.github.io/lightspeed-stack/conversations_api.html) |
| **Authentication & Authorization** | [Auth Guide](https://lightspeed-core.github.io/lightspeed-stack/auth.html) |
| **RAG & BYOK** | [RAG Guide](https://lightspeed-core.github.io/lightspeed-stack/rag_guide.html) \| [BYOK Guide](https://lightspeed-core.github.io/lightspeed-stack/byok_guide.html) |
| **Testing** | [Testing Guide](https://lightspeed-core.github.io/lightspeed-stack/testing.html) \| [E2E Testing](https://lightspeed-core.github.io/lightspeed-stack/e2e_testing.html) |

## Quick Start

```bash
# 1. Install dependencies
uv sync --group dev --group llslibdev

# 2. Generate Llama Stack configuration
./scripts/generate_local_run.sh

# 3. Set your LLM API key (example with OpenAI)
export OPENAI_API_KEY=sk-xxxxx

# 4. Start Llama Stack server
uv run llama stack run local-run.yaml

# 5. Start Lightspeed Core Stack
make run

# 6. Access the web UI at http://localhost:8080/
# macOS: open http://localhost:8080/
# Linux: xdg-open http://localhost:8080/
# Cross-platform: python3 -m webbrowser http://localhost:8080/
```

For detailed installation instructions, see the [Getting Started Guide](https://lightspeed-core.github.io/lightspeed-stack/getting_started.html).

## Key Features

- **Multi-Provider Support**: OpenAI, Azure OpenAI, Google VertexAI, IBM WatsonX, RHOAI, RHEL AI
- **Enterprise Security**: Authentication, RBAC authorization, secure credential management
- **Resource Management**: Token-based quota limits and usage tracking
- **Conversation Management**: Multi-turn conversations with history and caching
- **RAG Integration**: Retrieval-Augmented Generation for context-aware responses
- **Tool Orchestration**: Model Context Protocol (MCP) server integration
- **Observability**: Prometheus metrics, structured logging, health checks
- **Agent-to-Agent Protocol**: A2A protocol support for multi-agent collaboration

## Container Images

Stable and development images are available on [Quay.io](https://quay.io/repository/lightspeed-core/lightspeed-stack):

```bash
# Pull latest stable release
podman pull quay.io/lightspeed-core/lightspeed-stack:latest

# Run with your configuration
podman run -it -p 8080:8080 \
  -v ./lightspeed-stack.yaml:/app-root/lightspeed-stack.yaml:Z \
  quay.io/lightspeed-core/lightspeed-stack:latest
```

See the [Deployment Guide](https://lightspeed-core.github.io/lightspeed-stack/deployment_guide.html) for detailed container setup.

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for:

- Development setup and workflow
- Coding standards and best practices
- Testing requirements
- Pull request process

## Development

```bash
# Run linters and formatters
make format        # Format code (black + ruff)
make verify        # Run all linters

# Run tests
make test-unit           # Unit tests with coverage
make test-integration    # Integration tests
make test-e2e            # End-to-end tests

# Generate documentation
make doc                 # Generate developer documentation
make openapi-doc         # Generate OpenAPI documentation
```

See the [Contributing Guide](CONTRIBUTING.md) for complete development instructions.

## Support & Community

- **Documentation**: [lightspeed-core.github.io/lightspeed-stack](https://lightspeed-core.github.io/lightspeed-stack/)
- **Issues**: [GitHub Issues](https://github.com/lightspeed-core/lightspeed-stack/issues)
- **Releases**: [GitHub Releases](https://github.com/lightspeed-core/lightspeed-stack/releases)

## License

Published under the [Apache 2.0 License](LICENSE)

## Related Projects

- [lightspeed-to-dataverse-exporter](https://github.com/lightspeed-core/lightspeed-to-dataverse-exporter) - Export user interaction data to Red Hat's Dataverse
- [Llama Stack](https://github.com/llamastack/llama-stack) - Meta's open-source framework for building LLM applications
