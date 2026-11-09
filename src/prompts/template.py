"""Mustache-style template validation and rendering.

Placeholders use ``{{name}}`` syntax with optional inner whitespace.
Only plain text substitution is supported; Jinja features (filters,
control flow, expressions) are not allowed.

Valid placeholder names must match ``[a-zA-Z_][a-zA-Z0-9_-]*``.
Variables are text-only: each value is a plain string that replaces
its corresponding placeholder verbatim.
"""

import re

from models.database.prompts import PromptVersion
from prompts.exceptions import PromptRenderError, PromptValidationError

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")

_VALID_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")


def _validate_variables(variables: list[str]) -> set[str]:
    """Validate variable names and reject duplicates.

    Parameters:
        variables: Declared variable names to validate.

    Returns:
        The validated variable names as a set.

    Raises:
        PromptValidationError: If the list contains duplicate names or
            any name has an invalid format.

    """
    unique = set(variables)
    if len(variables) != len(unique):
        raise PromptValidationError("The variables contain duplicate names")

    for variable in unique:
        if not variable or not _VALID_NAME_RE.match(variable):
            raise PromptValidationError(
                f"The variable list contains invalid name format: {variable}"
            )

    return unique


def _extract_placeholders(template: str) -> set[str]:
    """Extract and validate all ``{{name}}`` placeholders from template text.

    Parameters:
        template: The template string to scan.

    Returns:
        Set of valid placeholder names found in the template.

    Raises:
        PromptValidationError: If any placeholder has an invalid name format.

    """
    raw_names = _PLACEHOLDER_RE.findall(template)
    valid = set()
    for raw_name in raw_names:
        if not raw_name or not _VALID_NAME_RE.match(raw_name):
            raise PromptValidationError(
                f"The template contains invalid name format for the placeholder: {raw_name}"
            )
        valid.add(raw_name)
    return valid


def validate_template(template: str, variables: list[str]) -> None:
    """Validate a template and its declared variables on create or update.

    Every placeholder in the template must appear in the declared variables
    list. Unused declared variables are allowed.

    Parameters:
        template: The template text to validate.
        variables: Declared variable names for the template.

    Raises:
        PromptValidationError: If the template is empty, contains invalid
            placeholder names, has duplicate variables, or has undeclared
            placeholders.

    """
    if not template.strip():
        raise PromptValidationError("The template must not be empty")

    declared_variables = _validate_variables(variables)
    placeholders = _extract_placeholders(template)
    undeclared = placeholders - declared_variables

    if undeclared:
        raise PromptValidationError(f"Undeclared placeholders: {undeclared}")


def render_template(prompt_version: PromptVersion, variables: dict[str, str]) -> str:
    """Render a prompt version by substituting placeholder values.

    Requires a value for every declared variable and rejects any extra keys.
    The stored PromptVersion is not modified.

    Parameters:
        prompt_version: The validated prompt version to render.
        variables: Mapping of variable names to their text substitution values.

    Returns:
        The rendered plain-text string.

    Raises:
        PromptRenderError: If required variables are missing or unexpected
            variables are provided.

    """
    declared = set(prompt_version.variables)
    provided = set(variables.keys())

    missing = declared - provided
    if missing:
        raise PromptRenderError(f"Missing variables: {missing}")

    return _PLACEHOLDER_RE.sub(
        lambda m: variables[m.group(1).strip()], prompt_version.template
    )
