"""Llama Stack configuration enrichment and synthesis.

This module can be used in two ways:
1. As a script: `python llama_stack_configuration.py -c config.yaml`
2. As a module: `from llama_stack_configuration import generate_configuration`

Two related responsibilities live here:

- **Enrichment** (legacy mode): takes an operator-supplied ``run.yaml`` and
  layers dynamic values (BYOK RAG, Solr/OKP, Azure Entra ID) on top of it.
- **Synthesis** (unified mode, LCORE-2336): builds a complete ``run.yaml`` from
  high-level operator inputs in ``lightspeed-stack.yaml`` — a baseline (built-in
  default, a profile file, or empty), the same enrichment, the high-level
  ``inference.providers`` section, and a raw ``native_override`` deep-merged
  last. ``run.yaml`` becomes an implementation detail LCORE owns rather than an
  operator-facing artifact.
"""

# pylint: disable=too-many-lines

import copy
import os
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import yaml
from ogx.core.stack import replace_env_vars
from pydantic import SecretStr

import constants
from log import get_logger

logger = get_logger(__name__)

# Maps a UnifiedInferenceProvider.type (canonical, backend-agnostic vocabulary)
# to the Llama Stack provider_type emitted by apply_high_level_inference. The
# completeness of this map against UnifiedInferenceProvider.type is asserted by
# a unit test so a new Literal value cannot be added without a mapping.
PROVIDER_TYPE_MAP: dict[str, str] = {
    "openai": "remote::openai",
    "ollama": "remote::ollama",
    "vllm": "remote::vllm",
    "sentence_transformers": "inline::sentence-transformers",
    "azure": "remote::azure",
    "vertexai": "remote::vertexai",
    "watsonx": "remote::watsonx",
    "vllm_rhaiis": "remote::vllm",
    "vllm_rhel_ai": "remote::vllm",
}

# Maps Llama Stack provider_type -> config field name for the auth token.
# Providers not listed default to "api_key".
API_KEY_FIELD_MAP: dict[str, str] = {
    "remote::vllm": "api_token",
}

# Package-relative path to the built-in default baseline run.yaml shipped with
# LCORE, used when unified mode selects baseline "default" without a profile.
DEFAULT_BASELINE_RESOURCE: Path = Path(__file__).parent / "data" / "default_run.yaml"

VECTOR_IO_TEMPLATES: dict[str, dict[str, Any]] = {
    "inline::faiss": {
        "persistence_backend": "{backend_name}",
        "persistence_namespace": "vector_io::faiss",
        "needs_storage_backend": True,
        "extra_fields": {},
    },
    "remote::pgvector": {
        "persistence_backend": "kv_default",
        "persistence_namespace": "vector_io::pgvector",
        "needs_storage_backend": False,
        "extra_fields": {
            "host": "${env.POSTGRES_HOST}",
            "port": "${env.POSTGRES_PORT}",
            "db": "${env.POSTGRES_DATABASE}",
            "user": "${env.POSTGRES_USER}",
            "password": "${env.POSTGRES_PASSWORD}",
        },
    },
}


class YamlDumper(yaml.Dumper):  # pylint: disable=too-many-ancestors
    """Custom YAML dumper with proper indentation levels."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        """Control the indentation level of formatted YAML output.

        Force block-style indentation for emitted YAML by ensuring the dumper
        never uses "indentless" indentation.

        Parameters:
        ----------
            flow (bool): Whether the YAML flow style is being used; forwarded
            to the base implementation.
            indentless (bool): Ignored — this implementation always enforces
            indented block style.
        """
        _ = indentless
        return super().increase_indent(flow, False)


# =============================================================================
# Enrichment: Azure Entra ID
# =============================================================================


def enrich_azure_entra_id_inference(
    ls_config: dict[str, Any],
    azure_entra_id: Optional[dict[str, Any]],
) -> None:
    """Enrich remote::azure inference provider for Entra ID authentication.

    When Azure Entra ID is configured, the remote::azure inference provider is enriched
    with model_validation=false to defer model validation to runtime.

    Parameters:
        ls_config (dict[str, Any]): Mutable Llama Stack configuration dictionary to update.
        azure_entra_id (Optional[dict[str, Any]]): Lightspeed azure_entra_id block,
            or None.

    Returns:
        None: The configuration is modified in place.
    """
    if azure_entra_id is None:
        return

    inference_providers = ls_config.get("providers", {}).get("inference", [])

    for provider in inference_providers:
        if provider.get("provider_type") != "remote::azure":
            continue

        provider_config = provider.setdefault("config", {})
        provider_config["model_validation"] = False
        logger.info(
            "Azure Entra ID: configured remote::azure provider with "
            "model_validation=false"
        )


# =============================================================================
# Enrichment: BYOK RAG
# =============================================================================


def _dedupe_vector_io_list(entries: list[Any]) -> list[dict[str, Any]]:
    """Keep the first dict per stripped ``provider_id``; keep entries without an id."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        raw_pid = item.get("provider_id")
        if raw_pid is None:
            out.append(item)
            continue
        key = str(raw_pid).strip()
        if not key:
            out.append(item)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def dedupe_providers_vector_io(ls_config: dict[str, Any]) -> None:
    """Collapse ``providers.vector_io`` to one entry per ``provider_id``."""
    if "providers" not in ls_config or "vector_io" not in ls_config["providers"]:
        return
    raw = ls_config["providers"]["vector_io"]
    if not isinstance(raw, list):
        return
    ls_config["providers"]["vector_io"] = _dedupe_vector_io_list(raw)


