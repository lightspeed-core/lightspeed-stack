# Upstream llama-stack built from Red Hat UBI
FROM registry.access.redhat.com/ubi9/ubi-minimal

USER root

# Install Python and build tools
RUN microdnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs \
    python3.12 python3.12-devel python3.12-pip git tar gcc gcc-c++ make
    
# Install uv
ENV PATH="/root/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy project files for dependency installation
WORKDIR /opt/app-root
COPY pyproject.toml uv.lock LICENSE README.md ./
COPY src ./src

# Install dependencies using uv sync
RUN uv sync --locked --no-install-project --group llslibdev

# Add virtual environment to PATH for llama command
ENV PATH="/opt/app-root/.venv/bin:$PATH"

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
