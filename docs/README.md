# Lightspeed-Stack Documentation

Welcome. This directory is published via GitHub Pages.
See the full documentation at [`../README.md`](../README.md) or browse sub-pages in `docs/`.

![Logo](https://lightspeed-core.github.io/lightspeed-stack/logo.jpg)

<!-- vim-markdown-toc GFM -->

* [Basic info](#basic-info)
* [User docs](#user-docs)
* [Developer doc](#developer-doc)
    * [API](#api)
    * [Models](#models)
    * [Testing](#testing)
* [Maintenance](#maintenance)
* [Design documents](#design-documents)
    * [Agent skills](#agent-skills)
    * [Automatic conversation expiration](#automatic-conversation-expiration)
    * [BYOK PDF support](#byok-pdf-support)
    * [Conversation compaction](#conversation-compaction)
    * [Supporting backport changes for releases](#supporting-backport-changes-for-releases)
    * [Human-in-the-loop (HIL)](#human-in-the-loop-hil)
    * [Llama Stack config merge (unified `lightspeed-stack.yaml`)](#llama-stack-config-merge-unified-lightspeed-stackyaml)
    * [Low overhead deployment for server mode](#low-overhead-deployment-for-server-mode)
    * [OpenTelemetry tracing in Lightspeed Core](#opentelemetry-tracing-in-lightspeed-core)
* [Demos](#demos)

<!-- vim-markdown-toc -->

## Basic info

[Overview](https://lightspeed-core.github.io/lightspeed-stack/basic_info/overview.html)

[Getting started](https://lightspeed-core.github.io/lightspeed-stack/basic_info/getting_started.html)

## User docs

[Deployment Guide](https://lightspeed-core.github.io/lightspeed-stack/user_doc/deployment_guide.html)

[Configuration options](https://lightspeed-core.github.io/lightspeed-stack/user_doc/config.html)

[Agent skills](https://lightspeed-core.github.io/lightspeed-stack/user_doc/skills_guide.html)

[A2A [Agent-to-Agent] Protocol](https://lightspeed-core.github.io/lightspeed-stack/user_doc/a2a_protocol.html)

[RAG configuration guide](https://lightspeed-core.github.io/lightspeed-stack/user_doc/rag_guide.html)

[BYOK guide](https://lightspeed-core.github.io/lightspeed-stack/user_doc/byok_guide.html)

[Authentication and Authorization](https://lightspeed-core.github.io/lightspeed-stack/user_doc/auth.html)

[User data collection](https://lightspeed-core.github.io/lightspeed-stack/user_doc/user_data_collection.html)

[Sentry error tracking](https://lightspeed-core.github.io/lightspeed-stack/sentry.html)

## Developer doc

[Architecture](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/ARCHITECTURE.html)

[Architecture diagram](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/architecture.svg)

[Installation on Linux](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/installation_linux.html)

[Installation on MacOS](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/installation_macos.html)

[Database structure](https://lightspeed-core.github.io/lightspeed-stack/DB/index.html)

[Providers](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/providers.html)

[Container Orchestration Guide](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/container_orchestration.html)

[Contributing guide](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/contributing_guide.html)

[Conversation history](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/conversation_history.html)

[Persistent storage](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/persistent_storage.html)

[Quota scheduler](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/quota_scheduler.html)

### API

[OpenAPI specification](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/openapi.html)

[Conversations API](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/conversations_api.html)

[Query endpoint](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/query_endpoint.html)

[Streaming query endpoint](https://lightspeed-core.github.io/lightspeed-stack/devel_doc/streaming_query_endpoint.html)

### Models

[Common](https://lightspeed-core.github.io/lightspeed-stack/models/common.html)

[Database](https://lightspeed-core.github.io/lightspeed-stack/models/database.html)

[Requests](https://lightspeed-core.github.io/lightspeed-stack/models/requests.html)

[Successful responses](https://lightspeed-core.github.io/lightspeed-stack/models/responses_succ.html)

[Error responses](https://lightspeed-core.github.io/lightspeed-stack/models/responses_errors.html)

[Compaction](https://lightspeed-core.github.io/lightspeed-stack/models/compaction.html)

### Testing

[Testing](https://lightspeed-core.github.io/lightspeed-stack/testing/testing.html)

[End-to-End Tests Guide](https://lightspeed-core.github.io/lightspeed-stack/testing/e2e_testing.html)

[List of e2e scenarios](https://lightspeed-core.github.io/lightspeed-stack/testing/e2e_scenarios.html)

## Maintenance

[Status of Lightspeed Core Stack versions](https://lightspeed-core.github.io/lightspeed-stack/maintenance/version_status.html)

[Supported versions](https://lightspeed-core.github.io/lightspeed-stack/maintenance/versions_supported.html)

[Unsupported versions](https://lightspeed-core.github.io/lightspeed-stack/maintenance/versions_unsupported.html)

[Migration guides](https://lightspeed-core.github.io/lightspeed-stack/migrations/)

[Branching](https://lightspeed-core.github.io/lightspeed-stack/maintenance/branching.html)

[Releasing](https://lightspeed-core.github.io/lightspeed-stack/maintenance/releasing.html)

[LTS process overview](https://lightspeed-core.github.io/lightspeed-stack/maintenance/lts_flow.html)

## Design documents

### Agent skills

[Spike](https://lightspeed-core.github.io/lightspeed-stack/design/agent-skills/agent-skills-spike.html)

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/agent-skills/agent-skills.html)

### Automatic conversation expiration

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/automatic-conversation-expiration/automatic-conversation-expiration.html)

### BYOK PDF support

[Spike](https://lightspeed-core.github.io/lightspeed-stack/design/byok-pdf/byok-pdf-spike.html)

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/byok-pdf/byok-pdf.html)

### Conversation compaction

[Spike](https://lightspeed-core.github.io/lightspeed-stack/design/conversation-compaction/conversation-compaction-spike.html)

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/conversation-compaction/conversation-compaction.html)

### Supporting backport changes for releases

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/supporting-backport-changes-for-releases/supporting-backport-changes-for-releases.html)

### Human-in-the-loop (HIL)

[Spike](https://lightspeed-core.github.io/lightspeed-stack/design/human-in-the-loop/human-in-the-loop-spike.html)

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/human-in-the-loop/human-in-the-loop.html)

### Llama Stack config merge (unified `lightspeed-stack.yaml`)

[Spike](https://lightspeed-core.github.io/lightspeed-stack/design/llama-stack-config-merge/llama-stack-config-merge-spike.html)

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/llama-stack-config-merge/llama-stack-config-merge.html)

[Profiles (Deployment Guide)](https://lightspeed-core.github.io/lightspeed-stack/deployment_guide.html#profiles)

### Low overhead deployment for server mode

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/low-overhead-deployment-for-server-mode/low-overhead-deployment-for-server-mode.html)

### OpenTelemetry tracing in Lightspeed Core

[Design](https://lightspeed-core.github.io/lightspeed-stack/design/observability-opentelemetry/observability-opentelemetry.html)

## Demos

[LCORE introduction](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/lcore.html#/)

[CodeRabbitAI](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/coderabbit.html#/)

[Lunch and Learn 2026](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/LnL_2026.html#/)

[LCORE weak points for AI-driven agentic flow](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/weak_points_for_ai.html#/)

