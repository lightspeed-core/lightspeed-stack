"""Database models for conversation persistence."""

import uuid
from datetime import datetime, UTC
from typing import Any, Optional

from sqlalchemy import (
    Column, String, DateTime, Integer, Text, JSON, Boolean, 
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel

Base = declarative_base()


class Conversation(Base):
    """Database model for conversations."""
    
    __tablename__ = "conversations"
    
    conversation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    model_id = Column(String(255), nullable=False)
    system_prompt = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    status = Column(String(50), default="active", index=True)
    metadata = Column(JSONB)
    
    # Relationships
    turns = relationship("ConversationTurn", back_populates="conversation", cascade="all, delete-orphan")
    agent_state = relationship("AgentState", back_populates="conversation", uselist=False, cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_conversations_user_created", "user_id", "created_at"),
        Index("idx_conversations_agent_updated", "agent_id", "updated_at"),
    )


class ConversationTurn(Base):
    """Database model for conversation turns."""
    
    __tablename__ = "conversation_turns"
    
    turn_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.conversation_id"), nullable=False, index=True)
    turn_number = Column(Integer, nullable=False)
    input_messages = Column(JSONB, nullable=False)
    output_message = Column(JSONB)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    metadata = Column(JSONB)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="turns")
    
    __table_args__ = (
        Index("idx_turns_conversation_number", "conversation_id", "turn_number"),
        UniqueConstraint("conversation_id", "turn_number", name="uq_conversation_turn_number"),
    )


class AgentState(Base):
    """Database model for agent state persistence."""
    
    __tablename__ = "agent_states"
    
    agent_id = Column(UUID(as_uuid=True), primary_key=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.conversation_id"), nullable=False, unique=True)
    agent_config = Column(JSONB, nullable=False)
    current_state = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    # Relationships
    conversation = relationship("Conversation", back_populates="agent_state")


# Pydantic models for API responses
class ConversationResponse(BaseModel):
    """Pydantic model for conversation response."""
    
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    agent_id: uuid.UUID
    model_id: str
    system_prompt: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status: str
    metadata: Optional[dict[str, Any]] = None
    turns: list["ConversationTurnResponse"] = []
    
    class Config:
        from_attributes = True


class ConversationTurnResponse(BaseModel):
    """Pydantic model for conversation turn response."""
    
    turn_id: uuid.UUID
    conversation_id: uuid.UUID
    turn_number: int
    input_messages: dict[str, Any]
    output_message: Optional[dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class AgentStateResponse(BaseModel):
    """Pydantic model for agent state response."""
    
    agent_id: uuid.UUID
    conversation_id: uuid.UUID
    agent_config: dict[str, Any]
    current_state: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Update forward references
ConversationResponse.model_rebuild() 