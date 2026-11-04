"""Unit tests for prompts template validation and rendering."""

import pytest

from models.database.prompts import PromptVersion
from prompts.exceptions import PromptRenderError, PromptValidationError
from prompts.template import (
    _extract_placeholders,
    _validate_variables,
    render_template,
    validate_template,
)


class TestValidateVariables:
    """Tests for _validate_variables."""

    def test_unique_variables(self) -> None:
        """Return a set when all variable names are unique."""
        result = _validate_variables(["name", "age", "city"])
        assert result == {"name", "age", "city"}

    def test_empty_list(self) -> None:
        """Return an empty set for an empty list."""
        result = _validate_variables([])
        assert result == set()

    def test_single_variable(self) -> None:
        """Return a set with one element."""
        result = _validate_variables(["name"])
        assert result == {"name"}

    def test_duplicate_variables(self) -> None:
        """Raise PromptValidationError when duplicates exist."""
        with pytest.raises(PromptValidationError, match="duplicate names"):
            _validate_variables(["name", "age", "name"])

    def test_invalid_name_starting_with_digit(self) -> None:
        """Raise PromptValidationError for name starting with digit."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _validate_variables(["123bad"])

    def test_invalid_empty_name(self) -> None:
        """Raise PromptValidationError for empty string variable name."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _validate_variables([""])

    def test_invalid_name_with_spaces(self) -> None:
        """Raise PromptValidationError for name containing spaces."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _validate_variables(["foo bar"])

    def test_invalid_name_with_dot(self) -> None:
        """Raise PromptValidationError for name with dot."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _validate_variables(["user.name"])

    def test_invalid_among_valid(self) -> None:
        """Raise PromptValidationError when one invalid name is mixed with valid ones."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _validate_variables(["name", "123bad", "age"])


class TestExtractPlaceholders:
    """Tests for _extract_placeholders."""

    def test_single_placeholder(self) -> None:
        """Extract a single placeholder."""
        result = _extract_placeholders("Hello {{name}}!")
        assert result == {"name"}

    def test_multiple_placeholders(self) -> None:
        """Extract multiple distinct placeholders."""
        result = _extract_placeholders("{{greeting}}, {{name}}! You are {{age}}.")
        assert result == {"greeting", "name", "age"}

    def test_repeated_placeholder(self) -> None:
        """Deduplicate repeated placeholders."""
        result = _extract_placeholders("{{name}} and {{name}} again")
        assert result == {"name"}

    def test_whitespace_inside_braces(self) -> None:
        """Strip whitespace inside braces."""
        result = _extract_placeholders("{{ name }} and {{  age  }}")
        assert result == {"name", "age"}

    def test_no_placeholders(self) -> None:
        """Return empty set for plain text."""
        result = _extract_placeholders("Hello world!")
        assert result == set()

    def test_underscore_and_hyphen_names(self) -> None:
        """Accept underscores and hyphens in names."""
        result = _extract_placeholders("{{first_name}} {{last-name}}")
        assert result == {"first_name", "last-name"}

    def test_leading_underscore(self) -> None:
        """Accept names starting with underscore."""
        result = _extract_placeholders("{{_private}}")
        assert result == {"_private"}

    def test_incomplete_opening_braces(self) -> None:
        """Treat incomplete opening braces as plain text."""
        result = _extract_placeholders("Hello {name}}")
        assert result == set()

    def test_incomplete_closing_braces(self) -> None:
        """Treat incomplete closing braces as plain text."""
        result = _extract_placeholders("Hello {{name}")
        assert result == set()

    def test_single_brace(self) -> None:
        """Treat single braces as plain text."""
        result = _extract_placeholders("Hello {name}")
        assert result == set()

    def test_empty_placeholder(self) -> None:
        """Raise PromptValidationError for empty placeholder."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _extract_placeholders("{{}}")

    def test_whitespace_only_placeholder(self) -> None:
        """Raise PromptValidationError for whitespace-only placeholder."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _extract_placeholders("{{   }}")

    def test_name_starting_with_digit(self) -> None:
        """Raise PromptValidationError for name starting with digit."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _extract_placeholders("{{123bad}}")

    def test_name_with_spaces(self) -> None:
        """Raise PromptValidationError for name containing spaces."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _extract_placeholders("{{foo bar}}")

    def test_name_with_pipe(self) -> None:
        """Raise PromptValidationError for Jinja-style filter syntax."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _extract_placeholders("{{name | upper}}")

    def test_name_with_dot(self) -> None:
        """Raise PromptValidationError for dotted path."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            _extract_placeholders("{{user.name}}")


class TestValidateTemplate:
    """Tests for validate_template."""

    def test_empty_template(self) -> None:
        """Raise PromptValidationError for empty template text."""
        with pytest.raises(PromptValidationError, match="must not be empty"):
            validate_template("", [])

    def test_whitespace_only_template(self) -> None:
        """Raise PromptValidationError for whitespace-only template text."""
        with pytest.raises(PromptValidationError, match="must not be empty"):
            validate_template("   ", [])

    def test_tabs_and_newlines_only_template(self) -> None:
        """Raise PromptValidationError for template with only tabs and newlines."""
        with pytest.raises(PromptValidationError, match="must not be empty"):
            validate_template("\t\n\r", [])

    def test_all_placeholders_declared(self) -> None:
        """Pass when every placeholder has a matching variable."""
        validate_template("Hello {{name}}, age {{age}}", ["name", "age"])

    def test_extra_declared_variables(self) -> None:
        """Pass when declared variables include unused names."""
        validate_template("Hello {{name}}", ["name", "age", "city"])

    def test_no_placeholders_no_variables(self) -> None:
        """Pass for plain text with no variables."""
        validate_template("Hello world!", [])

    def test_no_placeholders_with_variables(self) -> None:
        """Pass for plain text with declared but unused variables."""
        validate_template("Hello world!", ["name"])

    def test_undeclared_placeholder(self) -> None:
        """Raise PromptValidationError for undeclared placeholder."""
        with pytest.raises(PromptValidationError, match="Undeclared placeholders"):
            validate_template("Hello {{name}}", [])

    def test_partially_undeclared(self) -> None:
        """Raise PromptValidationError when some placeholders are undeclared."""
        with pytest.raises(PromptValidationError, match="Undeclared placeholders"):
            validate_template("{{greeting}} {{name}}", ["greeting"])

    def test_duplicate_variables_rejected(self) -> None:
        """Raise PromptValidationError for duplicate variable names."""
        with pytest.raises(PromptValidationError, match="duplicate names"):
            validate_template("{{name}}", ["name", "name"])

    def test_invalid_placeholder_rejected(self) -> None:
        """Raise PromptValidationError for invalid placeholder name."""
        with pytest.raises(PromptValidationError, match="invalid name format"):
            validate_template("{{123}}", ["123"])


def _make_prompt_version(template: str, variables: list[str]) -> PromptVersion:
    """Create a PromptVersion instance for testing."""
    return PromptVersion(
        prompt_id="pmpt_test",
        version=1,
        template=template,
        variables=variables,
    )


class TestRenderTemplate:
    """Tests for render_template."""

    def test_simple_render(self) -> None:
        """Render a template with one placeholder."""
        version = _make_prompt_version("Hello {{name}}!", ["name"])
        result = render_template(version, {"name": "Alice"})
        assert result == "Hello Alice!"

    def test_multiple_placeholders(self) -> None:
        """Render a template with multiple placeholders."""
        version = _make_prompt_version("{{greeting}}, {{name}}!", ["greeting", "name"])
        result = render_template(version, {"greeting": "Hi", "name": "Bob"})
        assert result == "Hi, Bob!"

    def test_repeated_placeholder(self) -> None:
        """Render a template where the same placeholder appears twice."""
        version = _make_prompt_version("{{name}} and {{name}}", ["name"])
        result = render_template(version, {"name": "Alice"})
        assert result == "Alice and Alice"

    def test_whitespace_in_placeholder(self) -> None:
        """Render a template with whitespace inside braces."""
        version = _make_prompt_version("Hello {{ name }}!", ["name"])
        result = render_template(version, {"name": "Alice"})
        assert result == "Hello Alice!"

    def test_no_placeholders(self) -> None:
        """Render plain text with no variables."""
        version = _make_prompt_version("Hello world!", [])
        result = render_template(version, {})
        assert result == "Hello world!"

    def test_missing_variable_value(self) -> None:
        """Raise PromptRenderError when a required variable is not provided."""
        version = _make_prompt_version("{{name}} {{age}}", ["name", "age"])
        with pytest.raises(PromptRenderError, match="Missing variables"):
            render_template(version, {"name": "Alice"})

    def test_does_not_modify_stored_version(self) -> None:
        """Rendering does not mutate the PromptVersion object."""
        version = _make_prompt_version("Hello {{name}}!", ["name"])
        original_template = version.template
        # Create a shallow copy we we're not referencing the same object
        original_variables = list(version.variables)
        render_template(version, {"name": "Alice"})
        assert version.template == original_template
        assert version.variables == original_variables

    def test_incomplete_braces_treated_as_text(self) -> None:
        """Incomplete braces in a stored template are left as plain text."""
        version = _make_prompt_version("Hello {{name} world", [])
        result = render_template(version, {})
        assert result == "Hello {{name} world"

    def test_special_characters_in_value(self) -> None:
        """Values containing braces or special characters are inserted literally."""
        version = _make_prompt_version("Output: {{value}}", ["value"])
        result = render_template(version, {"value": "{{not_a_placeholder}}"})
        assert result == "Output: {{not_a_placeholder}}"
