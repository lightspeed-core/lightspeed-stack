"""Prepare conversation ids and message history for the next agent run."""

from __future__ import annotations

from typing import Optional

from pydantic_ai_harness.step_persistence import StepStore

from conversations.agent_history.history import (
    load_conversation_history,
    load_run_history,
)
from conversations.agent_history.models import ResolvedAgentRun, RunResolutionParams
from conversations.display_history.context_resolution import (
    plan_conversation_continuation,
    plan_previous_response_continuation,
)


async def resolve_from_conversation(
    step_store: Optional[StepStore],
    conversation_id: str,
    user_id: str,
    others_allowed: bool,
) -> ResolvedAgentRun:
    """Continue an existing conversation with a new response.

    Args:
        step_store: Agent step store, or None when persistence is off.
        conversation_id: Conversation to continue.
        user_id: User requesting access.
        others_allowed: Whether other users' conversations are readable.

    Returns:
        New response id, the same conversation id, and prior messages.

    """
    plan = plan_conversation_continuation(conversation_id, user_id, others_allowed)
    history = await load_conversation_history(step_store, plan.conversation_id)
    return ResolvedAgentRun.continue_conversation(
        conversation_id=plan.conversation_id,
        message_history=history,
    )


async def resolve_from_previous_response(
    step_store: Optional[StepStore],
    previous_response_id: str,
    user_id: str,
    others_allowed: bool,
) -> ResolvedAgentRun:
    """Continue from a prior response, or fork if it is not the latest.

    Args:
        step_store: Agent step store, or None when persistence is off.
        previous_response_id: Response to continue from.
        user_id: User requesting access.
        others_allowed: Whether other users' conversations are readable.

    Returns:
        New response id, conversation id (existing or forked), and prior messages.

    """
    plan = plan_previous_response_continuation(
        previous_response_id,
        user_id,
        others_allowed,
    )
    history = await load_run_history(step_store, plan.source_response_id)
    if plan.fork:
        return ResolvedAgentRun.new_conversation(message_history=history)
    return ResolvedAgentRun.continue_conversation(
        conversation_id=plan.conversation_id,
        message_history=history,
    )


async def resolve_run_context(
    step_store: Optional[StepStore],
    params: RunResolutionParams,
) -> ResolvedAgentRun:
    """Resolve conversation ids and history from continuation inputs.

    The request has at most one continuation context. When none is set, starts
    a new conversation if storing is enabled; otherwise returns a stateless run.

    Args:
        step_store: Agent step store, or None when persistence is off.
        params: User, access flags, and at most one continuation id.

    Returns:
        New response id, optional conversation id, and prior messages.

    """
    if params.conversation_id:
        return await resolve_from_conversation(
            step_store,
            params.conversation_id,
            params.user_id,
            params.others_allowed,
        )
    if params.previous_response_id:
        return await resolve_from_previous_response(
            step_store,
            params.previous_response_id,
            params.user_id,
            params.others_allowed,
        )
    if params.store:
        return ResolvedAgentRun.new_conversation()
    return ResolvedAgentRun.stateless()
