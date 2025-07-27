"""Tests for persistence implementation."""

import pytest
import uuid
from datetime import datetime, UTC
from unittest.mock import Mock, patch

from models.config import DatabaseConfiguration, PersistenceConfiguration
from services.persistence import (
    DatabaseService,
    ConversationPersistenceService,
    AgentStatePersistenceService,
    PersistenceManager,
)
from models.persistence import Conversation, ConversationTurn, AgentState


class TestDatabaseService:
    """Test database service functionality."""

    def test_database_service_initialization(self):
        """Test database service initialization."""
        db_config = DatabaseConfiguration(
            host="localhost",
            port=5432,
            name="test_db",
            username="test_user",
            password="test_password",
        )
        
        service = DatabaseService(db_config)
        assert service.db_config == db_config
        assert service.engine is not None
        assert service.SessionLocal is not None

    def test_connection_string_building(self):
        """Test connection string building."""
        db_config = DatabaseConfiguration(
            host="localhost",
            port=5432,
            name="test_db",
            username="test_user",
            password="test_password",
        )
        
        service = DatabaseService(db_config)
        # The connection string should be built correctly
        assert service.db_config.host == "localhost"
        assert service.db_config.port == 5432


class TestConversationPersistenceService:
    """Test conversation persistence service functionality."""

    @pytest.fixture
    def mock_db_service(self):
        """Create a mock database service."""
        mock_service = Mock()
        mock_service.get_session.return_value.__enter__.return_value = Mock()
        mock_service.get_session.return_value.__exit__.return_value = None
        return mock_service

    @pytest.fixture
    def conversation_service(self, mock_db_service):
        """Create conversation service with mock database."""
        return ConversationPersistenceService(mock_db_service)

    def test_create_conversation(self, conversation_service, mock_db_service):
        """Test conversation creation."""
        conversation_id = uuid.uuid4()
        user_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        
        # Mock the session
        mock_session = Mock()
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session
        
        # Mock the conversation object
        mock_conversation = Mock()
        mock_conversation.conversation_id = conversation_id
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        result = conversation_service.create_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            agent_id=agent_id,
            model_id="test-model",
            system_prompt="Test prompt",
        )
        
        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestAgentStatePersistenceService:
    """Test agent state persistence service functionality."""

    @pytest.fixture
    def mock_db_service(self):
        """Create a mock database service."""
        mock_service = Mock()
        mock_service.get_session.return_value.__enter__.return_value = Mock()
        mock_service.get_session.return_value.__exit__.return_value = None
        return mock_service

    @pytest.fixture
    def agent_state_service(self, mock_db_service):
        """Create agent state service with mock database."""
        return AgentStatePersistenceService(mock_db_service)

    def test_save_agent_state(self, agent_state_service, mock_db_service):
        """Test agent state saving."""
        agent_id = uuid.uuid4()
        conversation_id = uuid.uuid4()
        
        # Mock the session
        mock_session = Mock()
        mock_db_service.get_session.return_value.__enter__.return_value = mock_session
        
        # Mock query result (no existing state)
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        # Mock the agent state object
        mock_agent_state = Mock()
        mock_agent_state.agent_id = agent_id
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        result = agent_state_service.save_agent_state(
            agent_id=agent_id,
            conversation_id=conversation_id,
            agent_config={"model_id": "test-model"},
            current_state={"status": "active"},
        )
        
        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestPersistenceManager:
    """Test persistence manager functionality."""

    def test_persistence_manager_initialization(self):
        """Test persistence manager initialization."""
        config = PersistenceConfiguration(
            type="postgresql",
            database=DatabaseConfiguration(
                host="localhost",
                port=5432,
                name="test_db",
                username="test_user",
                password="test_password",
            )
        )
        
        manager = PersistenceManager(config)
        assert manager.config == config
        assert manager.db_service is not None
        assert manager.conversation_service is not None
        assert manager.agent_state_service is not None

    def test_persistence_manager_invalid_type(self):
        """Test persistence manager with invalid type."""
        config = PersistenceConfiguration(
            type="invalid_type",
            database=DatabaseConfiguration(
                host="localhost",
                port=5432,
                name="test_db",
                username="test_user",
                password="test_password",
            )
        )
        
        with pytest.raises(ValueError, match="Unsupported persistence type"):
            PersistenceManager(config)

    def test_persistence_manager_missing_database(self):
        """Test persistence manager with missing database config."""
        config = PersistenceConfiguration(
            type="postgresql",
            database=None,
        )
        
        with pytest.raises(ValueError, match="Database configuration is required"):
            PersistenceManager(config)


