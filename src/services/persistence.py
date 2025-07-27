"""Database service layer for conversation persistence."""

import logging
import uuid
from datetime import datetime, UTC
from typing import Any, Optional, List

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.pool import QueuePool

from models.config import DatabaseConfiguration, PersistenceConfiguration
from models.persistence import Base, Conversation, ConversationTurn, AgentState

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for database operations."""
    
    def __init__(self, db_config: DatabaseConfiguration):
        """Initialize database service with configuration."""
        self.db_config = db_config
        self.engine = None
        self.SessionLocal = None
        self._initialize_engine()
    
    def _initialize_engine(self) -> None:
        """Initialize SQLAlchemy engine with connection pooling."""
        # Build connection string
        password_part = f":{self.db_config.password}" if self.db_config.password else ""
        connection_string = (
            f"postgresql://{self.db_config.username}{password_part}"
            f"@{self.db_config.host}:{self.db_config.port}/{self.db_config.name}"
        )
        
        # Create engine with connection pooling
        self.engine = create_engine(
            connection_string,
            poolclass=QueuePool,
            pool_size=self.db_config.pool_size,
            max_overflow=self.db_config.max_overflow,
            pool_timeout=self.db_config.pool_timeout,
            pool_recycle=self.db_config.pool_recycle,
            pool_pre_ping=True,
            echo=False,  # Set to True for SQL debugging
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info("Database engine initialized with connection pooling")
    
    def create_tables(self) -> None:
        """Create all database tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logger.error("Failed to create database tables: %s", e)
            raise
    
    def get_session(self) -> Session:
        """Get a database session."""
        return self.SessionLocal()
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
                logger.info("Database connection test successful")
                return True
        except SQLAlchemyError as e:
            logger.error("Database connection test failed: %s", e)
            return False


