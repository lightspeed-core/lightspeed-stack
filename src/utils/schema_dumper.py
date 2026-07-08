"""Function to dump the configuration schema into OpenAPI-compatible format."""

import json
from typing import Any

from pydantic.json_schema import models_json_schema

from models.config import Configuration

from utils.json_schema_updater import recursive_update


def dump_schema(filename: str) -> None:
    """Dump the configuration schema into OpenAPI-compatible JSON file.

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
            [(model, "validation") for model in [Configuration]],
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
