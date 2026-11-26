"""Output settings for an agent, from a Responses request (LCORE-4717).

``text.format`` is the output contract of a ``/v1/responses`` request, not a
model setting. On the pydantic-ai path the agent enforces it through its
``output_type``: ``str`` for plain text, a ``StructuredDict`` built from the
request's schema for ``json_object`` and ``json_schema``, wrapped in the
structured output mode the selected model's profile can honor. Design:
``docs/design/inference-backend-migration/pai-responses-lcore-rewrite.md``
section 4.8.

When the request carries client function tools, ``DeferredToolRequests``
joins the output type so a function call can end the run and be projected
as a ``function_call`` item; server-side tools (MCP, file search) run inside
the loop and do not.

An invalid or incomplete client schema is a request error raised when the
settings are built, before the run starts. ``text.verbosity`` is not part
of the output type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, Optional

from fastapi import HTTPException
from ogx_api.openai_responses import OpenAIResponseInputToolFunction
from pydantic_ai import (
    DeferredToolRequests,
    NativeOutput,
    PromptedOutput,
    StructuredDict,
    ToolOutput,
)
from pydantic_ai.output import OutputSpec
from pydantic_ai.profiles import ModelProfile

from log import get_logger
from models.api.responses.error import UnprocessableEntityResponse
from models.common.responses.responses_api_params import ResponsesApiParams

logger = get_logger(__name__)

FormatType = Literal["text", "json_object", "json_schema"]

FORMAT_TEXT: Final[str] = "text"
FORMAT_JSON_OBJECT: Final[str] = "json_object"

JSON_OBJECT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": True,
}
"""The free-form object contract of ``json_object``."""


def _reject(cause: str) -> HTTPException:
    """Build the 422 for a ``text.format`` the run cannot start with."""
    error_response = UnprocessableEntityResponse(
        response="Invalid text.format", cause=cause
    )
    return HTTPException(**error_response.model_dump())


@dataclass
class OutputSettings:
    """The output contract a request asked for.

    Attributes:
        format_type: ``text``, ``json_object`` or ``json_schema``.
        schema: The client's JSON schema, for ``json_schema``.
        name: Name of the structured type, for ``json_schema``.
        description: Description of the structured type, for ``json_schema``.
        strict: Whether the provider must enforce the schema strictly.
        client_function_tools: Whether the request declares function tools
            the client executes itself, which can end the run.

    """

    format_type: FormatType = "text"
    schema: Optional[dict[str, Any]] = None
    name: Optional[str] = None
    description: Optional[str] = None
    strict: Optional[bool] = None
    client_function_tools: bool = False

    @classmethod
    def from_responses_request(cls, params: ResponsesApiParams) -> OutputSettings:
        """Read ``text.format`` of a Responses request.

        Parameters:
            params: The sanitized request parameters.

        Returns:
            The output contract; plain text when no format is given.

        Raises:
            HTTPException: 422 for a ``json_schema`` format without a schema or
                a name, or whose schema does not describe an object. The
                format type itself is validated by the request model.

        """
        fmt = (params.text.format if params.text is not None else None) or {}
        format_type: FormatType = fmt.get("type") or "text"
        if format_type == "json_schema":
            schema = fmt.get("schema")
            name = fmt.get("name")
            if not isinstance(schema, dict):
                raise _reject("json_schema requires a schema object")
            if not name:
                raise _reject("json_schema requires a name")
            if schema.get("type") != "object" or not isinstance(
                schema.get("properties", {}), dict
            ):
                raise _reject("json_schema requires a schema of type object")
        return cls(
            format_type=format_type,
            schema=fmt.get("schema"),
            name=fmt.get("name"),
            description=fmt.get("description"),
            strict=fmt.get("strict"),
            client_function_tools=any(
                isinstance(tool, OpenAIResponseInputToolFunction)
                for tool in params.tools or []
            ),
        )

    def _structured_type(self) -> type[dict[str, Any]]:
        """Build the structured output type for ``json_object`` or ``json_schema``."""
        if self.format_type == FORMAT_JSON_OBJECT:
            return StructuredDict(JSON_OBJECT_SCHEMA, name=FORMAT_JSON_OBJECT)
        assert self.schema is not None  # validated by from_responses_request
        return StructuredDict(self.schema, name=self.name, description=self.description)

    def output_type_for(self, profile: ModelProfile) -> OutputSpec[Any]:
        """Return the agent ``output_type`` for this contract and model.

        The profile decides which structured output mode enforces the
        contract: native when the model supports JSON schema output,
        tool-based when it supports tools, prompted otherwise.

        Parameters:
            profile: The selected model's profile, from ``Model.profile``.

        Returns:
            ``str`` for plain text; otherwise the structured type wrapped in
            the output mode chosen for the profile. With client function
            tools on the request, a list of that and ``DeferredToolRequests``.

        """
        contract = self._contract(profile)
        if self.client_function_tools:
            return [contract, DeferredToolRequests]
        return contract

    def _contract(self, profile: ModelProfile) -> OutputSpec[Any]:
        """Return the output contract without deferred tool requests."""
        if self.format_type == FORMAT_TEXT:
            return str
        structured = self._structured_type()
        if profile.get("supports_json_schema_output"):
            return NativeOutput(structured, strict=self.strict)
        if profile.get("supports_tools"):
            return ToolOutput(structured, strict=self.strict)
        return PromptedOutput(structured)
