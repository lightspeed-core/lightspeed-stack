"""Utility function to dump schema with list of models into OpenAPI-compatible JSON format."""

import json

from pydantic.json_schema import models_json_schema

from lightspeed_stack.utils.json_schema_updater import recursive_update


def dump_openapi_schema(models: list, filename: str) -> None:
    """Write an OpenAPI-compatible JSON schema for the given models to a file.

    Parameters:
    ----------
        - models: list - Pydantic model classes to include in the schema
        - filename: str - name of file to export the schema to

    Raises:
    ------
        IOError: If the file cannot be written.
    """
    with open(filename, "w", encoding="utf-8") as fout:
        _, schemas = models_json_schema(
            [(model, "validation") for model in models],
            ref_template="`#/components/schemas/`{model}",
        )
        schemas = recursive_update(schemas)
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
