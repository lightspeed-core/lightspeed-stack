---
layout: default
nav_order: 1
---

# Lightspeed core stack

About The Project

Lightspeed Core Stack (LCS) is an AI-powered assistant that provides answers to
product questions using backend LLM services, agents, and RAG databases.

![Logo](https://lightspeed-core.github.io/lightspeed-stack/logo.jpg)

<!-- vim-markdown-toc GFM -->

* [Overview](#overview)
* [Installation and configuration](#installation-and-configuration)
* [Status of Lightspeed Core Stack versions](#status-of-lightspeed-core-stack-versions)
* [Info for developers](#info-for-developers)
* [API](#api)
* [RAG and BYOK](#rag-and-byok)
* [Other features](#other-features)
* [Models](#models)
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
* [Testing](#testing)
* [Releasing](#releasing)
* [Demos](#demos)

<!-- vim-markdown-toc -->

## Overview

[Architecture](https://lightspeed-core.github.io/lightspeed-stack/ARCHITECTURE.html)

[Architecture diagram](https://lightspeed-core.github.io/lightspeed-stack/architecture.svg)

[Getting started](https://lightspeed-core.github.io/lightspeed-stack/getting_started.html)

[Authentication and Authorization](https://lightspeed-core.github.io/lightspeed-stack/auth.html)

## Installation and configuration

[Deployment Guide](https://lightspeed-core.github.io/lightspeed-stack/deployment_guide.html)

[Container Orchestration Guide](https://lightspeed-core.github.io/lightspeed-stack/container_orchestration.html)

[Linux](https://lightspeed-core.github.io/lightspeed-stack/installation_linux.html)

[MacOS](https://lightspeed-core.github.io/lightspeed-stack/installation_macos.html)

[Configuration](https://lightspeed-core.github.io/lightspeed-stack/config.html)

## Status of Lightspeed Core Stack versions

[Status of Lightspeed Core Stack versions](https://lightspeed-core.github.io/lightspeed-stack/version_status.html)

[Supported versions](https://lightspeed-core.github.io/lightspeed-stack/versions_supported.html)

[Unsupported versions](https://lightspeed-core.github.io/lightspeed-stack/versions_unsupported.html)

## Migration guides

[Migration guides](https://lightspeed-core.github.io/lightspeed-stack/migrations/)

## Info for developers

[Contributing guide](https://lightspeed-core.github.io/lightspeed-stack/contributing_guide.html)

## API

[OpenAPI specification](https://lightspeed-core.github.io/lightspeed-stack/openapi.html)

[Conversations API](https://lightspeed-core.github.io/lightspeed-stack/conversations_api.html)

[A2A [Agent-to-Agent] Protocol](https://lightspeed-core.github.io/lightspeed-stack/a2a_protocol.html)

## RAG and BYOK

[RAG Configuration Guide](https://lightspeed-core.github.io/lightspeed-stack/rag_guide.html)

[BYOK guide](https://lightspeed-core.github.io/lightspeed-stack/byok_guide.html)

## Other features

[Providers](https://lightspeed-core.github.io/lightspeed-stack/providers.html)

[Sentry error tracking](https://lightspeed-core.github.io/lightspeed-stack/sentry.html)

[User data collection](https://lightspeed-core.github.io/lightspeed-stack/user_data_collection.html)

[Database structure](https://lightspeed-core.github.io/lightspeed-stack/DB/index.html)

[Agent skills](https://lightspeed-core.github.io/lightspeed-stack/skills_guide.html)

## Models

[Common](https://lightspeed-core.github.io/lightspeed-stack/models/common.html)

[Database](https://lightspeed-core.github.io/lightspeed-stack/models/database.html)

[Requests](https://lightspeed-core.github.io/lightspeed-stack/models/requests.html)

[Successful responses](https://lightspeed-core.github.io/lightspeed-stack/models/responses_succ.html)

[Error responses](https://lightspeed-core.github.io/lightspeed-stack/models/responses_errors.html)

[Compaction](https://lightspeed-core.github.io/lightspeed-stack/models/compaction.html)


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

## Testing

[Testing](https://lightspeed-core.github.io/lightspeed-stack/testing.html)

[End-to-End Tests Guide](https://lightspeed-core.github.io/lightspeed-stack/e2e_testing.html)

[List of e2e scenarios](https://lightspeed-core.github.io/lightspeed-stack/e2e_scenarios.html)

## Releasing

[Branching](https://lightspeed-core.github.io/lightspeed-stack/branching.html)

[Releasing](https://lightspeed-core.github.io/lightspeed-stack/releasing.html)

[LTS provess overview](https://lightspeed-core.github.io/lightspeed-stack/lts_flow.html)

## Demos

[LCORE introduction](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/lcore.html#/)

[CodeRabbitAI](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/coderabbit.html#/)

[Lunch and Learn 2026](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/LnL_2026.html#/)

[LCORE weak points for AI-driven agentic flow](https://lightspeed-core.github.io/lightspeed-stack/demos/lcore/weak_points_for_ai.html#/)

