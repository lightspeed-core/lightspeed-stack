"""Function to dump the schema of all data models into OpenAPI-compatible format."""

import json

from pydantic.json_schema import models_json_schema

import models.compaction as models_compaction
from utils.json_schema_updater import recursive_update


def dump_models(filename: str) -> None:
    """Dump the schema of all models into OpenAPI-compatible JSON file.

    Parameters:
    ----------
        - filename: str - name of file to export the schema to

    Returns:
    -------
        - None

    Raises:
    ------
        IOError: If the file cannot be written.
    """
    with open(filename, "w", encoding="utf-8") as fout:
        # retrieve the schema
        _, schemas = models_json_schema(
            [(model, "validation") for model in [
                models_compaction.ConversationSummary
                ]],
            ref_template="#/components/schemas/{model}",
        )

        # fix the schema
        schemas = recursive_update(schemas)

        # add all required metadata
        openapi_schema = {
            "openapi": "3.0.0",
            "info": {
                "title": "Lightspeed Core Stack",
                "version": "0.3.0",
            },
            "components": {
                "schemas": schemas.get("$defs", {}),
            },
            "paths": {},
        }
        json.dump(openapi_schema, fout, indent=4)
