# Upstream llama-stack built from Red Hat UBI Python 3.12 image
FROM registry.access.redhat.com/ubi9/python-312

USER root

# Install additional build tools
RUN dnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs \
    git tar gcc gcc-c++ make && \
    dnf clean all
    
# Install uv
ENV PATH="/root/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy project files for dependency installation
WORKDIR /opt/app-root
COPY pyproject.toml uv.lock LICENSE README.md ./
COPY src ./src
COPY providers ./providers

# Install dependencies using uv sync
RUN uv sync --locked --no-install-project --group llslibdev

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

# Copy enrichment scripts for runtime config enrichment
COPY src/llama_stack_configuration.py /opt/app-root/llama_stack_configuration.py
COPY scripts/llama-stack-entrypoint.sh /opt/app-root/enrich-entrypoint.sh
RUN chmod +x /opt/app-root/enrich-entrypoint.sh && \
    chown 1001:0 /opt/app-root/enrich-entrypoint.sh /opt/app-root/llama_stack_configuration.py

# Switch back to the original user
USER 1001

ENTRYPOINT ["/opt/app-root/enrich-entrypoint.sh"]
