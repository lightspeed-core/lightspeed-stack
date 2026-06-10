# DEPS_IMAGE selects the base layer.
# Default: build deps inline (slow but self-contained).
# Override with --build-arg DEPS_IMAGE=lightspeed-llama-stack-deps:local
# to use a pre-built deps image (fast rebuilds, used by `make build-llama-stack-image`).
ARG DEPS_IMAGE=deps-builder

# --- Stage 1: deps (skipped by BuildKit when DEPS_IMAGE is overridden) ---
FROM registry.access.redhat.com/ubi9/python-312 AS deps-builder

USER root

# Install additional build tools
RUN dnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs \
    git tar gcc gcc-c++ make && \
    dnf clean all

# Install uv
ENV PATH="/root/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy only dependency-related files
WORKDIR /opt/app-root
COPY pyproject.toml uv.lock LICENSE README.md ./
COPY src/version.py ./src/version.py

# Copy submodule dependency files only (source copied in app stage)
COPY providers/pyproject.tom[l] providers/uv.loc[k] ./providers/

# Install dependencies (not the project itself)
RUN uv sync --locked --no-install-project --group llslibdev
RUN if [ -f providers/pyproject.toml ]; then \
        cd providers && uv export --locked --no-hashes > /tmp/providers-reqs.txt \
        && uv pip install -r /tmp/providers-reqs.txt; \
    fi

# Add virtual environment to PATH for llama command
# Add providers to PYTHONPATH so lightspeed_stack_providers modules can be imported
ENV PATH="/opt/app-root/.venv/bin:$PATH" \
    PYTHONPATH="/opt/app-root/src:/opt/app-root/providers"

# Set HOME directory so llama-stack uses /opt/app-root/src/.llama
ENV HOME="/opt/app-root/src"

# Create python3 symlink for compatibility
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3

# Create required directories
RUN mkdir -p /opt/app-root/src/.llama/storage \
             /opt/app-root/src/.llama/providers.d \
             /opt/app-root/src/.cache/huggingface && \
    chown -R 1001:0 /opt/app-root && \
    chmod -R 775 /opt/app-root

USER 1001

# --- Stage 2: app (thin source-only layer) ---
FROM ${DEPS_IMAGE}

USER root

# Copy source code and providers submodule
COPY src ./src
COPY provider[s] ./providers

# Copy enrichment scripts for runtime config enrichment
COPY src/llama_stack_configuration.py /opt/app-root/llama_stack_configuration.py
COPY scripts/llama-stack-entrypoint.sh /opt/app-root/enrich-entrypoint.sh
RUN chmod +x /opt/app-root/enrich-entrypoint.sh && \
    chown 1001:0 /opt/app-root/enrich-entrypoint.sh /opt/app-root/llama_stack_configuration.py && \
    chown -R 1001:0 /opt/app-root/src && \
    chmod -R 775 /opt/app-root/src

# Switch back to the original user
USER 1001

ENTRYPOINT ["/opt/app-root/enrich-entrypoint.sh"]
