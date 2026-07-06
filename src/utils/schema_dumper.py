"""Function to dump the configuration schema into OpenAPI-compatible format."""

import json
from typing import Any

from pydantic.json_schema import models_json_schema

from models.config import Configuration


# pylint: disable=too-many-boolean-expressions
def recursive_update(
    original: dict[str, Any],
) -> dict[str, Any]:
    """Transform a JSON Schema-like dictionary into an OpenAPI-compatible schema.

    Recursively walks the input mapping and applies compatibility fixes:
    - converts patterns like `anyOf: [{ "type": X }, { "type": "null" }]` into
      a single `"type": X` with `"nullable": True` (optional types)
    - rewrites `"exclusiveMinimum"` to `"minimum"`
    - otherwise preserves entries

    Parameters:
    ----------
        original (dict[str, Any]): Input schema dictionary that is produced by
        Pydantic.

    Returns:
    -------
        dict[str, Any]: A new schema dictionary with all OpenAPI-compatible
        transformations applied.
    """
    new: dict[str, Any] = {}
    for key, value in original.items():
        # recurse into sub-dictionaries
        if isinstance(value, dict):
            new[key] = recursive_update(value)
        # optional types fixes
        elif (
            key == "anyOf"
            and isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], dict)
            and "type" in value[0]
            and isinstance(value[1], dict)
            and value[1].get("type") == "null"
        ):
            # only the first type is correct,
            # we need to ignore the second one
            val = value[0]["type"]
            new["type"] = val
            # create new attribute
            new["nullable"] = True
        # exclusiveMinimum attribute handling is broken
        # in Pydantic - this is simple fix
        elif key == "exclusiveMinimum":
            new["minimum"] = value
        else:
            new[key] = value
    return new


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
