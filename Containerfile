# vim: set filetype=dockerfile
FROM registry.access.redhat.com/ubi9/ubi-minimal AS builder

ARG APP_ROOT=/app-root
ARG LSC_SOURCE_DIR=.

# UV_PYTHON_DOWNLOADS=0 : Disable Python interpreter downloads and use the system interpreter.
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="$PATH:/root/.local/bin"

WORKDIR /app-root

RUN microdnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs \
    python3.12 python3.12-devel python3.12-pip git tar \
    gcc gcc-c++ make

# Add explicit files and directories
# (avoid accidental inclusion of local directories or env files or credentials)
COPY ${LSC_SOURCE_DIR}/src ./src
COPY ${LSC_SOURCE_DIR}/pyproject.toml ${LSC_SOURCE_DIR}/LICENSE ${LSC_SOURCE_DIR}/README.md ${LSC_SOURCE_DIR}/uv.lock ./

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN uv sync --locked --no-dev && \
    uv pip install \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp \
    opentelemetry-instrumentation \
    aiosqlite \
    litellm \
    blobfile \
    datasets \
    sqlalchemy \
    faiss-cpu \
    mcp \
    autoevals \
    psutil \
    torch \
    peft \
    trl


# Final image without uv package manager
FROM registry.access.redhat.com/ubi9/python-312-minimal
ARG APP_ROOT=/app-root
WORKDIR /app-root

# PYTHONDONTWRITEBYTECODE 1 : disable the generation of .pyc
# PYTHONUNBUFFERED 1 : force the stdout and stderr streams to be unbuffered
# PYTHONCOERCECLOCALE 0, PYTHONUTF8 1 : skip legacy locales and use UTF-8 mode
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONCOERCECLOCALE=0 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=en_US.UTF-8

COPY --from=builder --chown=1001:1001 /app-root /app-root

# this directory is checked by ecosystem-cert-preflight-checks task in Konflux
COPY --from=builder /app-root/LICENSE /licenses/

# Add executables from .venv to system PATH
ENV PATH="/app-root/.venv/bin:$PATH"

# Run the application
EXPOSE 8080
ENTRYPOINT ["python3.12", "src/lightspeed_stack.py"]

LABEL vendor="Red Hat, Inc."

# no-root user is checked in Konflux
USER 1001
