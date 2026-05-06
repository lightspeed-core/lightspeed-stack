"""Llama Stack configuration enrichment.

This module can be used in two ways:
1. As a script: `python llama_stack_configuration.py -c config.yaml`
2. As a module: `from llama_stack_configuration import generate_configuration`
"""

from argparse import ArgumentParser
from typing import Any, Optional
from urllib.parse import urljoin

import yaml
from llama_stack.core.stack import replace_env_vars
from pydantic import SecretStr

import constants
from log import get_logger

logger = get_logger(__name__)

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