class TestDatabaseModels:
    """Test database model definitions."""

    def test_conversation_model(self):
        """Test conversation model structure."""
        conversation = Conversation(
            conversation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            model_id="test-model",
            system_prompt="Test prompt",
            status="active",
        )
        
        assert conversation.conversation_id is not None
        assert conversation.user_id is not None
        assert conversation.agent_id is not None
        assert conversation.model_id == "test-model"
        assert conversation.system_prompt == "Test prompt"
        assert conversation.status == "active"

    def test_conversation_turn_model(self):
        """Test conversation turn model structure."""
        turn = ConversationTurn(
            conversation_id=uuid.uuid4(),
            turn_number=1,
            input_messages=[{"role": "user", "content": "Hello"}],
            output_message={"role": "assistant", "content": "Hi there!"},
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        
        assert turn.conversation_id is not None
        assert turn.turn_number == 1
        assert len(turn.input_messages) == 1
        assert turn.output_message is not None
        assert turn.started_at is not None
        assert turn.completed_at is not None

    def test_agent_state_model(self):
        """Test agent state model structure."""
        agent_state = AgentState(
            agent_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            agent_config={"model_id": "test-model", "system_prompt": "Test"},
            current_state={"status": "active"},
        )
        
        assert agent_state.agent_id is not None
        assert agent_state.conversation_id is not None
        assert agent_state.agent_config is not None
        assert agent_state.current_state is not None


class TestConfigurationValidation:
    """Test configuration validation."""

    def test_valid_database_configuration(self):
        """Test valid database configuration."""
        config = DatabaseConfiguration(
            host="localhost",
            port=5432,
            name="test_db",
            username="test_user",
            password="test_password",
            pool_size=20,
            max_overflow=30,
        )
        
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.pool_size == 20
        assert config.max_overflow == 30

    def test_invalid_port(self):
        """Test invalid port configuration."""
        with pytest.raises(ValueError, match="Port value should be between 1 and 65535"):
            DatabaseConfiguration(
                host="localhost",
                port=70000,  # Invalid port
                name="test_db",
                username="test_user",
            )

    def test_invalid_pool_size(self):
        """Test invalid pool size configuration."""
        with pytest.raises(ValueError, match="Pool size must be at least 1"):
            DatabaseConfiguration(
                host="localhost",
                port=5432,
                name="test_db",
                username="test_user",
                pool_size=0,  # Invalid pool size
            )

    def test_valid_persistence_configuration(self):
        """Test valid persistence configuration."""
        config = PersistenceConfiguration(
            type="postgresql",
            database=DatabaseConfiguration(
                host="localhost",
                port=5432,
                name="test_db",
                username="test_user",
            ),
            agent_cache_max_size=1000,
            agent_cache_ttl_seconds=3600,
            enable_rehydration=True,
            conversation_retention_days=90,
        )
        
        assert config.type == "postgresql"
        assert config.agent_cache_max_size == 1000
        assert config.agent_cache_ttl_seconds == 3600
        assert config.enable_rehydration is True
        assert config.conversation_retention_days == 90

    def test_invalid_persistence_type(self):
        """Test invalid persistence type."""
        with pytest.raises(ValueError, match="Unsupported persistence type"):
            PersistenceConfiguration(
                type="invalid_type",
                database=DatabaseConfiguration(
                    host="localhost",
                    port=5432,
                    name="test_db",
                    username="test_user",
                ),
            ) 