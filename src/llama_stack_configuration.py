"""Llama Stack configuration enrichment.

This module can be used in two ways:
1. As a script: `python llama_stack_configuration.py -c config.yaml`
2. As a module: `from llama_stack_configuration import generate_configuration`
"""

import os
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin

import yaml
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential, CredentialUnavailableError
from llama_stack.core.stack import replace_env_vars

import constants
from log import get_logger

logger = get_logger(__name__)


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


def setup_azure_entra_id_token(
    azure_config: Optional[dict[str, Any]], env_file: str
) -> None:
    """Generate Azure Entra ID access token and write to .env file.

    Skips generation if AZURE_API_KEY is already set (e.g., orchestrator-injected).
    """
    # Skip if already injected by orchestrator (secure production setup)
    if os.environ.get("AZURE_API_KEY"):
        logger.info("Azure Entra ID: AZURE_API_KEY already set, skipping generation")
        return

    if azure_config is None:
        logger.info("Azure Entra ID: Not configured, skipping")
        return

    tenant_id = azure_config.get("tenant_id")
    client_id = azure_config.get("client_id")
    client_secret = azure_config.get("client_secret")
    scope = azure_config.get("scope", "https://cognitiveservices.azure.com/.default")

    if not all([tenant_id, client_id, client_secret]):
        logger.warning(
            "Azure Entra ID: Missing required fields (tenant_id, client_id, client_secret)"
        )
        return

    try:
        credential = ClientSecretCredential(
            tenant_id=str(tenant_id),
            client_id=str(client_id),
            client_secret=str(client_secret),
        )

        token = credential.get_token(scope)

        # Write to .env file
        # Create file if it doesn't exist
        Path(env_file).touch()

        lines = []
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Update or add AZURE_API_KEY
        key_found = False
        for i, line in enumerate(lines):
            if line.startswith("AZURE_API_KEY="):
                lines[i] = f"AZURE_API_KEY={token.token}\n"
                key_found = True
                break

        if not key_found:
            lines.append(f"AZURE_API_KEY={token.token}\n")

        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logger.info(
            "Azure Entra ID: Access token set in env and written to %s", env_file
        )

    except (ClientAuthenticationError, CredentialUnavailableError) as e:
        logger.error("Azure Entra ID: Failed to generate token: %s", e)


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

    # add new backends for each BYOK RAG
    for brag in byok_rag:
        if not brag.get("rag_id"):
            raise ValueError(f"BYOK RAG entry is missing required 'rag_id': {brag}")
        rag_id = brag["rag_id"]
        backend_name = f"byok_{rag_id}_storage"
        output[backend_name] = {
            "type": "kv_sqlite",
            "db_path": brag.get("db_path", f".llama/{rag_id}.db"),
        }
    logger.info(
        "Added %s backends into storage.backends section, total backends %s",
        len(byok_rag),
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
        output.append(
            {
                "provider_id": provider_id,
                "provider_type": brag.get("rag_type", "inline::faiss"),
                "config": {
                    "persistence": {
                        "namespace": "vector_io::faiss",
                        "backend": backend_name,
                    }
                },
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
    base_url = (
        str(rhokp_raw) if rhokp_raw is not None else constants.RH_SERVER_OKP_DEFAULT_URL
    )
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
# Synthesis for Unified Mode (LCORE-836)
# =============================================================================


DEFAULT_BASELINE_RESOURCE = "default_run.yaml"

PROVIDER_TYPE_MAP: dict[str, str] = {
    "openai": "remote::openai",
    "sentence_transformers": "inline::sentence-transformers",
    "azure": "remote::azure",
    "vertexai": "remote::vertexai",
    "watsonx": "remote::watsonx",
    "vllm_rhaiis": "remote::vllm",
    "vllm_rhel_ai": "remote::vllm",
}


def load_default_baseline() -> dict[str, Any]:
    """Load LCORE's built-in default Llama Stack baseline config.

    Returns:
        dict[str, Any]: The default baseline run.yaml parsed as a dict.
    """
    # importlib.resources-style load; `src/data/default_run.yaml` is shipped
    # with the package.
    baseline_path = Path(__file__).parent / "data" / DEFAULT_BASELINE_RESOURCE
    logger.info("Loading built-in default baseline from %s", baseline_path)
    with open(baseline_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def deep_merge_list_replace(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Deep-merge `overlay` onto `base`.

    Maps are merged recursively. Lists and scalars in `overlay` replace the
    corresponding entry in `base` (no append semantics). Result is a new dict;
    neither argument is mutated.

    Parameters:
        base: The base mapping.
        overlay: The mapping whose values take precedence.

    Returns:
        dict[str, Any]: A new mapping with overlay applied on top of base.
    """
    import copy  # pylint: disable=import-outside-toplevel

    result: dict[str, Any] = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_list_replace(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def apply_high_level_inference(
    ls_config: dict[str, Any], inference: dict[str, Any]
) -> None:
    """Apply a high-level `inference` block into `ls_config['providers']['inference']`.

    Replaces the inference provider list entirely. Use `native_override` for
    additive tweaks.

    Parameters:
        ls_config: Llama Stack config dict (modified in place).
        inference: High-level inference section as a dict (with 'providers' list).
    """
    providers_out: list[dict[str, Any]] = []
    for provider in inference.get("providers", []):
        p_type = provider["type"]
        entry: dict[str, Any] = {
            "provider_id": p_type,
            "provider_type": PROVIDER_TYPE_MAP[p_type],
        }
        cfg: dict[str, Any] = {}
        if provider.get("api_key_env"):
            cfg["api_key"] = f"${{env.{provider['api_key_env']}}}"
        if provider.get("allowed_models"):
            cfg["allowed_models"] = provider["allowed_models"]
        if provider.get("extra"):
            cfg.update(provider["extra"])
        if cfg:
            entry["config"] = cfg
        providers_out.append(entry)

    if "providers" not in ls_config:
        ls_config["providers"] = {}
    ls_config["providers"]["inference"] = providers_out
    logger.info(
        "Applied high-level inference section: %s provider entries",
        len(providers_out),
    )


def synthesize_configuration(
    lcs_config: dict[str, Any],
    config_file_dir: Optional[Path] = None,
    default_baseline: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Synthesize a full Llama Stack run.yaml from a unified-mode LCORE config.

    Pipeline:
        1. Baseline = profile file (if set) else `default_baseline` (if provided)
           else LCORE's built-in default.
        2. Apply existing top-level enrichment (BYOK RAG, Solr/OKP).
           Azure Entra ID is intentionally not run here (side-effect on .env).
        3. Apply high-level sections (inference, and later storage/safety/...).
        4. Deep-merge (list-replace) `native_override`.

    Precedence: profile < high-level sections < native_override.

    Parameters:
        lcs_config: Full lightspeed-stack.yaml content as a dict (env-expanded).
        config_file_dir: Directory containing the lightspeed-stack.yaml, used
            to resolve relative `profile:` paths. If None, relative paths are
            resolved against the current working directory.
        default_baseline: Override for the baseline when `profile:` is unset
            (primarily for tests). If None, LCORE's built-in baseline is used.

    Returns:
        dict[str, Any]: The synthesized Llama Stack run.yaml as a dict.

    Raises:
        ValueError: If llama_stack.config is not present in `lcs_config`.
    """
    unified = (lcs_config.get("llama_stack") or {}).get("config")
    if unified is None:
        raise ValueError(
            "synthesize_configuration called without llama_stack.config set"
        )

    # 1. Baseline
    profile = unified.get("profile")
    baseline_kind = unified.get("baseline", "default")
    if profile:
        profile_path = Path(profile)
        if not profile_path.is_absolute() and config_file_dir is not None:
            profile_path = config_file_dir / profile_path
        logger.info("Loading unified-mode profile baseline from %s", profile_path)
        with open(profile_path, "r", encoding="utf-8") as f:
            ls_config: dict[str, Any] = yaml.safe_load(f)
    elif baseline_kind == "empty":
        logger.info("Unified mode: starting from empty baseline")
        ls_config = {}
    elif default_baseline is not None:
        import copy  # pylint: disable=import-outside-toplevel

        ls_config = copy.deepcopy(default_baseline)
    else:
        ls_config = load_default_baseline()

    dedupe_providers_vector_io(ls_config)

    # 2. Existing enrichment (BYOK RAG, Solr/OKP) — Azure stays out (file side-effect).
    enrich_byok_rag(ls_config, lcs_config.get("byok_rag", []))
    enrich_solr(ls_config, lcs_config.get("rag", {}), lcs_config.get("okp", {}))

    # 3. High-level sections
    inference = unified.get("inference")
    if inference is not None:
        apply_high_level_inference(ls_config, inference)

    # 4. native_override — deep-merge (list-replace)
    native_override = unified.get("native_override") or {}
    if native_override:
        ls_config = deep_merge_list_replace(ls_config, native_override)

    dedupe_providers_vector_io(ls_config)
    return ls_config


def migrate_config_dumb(
    run_yaml_path: str,
    lightspeed_yaml_path: str,
    output_path: str,
) -> None:
    """Lossless lift-and-shift migration: fold run.yaml into lightspeed-stack.yaml.

    Reads the legacy two-file configuration (run.yaml + lightspeed-stack.yaml)
    and writes a unified single-file configuration where the entire run.yaml
    content is placed under `llama_stack.config.native_override`. Removes any
    `llama_stack.library_client_config_path` that referenced the old run.yaml.

    This is the "dumb" migration mode — preserves 100% of the existing
    Llama Stack schema content. A future `--smart` mode (out of scope for this
    PoC) would factor portions into high-level sections.

    Parameters:
        run_yaml_path: Path to the existing Llama Stack run.yaml.
        lightspeed_yaml_path: Path to the existing lightspeed-stack.yaml.
        output_path: Path to write the unified lightspeed-stack.yaml.
    """
    logger.info("Reading %s and %s for migration", lightspeed_yaml_path, run_yaml_path)

    with open(run_yaml_path, "r", encoding="utf-8") as f:
        run_yaml_content: dict[str, Any] = yaml.safe_load(f)

    with open(lightspeed_yaml_path, "r", encoding="utf-8") as f:
        lcs_yaml: dict[str, Any] = yaml.safe_load(f)

    llama_stack_section = lcs_yaml.setdefault("llama_stack", {})
    llama_stack_section.pop("library_client_config_path", None)
    # `baseline: empty` is required for true lossless round-trip: default baseline
    # would add extra keys not present in the source run.yaml.
    llama_stack_section["config"] = {
        "baseline": "empty",
        "native_override": run_yaml_content,
    }

    logger.info("Writing unified configuration to %s", output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(lcs_yaml, f, Dumper=YamlDumper, default_flow_style=False)


def synthesize_to_file(
    lcs_config: dict[str, Any],
    output_file: str,
    config_file_dir: Optional[Path] = None,
) -> None:
    """Synthesize unified-mode Llama Stack config and write it to disk.

    Secrets are never resolved — env-var references like `${env.FOO}` are
    preserved verbatim in the output.

    Parameters:
        lcs_config: lightspeed-stack.yaml as a dict.
        output_file: Path to write the synthesized run.yaml.
        config_file_dir: Directory for resolving relative profile paths.
    """
    ls_config = synthesize_configuration(lcs_config, config_file_dir=config_file_dir)
    logger.info("Writing synthesized Llama Stack configuration to %s", output_file)
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(ls_config, f, Dumper=YamlDumper, default_flow_style=False)


# =============================================================================
# Main Generation Function (service/container mode only)
# =============================================================================


def generate_configuration(
    input_file: str,
    output_file: str,
    config: dict[str, Any],
    env_file: str = ".env",
) -> None:
    """Generate enriched Llama Stack configuration for service/container mode.

    Args:
        input_file: Path to input Llama Stack config
        output_file: Path to write enriched config
        config: Lightspeed config dict (from YAML)
        env_file: Path to .env file
    """
    logger.info("Reading Llama Stack configuration from file %s", input_file)

    with open(input_file, "r", encoding="utf-8") as file:
        ls_config = yaml.safe_load(file)

    dedupe_providers_vector_io(ls_config)

    # Enrichment: Azure Entra ID token
    setup_azure_entra_id_token(config.get("azure_entra_id"), env_file)

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
    """CLI entry point.

    Auto-detects the mode:
    - Unified mode: `llama_stack.config` present in the lightspeed config file.
      Synthesizes the full run.yaml (no `-i/--input` needed); writes to `-o`.
    - Legacy mode: requires `-i/--input` run.yaml; enriches it and writes to `-o`.
    """
    parser = ArgumentParser(
        description="Produce Llama Stack run.yaml from Lightspeed config.",
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
        help="Input Llama Stack config for legacy-mode enrichment "
        "(default: run.yaml; ignored in unified mode)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="run_.yaml",
        help="Output run.yaml path (default: run_.yaml)",
    )
    parser.add_argument(
        "-e",
        "--env-file",
        default=".env",
        help="Path to .env file for AZURE_API_KEY (default: .env)",
    )
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        config = replace_env_vars(config)

    unified_present = (config.get("llama_stack") or {}).get("config") is not None
    if unified_present:
        logger.info("Unified mode detected (llama_stack.config present)")
        # Azure Entra ID side-effect (writes .env) stays part of boot — still run it.
        setup_azure_entra_id_token(config.get("azure_entra_id"), args.env_file)
        synthesize_to_file(
            config,
            args.output,
            config_file_dir=Path(args.config).resolve().parent,
        )
    else:
        logger.info("Legacy mode detected (no llama_stack.config)")
        generate_configuration(args.input, args.output, config, args.env_file)


if __name__ == "__main__":
    main()
