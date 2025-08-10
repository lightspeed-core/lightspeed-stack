# vim: set filetype=dockerfile
FROM registry.access.redhat.com/ubi9/ubi-minimal

ARG APP_ROOT=/app-root

ENV PATH="$PATH:/root/.local/bin"

WORKDIR ${APP_ROOT}
COPY run.yaml ./

RUN microdnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs \
    python3.12 python3.12-devel python3.12-pip git tar

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN uv -h

RUN uv venv && \
    uv pip install llama-stack==0.2.17 \
    fastapi \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp \
    opentelemetry-instrumentation \
    aiosqlite \
    litellm[proxy]==1.75.3 \
    openai==1.99.1 \
    uvicorn \
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

CMD ["uv", "run", "llama", "stack", "run", "run.yaml"]
