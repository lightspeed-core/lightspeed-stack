"""Utility functions for system prompts."""

from fastapi import HTTPException

import constants
from configuration import AppConfig
from models.requests import QueryRequest
from models.responses import UnprocessableEntityResponse


def get_system_prompt(query_request: QueryRequest, config: AppConfig) -> str:
    """
    Resolve which system prompt to use for a query.

    Precedence (highest to lowest):
    1. Per-request `system_prompt` from `query_request.system_prompt`.
    2. The `custom_profile`'s "default" prompt (when present), accessed via
       `config.customization.custom_profile.get_prompts().get("default")`.
    3. `config.customization.system_prompt` from application configuration.
    4. The module default `constants.DEFAULT_SYSTEM_PROMPT` (lowest precedence).

    If configuration disables per-request system prompts
    (config.customization.disable_query_system_prompt) and the incoming
    `query_request` contains a `system_prompt`, an HTTP 422 Unprocessable
    Entity is raised instructing the client to remove the field.

    Parameters:
        query_request (QueryRequest): The incoming query payload; may contain a
        per-request `system_prompt`.
        config (AppConfig): Application configuration which may include
        customization flags, a custom profile, and a default `system_prompt`.

    Returns:
        str: The resolved system prompt to apply to the request.
    """
    system_prompt_disabled = (
        config.customization is not None
        and config.customization.disable_query_system_prompt
    )
    if system_prompt_disabled and query_request.system_prompt:
        response = UnprocessableEntityResponse(
            response="System prompt customization is disabled",
            cause=(
                "This instance does not support customizing the system prompt in the "
                "query request (disable_query_system_prompt is set). Please remove the "
                "system_prompt field from your request."
            ),
        )
        raise HTTPException(**response.model_dump())

    if query_request.system_prompt:
        # Query taking precedence over configuration is the only behavior that
        # makes sense here - if the configuration wants precedence, it can
        # disable query system prompt altogether with disable_query_system_prompt.
        return query_request.system_prompt

    # profile takes precedence for setting prompt
    if (
        config.customization is not None
        and config.customization.custom_profile is not None
    ):
        prompt = config.customization.custom_profile.get_prompts().get("default")
        if prompt:
            return prompt

    if (
        config.customization is not None
        and config.customization.system_prompt is not None
    ):
        return config.customization.system_prompt

    # default system prompt has the lowest precedence
    return constants.DEFAULT_SYSTEM_PROMPT


def get_topic_summary_system_prompt(config: AppConfig) -> str:
    """
    Get the topic summary system prompt.

    Parameters:
        config (AppConfig): Application configuration from which to read
                            customization/profile settings.

    Returns:
        str: The topic summary system prompt from the active custom profile if
             set, otherwise the default prompt.
    """
    # profile takes precedence for setting prompt
    if (
        config.customization is not None
        and config.customization.custom_profile is not None
    ):
        prompt = config.customization.custom_profile.get_prompts().get("topic_summary")
        if prompt:
            return prompt

    return constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT
