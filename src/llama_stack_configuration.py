"""Llama Stack configuration enrichment.

This module can be used in two ways:
1. As a script: `python llama_stack_configuration.py -c config.yaml`
2. As a module: `from llama_stack_configuration import generate_configuration`
"""

import os
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

import yaml
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential, CredentialUnavailableError
from llama_stack.core.stack import replace_env_vars
from log import get_logger

logger = get_logger(__name__)


class YamlDumper(yaml.Dumper):  # pylint: disable=too-many-ancestors
    """Custom YAML dumper with proper indentation levels."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        """Control the indentation level of formatted YAML output.

        Force block-style indentation for emitted YAML by ensuring the dumper
        never uses "indentless" indentation.

        Parameters:
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
    azure_config: dict[str, Any] | None, env_file: str
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


def construct_storage_backends_section(
    ls_config: dict[str, Any], byok_rag: list[dict[str, Any]]
) -> dict[str, Any]:
    """Construct storage.backends section in Llama Stack configuration file.

    Builds the storage.backends section for a Llama Stack configuration by
    preserving existing backends and adding new ones for each BYOK RAG.

    Parameters:
        ls_config (dict[str, Any]): Existing Llama Stack configuration mapping.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG definitions.

    Returns:
        dict[str, Any]: The storage.backends dict with new backends added.
    """
    output: dict[str, Any] = {}

    # preserve existing backends
    if "storage" in ls_config and "backends" in ls_config["storage"]:
        output = ls_config["storage"]["backends"].copy()

    # add new backends for each BYOK RAG
    for brag in byok_rag:
        vector_db_id = brag.get("vector_db_id", "")
        backend_name = f"byok_{vector_db_id}_storage"
        output[backend_name] = {
            "type": "kv_sqlite",
            "db_path": brag.get("db_path", f".llama/{vector_db_id}.db"),
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
        ls_config (dict[str, Any]): Existing Llama Stack configuration mapping
        used as the base; existing `registered_resources.vector_stores` entries
        are preserved if present.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG definitions to be added to
        the `vector_stores` section.

    Returns:
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
    existing_store_ids = {vs.get("vector_store_id") for vs in output}
    added = 0
    for brag in byok_rag:
        vector_db_id = brag.get("vector_db_id", "")
        if vector_db_id in existing_store_ids:
            continue
        existing_store_ids.add(vector_db_id)
        added += 1
        output.append(
            {
                "vector_store_id": vector_db_id,
                "provider_id": f"byok_{vector_db_id}",
                "embedding_model": brag.get("embedding_model", ""),
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
        ls_config (dict[str, Any]): Existing Llama Stack configuration mapping.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG definitions.

    Returns:
        list[dict[str, Any]]: The models list with embedding models added.
    """
    output: list[dict[str, Any]] = []

    # preserve existing models
    if "registered_resources" in ls_config:
        if "models" in ls_config["registered_resources"]:
            output = ls_config["registered_resources"]["models"].copy()

    # add embedding models for each BYOK RAG
    for brag in byok_rag:
        embedding_model = brag.get("embedding_model", "")
        vector_db_id = brag.get("vector_db_id", "")
        embedding_dimension = brag.get("embedding_dimension")

        # Strip sentence-transformers/ prefix if present
        provider_model_id = embedding_model
        if provider_model_id.startswith("sentence-transformers/"):
            provider_model_id = provider_model_id[len("sentence-transformers/") :]

        # Skip if embedding model already registered
        existing_model_ids = [m.get("provider_model_id") for m in output]
        if provider_model_id in existing_model_ids:
            continue

        output.append(
            {
                "model_id": f"byok_{vector_db_id}_embedding",
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
        ls_config (dict[str, Any]): Existing Llama Stack configuration
        dictionary; if it contains providers.vector_io, those entries are used
        as the starting list.
        byok_rag (list[dict[str, Any]]): List of BYOK RAG specifications to convert
        into provider entries.

    Returns:
        list[dict[str, Any]]: The resulting providers/vector_io list containing
        the original entries (if any) plus one entry per item in `byok_rag`.
        Each appended entry has `provider_id` set to "byok_<vector_db_id>",
        `provider_type` set from the RAG item, and a `config` with `persistence`
        referencing the corresponding backend.
    """
    output = []

    # fill-in existing vector_io entries
    if "providers" in ls_config and "vector_io" in ls_config["providers"]:
        output = ls_config["providers"]["vector_io"].copy()

    # append new vector_io entries
    for brag in byok_rag:
        vector_db_id = brag.get("vector_db_id", "")
        backend_name = f"byok_{vector_db_id}_storage"
        provider_id = f"byok_{vector_db_id}"
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
        len(byok_rag),
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

    # Enrichment: Azure Entra ID token
    setup_azure_entra_id_token(config.get("azure_entra_id"), env_file)

    # Enrichment: BYOK RAG
    enrich_byok_rag(ls_config, config.get("byok_rag", []))

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

    generate_configuration(args.input, args.output, config, args.env_file)


if __name__ == "__main__":
    main()