class ConversationPersistenceService:
    """Service for conversation persistence operations."""
    
    def __init__(self, db_service: DatabaseService):
        """Initialize conversation persistence service."""
        self.db_service = db_service
    
    def create_conversation(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        agent_id: uuid.UUID,
        model_id: str,
        system_prompt: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Conversation:
        """Create a new conversation."""
        try:
            with self.db_service.get_session() as session:
                conversation = Conversation(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    model_id=model_id,
                    system_prompt=system_prompt,
                    metadata=metadata,
                )
                session.add(conversation)
                session.commit()
                session.refresh(conversation)
                logger.info("Created conversation %s", conversation_id)
                return conversation
        except IntegrityError as e:
            logger.error("Failed to create conversation %s: %s", conversation_id, e)
            raise
        except SQLAlchemyError as e:
            logger.error("Database error creating conversation %s: %s", conversation_id, e)
            raise
    
    def get_conversation(self, conversation_id: uuid.UUID) -> Optional[Conversation]:
        """Get conversation by ID."""
        try:
            with self.db_service.get_session() as session:
                conversation = session.query(Conversation).filter(
                    Conversation.conversation_id == conversation_id
                ).first()
                return conversation
        except SQLAlchemyError as e:
            logger.error("Database error getting conversation %s: %s", conversation_id, e)
            raise
    
    def get_conversations_by_user(self, user_id: uuid.UUID, limit: int = 100) -> List[Conversation]:
        """Get conversations for a user."""
        try:
            with self.db_service.get_session() as session:
                conversations = session.query(Conversation).filter(
                    Conversation.user_id == user_id,
                    Conversation.status == "active"
                ).order_by(Conversation.updated_at.desc()).limit(limit).all()
                return conversations
        except SQLAlchemyError as e:
            logger.error("Database error getting conversations for user %s: %s", user_id, e)
            raise
    
    def update_conversation(
        self,
        conversation_id: uuid.UUID,
        **kwargs: Any,
    ) -> Optional[Conversation]:
        """Update conversation."""
        try:
            with self.db_service.get_session() as session:
                conversation = session.query(Conversation).filter(
                    Conversation.conversation_id == conversation_id
                ).first()
                
                if not conversation:
                    return None
                
                for key, value in kwargs.items():
                    if hasattr(conversation, key):
                        setattr(conversation, key, value)
                
                conversation.updated_at = datetime.now(UTC)
                session.commit()
                session.refresh(conversation)
                logger.info("Updated conversation %s", conversation_id)
                return conversation
        except SQLAlchemyError as e:
            logger.error("Database error updating conversation %s: %s", conversation_id, e)
            raise
    
    def delete_conversation(self, conversation_id: uuid.UUID) -> bool:
        """Delete conversation (soft delete by setting status to deleted)."""
        try:
            with self.db_service.get_session() as session:
                conversation = session.query(Conversation).filter(
                    Conversation.conversation_id == conversation_id
                ).first()
                
                if not conversation:
                    return False
                
                conversation.status = "deleted"
                conversation.updated_at = datetime.now(UTC)
                session.commit()
                logger.info("Deleted conversation %s", conversation_id)
                return True
        except SQLAlchemyError as e:
            logger.error("Database error deleting conversation %s: %s", conversation_id, e)
            raise
    
    def add_conversation_turn(
        self,
        conversation_id: uuid.UUID,
        turn_number: int,
        input_messages: dict[str, Any],
        output_message: Optional[dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ConversationTurn:
        """Add a turn to a conversation."""
        try:
            with self.db_service.get_session() as session:
                turn = ConversationTurn(
                    conversation_id=conversation_id,
                    turn_number=turn_number,
                    input_messages=input_messages,
                    output_message=output_message,
                    started_at=started_at or datetime.now(UTC),
                    completed_at=completed_at,
                    metadata=metadata,
                )
                session.add(turn)
                session.commit()
                session.refresh(turn)
                logger.info("Added turn %d to conversation %s", turn_number, conversation_id)
                return turn
        except IntegrityError as e:
            logger.error("Failed to add turn %d to conversation %s: %s", turn_number, conversation_id, e)
            raise
        except SQLAlchemyError as e:
            logger.error("Database error adding turn to conversation %s: %s", conversation_id, e)
            raise
    
    def get_conversation_turns(self, conversation_id: uuid.UUID) -> List[ConversationTurn]:
        """Get all turns for a conversation."""
        try:
            with self.db_service.get_session() as session:
                turns = session.query(ConversationTurn).filter(
                    ConversationTurn.conversation_id == conversation_id
                ).order_by(ConversationTurn.turn_number).all()
                return turns
        except SQLAlchemyError as e:
            logger.error("Database error getting turns for conversation %s: %s", conversation_id, e)
            raise


class AgentStatePersistenceService:
    """Service for agent state persistence operations."""
    
    def __init__(self, db_service: DatabaseService):
        """Initialize agent state persistence service."""
        self.db_service = db_service
    
    def save_agent_state(
        self,
        agent_id: uuid.UUID,
        conversation_id: uuid.UUID,
        agent_config: dict[str, Any],
        current_state: Optional[dict[str, Any]] = None,
    ) -> AgentState:
        """Save agent state."""
        try:
            with self.db_service.get_session() as session:
                # Check if agent state already exists
                existing_state = session.query(AgentState).filter(
                    AgentState.agent_id == agent_id
                ).first()
                
                if existing_state:
                    # Update existing state
                    existing_state.agent_config = agent_config
                    existing_state.current_state = current_state
                    existing_state.updated_at = datetime.now(UTC)
                    session.commit()
                    session.refresh(existing_state)
                    logger.info("Updated agent state for agent %s", agent_id)
                    return existing_state
                else:
                    # Create new state
                    agent_state = AgentState(
                        agent_id=agent_id,
                        conversation_id=conversation_id,
                        agent_config=agent_config,
                        current_state=current_state,
                    )
                    session.add(agent_state)
                    session.commit()
                    session.refresh(agent_state)
                    logger.info("Created agent state for agent %s", agent_id)
                    return agent_state
        except SQLAlchemyError as e:
            logger.error("Database error saving agent state for agent %s: %s", agent_id, e)
            raise
    
    def get_agent_state(self, agent_id: uuid.UUID) -> Optional[AgentState]:
        """Get agent state by agent ID."""
        try:
            with self.db_service.get_session() as session:
                agent_state = session.query(AgentState).filter(
                    AgentState.agent_id == agent_id
                ).first()
                return agent_state
        except SQLAlchemyError as e:
            logger.error("Database error getting agent state for agent %s: %s", agent_id, e)
            raise
    
    def get_agent_state_by_conversation(self, conversation_id: uuid.UUID) -> Optional[AgentState]:
        """Get agent state by conversation ID."""
        try:
            with self.db_service.get_session() as session:
                agent_state = session.query(AgentState).filter(
                    AgentState.conversation_id == conversation_id
                ).first()
                return agent_state
        except SQLAlchemyError as e:
            logger.error("Database error getting agent state for conversation %s: %s", conversation_id, e)
            raise
    
    def delete_agent_state(self, agent_id: uuid.UUID) -> bool:
        """Delete agent state."""
        try:
            with self.db_service.get_session() as session:
                agent_state = session.query(AgentState).filter(
                    AgentState.agent_id == agent_id
                ).first()
                
                if not agent_state:
                    return False
                
                session.delete(agent_state)
                session.commit()
                logger.info("Deleted agent state for agent %s", agent_id)
                return True
        except SQLAlchemyError as e:
            logger.error("Database error deleting agent state for agent %s: %s", agent_id, e)
            raise


class PersistenceManager:
    """Main persistence manager that coordinates all persistence operations."""
    
    def __init__(self, persistence_config: PersistenceConfiguration):
        """Initialize persistence manager."""
        self.config = persistence_config
        
        if persistence_config.type == "postgresql" and persistence_config.database:
            self.db_service = DatabaseService(persistence_config.database)
            self.conversation_service = ConversationPersistenceService(self.db_service)
            self.agent_state_service = AgentStatePersistenceService(self.db_service)
        else:
            raise ValueError("PostgreSQL persistence is required but not configured")
    
    def initialize(self) -> None:
        """Initialize the persistence layer."""
        try:
            # Test database connection
            if not self.db_service.test_connection():
                raise RuntimeError("Database connection test failed")
            
            # Create tables if they don't exist
            self.db_service.create_tables()
            
            logger.info("Persistence layer initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize persistence layer: %s", e)
            raise
    
    def get_conversation_service(self) -> ConversationPersistenceService:
        """Get conversation persistence service."""
        return self.conversation_service
    
    def get_agent_state_service(self) -> AgentStatePersistenceService:
        """Get agent state persistence service."""
        return self.agent_state_service 