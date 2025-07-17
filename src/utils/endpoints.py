"""Utility functions for endpoint handlers."""

from fastapi import HTTPException, status

import constants
from models.requests import QueryRequest
from configuration import AppConfig


def check_configuration_loaded(configuration: AppConfig) -> None:
    """Check that configuration is loaded and raise exception when it is not."""
    if configuration is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"response": "Configuration is not loaded"},
        )


def get_system_prompt(query_request: QueryRequest, configuration: AppConfig) -> str:
    """Get the system prompt: the provided one, configured one, or default one."""
    system_prompt_disabled = (
        configuration.customization is not None
        and configuration.customization.disable_query_system_prompt
    )
    if system_prompt_disabled and query_request.system_prompt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "response": (
                    "This instance does not support customizing the system prompt in the "
                    "query request (disable_query_system_prompt is set). Please remove the "
                    "system_prompt field from your request."
                )
            },
        )

    if query_request.system_prompt:
        # Query taking precedence over configuration is the only behavior that
        # makes sense here - if the configuration wants precedence, it can
        # disable query system prompt altogether with disable_system_prompt.
        return query_request.system_prompt

    if (
        configuration.customization is not None
        and configuration.customization.system_prompt is not None
    ):
        return configuration.customization.system_prompt

    # default system prompt has the lowest precedence
    return constants.DEFAULT_SYSTEM_PROMPT
