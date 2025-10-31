# vim: set filetype=dockerfile
FROM registry.access.redhat.com/ubi9/python-312 AS builder

ARG APP_ROOT=/app-root
ARG LSC_SOURCE_DIR=.

# UV_PYTHON_DOWNLOADS=0 : Disable Python interpreter downloads and use the system interpreter.
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app-root

# Install gcc - required by polyleven python package on aarch64
# (dependency of autoevals, no pre-built binary wheels for linux on aarch64)
USER root
RUN dnf --disablerepo="*" --enablerepo="ubi-9-appstream-rpms" --enablerepo="ubi-9-baseos-rpms" install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs gcc

# Install uv package manager
RUN pip3.12 install "uv==0.8.15"

# Add explicit files and directories
# (avoid accidental inclusion of local directories or env files or credentials)
COPY ${LSC_SOURCE_DIR}/src ./src
COPY ${LSC_SOURCE_DIR}/pyproject.toml ${LSC_SOURCE_DIR}/LICENSE ${LSC_SOURCE_DIR}/README.md ${LSC_SOURCE_DIR}/uv.lock ${LSC_SOURCE_DIR}/requirements.txt ./

# Bundle additional dependencies for library mode.
# Source cachi2 environment for hermetic builds if available, otherwise use normal installation
# cachi2.env has these env vars:
# PIP_FIND_LINKS=/cachi2/output/deps/pip
# PIP_NO_INDEX=true
RUN if [ -f /cachi2/cachi2.env ]; then \
    . /cachi2/cachi2.env && uv venv --seed --no-index --find-links ${PIP_FIND_LINKS} && . .venv/bin/activate && pip install --no-index --find-links ${PIP_FIND_LINKS} -r requirements.txt; \
    else \
    uv sync --locked --no-dev --group llslibdev; \
    fi

# Explicitly remove some packages to mitigate some CVEs
# - GHSA-wj6h-64fc-37mp: python-ecdsa package won't fix it upstream.
#   This package is required by python-jose. python-jose supports multiple
#   backends. By default it uses python-cryptography package instead of
#   python-ecdsa. It is safe to remove python-ecdsa package.
RUN uv pip uninstall ecdsa

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

# Add uv to final image for derived images to add additional dependencies
# with command:
# $ uv pip install <dependency>
# Temporarily disabled due to temp directory issues
# RUN pip3.12 install "uv==0.8.15"

USER root

# Additional tools for derived images
RUN microdnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs jq patch

# Add executables from .venv to system PATH
ENV PATH="/app-root/.venv/bin:$PATH"

# Run the application
EXPOSE 8080
ENTRYPOINT ["python3.12", "src/lightspeed_stack.py"]

LABEL vendor="Red Hat, Inc."

# no-root user is checked in Konflux
USER 1001
