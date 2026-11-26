"""Unit tests for output settings built from a Responses request (LCORE-4717)."""

from typing import Any, Optional, cast

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter
from pydantic_ai import NativeOutput, PromptedOutput, ToolOutput
from pydantic_ai.profiles import ModelProfile

from agent.types.settings.output import OutputSettings
from models.common.responses.responses_api_params import ResponsesApiParams

NATIVE = ModelProfile(supports_json_schema_output=True, supports_tools=True)
TOOL_ONLY = ModelProfile(supports_json_schema_output=False, supports_tools=True)
PROMPTED_ONLY = ModelProfile(supports_json_schema_output=False, supports_tools=False)
PERSON = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}


def _params(text: Optional[dict[str, Any]] = None, **fields: Any) -> ResponsesApiParams:
    """Build params for a plain request with the given text configuration."""
    return ResponsesApiParams.model_validate(
        {
            "model": "openai/gpt-x",
            "input": "hi",
            "conversation": "123e4567-e89b-12d3-a456-426614174000",
            "stream": False,
            "store": True,
            "text": text,
            **fields,
        }
    )


def _output_type(text: Optional[dict[str, Any]], profile: ModelProfile) -> Any:
    """Build the settings from a request and return the output type for *profile*."""
    return OutputSettings.from_responses_request(_params(text)).output_type_for(profile)


def _schema_of(output: Any) -> dict[str, Any]:
    """Return the JSON schema of a StructuredDict, through its output wrapper."""
    wrapped = output.outputs if hasattr(output, "outputs") else output.output
    return TypeAdapter(wrapped).json_schema()


class TestFormatMapping:
    """Each text.format type maps to its output contract."""

    @pytest.mark.parametrize(
        "text", [None, {}, {"format": {"type": "text"}}, {"verbosity": "low"}]
    )
    def test_text_or_absent_is_str(self, text: Optional[dict[str, Any]]) -> None:
        """No format, an empty text object or type text all mean a plain string answer."""
        settings = OutputSettings.from_responses_request(_params(text))
        assert settings == OutputSettings()
        assert settings.output_type_for(NATIVE) is str

    def test_json_object_is_a_free_form_object(self) -> None:
        """The structured type accepts any object."""
        output = _output_type({"format": {"type": "json_object"}}, NATIVE)
        assert isinstance(output, NativeOutput)
        schema = _schema_of(output)
        assert schema["type"] == "object"
        assert schema.get("additionalProperties") is True
        assert schema["title"] == "json_object"

    def test_json_schema_carries_schema_name_and_description(self) -> None:
        """Schema, name and description are carried into the structured type."""
        settings = OutputSettings.from_responses_request(
            _params(
                {
                    "format": {
                        "type": "json_schema",
                        "name": "person",
                        "description": "A person",
                        "schema": PERSON,
                    }
                }
            )
        )
        assert settings == OutputSettings(
            format_type="json_schema",
            schema=PERSON,
            name="person",
            description="A person",
        )
        schema = _schema_of(settings.output_type_for(NATIVE))
        assert schema["properties"] == PERSON["properties"]
        assert schema["required"] == ["name"]
        assert schema["title"] == "person"
        assert schema["description"] == "A person"

    def test_strict_is_passed_to_the_output_mode(self) -> None:
        """strict reaches the native output wrapper."""
        output = _output_type(
            {
                "format": {
                    "type": "json_schema",
                    "name": "p",
                    "schema": PERSON,
                    "strict": True,
                }
            },
            NATIVE,
        )
        assert isinstance(output, NativeOutput)
        assert output.strict is True


class TestOutputModeFollowsTheProfile:
    """The profile decides which structured output mode enforces the contract."""

    def test_native_when_the_model_supports_json_schema_output(self) -> None:
        """Native structured output is preferred."""
        assert isinstance(
            _output_type({"format": {"type": "json_object"}}, NATIVE), NativeOutput
        )

    def test_tool_when_only_tools_are_supported(self) -> None:
        """Tool-based output comes next."""
        assert isinstance(
            _output_type({"format": {"type": "json_object"}}, TOOL_ONLY), ToolOutput
        )

    def test_prompted_as_the_fallback(self) -> None:
        """Prompted output is the last resort."""
        assert isinstance(
            _output_type({"format": {"type": "json_object"}}, PROMPTED_ONLY),
            PromptedOutput,
        )

    def test_unknown_profile_uses_the_prompted_fallback(self) -> None:
        """A profile that says nothing cannot promise native or tool output."""
        assert isinstance(
            _output_type({"format": {"type": "json_object"}}, ModelProfile()),
            PromptedOutput,
        )


@pytest.mark.parametrize(
    ("fmt", "cause"),
    [
        ({"type": "json_schema", "name": "p"}, "schema"),
        ({"type": "json_schema", "schema": PERSON}, "name"),
        ({"type": "json_schema", "name": "p", "schema": {"type": "string"}}, "object"),
        ({"type": "json_schema", "name": "p", "schema": {"properties": []}}, "object"),
    ],
)
def test_incomplete_or_invalid_schema_fails_before_the_run(
    fmt: dict[str, Any], cause: str
) -> None:
    """An invalid or incomplete json_schema is a 422, raised when the settings are built."""
    with pytest.raises(HTTPException) as exc_info:
        OutputSettings.from_responses_request(_params({"format": fmt}))
    assert exc_info.value.status_code == 422
    detail = cast(dict[str, str], exc_info.value.detail)
    assert cause in detail["cause"]
