"""Pydantic-ai capability for delegating tasks to external A2A agents."""

from __future__ import annotations

from dataclasses import dataclass, field

from a2a.client import A2AClientError
from a2a.client.client import Client
from a2a.client.helpers import create_text_message_object
from a2a.types import (
    Message,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TextPart,
)
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.toolsets import FunctionToolset

from a2a_client.manager import A2AClientManager
from log import get_logger

logger = get_logger(__name__)


def _extract_text_from_artifact(event: TaskArtifactUpdateEvent) -> str:
    """Extract text content from an A2A artifact event.

    Parameters:
        event: A2A artifact update event.

    Returns:
        Concatenated text from all text parts in the artifact.
    """
    parts = []
    for part in event.artifact.parts:
        if isinstance(part.root, TextPart):
            parts.append(part.root.text)
    return "".join(parts)


@dataclass
class A2ADelegationCapability(AbstractCapability[object]):
    """Capability enabling delegation of tasks to external A2A agents.

    Provides two tools to the pydantic-ai agent:
    - ``list_agents``: list available agents and their descriptions
    - ``delegate_to_agent``: send a task to a named agent and return its response
    """

    _manager: A2AClientManager = field(repr=False)
    _toolset: FunctionToolset[object] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Register delegation tools on the internal toolset."""
        self._toolset = FunctionToolset[object]()
        self._register_tools()

    def _register_tools(self) -> None:
        """Register the list_agents and delegate_to_agent tools."""
        manager = self._manager

        @self._toolset.tool_plain
        async def list_agents() -> dict[str, str]:
            """List all external agents available for task delegation.

            <summary>List external agents available for delegation.</summary>

            Returns:
                Dictionary mapping agent names to their descriptions.
            """
            return {
                name: card.description or ""
                for name, card in manager.list_agents().items()
            }

        @self._toolset.tool_plain
        async def delegate_to_agent(agent_name: str, task: str) -> str:
            """Delegate a task to an external A2A agent and return its response.

            <summary>Delegate a task to an external agent.</summary>

            Use this tool when a user's request matches the expertise of one of
            the available external agents. Call ``list_agents`` first to see
            which agents are available.

            Args:
                agent_name: Name of the agent to delegate to (from list_agents).
                task: The task description or question to send to the agent.

            Returns:
                The agent's text response.
            """
            client = manager.get_client(agent_name)
            if client is None:
                available = ", ".join(manager.list_agents().keys())
                raise ModelRetry(
                    f"Agent '{agent_name}' not found. Available: {available}"
                )

            try:
                logger.debug("Delegating task to agent '%s'", agent_name)
                message = create_text_message_object(role=Role.user, content=task)
                return await _send_and_collect(client, message)
            except A2AClientError as e:
                logger.warning(
                    "A2A delegation to '%s' failed: %s",
                    agent_name,
                    e,
                )
                return (
                    f"Delegation to agent '{agent_name}' failed: {e}. "
                    "Please try answering directly or inform the user."
                )

    def get_toolset(self) -> FunctionToolset[object]:
        """Return the delegation toolset.

        Returns:
            FunctionToolset with list_agents and delegate_to_agent tools.
        """
        return self._toolset

    def get_instructions(self) -> str | None:
        """Return instructions about available external agents.

        Returns:
            System prompt text describing the delegation capability.
        """
        agents = self._manager.list_agents()
        if not agents:
            return None
        lines = ["You can delegate tasks to these external agents when appropriate:"]
        for name, card in agents.items():
            skills_text = ""
            if card.skills:
                skill_names = [s.name for s in card.skills if s.name]
                if skill_names:
                    skills_text = f" (skills: {', '.join(skill_names)})"
            lines.append(
                f"- {name}: {card.description or 'No description'}{skills_text}"
            )
        lines.append(
            "Use list_agents to see current availability, "
            "then delegate_to_agent to send a task."
        )
        return "\n".join(lines)


async def _send_and_collect(client: Client, message: Message) -> str:
    """Send a message to an A2A client and collect the text response.

    Parameters:
        client: A2A Client instance.
        message: Message to send.

    Returns:
        Concatenated text from the agent's response.
    """
    text_parts: list[str] = []
    async for event in client.send_message(message):
        if isinstance(event, Message):
            for part in event.parts:
                if isinstance(part.root, TextPart):
                    text_parts.append(part.root.text)
        elif isinstance(event, tuple):
            _task, update_event = event
            if isinstance(update_event, TaskArtifactUpdateEvent):
                text_parts.append(_extract_text_from_artifact(update_event))
            elif (
                update_event is not None
                and hasattr(update_event, "status")
                and update_event.status.state
                in (TaskState.failed, TaskState.rejected, TaskState.canceled)
            ):
                fail_msg = f"Agent task {update_event.status.state.value}"
                if update_event.status.message:
                    for part in update_event.status.message.parts:
                        if isinstance(part.root, TextPart):
                            fail_msg = part.root.text
                            break
                return f"Delegation failed: {fail_msg}"
    return "".join(text_parts) or "Agent returned no response."
