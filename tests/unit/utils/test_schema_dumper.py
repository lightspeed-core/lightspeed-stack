"""Unit tests for utils/schema_dumper module."""

from json import load
from pathlib import Path
from typing import Any

from utils.schema_dumper import dump_schema, recursive_update


def test_update_empty_input() -> None:
    """Test how recursive_update function transforms empty input."""
    original: dict[str, Any] = {}
    expected: dict[str, Any] = {}

    # perform the update
    result = recursive_update(original)

    # empty dict should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_no_change_for_simple_schema() -> None:
    """Test how recursive_update function trasforms simple non-empty input."""
    original: dict[str, Any] = {
        "type": "string",
        "maxLength": 10,
    }

    # we need to distinguish between original and a copy
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_no_change_for_simple_object() -> None:
    """Test how recursive_update function trasforms simple non-empty input."""
    original: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
    }

    # we need to distinguish between original and a copy
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_recursive_recurse_into_subdicts() -> None:
    """Test the recursive_update on input containing sub-dictionaries."""
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": 0},
        },
    }
    expected = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0},
        },
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_exclusive_minimum_handling_positive_value() -> None:
    """Test how minimum integer value description is transformed by recursive_update function."""
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": 100},
        },
    }
    expected = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 100},
        },
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_exclusive_minimum_handling_zero_value() -> None:
    """Test how minimum integer value description is transformed by recursive_update function."""
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": 0},
        },
    }
    expected = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0},
        },
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_exclusive_minimum_handling_negative_value() -> None:
    """Test how minimum integer value description is transformed by recursive_update function."""
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": -100},
        },
    }
    expected = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": -100},
        },
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_anyof_with_null_transformed_to_nullable() -> None:
    """Test how the de-facto Optional type is transformed."""
    original = {
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ]
    }
    expected = {
        "type": "string",
        "nullable": True,
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_anyof_with_null_transformed_to_nullable_different_type() -> None:
    """Test how the de-facto Optional type is transformed."""
    original = {
        "anyOf": [
            {"type": "integer"},
            {"type": "null"},
        ]
    }
    expected = {
        "type": "integer",
        "nullable": True,
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_anyof_list_with_more_complex_first_entry() -> None:
    """Test how the de-facto Optional type is transformed."""
    original = {
        "anyOf": [
            {"type": "array", "items": {"type": "integer"}},
            {"type": "null"},
        ]
    }
    expected = {
        "type": "array",
        "nullable": True,
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_anyof_not_transformed_when_conditions_not_met() -> None:
    """Test various conditions where anyOf should be left unchanged."""
    cases = [
        {"anyOf": "not-a-list"},
        {"anyOf": [{"type": "string"}]},  # length < 2
        {"anyOf": [{"notype": "x"}, {"type": "null"}]},  # first item missing type
        {"anyOf": [{"type": "string"}, {"type": "number"}]},  # second not null
        {
            "anyOf": [{"type": "integer"}, {"type": "integer"}]
        },  # both types are the same
    ]

    for original in cases:
        # perform the update
        result = recursive_update(original)

        # non-empty dict with known content should be returned
        assert result == original


def test_mixed_keys_preserve_order_like_behavior() -> None:
    """Verify that keys other than handled ones are preserved."""
    original = {
        "exclusiveMinimum": 5,
        "anyOf": [
            {"type": "integer"},
            {"type": "null"},
        ],
        "description": "example",
    }
    # exclusiveMinimum should become minimum; anyOf -> type+nullable and description preserved
    expected = {
        "minimum": 5,
        "type": "integer",
        "nullable": True,
        "description": "example",
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_deeply_nested_anyof_and_exclusive_minimum() -> None:
    """More complicated structures."""
    original = {
        "level1": {
            "level2": {
                "anyOf": [
                    {"type": "object", "properties": {"x": {"type": "string"}}},
                    {"type": "null"},
                ],
                "exclusiveMinimum": 1,
            }
        }
    }
    expected = {
        "level1": {
            "level2": {
                "type": "object",
                "nullable": True,
                "minimum": 1,
            }
        }
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_preserve_other_types_and_lists() -> None:
    """Nullable/optional types handling."""
    original = {
        "type": "object",
        "required": ["a", "b"],
        "properties": {
            "a": {"type": "integer"},
            "b": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        },
    }
    expected = {
        "type": "object",
        "required": ["a", "b"],
        "properties": {
            "a": {"type": "integer"},
            "b": {"type": "boolean", "nullable": True},
        },
    }
    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_handles_none_values() -> None:
    """None values should be preserved."""
    original = {"key": None}
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_handles_empty_lists() -> None:
    """Empty list values should be preserved."""
    original: dict[str, Any] = {"key": []}
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_handles_empty_maps() -> None:
    """Empty maps values should be preserved."""
    original: dict[str, Any] = {"key": {}}
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_anyof_with_additional_fields_on_first_item() -> None:
    """Optional (nullable) types with additional fields."""
    original = {
        "anyOf": [
            {"type": "string", "format": "email", "maxLength": 50},
            {"type": "null"},
        ]
    }
    expected = {
        "type": "string",
        "nullable": True,
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_anyof_with_additional_fields_more_items() -> None:
    """Optional (nullable) types with additional fields."""
    original = {
        "exclusiveMinimum": 5,
        "anyOf": [
            {"type": "string", "format": "email", "maxLength": 50},
            {"type": "null"},
        ],
        "description": "example",
    }
    expected = {
        "minimum": 5,
        "type": "string",
        "nullable": True,
        "description": "example",
    }

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_dump_schema(tmpdir: Path) -> None:
    """Test that schema can be dump into a JSON file.

    An example of schema dump:
    {
        "openapi": "3.0.0",
        "info": {
            "title": "Lightspeed Core Stack",
            "version": "0.3.0"
        },
        "components": {
            "schemas": {
                "A2AStateConfiguration": {
                    "additionalProperties": false,
                    "description": "xyzzy",
                    "properties": {
                        "sqlite": {
                            "anyOf": [
                                {
                                    "$ref": "#/components/schemas/SQLiteDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "SQLite database configuration for A2A state storage.",
                            "title": "SQLite configuration"
                        },
                    ...
                }
                ...
                ...
                ...
        },
        "paths": {}
    }
    """
    filename = tmpdir / "foo.json"
    dump_schema(str(filename))

    with open(filename, "r", encoding="utf-8") as fin:
        # schema should be stored in JSON format
        content = load(fin)
        assert content is not None

        # top-level keys test
        keys = ("openapi", "info", "components", "paths")
        for key in keys:
            assert key in content

        # components should be top-level node
        components = content["components"]
        assert components is not None

        # schemas should be a node stored inside components node
        assert "schemas" in components
        schemas = components["schemas"]
        assert schemas is not None

        # list of schemas expected in a dump
        expected_schemas = (
            "A2AStateConfiguration",
            "APIKeyTokenConfiguration",
            "AccessRule",
            "Action",
            "ApprovalFilter",
            "ApprovalsConfiguration",
            "AuthenticationConfiguration",
            "AuthorizationConfiguration",
            "AzureEntraIdConfiguration",
            "ByokRag",
            "CORSConfiguration",
            "CompactionConfiguration",
            "Configuration",
            "ConversationHistoryConfiguration",
            "CustomProfile",
            "Customization",
            "DatabaseConfiguration",
            "InMemoryCacheConfig",
            "InferenceConfiguration",
            "JsonPathOperator",
            "JwkConfiguration",
            "JwtConfiguration",
            "JwtRoleRule",
            "LlamaStackConfiguration",
            "ModelContextProtocolServer",
            "OkpConfiguration",
            "PostgreSQLDatabaseConfiguration",
            "QuotaHandlersConfiguration",
            "QuotaLimiterConfiguration",
            "QuotaSchedulerConfiguration",
            "RHIdentityConfiguration",
            "RagConfiguration",
            "RerankerConfiguration",
            "RlsapiV1Configuration",
            "SQLiteDatabaseConfiguration",
            "ServiceConfiguration",
            "SkillsConfiguration",
            "SplunkConfiguration",
            "TLSConfiguration",
            "UserDataCollection",
        )
        for expected_schema in expected_schemas:
            assert expected_schema in schemas
