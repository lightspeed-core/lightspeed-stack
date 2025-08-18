"""Utility functions for endpoint handlers."""

from contextlib import suppress
import logging
from fastapi import HTTPException, status
from llama_stack_client._client import AsyncLlamaStackClient
from llama_stack_client.lib.agents.agent import AsyncAgent

import constants
from models.requests import QueryRequest
from models.database.conversations import UserConversation
from app.database import get_session
from configuration import AppConfig
from utils.suid import get_suid
from utils.types import GraniteToolParser


logger = logging.getLogger("utils.endpoints")


def validate_conversation_ownership(
    user_id: str, conversation_id: str
) -> UserConversation | None:
    """Validate that the conversation belongs to the user."""
    with get_session() as session:
        conversation = (
            session.query(UserConversation)
            .filter_by(id=conversation_id, user_id=user_id)
            .first()
        )
        return conversation


def check_configuration_loaded(config: AppConfig) -> None:
    """Check that configuration is loaded and raise exception when it is not."""
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"response": "Configuration is not loaded"},
        )


def get_system_prompt(query_request: QueryRequest, config: AppConfig) -> str:
    """Get the system prompt: the provided one, configured one, or default one."""
    system_prompt_disabled = (
        config.customization is not None
        and config.customization.disable_query_system_prompt
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
        config.customization is not None
        and config.customization.system_prompt is not None
    ):
        return config.customization.system_prompt

    # default system prompt has the lowest precedence
    return constants.DEFAULT_SYSTEM_PROMPT


# # pylint: disable=R0913,R0917
async def get_agent(
    client: AsyncLlamaStackClient,
    model_id: str,
    system_prompt: str,
    available_input_shields: list[str],
    available_output_shields: list[str],
    conversation_id: str | None,
    no_tools: bool = False,
) -> tuple[AsyncAgent, str, str]:
    """Get existing agent or create a new one with session persistence."""
    existing_agent_id = None
    if conversation_id:
        with suppress(ValueError):
            agent_response = await client.agents.retrieve(agent_id=conversation_id)
            existing_agent_id = agent_response.agent_id

    logger.debug("Creating new agent")
    agent = AsyncAgent(
        client,  # type: ignore[arg-type]
        model=model_id,
        instructions=system_prompt,
        input_shields=available_input_shields if available_input_shields else [],
        output_shields=available_output_shields if available_output_shields else [],
        tool_parser=None if no_tools else GraniteToolParser.get_parser(model_id),
        enable_session_persistence=True,
    )
    await agent.initialize()

    if existing_agent_id and conversation_id:
        orphan_agent_id = agent.agent_id
        agent._agent_id = conversation_id  # type: ignore[assignment]  # pylint: disable=protected-access
        await client.agents.delete(agent_id=orphan_agent_id)
        sessions_response = await client.agents.session.list(agent_id=conversation_id)
        logger.info("session response: %s", sessions_response)
        try:
            session_id = str(sessions_response.data[0]["session_id"])
        except IndexError as e:
            logger.error("No sessions found for conversation %s", conversation_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "response": "Conversation not found",
                    "cause": f"Conversation {conversation_id} could not be retrieved.",
                },
            ) from e
    else:
        conversation_id = agent.agent_id
        session_id = await agent.create_session(get_suid())

    return agent, conversation_id, session_id
