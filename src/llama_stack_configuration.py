"""Llama Stack configuration handling."""

from typing import Any

import yaml

from log import get_logger

from models.config import Configuration, ByokRag

logger = get_logger(__name__)


# pylint: disable=too-many-ancestors
class YamlDumper(yaml.Dumper):
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


def generate_configuration(
    input_file: str, output_file: str, config: Configuration
) -> None:
    """Generate new Llama Stack configuration.

    Update a Llama Stack YAML configuration file by inserting BYOK RAG vector
    DB and provider entries when present.

    Reads the YAML configuration from `input_file`, and if `config.byok_rag`
    contains items, updates or creates the `vector_dbs` and
    `providers.vector_io` sections (preserving any existing entries) based on
    that BYOK RAG data, then writes the resulting configuration to
    `output_file`. If `config.byok_rag` is empty, the input configuration is
    written unchanged to `output_file`.

    Parameters:
        input_file (str): Path to the existing Llama Stack YAML configuration to read.
        output_file (str): Path where the updated YAML configuration will be written.
        config (Configuration): Configuration object whose `byok_rag` list
        supplies BYOK RAG entries to be added.
    """
    logger.info("Reading Llama Stack configuration from file %s", input_file)

    with open(input_file, "r", encoding="utf-8") as file:
        ls_config = yaml.safe_load(file)

    if len(config.byok_rag) == 0:
        logger.info("BYOK RAG is not configured: finishing")
    else:
        logger.info("Processing Llama Stack configuration")
        # create or update configuration section vector_dbs
        ls_config["vector_dbs"] = construct_vector_dbs_section(
            ls_config, config.byok_rag
        )
        # create or update configuration section providers/vector_io
        ls_config["providers"]["vector_io"] = construct_vector_io_providers_section(
            ls_config, config.byok_rag
        )

    logger.info("Writing Llama Stack configuration into file %s", output_file)

    with open(output_file, "w", encoding="utf-8") as file:
        yaml.dump(ls_config, file, Dumper=YamlDumper, default_flow_style=False)


def construct_vector_dbs_section(
    ls_config: dict[str, Any], byok_rag: list[ByokRag]
) -> list[dict[str, Any]]:
    """Construct vector_dbs section in Llama Stack configuration file.

    Builds the vector_dbs section for a Llama Stack configuration.

    Parameters:
        ls_config (dict[str, Any]): Existing Llama Stack configuration mapping
        used as the base; existing `vector_dbs` entries are preserved if
        present.
        byok_rag (list[ByokRag]): List of BYOK RAG definitions to be added to
        the `vector_dbs` section.

    Returns:
        list[dict[str, Any]]: The `vector_dbs` list where each entry is a mapping with keys:
            - `vector_db_id`: identifier of the vector database
            - `provider_id`: provider identifier prefixed with `"byok_"`
            - `embedding_model`: name of the embedding model
            - `embedding_dimension`: embedding vector dimensionality
    """
    output = []

    # fill-in existing vector_dbs entries
    if "vector_dbs" in ls_config:
        output = ls_config["vector_dbs"]

    # append new vector_dbs entries
    for brag in byok_rag:
        output.append(
            {
                "vector_db_id": brag.vector_db_id,
                "provider_id": "byok_" + brag.vector_db_id,
                "embedding_model": brag.embedding_model,
                "embedding_dimension": brag.embedding_dimension,
            }
        )
    logger.info(
        "Added %s items into vector_dbs section, total items %s",
        len(byok_rag),
        len(output),
    )
    return output


def construct_vector_io_providers_section(
    ls_config: dict[str, Any], byok_rag: list[ByokRag]
) -> list[dict[str, Any]]:
    """Construct providers/vector_io section in Llama Stack configuration file.

    Builds the providers/vector_io list for a Llama Stack configuration by
    preserving existing entries and appending providers derived from BYOK RAG
    entries.

    Parameters:
        ls_config (dict[str, Any]): Existing Llama Stack configuration
        dictionary; if it contains providers.vector_io, those entries are used
        as the starting list.
        byok_rag (list[ByokRag]): List of BYOK RAG specifications to convert
        into provider entries.

    Returns:
        list[dict[str, Any]]: The resulting providers/vector_io list containing
        the original entries (if any) plus one entry per item in `byok_rag`.
        Each appended entry has `provider_id` set to "byok_<vector_db_id>",
        `provider_type` set from the RAG item, and a `config` with a `kvstore`
        pointing to ".llama/<vector_db_id>.db", `namespace` as None, and `type`
        "sqlite".
    """
    output = []

    # fill-in existing vector_io entries
    if "vector_io" in ls_config["providers"]:
        output = ls_config["providers"]["vector_io"]

    # append new vector_io entries
    for brag in byok_rag:
        output.append(
            {
                "provider_id": "byok_" + brag.vector_db_id,
                "provider_type": brag.rag_type,
                "config": {
                    "kvstore": {
                        "db_path": ".llama/" + brag.vector_db_id + ".db",
                        "namespace": None,
                        "type": "sqlite",
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