def construct_storage_backends_section(
    ls_config: dict[str, Any], byok_rag: list[dict[str, Any]]
) -> dict[str, Any]:
    """Construct storage.backends section in Llama Stack configuration file.

    Builds the storage.backends section for a Llama Stack configuration by
    preserving existing backends and adding new ones for each BYOK RAG.

    Parameters:
    ----------
        ls_config (dict[str, Any]): Existing Llama Stack configuration mapping.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG definitions.

    Returns:
    -------
        dict[str, Any]: The storage.backends dict with new backends added.
    """
    output: dict[str, Any] = {}

    # preserve existing backends
    if "storage" in ls_config and "backends" in ls_config["storage"]:
        output = ls_config["storage"]["backends"].copy()

    # add new backends for each BYOK RAG (skip types that don't need one)
    added = 0
    for brag in byok_rag:
        if not brag.get("rag_id"):
            raise ValueError(f"BYOK RAG entry is missing required 'rag_id': {brag}")
        rag_type = brag.get("rag_type", constants.DEFAULT_RAG_TYPE)
        template = VECTOR_IO_TEMPLATES.get(rag_type, {})
        if not template.get("needs_storage_backend", True):
            continue
        rag_id = brag["rag_id"]
        backend_name = f"byok_{rag_id}_storage"
        output[backend_name] = {
            "type": "kv_sqlite",
            "db_path": brag.get("db_path", f".llama/{rag_id}.db"),
        }
        added += 1
    logger.info(
        "Added %s backends into storage.backends section, total backends %s",
        added,
        len(output),
    )
    return output


