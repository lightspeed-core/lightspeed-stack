"""Utility functions for system prompts."""

from fastapi import HTTPException

import constants
from configuration import configuration
from models.responses import UnprocessableEntityResponse


def get_system_prompt(system_prompt: str | None) -> str:
    """
    Resolve which system prompt to use for a query.

    get_system_prompt resolves the system prompt with the following precedence
    (highest to lowest):
    1. Per-request system prompt from the `system_prompt` argument (when allowed).
    2. The custom profile's "default" prompt (when present), from application
       configuration.
    3. The application configuration system prompt.
    4. The module default `constants.DEFAULT_SYSTEM_PROMPT` (lowest precedence).

    Parameters:
        system_prompt: Optional per-request system prompt from the query; may be
            None.

    Returns:
        The resolved system prompt string to apply to the request.

    Raises:
        HTTPException: 422 Unprocessable Entity when per-request system prompts
            are disabled (disable_query_system_prompt) and a non-None
            `system_prompt` is provided; the response instructs the client to
            remove the system_prompt field from the request.
    """
    system_prompt_disabled = (
        configuration.customization is not None
        and configuration.customization.disable_query_system_prompt
    )
    if system_prompt_disabled and system_prompt:
        response = UnprocessableEntityResponse(
            response="System prompt customization is disabled",
            cause=(
                "This instance does not support customizing the system prompt in the "
                "query request (disable_query_system_prompt is set). Please remove the "
                "system_prompt field from your request."
            ),
        )
        raise HTTPException(**response.model_dump())

    if system_prompt:
        # Query taking precedence over configuration is the only behavior that
        # makes sense here - if the configuration wants precedence, it can
        # disable query system prompt altogether with disable_query_system_prompt.
        return system_prompt

    # profile takes precedence for setting prompt
    if (
        configuration.customization is not None
        and configuration.customization.custom_profile is not None
    ):
        prompt = configuration.customization.custom_profile.get_prompts().get("default")
        if prompt:
            return prompt

    if (
        configuration.customization is not None
        and configuration.customization.system_prompt is not None
    ):
        return configuration.customization.system_prompt

    # default system prompt has the lowest precedence
    return constants.DEFAULT_SYSTEM_PROMPT


def get_topic_summary_system_prompt() -> str:
    """
    Get the topic summary system prompt.

    Returns:
        str: The topic summary system prompt from the active custom profile if
             set, otherwise the default prompt.
    """
    # profile takes precedence for setting prompt
    if (
        configuration.customization is not None
        and configuration.customization.custom_profile is not None
    ):
        prompt = configuration.customization.custom_profile.get_prompts().get(
            "topic_summary"
        )
        if prompt:
            return prompt

    return constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT
