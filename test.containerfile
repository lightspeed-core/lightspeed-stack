# vim: set filetype=dockerfile
FROM registry.access.redhat.com/ubi9/ubi-minimal

ARG APP_ROOT=/app-root

ENV PATH="$PATH:/root/.local/bin"

WORKDIR ${APP_ROOT}
COPY run.yaml ./
COPY pyproject.toml ./
COPY uv.lock ./
COPY LICENSE ./
COPY README.md ./
COPY src/ ./src/

RUN microdnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs \
    python3.12 python3.12-devel python3.12-pip git tar

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN uv -h

# Install from pyproject.toml using uv sync for version consistency  
# Note: using --no-install-project since this is llama-stack container, not lightspeed-stack
# Include dev deps for testing (pytest, behave, etc.)
RUN uv sync --locked --no-install-project --group dev --group llslibdev

CMD ["uv", "run", "llama", "stack", "run", "run.yaml"]
