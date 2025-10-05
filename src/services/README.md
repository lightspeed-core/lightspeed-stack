# Services

This directory contains the service components and documentation for lightspeed-stack.

## Available Services

### Data Collector Service

The Data Collector Service handles the collection, packaging, and transmission of user interaction data and feedback to Red Hat's analytics infrastructure.

**📖 [Read the full Data Collector documentation](../../docs/data_collector.md)**

Key features:
- Collects user interaction transcripts and feedback data
- Packages data into tarballs for transmission
- Configurable ingress upload server endpoint and authentication token
- Configurable upload intervals and cleanup policies

## Service Architecture

Services in this directory are designed to run alongside the main lightspeed-stack application, providing additional functionality for data collection, monitoring, and analytics.

Each service can be:
- Configured via the main `lightspeed-stack.yaml` configuration file
- Run independently using dedicated make targets
- Enabled/disabled based on deployment requirements

## Getting Started

To run a service, refer to its specific documentation for configuration options and startup commands. Most services can be started using make targets from the project root. 