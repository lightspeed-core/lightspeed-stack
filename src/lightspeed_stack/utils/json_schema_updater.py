"""Function to transform a JSON Schema-like dictionary into an OpenAPI-compatible schema."""

from typing import Any


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
