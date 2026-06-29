"""Helpers for running Pydantic AI agents against Llama Stack (Responses API compatibility)."""

from __future__ import annotations

from typing import Any, Final, Optional, cast

from llama_stack.core.library_client import AsyncLlamaStackAsLibraryClient
from llama_stack_client import AsyncLlamaStackClient
from pydantic_ai.agent import Agent
from pydantic_ai.capabilities import AgentCapability
from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai_skills import SkillsCapability

from models.common.responses import ResponseInput
from models.common.responses.responses_api_params import ResponsesApiParams
from models.config import SkillsConfiguration
from pydantic_ai_lightspeed.llamastack import (
    CompactionTurnContext,
    LlamaStackProvider,
    LlamaStackResponsesModel,
)

_LLS_RESPONSES_EXTRA_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "conversation",
        "max_infer_iters",
        "tool_choice",
        "include",
        "text",
        "reasoning",
        "prompt",
        "metadata",
        "max_tool_calls",
        "safety_identifier",
    }
)


def llama_stack_provider_from_client(
    client: AsyncLlamaStackClient | AsyncLlamaStackAsLibraryClient,
) -> LlamaStackProvider:
    """Construct a Pydantic AI Llama Stack provider backed by the same client as ``/query``."""
    if isinstance(client, AsyncLlamaStackAsLibraryClient):
        return LlamaStackProvider(library_client=client)
    api_key = client.api_key or "not-needed"
    base = str(client.base_url).rstrip("/")
    base_url = base if base.endswith("/v1") else f"{base}/v1"
    return LlamaStackProvider(
        base_url=base_url,
        api_key=api_key,
        http_client=client._client,  # pylint: disable=protected-access
    )


def _model_settings_from_responses_params(
    responses_params: ResponsesApiParams,
) -> OpenAIResponsesModelSettings:
    """Map ``ResponsesApiParams`` into Pydantic AI OpenAI Responses model settings."""
    payload = responses_params.model_dump(exclude_none=True)
    extra_body = {k: v for k, v in payload.items() if k in _LLS_RESPONSES_EXTRA_FIELDS}
    settings_dict: dict[str, Any] = {}
    if extra_body:
        settings_dict["extra_body"] = extra_body
    if responses_params.max_output_tokens is not None:
        settings_dict["max_tokens"] = responses_params.max_output_tokens
    if responses_params.temperature is not None:
        settings_dict["temperature"] = responses_params.temperature
    if responses_params.parallel_tool_calls is not None:
        settings_dict["parallel_tool_calls"] = responses_params.parallel_tool_calls
    if responses_params.extra_headers:
        settings_dict["extra_headers"] = dict(responses_params.extra_headers)
    settings_dict["openai_store"] = responses_params.store
    if responses_params.tools is not None:
        settings_dict["openai_native_tools"] = responses_params.tools
    if responses_params.previous_response_id is not None:
        settings_dict["openai_previous_response_id"] = (
            responses_params.previous_response_id
        )
    return cast(OpenAIResponsesModelSettings, settings_dict)


def _skills_capability(
    skills_config: Optional[SkillsConfiguration],
) -> Optional[SkillsCapability]:
    """Return a skills capability when skill paths are configured.

    Args:
        skills_config: Agent skills configuration from LCS, or None when skills are disabled.

    Returns:
        SkillsCapability when skill paths are configured, or None when skills are disabled.
    """
    if skills_config is None or not skills_config.paths:
        return None
    return SkillsCapability(
        directories=[str(path) for path in skills_config.paths],
        validate=False,
    )


def _agent_capabilities(
    skills: Optional[SkillsConfiguration],
) -> Optional[list[AgentCapability[Any]]]:
    """Assemble pydantic-ai capabilities for an LCS agent.

    Args:
        skills: Agent skills configuration from LCS, or None when skills are disabled.

    Returns:
        Configured capabilities, or None when no capabilities are enabled.
    """
    capabilities: list[AgentCapability[SkillsCapability]] = []
    if skills_capability := _skills_capability(skills):
        capabilities.append(skills_capability)
    return capabilities or None


def build_agent(
    client: AsyncLlamaStackClient | AsyncLlamaStackAsLibraryClient,
    responses_params: ResponsesApiParams,
    skills: Optional[SkillsConfiguration],
    original_input: Optional[ResponseInput] = None,
) -> Agent[None, str]:
    """Build a Pydantic AI agent that mirrors ``responses_params`` on the Llama Stack backend.

    Uses ``LlamaStackProvider`` with the same ``AsyncLlamaStackClient`` (or library client)
    as the query endpoint, and ``OpenAIResponsesModel`` so requests follow the Responses API.
    Llama-Stack-specific fields (conversation, tools, MCP headers, etc.) are passed via
    ``model_settings['extra_body']`` so they merge into the OpenAI client request body.

    Parameters:
        client: Initialized Llama Stack client from ``AsyncLlamaStackClientHolder().get_client()``.
        responses_params: Parameters produced by ``prepare_responses_params`` for this turn.
        skills: Agent skills configuration from LCS, or None when skills are disabled.
        original_input: When set, enables compacted-turn persistence on the model.

    Returns:
        ``Agent`` configured for ``await agent.run(...)`` (or streaming) against the same
        stack configuration as ``client.responses.create(**responses_params.model_dump())``.
    """
    provider = llama_stack_provider_from_client(client)
    settings = _model_settings_from_responses_params(responses_params)

    compaction = (
        CompactionTurnContext(
            client=client,
            conversation_id=responses_params.conversation,
            latest_round_input=original_input,
        )
        if original_input is not None
        else None
    )

    model = LlamaStackResponsesModel(
        responses_params.model,
        provider=provider,
        settings=settings,
        compaction=compaction,
    )
    return Agent(
        model,
        instructions=responses_params.instructions,
        capabilities=_agent_capabilities(skills),
        defer_model_check=True,
    )
