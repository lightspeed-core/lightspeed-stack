"""Unit tests for utils/json_schema_updater module."""

from typing import Any

from lightspeed_stack.utils.json_schema_updater import recursive_update


def test_update_empty_input() -> None:
    """Test how recursive_update function transforms empty input."""
    # input to updater
    original: dict[str, Any] = {}

    # expected output from updater
    expected: dict[str, Any] = {}

    # perform the update
    result = recursive_update(original)

    # empty dict should be returned
    assert result == expected

    # ensure a new dict is returned, not the same object
    assert result is not original


def test_no_change_for_simple_schema() -> None:
    """Test how recursive_update function trasforms simple non-empty input."""
    # input to updater
    original: dict[str, Any] = {
        "type": "string",
        "maxLength": 10,
    }

    # expected output from updater
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
    # input to updater
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
    # input to updater
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": 0},
        },
    }

    # expected output from updater
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
    # input to updater
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": 100},
        },
    }

    # expected output from updater
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
    # input to updater
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": 0},
        },
    }

    # expected output from updater
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
    # input to updater
    original = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "exclusiveMinimum": -100},
        },
    }

    # expected output from updater
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
    # input to updater
    original = {
        "anyOf": [
            {"type": "string"},
            {"type": "null"},
        ]
    }

    # expected output from updater
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
    # input to updater
    original = {
        "anyOf": [
            {"type": "integer"},
            {"type": "null"},
        ]
    }

    # expected output from updater
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
    # input to updater
    original = {
        "anyOf": [
            {"type": "array", "items": {"type": "integer"}},
            {"type": "null"},
        ]
    }

    # expected output from updater
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
    # input to updater
    original = {
        "exclusiveMinimum": 5,
        "anyOf": [
            {"type": "integer"},
            {"type": "null"},
        ],
        "description": "example",
    }

    # expected output from updater
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
    # input to updater
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

    # expected output from updater
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
    # input to updater
    original = {
        "type": "object",
        "required": ["a", "b"],
        "properties": {
            "a": {"type": "integer"},
            "b": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        },
    }

    # expected output from updater
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
    # input to updater
    original = {"key": None}

    # expected output from updater
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_handles_empty_lists() -> None:
    """Empty list values should be preserved."""
    # input to updater
    original: dict[str, Any] = {"key": []}

    # expected output from updater
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_handles_empty_maps() -> None:
    """Empty maps values should be preserved."""
    # input to updater
    original: dict[str, Any] = {"key": {}}

    # expected output from updater
    expected = original.copy()

    # perform the update
    result = recursive_update(original)

    # non-empty dict with known content should be returned
    assert result == expected


def test_anyof_with_additional_fields_on_first_item() -> None:
    """Optional (nullable) types with additional fields."""
    # input to updater
    original = {
        "anyOf": [
            {"type": "string", "format": "email", "maxLength": 50},
            {"type": "null"},
        ]
    }

    # expected output from updater
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
    # input to updater
    original = {
        "exclusiveMinimum": 5,
        "anyOf": [
            {"type": "string", "format": "email", "maxLength": 50},
            {"type": "null"},
        ],
        "description": "example",
    }

    # expected output from updater
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
