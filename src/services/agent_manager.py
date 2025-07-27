"""Persistent agent manager service."""

import logging
import uuid
from typing import Any, Optional, Tuple

from cachetools import TTLCache
from llama_stack_client.lib.agents.agent import Agent
from llama_stack_client import LlamaStackClient

from configuration import configuration
from services.persistence import PersistenceManager
from utils.suid import get_suid
from utils.types import GraniteToolParser

logger = logging.getLogger(__name__)


class PersistentAgentManager:
    """Manages agents with persistent storage and rehydration capabilities."""
    
    def __init__(self, persistence_manager: PersistenceManager):
        """Initialize persistent agent manager."""
        self.persistence_manager = persistence_manager
        self.conversation_service = persistence_manager.get_conversation_service()
        self.agent_state_service = persistence_manager.get_agent_state_service()
        
        # In-memory cache for active agents (with TTL)
        config = persistence_manager.config
        self.agent_cache = TTLCache(
            maxsize=config.agent_cache_max_size,
            ttl=config.agent_cache_ttl_seconds
        )
        
        logger.info("Persistent agent manager initialized")
    
    def get_or_create_agent(
        self,
        client: LlamaStackClient,
        model_id: str,
        system_prompt: str,
        available_input_shields: list[str],
        available_output_shields: list[str],
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Tuple[Agent, str]:
        """Get existing agent or create a new one with session persistence."""
        
        # Convert string IDs to UUIDs
        conversation_uuid = None
        user_uuid = None
        
        if conversation_id:
            try:
                conversation_uuid = uuid.UUID(conversation_id)
            except ValueError:
                logger.error("Invalid conversation ID format: %s", conversation_id)
                raise ValueError(f"Invalid conversation ID format: {conversation_id}")
        
        if user_id:
            try:
                user_uuid = uuid.UUID(user_id)
            except ValueError:
                logger.error("Invalid user ID format: %s", user_id)
                raise ValueError(f"Invalid user ID format: {user_id}")
        
        # Check in-memory cache first
        if conversation_id and conversation_id in self.agent_cache:
            logger.debug("Reusing existing agent from cache: %s", conversation_id)
            return self.agent_cache[conversation_id], conversation_id
        
        # Try to rehydrate from database
        if conversation_uuid and self.persistence_manager.config.enable_rehydration:
            agent = self._rehydrate_agent(client, conversation_uuid, model_id, system_prompt)
            if agent:
                logger.debug("Rehydrated agent from database: %s", conversation_id)
                self.agent_cache[conversation_id] = agent
                return agent, conversation_id
        
        # Create new agent
        logger.debug("Creating new agent")
        agent = Agent(
            client,
            model=model_id,
            instructions=system_prompt,
            input_shields=available_input_shields if available_input_shields else [],
            output_shields=available_output_shields if available_output_shields else [],
            tool_parser=GraniteToolParser.get_parser(model_id),
            enable_session_persistence=True,
        )
        
        # Create session
        new_conversation_id = agent.create_session(get_suid())
        logger.debug("Created new agent and conversation_id: %s", new_conversation_id)
        
        # Store in cache
        self.agent_cache[new_conversation_id] = agent
        
        # Persist to database
        if user_uuid:
            self._persist_conversation(
                conversation_id=new_conversation_id,
                user_id=user_uuid,
                agent_id=agent.agent_id,
                model_id=model_id,
                system_prompt=system_prompt,
                agent=agent,
            )
        
        return agent, new_conversation_id
    
    def _rehydrate_agent(
        self,
        client: LlamaStackClient,
        conversation_id: uuid.UUID,
        model_id: str,
        system_prompt: str,
    ) -> Optional[Agent]:
        """Rehydrate agent from persistent storage."""
        try:
            # Get conversation from database
            conversation = self.conversation_service.get_conversation(conversation_id)
            if not conversation:
                logger.debug("No conversation found for ID: %s", conversation_id)
                return None
            
            # Get agent state
            agent_state = self.agent_state_service.get_agent_state_by_conversation(conversation_id)
            if not agent_state:
                logger.debug("No agent state found for conversation: %s", conversation_id)
                return None
            
            # Create agent with stored configuration
            agent_config = agent_state.agent_config
            agent = Agent(
                client,
                model=agent_config.get("model_id", model_id),
                instructions=agent_config.get("system_prompt", system_prompt),
                input_shields=agent_config.get("input_shields", []),
                output_shields=agent_config.get("output_shields", []),
                tool_parser=GraniteToolParser.get_parser(agent_config.get("model_id", model_id)),
                enable_session_persistence=True,
            )
            
            # Restore session (this would need to be implemented in llama-stack)
            # For now, we'll create a new session but keep the conversation_id
            # TODO: Implement session restoration in llama-stack
            logger.info("Rehydrated agent for conversation: %s", conversation_id)
            return agent
            
        except Exception as e:
            logger.error("Failed to rehydrate agent for conversation %s: %s", conversation_id, e)
            return None
    
    def _persist_conversation(
        self,
        conversation_id: str,
        user_id: uuid.UUID,
        agent_id: str,
        model_id: str,
        system_prompt: str,
        agent: Agent,
    ) -> None:
        """Persist conversation and agent state to database."""
        try:
            conversation_uuid = uuid.UUID(conversation_id)
            agent_uuid = uuid.UUID(agent_id)
            
            # Create conversation record
            self.conversation_service.create_conversation(
                conversation_id=conversation_uuid,
                user_id=user_id,
                agent_id=agent_uuid,
                model_id=model_id,
                system_prompt=system_prompt,
                metadata={
                    "created_by": "persistent_agent_manager",
                    "agent_type": "Agent",
                },
            )
            
            # Save agent state
            agent_config = {
                "model_id": model_id,
                "system_prompt": system_prompt,
                "input_shields": agent.input_shields,
                "output_shields": agent.output_shields,
                "tool_parser": str(type(agent.tool_parser)),
            }
            
            self.agent_state_service.save_agent_state(
                agent_id=agent_uuid,
                conversation_id=conversation_uuid,
                agent_config=agent_config,
                current_state=None,  # TODO: Implement agent state serialization
            )
            
            logger.info("Persisted conversation and agent state: %s", conversation_id)
            
        except Exception as e:
            logger.error("Failed to persist conversation %s: %s", conversation_id, e)
            # Don't raise - persistence failure shouldn't break the flow
    
    def add_conversation_turn(
        self,
        conversation_id: str,
        turn_number: int,
        input_messages: list[dict[str, Any]],
        output_message: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add a turn to the conversation in persistent storage."""
        try:
            conversation_uuid = uuid.UUID(conversation_id)
            
            self.conversation_service.add_conversation_turn(
                conversation_id=conversation_uuid,
                turn_number=turn_number,
                input_messages=input_messages,
                output_message=output_message,
                metadata=metadata,
            )
            
            logger.debug("Added turn %d to conversation %s", turn_number, conversation_id)
            
        except Exception as e:
            logger.error("Failed to add turn to conversation %s: %s", conversation_id, e)
            # Don't raise - persistence failure shouldn't break the flow
    
    def get_conversation_id_to_agent_id_mapping(self) -> dict[str, str]:
        """Get the mapping of conversation IDs to agent IDs from persistent storage."""
        try:
            # This is a simplified implementation
            # In a real implementation, you might want to cache this mapping
            # or implement a more efficient query
            mapping = {}
            
            # For now, we'll return an empty mapping
            # The actual implementation would query the database
            # and build the mapping from conversation and agent state records
            
            return mapping
            
        except Exception as e:
            logger.error("Failed to get conversation to agent mapping: %s", e)
            return {}
    
    def cleanup_old_conversations(self) -> None:
        """Clean up old conversations based on retention policy."""
        try:
            retention_days = self.persistence_manager.config.conversation_retention_days
            # TODO: Implement cleanup logic
            logger.info("Cleanup of old conversations not yet implemented")
            
        except Exception as e:
            logger.error("Failed to cleanup old conversations: %s", e)
    
    def get_conversation_history(self, conversation_id: str) -> Optional[list[dict[str, Any]]]:
        """Get conversation history from persistent storage."""
        try:
            conversation_uuid = uuid.UUID(conversation_id)
            turns = self.conversation_service.get_conversation_turns(conversation_uuid)
            
            history = []
            for turn in turns:
                turn_data = {
                    "turn_number": turn.turn_number,
                    "input_messages": turn.input_messages,
                    "output_message": turn.output_message,
                    "started_at": turn.started_at.isoformat() if turn.started_at else None,
                    "completed_at": turn.completed_at.isoformat() if turn.completed_at else None,
                    "metadata": turn.metadata,
                }
                history.append(turn_data)
            
            return history
            
        except Exception as e:
            logger.error("Failed to get conversation history for %s: %s", conversation_id, e)
            return None
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete conversation from persistent storage."""
        try:
            conversation_uuid = uuid.UUID(conversation_id)
            
            # Remove from cache
            if conversation_id in self.agent_cache:
                del self.agent_cache[conversation_id]
            
            # Soft delete from database
            success = self.conversation_service.delete_conversation(conversation_uuid)
            
            if success:
                logger.info("Deleted conversation: %s", conversation_id)
            
            return success
            
        except Exception as e:
            logger.error("Failed to delete conversation %s: %s", conversation_id, e)
            return False 