def construct_vector_stores_section(
    ls_config: dict[str, Any], byok_rag: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Construct registered_resources.vector_stores section in Llama Stack config.

    Builds the vector_stores section for a Llama Stack configuration.

    Parameters:
    ----------
        ls_config (dict[str, Any]): Existing Llama Stack configuration mapping
        used as the base; existing `registered_resources.vector_stores` entries
        are preserved if present.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG definitions to be added to
        the `vector_stores` section.

    Returns:
    -------
        list[dict[str, Any]]: The `vector_stores` list where each entry is a mapping with keys:
            - `vector_store_id`: identifier of the vector store (for Llama Stack config)
            - `provider_id`: provider identifier prefixed with `"byok_"`
            - `embedding_model`: name of the embedding model
            - `embedding_dimension`: embedding vector dimensionality
    """
    output = []

    # fill-in existing vector_stores entries from registered_resources
    if "registered_resources" in ls_config:
        if "vector_stores" in ls_config["registered_resources"]:
            output = ls_config["registered_resources"]["vector_stores"].copy()

    # append new vector_stores entries, skipping duplicates
    # Resolve ${env.VAR} patterns so comparisons work when existing entries
    # use environment variable references and new entries have resolved values.
    existing_store_ids = {
        replace_env_vars(vs.get("vector_store_id", "")) for vs in output
    }
    added = 0
    for brag in byok_rag:
        if not brag.get("rag_id"):
            raise ValueError(f"BYOK RAG entry is missing required 'rag_id': {brag}")
        if not brag.get("vector_db_id"):
            raise ValueError(
                f"BYOK RAG entry is missing required 'vector_db_id': {brag}"
            )
        rag_id = brag["rag_id"]
        vector_db_id = brag["vector_db_id"]
        if vector_db_id in existing_store_ids:
            continue
        existing_store_ids.add(vector_db_id)
        added += 1
        embedding_model = brag.get("embedding_model", constants.DEFAULT_EMBEDDING_MODEL)
        output.append(
            {
                "vector_store_id": vector_db_id,
                "provider_id": f"byok_{rag_id}",
                "embedding_model": embedding_model,
                "embedding_dimension": brag.get("embedding_dimension"),
            }
        )
    logger.info(
        "Added %s items into registered_resources.vector_stores, total items %s",
        added,
        len(output),
    )
    return output


def construct_models_section(
    ls_config: dict[str, Any], byok_rag: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Construct registered_resources.models section with embedding models.

    Adds embedding model entries for each BYOK RAG configuration.

    Parameters:
    ----------
        ls_config (dict[str, Any]): Existing Llama Stack configuration mapping.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG definitions.

    Returns:
    -------
        list[dict[str, Any]]: The models list with embedding models added.
    """
    output: list[dict[str, Any]] = []

    # preserve existing models
    if "registered_resources" in ls_config:
        if "models" in ls_config["registered_resources"]:
            output = ls_config["registered_resources"]["models"].copy()

    # add embedding models for each BYOK RAG
    for brag in byok_rag:
        if not brag.get("rag_id"):
            raise ValueError(f"BYOK RAG entry is missing required 'rag_id': {brag}")
        rag_id = brag["rag_id"]
        embedding_model = brag.get("embedding_model", constants.DEFAULT_EMBEDDING_MODEL)
        embedding_dimension = brag.get("embedding_dimension")

        # Skip if no embedding model specified
        if not embedding_model:
            continue

        # Strip sentence-transformers/ prefix if present
        provider_model_id = embedding_model
        provider_model_id = provider_model_id.removeprefix("sentence-transformers/")

        # Skip if embedding model already registered
        existing_model_ids = [m.get("provider_model_id") for m in output]
        if provider_model_id in existing_model_ids:
            continue

        output.append(
            {
                "model_id": f"byok_{rag_id}_embedding",
                "model_type": "embedding",
                "provider_id": "sentence-transformers",
                "provider_model_id": provider_model_id,
                "metadata": {
                    "embedding_dimension": embedding_dimension,
                },
            }
        )
    logger.info(
        "Added embedding models into registered_resources.models, total models %s",
        len(output),
    )
    return output


def _build_vector_io_config(
    rag_type: str, backend_name: str, brag: dict[str, Any]
) -> dict[str, Any]:
    """Build the provider config dict from VECTOR_IO_TEMPLATES.

    Parameters:
        rag_type: Llama Stack provider type (e.g. 'inline::faiss', 'remote::pgvector').
        backend_name: Storage backend name (used when template has '{backend_name}').
        brag: BYOK RAG entry dict — extra_fields are read from here.

    Returns:
        dict[str, Any]: Provider config mapping.
    """
    template = VECTOR_IO_TEMPLATES.get(rag_type)
    if template is None:
        raise ValueError(
            f"Unsupported rag_type '{rag_type}'. "
            f"Supported types: {list(VECTOR_IO_TEMPLATES.keys())}"
        )
    persistence_backend = template["persistence_backend"].format(
        backend_name=backend_name
    )
    config: dict[str, Any] = {
        "persistence": {
            "namespace": template["persistence_namespace"],
            "backend": persistence_backend,
        }
    }
    for field, default in template.get("extra_fields", {}).items():
        value = brag.get(field)
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if value is None or (isinstance(value, str) and not value.strip()):
            value = default
        config[field] = value
    return config


def construct_vector_io_providers_section(
    ls_config: dict[str, Any], byok_rag: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Construct providers/vector_io section in Llama Stack configuration file.

    Builds the providers/vector_io list for a Llama Stack configuration by
    preserving existing entries and appending providers derived from BYOK RAG
    entries.

    Parameters:
    ----------
        ls_config (dict[str, Any]): Existing Llama Stack configuration
        dictionary; if it contains providers.vector_io, those entries are used
        as the starting list.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG specifications to convert
        into provider entries.

    Returns:
    -------
        list[dict[str, Any]]: The resulting providers/vector_io list containing
        the original entries (if any) plus one entry per item in `byok_rag`.
        Each appended entry has `provider_id` set to "byok_<vector_db_id>",
        `provider_type` set from the RAG item, and a `config` with `persistence`
        referencing the corresponding backend.
    """
    output: list[dict[str, Any]] = []

    if "providers" in ls_config and "vector_io" in ls_config["providers"]:
        raw = ls_config["providers"]["vector_io"]
        if isinstance(raw, list):
            output = _dedupe_vector_io_list(raw)
        else:
            output = []

    existing_ids = {
        str(p["provider_id"]).strip()
        for p in output
        if p.get("provider_id") is not None and str(p["provider_id"]).strip()
    }

    added = 0
    for brag in byok_rag:
        if not brag.get("rag_id"):
            raise ValueError(f"BYOK RAG entry is missing required 'rag_id': {brag}")
        rag_id = str(brag["rag_id"]).strip()
        backend_name = f"byok_{rag_id}_storage"
        provider_id = f"byok_{rag_id}"
        if provider_id in existing_ids:
            continue
        existing_ids.add(provider_id)
        added += 1
        rag_type = brag.get("rag_type", constants.DEFAULT_RAG_TYPE)
        config = _build_vector_io_config(rag_type, backend_name, brag)
        output.append(
            {
                "provider_id": provider_id,
                "provider_type": rag_type,
                "config": config,
            }
        )
    logger.info(
        "Added %s items into providers/vector_io section, total items %s",
        added,
        len(output),
    )
    return output


def enrich_byok_rag(ls_config: dict[str, Any], byok_rag: list[dict[str, Any]]) -> None:
    """Enrich Llama Stack config with BYOK RAG settings.

    Args:
        ls_config: Llama Stack configuration dict (modified in place)
        byok_rag: List of BYOK RAG configurations
    """
    if len(byok_rag) == 0:
        logger.info("BYOK RAG is not configured: skipping")
        dedupe_providers_vector_io(ls_config)
        return

    logger.info("Enriching Llama Stack config with BYOK RAG")

    # Add storage backends
    if "storage" not in ls_config:
        ls_config["storage"] = {}
    ls_config["storage"]["backends"] = construct_storage_backends_section(
        ls_config, byok_rag
    )

    # Add vector_io providers
    if "providers" not in ls_config:
        ls_config["providers"] = {}
    ls_config["providers"]["vector_io"] = construct_vector_io_providers_section(
        ls_config, byok_rag
    )

    # Add registered vector stores
    if "registered_resources" not in ls_config:
        ls_config["registered_resources"] = {}
    ls_config["registered_resources"]["vector_stores"] = (
        construct_vector_stores_section(ls_config, byok_rag)
    )

    # Add embedding models
    ls_config["registered_resources"]["models"] = construct_models_section(
        ls_config, byok_rag
    )


# =============================================================================
# Enrichment: Solr
# =============================================================================


def enrich_solr(  # pylint: disable=too-many-locals
    ls_config: dict[str, Any],
    rag_config: dict[str, Any],
    okp_config: dict[str, Any],
) -> None:
    """Enrich Llama Stack config with Solr settings.

    Args:
        ls_config: Llama Stack configuration dict (modified in place)
        rag_config: RAG configuration dict. Used keys:
            - inline (list[str]): inline RAG IDs
            - tool (list[str]): tool RAG IDs
        okp_config: OKP configuration dict. Used keys:
            - chunk_filter_query (str): Solr filter query for chunk retrieval
            - rhokp_url (str): OKP/Solr base URL (e.g. from ${env.RH_SERVER_OKP})
    """
    inline_ids = rag_config.get("inline") or []
    tool_ids = rag_config.get("tool") or []
    okp_enabled = constants.OKP_RAG_ID in inline_ids or constants.OKP_RAG_ID in tool_ids

    if not okp_enabled:
        logger.info("OKP is not enabled: skipping")
        return

    user_filter = okp_config.get("chunk_filter_query")
    chunk_filter_query = (
        f"{constants.SOLR_CHUNK_FILTER_QUERY} AND {user_filter}"
        if user_filter
        else constants.SOLR_CHUNK_FILTER_QUERY
    )

    rhokp_raw = okp_config.get("rhokp_url")
    base_url_raw = (
        str(rhokp_raw) if rhokp_raw is not None else constants.RH_SERVER_OKP_DEFAULT_URL
    )
    # Resolve environment variables in the URL (e.g., ${env.RH_SERVER_OKP})
    base_url = replace_env_vars(base_url_raw)
    solr_url = urljoin(base_url, "/solr")

    logger.info("Enriching Llama Stack config with OKP")

    # Add vector_io provider for Solr
    if "providers" not in ls_config:
        ls_config["providers"] = {}
    if "vector_io" not in ls_config["providers"]:
        ls_config["providers"]["vector_io"] = []

    # Add Solr provider if not already present
    existing_providers = [
        p.get("provider_id") for p in ls_config["providers"]["vector_io"]
    ]
    if constants.SOLR_PROVIDER_ID not in existing_providers:
        collection_env = (
            f"${{env.SOLR_COLLECTION:={constants.SOLR_DEFAULT_VECTOR_STORE_ID}}}"
        )
        vector_field_env = (
            f"${{env.SOLR_VECTOR_FIELD:={constants.SOLR_DEFAULT_VECTOR_FIELD}}}"
        )
        content_field_env = (
            f"${{env.SOLR_CONTENT_FIELD:={constants.SOLR_DEFAULT_CONTENT_FIELD}}}"
        )
        embedding_model_env = (
            f"${{env.SOLR_EMBEDDING_MODEL:={constants.SOLR_DEFAULT_EMBEDDING_MODEL}}}"
        )
        embedding_dim_env = (
            f"${{env.SOLR_EMBEDDING_DIM:={constants.SOLR_DEFAULT_EMBEDDING_DIMENSION}}}"
        )
        ls_config["providers"]["vector_io"].append(
            {
                "provider_id": constants.SOLR_PROVIDER_ID,
                "provider_type": "remote::solr_vector_io",
                "config": {
                    "solr_url": solr_url,
                    "collection_name": collection_env,
                    "vector_field": vector_field_env,
                    "content_field": content_field_env,
                    "embedding_model": embedding_model_env,
                    "embedding_dimension": embedding_dim_env,
                    "chunk_window_config": {
                        "chunk_parent_id_field": "parent_id",
                        "chunk_content_field": "chunk_field",
                        "chunk_index_field": "chunk_index",
                        "chunk_token_count_field": "num_tokens",
                        "chunk_online_source_url_field": "online_source_url",
                        "chunk_source_path_field": "source_path",
                        "parent_total_chunks_field": "total_chunks",
                        "parent_total_tokens_field": "total_tokens",
                        "chunk_filter_query": chunk_filter_query,
                        "chunk_family_fields": ["headings"],
                    },
                    "persistence": {
                        "namespace": constants.SOLR_DEFAULT_VECTOR_STORE_ID,
                        "backend": "kv_default",
                    },
                },
            }
        )
        logger.info("Added OKP provider to providers/vector_io")

    # Add vector store registration for Solr
    if "registered_resources" not in ls_config:
        ls_config["registered_resources"] = {}
    if "vector_stores" not in ls_config["registered_resources"]:
        ls_config["registered_resources"]["vector_stores"] = []

    # Add Solr vector store if not already present
    existing_stores = [
        vs.get("vector_store_id")
        for vs in ls_config["registered_resources"]["vector_stores"]
    ]
    if constants.SOLR_DEFAULT_VECTOR_STORE_ID not in existing_stores:
        # Build environment variable expression
        embedding_model_env = (
            f"${{env.SOLR_EMBEDDING_MODEL:={constants.SOLR_DEFAULT_EMBEDDING_MODEL}}}"
        )

        ls_config["registered_resources"]["vector_stores"].append(
            {
                "vector_store_id": constants.SOLR_DEFAULT_VECTOR_STORE_ID,
                "provider_id": constants.SOLR_PROVIDER_ID,
                "embedding_model": embedding_model_env,
                "embedding_dimension": constants.SOLR_DEFAULT_EMBEDDING_DIMENSION,
            }
        )
        logger.info(
            "Added %s vector store to registered_resources",
            constants.SOLR_DEFAULT_VECTOR_STORE_ID,
        )

    # Add Solr embedding model to registered_resources.models if not already present
    if "models" not in ls_config["registered_resources"]:
        ls_config["registered_resources"]["models"] = []

    # Strip sentence-transformers/ prefix from constant for provider_model_id
    provider_model_id = constants.SOLR_DEFAULT_EMBEDDING_MODEL
    provider_model_id = provider_model_id.removeprefix("sentence-transformers/")

    # Check if already registered
    registered_models = ls_config["registered_resources"]["models"]
    existing_model_ids = [m.get("provider_model_id") for m in registered_models]
    if provider_model_id not in existing_model_ids:
        # Build environment variable expression
        provider_model_env = f"${{env.SOLR_EMBEDDING_MODEL:={provider_model_id}}}"

        ls_config["registered_resources"]["models"].append(
            {
                "model_id": "solr_embedding",
                "model_type": "embedding",
                "provider_id": "sentence-transformers",
                "provider_model_id": provider_model_env,
                "metadata": {
                    "embedding_dimension": constants.SOLR_DEFAULT_EMBEDDING_DIMENSION,
                },
            }
        )
        logger.info("Added OKP embedding model to registered_resources.models")


# =============================================================================
# Synthesis: unified-mode run.yaml generation (LCORE-2336)
# =============================================================================


def load_default_baseline() -> dict[str, Any]:
    """Load LCORE's built-in default baseline Llama Stack configuration.

    Returns:
        dict[str, Any]: The parsed contents of ``src/data/default_run.yaml``,
        the baseline used when unified mode selects ``baseline: default``
        without a profile.

    Raises:
        OSError: If the shipped baseline file cannot be read.
        yaml.YAMLError: If the baseline file is not valid YAML.
    """
    with open(DEFAULT_BASELINE_RESOURCE, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def deep_merge_list_replace(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Deep-merge ``overlay`` onto ``base`` with list-replacement semantics.

    Maps are merged recursively; lists and scalars from the overlay replace the
    corresponding value in the base wholesale (Decision T2). Neither argument is
    mutated — a new dict is returned.

    Parameters:
        base: The base mapping (e.g. the synthesized baseline so far).
        overlay: The mapping whose values take precedence (e.g. native_override).

    Returns:
        dict[str, Any]: A new merged mapping.
    """
    result = copy.deepcopy(base)
    for key, overlay_value in overlay.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            result[key] = deep_merge_list_replace(base_value, overlay_value)
        else:
            result[key] = copy.deepcopy(overlay_value)
    return result


def apply_high_level_inference(
    ls_config: dict[str, Any], inference: dict[str, Any]
) -> None:
    """Expand high-level ``inference.providers`` into Llama Stack provider entries.

    Each high-level provider is mapped to a Llama Stack ``providers.inference``
    entry via :data:`PROVIDER_TYPE_MAP`. The emitted ``provider_id`` is the
    optional explicit high-level ``id`` when set; otherwise the provider ``type``
    with underscores hyphenated, so an inline embedder declared as
    ``sentence_transformers`` becomes ``sentence-transformers`` and matches the
    baseline's ecosystem convention (e.g. the default embedding model reference).
    An entry whose ``provider_id`` already exists in the baseline (or was emitted
    by an earlier high-level entry) is replaced with an info log; new ones are
    appended. Secrets are emitted as ``${env.<VAR>}`` references, never resolved
    values (R6).

    Parameters:
        ls_config: The Llama Stack configuration being synthesized (modified in
            place).
        inference: The root ``inference`` section as a dict; only its
            ``providers`` list is consumed here.

    Returns:
        None: ``ls_config`` is modified in place.
    """
    providers = inference.get("providers") or []
    if not providers:
        return

    providers_section = ls_config.setdefault("providers", {})
    inference_list = providers_section.setdefault("inference", [])

    for provider in providers:
        provider_type = provider["type"]
        emitted_id = provider.get("id") or provider_type.replace("_", "-")
        ls_provider_type = PROVIDER_TYPE_MAP[provider_type]
        entry: dict[str, Any] = {
            "provider_id": emitted_id,
            "provider_type": ls_provider_type,
        }

        provider_config: dict[str, Any] = {}
        if provider.get("extra"):
            provider_config.update(provider["extra"])
        if provider.get("api_key_env"):
            key_field = API_KEY_FIELD_MAP.get(ls_provider_type, "api_key")
            provider_config[key_field] = "${env." + provider["api_key_env"] + "}"
        if provider.get("allowed_models"):
            provider_config["allowed_models"] = provider["allowed_models"]
        if provider_config:
            entry["config"] = provider_config

        # Replace a baseline provider with the same id, else append.
        for index, existing in enumerate(inference_list):
            if isinstance(existing, dict) and existing.get("provider_id") == emitted_id:
                logger.info(
                    "Replacing existing inference provider with "
                    "provider_id=%r; a later high-level entry overwrote it",
                    emitted_id,
                )
                inference_list[index] = entry
                break
        else:
            inference_list.append(entry)

    logger.info(
        "Applied %d high-level inference provider(s) to synthesized config",
        len(providers),
    )


def ensure_mcp_tool_runtime(ls_config: dict[str, Any]) -> None:
    """Ensure the default MCP tool_runtime provider exists in ``ls_config``.

    Adds ``tool_runtime`` to ``apis`` when missing, then appends the default
    ``model-context-protocol`` provider under ``providers.tool_runtime`` when
    no entry with that ``provider_id`` is already present. Existing entries
    (including ``rag-runtime``) are left untouched.

    Parameters:
        ls_config: The Llama Stack configuration being synthesized (modified
            in place).

    Returns:
        None: ``ls_config`` is modified in place.
    """
    apis = ls_config.setdefault("apis", [])
    if "tool_runtime" not in apis:
        apis.append("tool_runtime")

    providers_section = ls_config.setdefault("providers", {})
    tool_runtime = providers_section.setdefault("tool_runtime", [])
    for existing in tool_runtime:
        if (
            isinstance(existing, dict)
            and existing.get("provider_id") == constants.MCP_TOOL_RUNTIME_PROVIDER_ID
        ):
            return

    tool_runtime.append(
        {
            "provider_id": constants.MCP_TOOL_RUNTIME_PROVIDER_ID,
            "provider_type": constants.MCP_TOOL_RUNTIME_PROVIDER_TYPE,
            "config": {},
        }
    )
    logger.info(
        "Added MCP tool_runtime provider provider_id=%r",
        constants.MCP_TOOL_RUNTIME_PROVIDER_ID,
    )


def _resolve_profile_path(profile: str, config_file_dir: Optional[str]) -> Path:
    """Resolve a ``profile:`` path against the loaded config's directory (R8).

    Absolute paths are returned as-is. Relative paths resolve against
    ``config_file_dir`` (the directory of the loaded ``lightspeed-stack.yaml``)
    when provided, otherwise against the current working directory.

    Parameters:
        profile: The profile path as written in the config.
        config_file_dir: Directory of the loaded ``lightspeed-stack.yaml``.

    Returns:
        Path: The resolved profile path.
    """
    path = Path(profile)
    if not path.is_absolute() and config_file_dir is not None:
        path = Path(config_file_dir) / path
    return path


def synthesize_configuration(
    lcs_config: dict[str, Any],
    config_file_dir: Optional[str] = None,
    default_baseline: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Synthesize a full Llama Stack ``run.yaml`` dict from a unified config.

    Implements the unified-mode synthesis pipeline: select a baseline (profile
    file, empty, or the built-in default), apply the existing enrichment
    (Azure Entra ID, BYOK RAG, Solr/OKP) for parity with legacy mode (R7),
    expand the high-level ``inference.providers`` section, ensure the default
    MCP tool_runtime provider when the baseline was not empty, and deep-merge
    the raw ``native_override`` last (R5).

    Parameters:
        lcs_config: The full ``lightspeed-stack.yaml`` parsed into a dict.
        config_file_dir: Directory of the loaded ``lightspeed-stack.yaml``,
            used to resolve a relative ``profile:`` path (R8).
        default_baseline: Optional pre-loaded baseline dict; when omitted and a
            default baseline is needed, :func:`load_default_baseline` is used.

    Returns:
        dict[str, Any]: The synthesized Llama Stack configuration.
    """
    llama_stack = lcs_config.get("llama_stack") or {}
    unified = llama_stack.get("config")  # None when only top-level inputs are set

    # 1-2. Select the baseline.
    baseline_was_empty = False
    if unified and unified.get("profile"):
        profile_path = _resolve_profile_path(unified["profile"], config_file_dir)
        logger.info("Loading synthesis baseline from profile %s", profile_path)
        with open(profile_path, "r", encoding="utf-8") as file:
            baseline = yaml.safe_load(file) or {}
    elif unified and unified.get("baseline") == "empty":
        logger.info("Synthesizing from an empty baseline")
        baseline_was_empty = True
        baseline = {}
    else:
        baseline = (
            default_baseline
            if default_baseline is not None
            else load_default_baseline()
        )

    ls_config: dict[str, Any] = copy.deepcopy(baseline)

    # 3. Normalize duplicated vector_io providers in the baseline.
    dedupe_providers_vector_io(ls_config)

    # 4. Existing enrichment — same calls as legacy generate_configuration so
    #    unified output matches legacy output for equivalent inputs (R7).
    enrich_azure_entra_id_inference(ls_config, lcs_config.get("azure_entra_id"))
    enrich_byok_rag(ls_config, lcs_config.get("byok_rag", []))
    enrich_solr(ls_config, lcs_config.get("rag", {}), lcs_config.get("okp", {}))

    # 5. High-level inference providers (Decision S5 — a root-level section).
    inference = lcs_config.get("inference") or {}
    if inference.get("providers"):
        apply_high_level_inference(ls_config, inference)

    # 6. Ensure MCP tool_runtime for default/profile baselines (skipped for
    #    baseline: empty so migrate round-trips stay lossless).
    if not baseline_was_empty:
        ensure_mcp_tool_runtime(ls_config)

    # 7. Raw escape hatch, deep-merged last with list replacement (R5).
    if unified and unified.get("native_override"):
        ls_config = deep_merge_list_replace(ls_config, unified["native_override"])

    # 8. Dedupe again in case native_override or enrichment reintroduced dupes.
    dedupe_providers_vector_io(ls_config)

    return ls_config


def synthesize_to_file(
    lcs_config: dict[str, Any],
    output_file: str,
    config_file_dir: Optional[str] = None,
    default_baseline: Optional[dict[str, Any]] = None,
) -> None:
    """Synthesize a unified config and write it to ``output_file`` with mode 0600.

    The synthesized ``run.yaml`` may carry literal secrets when an operator put
    them into ``native_override`` (or migrated a legacy file), so the file is
    created owner-read/write-only and re-chmodded on every boot rather than
    relying on umask (R10). Parent directories are created as needed.

    Parameters:
        lcs_config: The full ``lightspeed-stack.yaml`` parsed into a dict.
        output_file: Destination path for the synthesized ``run.yaml``.
        config_file_dir: Directory of the loaded ``lightspeed-stack.yaml`` for
            relative ``profile:`` resolution (R8).
        default_baseline: Optional pre-loaded baseline dict.

    Returns:
        None.
    """
    ls_config = synthesize_configuration(lcs_config, config_file_dir, default_baseline)

    path = Path(output_file)
    if path.parent != Path(""):
        path.parent.mkdir(parents=True, exist_ok=True)

    # O_CREAT's mode only applies when the file is newly created; chmod after
    # the write guarantees 0600 even when overwriting a pre-existing file.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        yaml.dump(ls_config, file, Dumper=YamlDumper, default_flow_style=False)
    os.chmod(str(path), 0o600)

    logger.info("Wrote synthesized Llama Stack configuration to %s (mode 0600)", path)


# =============================================================================
# Migration: legacy two-file config -> unified single file (LCORE-2337)
# =============================================================================


def migrate_config_dumb(
    run_yaml_path: str,
    lightspeed_yaml_path: str,
    output_path: str,
) -> None:
    """Migrate a legacy two-file config to a unified single file (dumb mode).

    "Dumb" lift-and-shift: the operator's ``lightspeed-stack.yaml`` is kept
    verbatim except for its ``llama_stack`` section, where
    ``library_client_config_path`` is dropped and replaced by a unified
    ``config`` block that lifts the *entire* legacy ``run.yaml`` body into
    ``native_override`` with ``baseline: empty``. Synthesizing the result then
    starts from an empty baseline and deep-merges only the lifted run.yaml, so
    it reproduces the original run.yaml (Decision T7) — a lossless round-trip,
    without trying to factor anything into high-level sections (that "smart"
    mode is deferred future work).

    All other ``lightspeed-stack.yaml`` content (name, service, byok_rag, …) is
    preserved untouched, so any existing enrichment keeps working in unified
    mode exactly as it did in legacy mode.

    Parameters:
        run_yaml_path: Path to the legacy Llama Stack ``run.yaml``.
        lightspeed_yaml_path: Path to the legacy ``lightspeed-stack.yaml``.
        output_path: Path to write the unified ``lightspeed-stack.yaml``.

    Returns:
        None.

    Raises:
        OSError: If an input file cannot be read or the output cannot be
            written.
        yaml.YAMLError: If an input file is not valid YAML.
        ValueError: If either input file does not parse to a mapping (e.g. an
            empty or comment-only file).
    """
    with open(run_yaml_path, "r", encoding="utf-8") as file:
        run_yaml = yaml.safe_load(file)
    with open(lightspeed_yaml_path, "r", encoding="utf-8") as file:
        lcs_config = yaml.safe_load(file)

    # An empty or comment-only YAML file parses to None; fail with a clear
    # message rather than a downstream AttributeError/TypeError.
    if not isinstance(lcs_config, dict):
        raise ValueError(
            f"{lightspeed_yaml_path} did not parse to a mapping; cannot migrate."
        )
    if not isinstance(run_yaml, dict):
        raise ValueError(f"{run_yaml_path} did not parse to a mapping; cannot migrate.")

    # Preserve the whole lightspeed-stack.yaml; only rewrite the llama_stack
    # section: drop the legacy path, add the unified config block.
    llama_stack = dict(lcs_config.get("llama_stack") or {})
    llama_stack.pop("library_client_config_path", None)
    llama_stack["config"] = {
        "baseline": "empty",
        "native_override": run_yaml,
    }
    lcs_config["llama_stack"] = llama_stack

    logger.info(
        "Migrating legacy config (%s + %s) to unified %s",
        lightspeed_yaml_path,
        run_yaml_path,
        output_path,
    )
    # The lifted run.yaml may carry literal secrets, so write owner-only (0600),
    # matching synthesize_to_file. O_CREAT's mode only applies on create, so
    # chmod after the write also tightens a pre-existing file.
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        yaml.dump(lcs_config, file, Dumper=YamlDumper, default_flow_style=False)
    os.chmod(output_path, 0o600)


# =============================================================================
# Main Generation Function (service/container mode only)
# =============================================================================


def generate_configuration(
    input_file: str,
    output_file: str,
    config: dict[str, Any],
) -> None:
    """Generate enriched Llama Stack configuration for service/container mode.

    Args:
        input_file: Path to input Llama Stack config
        output_file: Path to write enriched config
        config: Lightspeed config dict (from YAML)
    """
    logger.info("Reading Llama Stack configuration from file %s", input_file)

    with open(input_file, "r", encoding="utf-8") as file:
        ls_config = yaml.safe_load(file)

    dedupe_providers_vector_io(ls_config)

    # Enrichment: Azure Entra ID deferred auth
    enrich_azure_entra_id_inference(ls_config, config.get("azure_entra_id"))

    # Enrichment: BYOK RAG
    enrich_byok_rag(ls_config, config.get("byok_rag", []))

    # Enrichment: Solr - enabled when "okp" appears in either inline or tool list
    enrich_solr(ls_config, config.get("rag", {}), config.get("okp", {}))

    dedupe_providers_vector_io(ls_config)

    logger.info("Writing Llama Stack configuration into file %s", output_file)

    with open(output_file, "w", encoding="utf-8") as file:
        yaml.dump(ls_config, file, Dumper=YamlDumper, default_flow_style=False)


# =============================================================================
# CLI Entry Point
# =============================================================================


def main() -> None:
    """CLI entry point."""
    parser = ArgumentParser(
        description="Enrich Llama Stack config with Lightspeed values",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="lightspeed-stack.yaml",
        help="Lightspeed config file (default: lightspeed-stack.yaml)",
    )
    parser.add_argument(
        "-i",
        "--input",
        default="run.yaml",
        help="Input Llama Stack config (default: run.yaml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="run_.yaml",
        help="Output enriched config (default: run_.yaml)",
    )
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    generate_configuration(args.input, args.output, config)


if __name__ == "__main__":
    main()
