# Llama Stack Container Orchestration

This guide explains how Lightspeed Core Stack (LCORE) manages the Llama Stack container lifecycle, including startup, teardown, customization, and troubleshooting.

## Table of Contents

* [Overview](#overview)
* [Quick Start](#quick-start)
* [Container Lifecycle](#container-lifecycle)
    * [Startup Sequence](#startup-sequence)
    * [Teardown and Cleanup](#teardown-and-cleanup)
* [Customization Options](#customization-options)
    * [Makefile Variables](#makefile-variables)
    * [Configuration Files](#configuration-files)
    * [Environment Variables](#environment-variables)
* [Health Checks and Monitoring](#health-checks-and-monitoring)
* [Troubleshooting](#troubleshooting)
    * [Common Issues](#common-issues)
    * [Debug Logs](#debug-logs)
* [Advanced Topics](#advanced-topics)
    * [Configuration Enrichment](#configuration-enrichment)
    * [Volume Mounts](#volume-mounts)
    * [Manual Container Management](#manual-container-management)

---

## Overview

When you run `make run`, the Makefile automatically:

1. **Builds** the llama-stack container image (if not already built)
2. **Stops and removes** any existing llama-stack container (ensures clean state)
3. **Starts** a new llama-stack container with your configuration
4. **Waits** for the container to pass health checks (up to 60 seconds)
5. **Starts** the Lightspeed Core Stack service
6. **Sets up** automatic cleanup on exit (Ctrl+C or kill signal)

This orchestration eliminates the need to manually manage two separate processes, providing a seamless single-command developer experience.

---

## Quick Start

### Prerequisites

- **Container Runtime**: Either Podman or Docker installed
  - **Podman** (recommended for RHEL/Fedora): `sudo dnf install podman`
  - **Docker**: Install from [docker.com](https://docs.docker.com/get-docker/)

The Makefile will auto-detect which runtime is available.

### Basic Usage

```bash
# Install dependencies
uv sync --group dev --group llslibdev

# Generate llama-stack config (run.yaml)
./scripts/generate_local_run.sh

# Set required environment variables
export OPENAI_API_KEY=sk-xxxxx

# Start everything (container + service)
make run
```

**Stop the service:** Press `Ctrl+C`. This will automatically stop and remove the llama-stack container.

---

## Container Lifecycle

### Startup Sequence

When you run `make run`, the following happens:

#### 1. Build Container Image

**Target:** `build-llama-stack-image`

```bash
make build-llama-stack-image
```

- Builds from `deploy/llama-stack/test.containerfile`
- Tags as `lightspeed-llama-stack:local` (customizable via `LLAMA_STACK_IMAGE`)
- Only rebuilds if the image doesn't exist or source files changed
- Removes any existing container before building (ensures clean build)

#### 2. Stop Existing Container

**Target:** `stop-llama-stack-container`

```bash
make stop-llama-stack-container
```

- Gracefully stops the container with 10-second timeout
- If graceful stop fails, captures logs to `/tmp/llama-stack-failure.log` and force-kills
- Safe to run even if no container is running

#### 3. Start New Container

**Target:** `start-llama-stack-container`

```bash
make start-llama-stack-container
```

Key features:
- **Port Mapping:** Host port 8321 → Container port 8321 (configurable)
- **Volume Mounts:** Mounts configs, scripts, and enrichment logic
- **Environment Variables:** Passes through all required env vars for providers
- **Health Check:** Built-in Docker/Podman health check using `/v1/health` endpoint
  - Checks every 10 seconds
  - 5-second timeout per check
  - 3 retries before marking unhealthy
  - 15-second grace period on startup

#### 4. Wait for Health

**Target:** `wait-for-llama-stack-health`

```bash
make wait-for-llama-stack-health
```

- Polls container health status (30 attempts × 2 seconds = 60 second timeout)
- Shows status on each attempt: `starting`, `healthy`, or `unhealthy`
- If timeout occurs, displays container logs and exits with error
- Example output:
  ```
  Waiting for llama-stack container to be healthy...
    Health status: starting (attempt 1/30)
    Health status: starting (attempt 2/30)
    Health status: healthy (attempt 3/30)
  ✓ Llama-stack is healthy and ready!
  ```

#### 5. Start Lightspeed Core Stack

**Target:** `run-stack`

```bash
make run-stack
```

- Starts the FastAPI service with `uv run src/lightspeed_stack.py`
- Connects to llama-stack at `http://localhost:8321` (or configured URL)
- Sets up trap handler to stop container on exit

### Teardown and Cleanup

#### Automatic Cleanup on Exit

When you press `Ctrl+C` or the process receives a termination signal, the trap handler automatically runs:

```bash
trap 'echo ""; echo "Stopping services..."; $(MAKE) stop-llama-stack-container' EXIT INT TERM
```

This ensures the llama-stack container is always cleaned up, even if the service crashes.

#### Manual Cleanup Commands

**Stop the container (keeps container for inspection):**
```bash
make stop-llama-stack-container
```

**Remove the container (saves logs first):**
```bash
make remove-llama-stack-container
```
- Logs saved to `/tmp/llama-stack-last-run.log`
- Container is removed but image remains

**Full cleanup (remove container + image):**
```bash
make clean-llama-stack
```
- Stops and removes container
- Deletes the container image
- Frees up disk space

---

## Customization Options

### Makefile Variables

Override any of these variables when running `make`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMA_STACK_CONTAINER_NAME` | `lightspeed-llama-stack` | Container name |
| `LLAMA_STACK_IMAGE` | `lightspeed-llama-stack:local` | Container image name and tag |
| `LLAMA_STACK_PORT` | `8321` | Host port for llama-stack |
| `LLAMA_STACK_CONFIG` | `run.yaml` | Llama Stack config file path |
| `CONFIG` | `lightspeed-stack.yaml` | LCORE config file path |
| `CONTAINER_RUNTIME` | auto-detected | Force specific runtime (`podman` or `docker`) |

#### Examples

**Use custom port:**
```bash
make run LLAMA_STACK_PORT=9321
```
*Note: Also update `llama_stack.url` in `lightspeed-stack.yaml` to `http://localhost:9321`*

**Use custom config files:**
```bash
make run CONFIG=my-config.yaml LLAMA_STACK_CONFIG=my-run.yaml
```

**Use custom container name:**
```bash
make run LLAMA_STACK_CONTAINER_NAME=my-llama-stack
```

**Force Docker instead of Podman:**
```bash
make run CONTAINER_RUNTIME=docker
```

### Configuration Files

#### `run.yaml` (Llama Stack Configuration)

This file configures the llama-stack server itself. Generated by `./scripts/generate_local_run.sh`.

**Key sections:**
- `providers`: Which LLM providers to enable (OpenAI, Azure, etc.)
- `apis`: Which APIs to expose (inference, safety, agents, etc.)
- `models`: Model registry and configurations

**Location:** Project root (default) or custom path via `LLAMA_STACK_CONFIG`

**Enrichment:** The container automatically enriches this file with settings from `lightspeed-stack.yaml` at startup (see [Configuration Enrichment](#configuration-enrichment)).

#### `lightspeed-stack.yaml` (LCORE Configuration)

This file configures the Lightspeed Core Stack service.

**Llama Stack connection settings:**
```yaml
llama_stack:
  use_as_library_client: false
  url: http://localhost:8321
  # api_key: custom-key  # Optional authentication
```

**Location:** Project root (default) or custom path via `CONFIG`

### Environment Variables

The Makefile passes these environment variables to the llama-stack container:

#### Required for OpenAI
- `OPENAI_API_KEY`: OpenAI API key for inference

#### Optional Provider Credentials

**Azure (Entra ID):**
- `TENANT_ID`: Azure tenant ID
- `CLIENT_ID`: Azure client ID
- `CLIENT_SECRET`: Azure client secret

**RHAIIS (Red Hat AI Inference Service):**
- `RHAIIS_URL`: RHAIIS server URL
- `RHAIIS_PORT`: RHAIIS server port
- `RHAIIS_API_KEY`: RHAIIS API key
- `RHAIIS_MODEL`: Default RHAIIS model

**RHEL AI:**
- `RHEL_AI_URL`: RHEL AI server URL
- `RHEL_AI_PORT`: RHEL AI server port
- `RHEL_AI_API_KEY`: RHEL AI API key
- `RHEL_AI_MODEL`: Default RHEL AI model

**Google Vertex AI:**
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to GCP credentials JSON
- `VERTEX_AI_PROJECT`: GCP project ID
- `VERTEX_AI_LOCATION`: GCP region

**IBM WatsonX:**
- `WATSONX_BASE_URL`: WatsonX API base URL
- `WATSONX_PROJECT_ID`: WatsonX project ID
- `WATSONX_API_KEY`: WatsonX API key

**AWS Bedrock:**
- `AWS_BEARER_TOKEN_BEDROCK`: AWS Bedrock bearer token

**Search Providers:**
- `BRAVE_SEARCH_API_KEY`: Brave Search API key
- `TAVILY_SEARCH_API_KEY`: Tavily Search API key

#### OKP/Solr RAG Configuration

**For OKP (Offline Knowledge Portal) RAG:**
- `RH_SERVER_OKP`: OKP server URL (e.g., `http://localhost:8081`)
- `SOLR_URL`: Solr server URL
- `SOLR_COLLECTION`: Solr collection name
- `SOLR_VECTOR_FIELD`: Vector field name in Solr
- `SOLR_CONTENT_FIELD`: Content field name in Solr
- `SOLR_EMBEDDING_MODEL`: Embedding model for RAG
- `SOLR_EMBEDDING_DIM`: Embedding dimension

See [OKP Guide](okp_guide.md) for detailed setup instructions.

#### Other Configuration

- `E2E_OPENAI_MODEL`: OpenAI model for E2E tests (default: `gpt-4o-mini`)
- `LLAMA_STACK_LOGGING`: Enable debug logging in llama-stack
- `FAISS_VECTOR_STORE_ID`: FAISS vector store identifier
- `LITELLM_DROP_PARAMS`: Drop unsupported params in LiteLLM (default: `true`)

#### Setting Environment Variables

**One-time:**
```bash
export OPENAI_API_KEY=sk-xxxxx
export RHAIIS_API_KEY=xxxxx
make run
```

**In a script:**
```bash
#!/bin/bash
export OPENAI_API_KEY=sk-xxxxx
export RHAIIS_API_KEY=xxxxx
export RHAIIS_URL=https://rhaiis.example.com
export RHAIIS_MODEL=granite-3.1-8b-instruct
make run
```

**Via .env file (not recommended for secrets):**
```bash
# Load from file
set -a
source .env
set +a
make run
```

---

## Health Checks and Monitoring

### Container-Level Health Check

The container has a built-in Docker/Podman health check:

```bash
# Check container health status
podman inspect --format='{{.State.Health.Status}}' lightspeed-llama-stack

# Possible values:
# - starting: Container is starting, health check not yet run
# - healthy: Health check passed
# - unhealthy: Health check failed 3 times
```

**Health check configuration:**
- **Command:** `curl -f http://localhost:8321/v1/health || exit 1`
- **Interval:** 10 seconds between checks
- **Timeout:** 5 seconds per check
- **Retries:** 3 consecutive failures before marking unhealthy
- **Start Period:** 15 second grace period on startup

### LCORE Readiness Endpoint

The `/v1/readiness` endpoint checks llama-stack connectivity:

```bash
# Check LCORE readiness
curl http://localhost:8080/v1/readiness

# Response when healthy:
{
  "ready": true,
  "reason": "All providers are healthy",
  "providers": []
}

# Response when llama-stack is unreachable (HTTP 503):
{
  "ready": false,
  "reason": "Providers not healthy: unknown",
  "providers": [
    {
      "provider_id": "unknown",
      "status": "error",
      "message": "Failed to initialize health check: Connection error"
    }
  ]
}
```

### Manual Health Checks

**Test llama-stack directly:**
```bash
curl http://localhost:8321/v1/health
# Expected: {"status":"OK"}
```

**Test LCORE liveness:**
```bash
curl http://localhost:8080/v1/liveness
# Expected: {"alive":true}
```

**View container logs:**
```bash
# Follow logs in real-time
podman logs -f lightspeed-llama-stack

# View last 50 lines
podman logs --tail 50 lightspeed-llama-stack
```

---

## Troubleshooting

### Common Issues

#### 1. Container Fails Health Check

**Symptoms:**
```
✗ ERROR: Llama-stack did not become healthy within 60 seconds
Container logs:
[error logs shown here]
```

**Causes:**
- Configuration error in `run.yaml`
- Missing required environment variable
- Port conflict (8321 already in use)
- Insufficient resources (CPU/memory)

**Solutions:**

1. **Check logs saved by Makefile:**
   ```bash
   cat /tmp/llama-stack-failure.log
   ```

2. **Inspect container manually:**
   ```bash
   # Container might still be running in unhealthy state
   podman logs lightspeed-llama-stack
   podman exec lightspeed-llama-stack curl http://localhost:8321/v1/health
   ```

3. **Test config enrichment:**
   ```bash
   # Run enrichment script manually to check for errors
   uv run src/llama_stack_configuration.py \
     -c lightspeed-stack.yaml \
     -i run.yaml \
     -o /tmp/enriched-run.yaml
   
   # Check output for errors
   cat /tmp/enriched-run.yaml
   ```

4. **Check for missing environment variables:**
   ```bash
   # Example error: "Environment variable 'OPENAI_API_KEY' not set"
   # Solution: export OPENAI_API_KEY=sk-xxxxx
   ```

#### 2. Port Conflict

**Symptoms:**
```
Error: cannot listen on the TCP port: listen tcp4 0.0.0.0:8321: bind: address already in use
```

**Solutions:**

1. **Find what's using port 8321:**
   ```bash
   sudo lsof -i :8321
   # or
   sudo ss -tulpn | grep 8321
   ```

2. **Kill the process or use a different port:**
   ```bash
   make run LLAMA_STACK_PORT=9321
   ```
   
   Don't forget to update `lightspeed-stack.yaml`:
   ```yaml
   llama_stack:
     url: http://localhost:9321
   ```

#### 3. Volume Mount Permission Issues (SELinux)

**Symptoms:**
```
Error: mkdir /opt/app-root/run.yaml: permission denied
```

**Cause:** SELinux on RHEL/Fedora blocks volume mounts

**Solution:** The Makefile already includes `:z` flags on volume mounts. If still failing:

```bash
# Temporarily set SELinux to permissive
sudo setenforce 0

# Check SELinux denials
sudo ausearch -m avc -ts recent

# Re-enable SELinux
sudo setenforce 1
```

#### 4. Container Build Fails

**Symptoms:**
```
Error: building at STEP "RUN uv sync...": error running subprocess
```

**Solutions:**

1. **Check network connectivity:**
   ```bash
   podman run --rm alpine ping -c 3 pypi.org
   ```

2. **Clear build cache:**
   ```bash
   make clean-llama-stack
   podman system prune -a
   make build-llama-stack-image
   ```

3. **Check disk space:**
   ```bash
   df -h
   # Need several GB free for build
   ```

#### 5. "No container runtime found"

**Symptoms:**
```
ERROR: No container runtime found. Install podman or docker.
```

**Solution:**
```bash
# On RHEL/Fedora
sudo dnf install podman

# On Ubuntu/Debian
sudo apt-get install podman
# or
curl -fsSL https://get.docker.com | sh
```

#### 6. Container Starts But LCORE Can't Connect

**Symptoms:**
- Container shows as healthy
- LCORE errors: `Connection refused` or `APIConnectionError`

**Solutions:**

1. **Check llama-stack URL in config:**
   ```yaml
   # lightspeed-stack.yaml
   llama_stack:
     url: http://localhost:8321  # Must match LLAMA_STACK_PORT
   ```

2. **Test connection manually:**
   ```bash
   curl http://localhost:8321/v1/health
   ```

3. **Check firewall rules:**
   ```bash
   sudo firewall-cmd --list-ports
   # If 8321 blocked, add it:
   sudo firewall-cmd --permanent --add-port=8321/tcp
   sudo firewall-cmd --reload
   ```

#### 7. Credential File Permission Errors (VertexAI, GCP)

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: '/tmp/vertex-credentials.json'
google.auth._default.load_credentials_from_file() failed to open credentials file
```

**Cause:**
The llama-stack container runs as UID 1001 (non-root user for security). When you mount a credentials file with restrictive permissions (`600`), the container user cannot read it:

- **Host file:** Owned by your user (e.g., UID 1000) with permissions `600` (owner-only)
- **Container process:** Runs as UID 1001 (different user)
- **Result:** Permission denied - UID 1001 cannot read a file owned by UID 1000 with `600` permissions

**Solutions:**

**Option 1: Use 644 permissions** (Works on all platforms)
```bash
chmod 644 /path/to/vertex-credentials.json
```

Allows container user (UID 1001) to read the file as "others" while keeping write access restricted to owner.

**Security note:** File becomes world-readable on the host. Acceptable for development environments where access to the filesystem is already restricted to your user account.

**Option 2: Use ACLs** (Linux only - more secure)

ACLs (Access Control Lists) allow you to grant read access to UID 1001 specifically without making the file world-readable. **Note:** This only works on Linux systems, not macOS.

**Install ACL tools (Linux):**
```bash
# RHEL/Fedora/CentOS
sudo dnf install acl

# Ubuntu/Debian
sudo apt-get install acl
```

**Grant read access to UID 1001 (Linux only):**
```bash
setfacl -m u:1001:r /path/to/vertex-credentials.json

# Verify
getfacl /path/to/vertex-credentials.json
# Output shows: user:1001:r--
```

This grants read-only access to UID 1001 (container user) without changing base permissions or making the file world-readable.

**macOS note:** macOS uses BSD ACLs and cannot assign numeric UID-based ACLs to non-existent host users. If you are testing locally on macOS, you must temporarily use `chmod 644` to allow the container access, but **be aware that this makes the credentials file world-readable on your host machine.** Alternately, ensure your local user matches the container's execution environment.

**Why this happens:**
This is expected container behavior. The container runs as a non-root user (UID 1001) for security - see `USER 1001` in `deploy/llama-stack/test.containerfile`. Files with `600` permissions are only accessible to their owner, and the container's UID differs from your host UID.

**Production recommendation:**
For production deployments, avoid mounting credential files entirely. Instead use:
- Kubernetes secrets with workload identity
- Cloud provider IAM roles (GCP Workload Identity, AWS IRSA, Azure Managed Identity)
- Secret management systems (Vault, AWS Secrets Manager)

### Debug Logs

The Makefile automatically saves logs to `/tmp` when issues occur:

| File | Content | When Created |
|------|---------|--------------|
| `/tmp/llama-stack-failure.log` | Last 200 lines of logs when container fails to stop gracefully | Container stop timeout |
| `/tmp/llama-stack-last-run.log` | Full logs before container removal | `make remove-llama-stack-container` |
| (Container logs) | View with `podman logs lightspeed-llama-stack` | While container is running |

**Enable debug logging in llama-stack:**
```bash
export LLAMA_STACK_LOGGING=debug
make run
```

---

## Advanced Topics

### Configuration Enrichment

When the llama-stack container starts, it automatically enriches the `run.yaml` file with settings from `lightspeed-stack.yaml`. This is done by the entrypoint script mounted into the container.

#### How It Works

1. **Entrypoint script** (`scripts/llama-stack-entrypoint.sh`) is mounted at `/opt/app-root/enrich-entrypoint.sh`
2. **Script runs** `/opt/app-root/.venv/bin/python3 /opt/app-root/llama_stack_configuration.py`
3. **Enrichment logic** (`src/llama_stack_configuration.py`) reads both configs and merges them
4. **Output** is written to `/tmp/enriched-run.yaml` inside the container
5. **Llama Stack starts** with the enriched config

#### What Gets Enriched

- **RAG configurations** from `lightspeed-stack.yaml` are injected into llama-stack config
- **OKP/Solr settings** are dynamically added
- **Provider configurations** from LCORE are merged with llama-stack providers

#### Manual Enrichment (for debugging)

```bash
# Run enrichment locally to see output
uv run src/llama_stack_configuration.py \
  -c lightspeed-stack.yaml \
  -i run.yaml \
  -o enriched-run.yaml

# Inspect the enriched config
cat enriched-run.yaml
```

### Volume Mounts

The container uses these volume mounts:

| Host Path | Container Path | Mode | Purpose |
|-----------|----------------|------|---------|
| `$(PWD)/run.yaml` | `/opt/app-root/run.yaml` | rw | Llama Stack config (enriched version written here) |
| `$(PWD)/lightspeed-stack.yaml` | `/opt/app-root/lightspeed-stack.yaml` | ro | LCORE config (read for enrichment) |
| `$(PWD)/scripts/llama-stack-entrypoint.sh` | `/opt/app-root/enrich-entrypoint.sh` | ro | Entrypoint script with enrichment logic |
| `$(PWD)/src/llama_stack_configuration.py` | `/opt/app-root/llama_stack_configuration.py` | ro | Python enrichment script |

**SELinux labels:**
- `:z`: Relabels for sharing between host and container (read-write)
- `:ro,z`: Read-only + relabel for SELinux compatibility

**Why mount scripts instead of baking into image?**
- Faster iteration during development (no rebuild needed)
- Easier debugging (modify script, restart container)
- Container image stays generic

### Manual Container Management

If you need more control than the Makefile provides, you can manage the container manually:

#### Build the Image
```bash
podman build -f deploy/llama-stack/test.containerfile -t my-llama-stack:custom .
```

#### Run the Container
```bash
podman run -d \
  --name my-llama-stack \
  -p 9000:8321 \
  -v $(pwd)/run.yaml:/opt/app-root/run.yaml:z \
  -v $(pwd)/lightspeed-stack.yaml:/opt/app-root/lightspeed-stack.yaml:ro,z \
  -e OPENAI_API_KEY \
  my-llama-stack:custom
```

#### Monitor the Container
```bash
# Follow logs
podman logs -f my-llama-stack

# Check health
podman inspect --format='{{.State.Health.Status}}' my-llama-stack

# Execute commands inside container
podman exec my-llama-stack curl http://localhost:8321/v1/health

# View container stats (CPU, memory)
podman stats my-llama-stack
```

#### Stop and Remove
```bash
# Stop gracefully
podman stop -t 10 my-llama-stack

# Remove container
podman rm my-llama-stack

# Remove image
podman rmi my-llama-stack:custom
```

#### Connect LCORE to Manual Container

Update `lightspeed-stack.yaml`:
```yaml
llama_stack:
  use_as_library_client: false
  url: http://localhost:9000  # Use your custom port
```

Then start LCORE without container orchestration:
```bash
make run-stack  # Skips container startup, just runs LCORE
```

---

## See Also

- [OKP Guide](okp_guide.md) - Setting up OKP RAG with containers
- [RAG Guide](rag_guide.md) - RAG configuration and BYOK vector stores
- [Deployment Guide](deployment_guide.md) - Production deployment options
- [Getting Started](getting_started.md) - Alternative: Library mode (no containers)
