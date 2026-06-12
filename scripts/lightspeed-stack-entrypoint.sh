#!/bin/bash
# Entrypoint for the library-mode lightspeed-stack container.
# Seeds the RAG kvstore into a writable location, then starts lightspeed-stack.

set -e

# Seed the RAG kvstore into the writable storage volume.
#
# The seed db is mounted read-only from the host (owned by the host user), but
# the embedded llama-stack runs as a non-root user and must write to this
# kvstore at startup (the resource registry shares it). Copying it into the
# storage tree makes the runtime db owned by the container user, so it is
# writable regardless of the host UID. See run.yaml -> storage.backends.kv_default.
RAG_SEED_DIR="${RAG_SEED_DIR:-/opt/app-root/rag-seed}"
STORAGE_RAG_DIR="${STORAGE_RAG_DIR:-/opt/app-root/src/.llama/storage/rag}"
if [ -d "$RAG_SEED_DIR" ]; then
    echo "Seeding RAG kvstore from $RAG_SEED_DIR into $STORAGE_RAG_DIR..."
    mkdir -p "$STORAGE_RAG_DIR"
    cp -f "$RAG_SEED_DIR"/*.db "$STORAGE_RAG_DIR"/
fi

# Use the venv interpreter explicitly: overriding the image entrypoint changes
# PATH ordering, so a bare `python3.12` may resolve to the system interpreter
# (without the app's dependencies) instead of the venv at /app-root/.venv.
exec /app-root/.venv/bin/python3.12 src/lightspeed_stack.py "$@"
