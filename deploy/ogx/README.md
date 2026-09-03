# Llama Stack container image

`test.containerfile` builds the Llama Stack server image used by
`docker-compose.yaml` (server mode, e.g. for the e2e suite). Besides the
Llama Stack distribution itself, the image bundles the pieces needed to
generate its run configuration at container start:

- `/opt/app-root/ogx_configuration.py` — the config-generation
  script (copied from `src/ogx_configuration.py`).
- `/opt/app-root/data/default_run.yaml` — the shipped default baseline
  (copied from `src/data/`), resolved by the script as `./data/` relative
  to its own location.
- `/opt/app-root/enrich-entrypoint.sh` — the entrypoint (copied from
  `scripts/ogx-entrypoint.sh`).

## Startup modes

The entrypoint invokes the script against the mounted
`lightspeed-stack.yaml`, and the script auto-detects the configuration
shape:

- **Unified mode** — the `lightspeed-stack.yaml` carries a *synthesis
  input* (a non-empty `inference.providers` or `vector_store.providers`,
  or a `llama_stack.config` block). The full `run.yaml` is synthesized
  from it; no external `run.yaml` mount is needed.
- **Legacy mode** — no synthesis input present. The mounted `run.yaml`
  (`$LLAMA_STACK_CONFIG`, default `/opt/app-root/run.yaml`) is enriched
  with lightspeed dynamic values (BYOK RAG, Solr/OKP, Azure Entra ID).

The repository `docker-compose.yaml` mounts both files and works for
either mode — with a unified `lightspeed-stack.yaml` the `run.yaml`
mount is simply ignored. A unified-only deployment needs just:

```yaml
services:
  llama-stack:
    build:
      context: .
      dockerfile: deploy/ogx/test.containerfile
    ports:
      - "8321:8321"
    volumes:
      - ./lightspeed-stack.yaml:/opt/app-root/lightspeed-stack.yaml:ro,z
```

## Rebuilding

The compose file also mounts host copies of the script, the baseline
data directory, and the entrypoint over their baked-in counterparts, so
`docker compose up` picks up local changes to any of them without an
image rebuild. Rebuild (`docker compose build llama-stack`) when
dependencies (`pyproject.toml` / `uv.lock`) or the providers change.
