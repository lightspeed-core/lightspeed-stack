# Conversation Persistence Implementation

This document describes the implementation of persistent conversation storage for Lightspeed Core Stack (LCS), replacing the in-memory conversation mapping with PostgreSQL-based persistence.

## Overview

The persistence implementation provides:
- **Persistent conversation storage** in PostgreSQL
- **Agent state persistence** for rehydration
- **Multi-replica support** through shared database
- **Automatic conversation history** tracking
- **Configurable retention policies**

## Architecture

### Database Schema

The persistence layer uses three main tables:

1. **`conversations`** - Stores conversation metadata
   - `conversation_id` (UUID, Primary Key)
   - `user_id` (UUID, indexed)
   - `agent_id` (UUID, indexed)
   - `model_id` (String)
   - `system_prompt` (Text)
   - `created_at` (DateTime)
   - `updated_at` (DateTime)
   - `status` (String, indexed)
   - `metadata` (JSONB)

2. **`conversation_turns`** - Stores individual conversation turns
   - `turn_id` (UUID, Primary Key)
   - `conversation_id` (UUID, Foreign Key)
   - `turn_number` (Integer)
   - `input_messages` (JSONB)
   - `output_message` (JSONB)
   - `started_at` (DateTime)
   - `completed_at` (DateTime)
   - `metadata` (JSONB)

3. **`agent_states`** - Stores agent configuration and state
   - `agent_id` (UUID, Primary Key)
   - `conversation_id` (UUID, Foreign Key, Unique)
   - `agent_config` (JSONB)
   - `current_state` (JSONB)
   - `created_at` (DateTime)
   - `updated_at` (DateTime)

### Service Layer

The implementation includes several service classes:

- **`DatabaseService`** - Handles database connections and session management
- **`ConversationPersistenceService`** - Manages conversation CRUD operations
- **`AgentStatePersistenceService`** - Manages agent state persistence
- **`PersistentAgentManager`** - Coordinates agent lifecycle with persistence
- **`PersistenceManager`** - Main coordinator for all persistence operations

## Configuration

### Basic Configuration

Add the following to your `lightspeed-stack.yaml`:

```yaml
persistence:
  type: "postgresql"
  database:
    host: "localhost"
    port: 5432
    name: "lightspeed_stack"
    username: "postgres"
    password: "your-password-here"
    ssl_mode: "prefer"
    pool_size: 20
    max_overflow: 30
    pool_timeout: 30
    pool_recycle: 3600
  agent_cache_max_size: 1000
  agent_cache_ttl_seconds: 3600
  enable_rehydration: true
  conversation_retention_days: 90
  enable_archival: false
```

### Configuration Options

- **`type`**: Database type (currently only "postgresql" supported)
- **`database`**: PostgreSQL connection configuration
- **`agent_cache_max_size`**: Maximum number of agents in memory cache
- **`agent_cache_ttl_seconds`**: Time-to-live for cached agents
- **`enable_rehydration`**: Whether to enable agent rehydration from database
- **`conversation_retention_days`**: Days to keep conversations before cleanup
- **`enable_archival`**: Whether to enable conversation archival (future feature)

## Database Setup

### 1. Install Dependencies

```bash
pip install sqlalchemy psycopg2-binary alembic
```

### 2. Create Database

```sql
CREATE DATABASE lightspeed_stack;
CREATE USER lightspeed_user WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE lightspeed_stack TO lightspeed_user;
```

### 3. Run Migrations

```bash
# Initialize Alembic (first time only)
alembic init migrations

# Create initial migration
alembic revision --autogenerate -m "Initial migration"

# Apply migrations
alembic upgrade head
```

## Usage

### Automatic Initialization

The persistence layer is automatically initialized during application startup if configured:

```python
# In src/lightspeed_stack.py
def initialize_persistence() -> None:
    """Initialize persistence layer if configured."""
    if configuration.persistence_configuration:
        try:
            from app.endpoints.query import initialize_persistent_agent_manager
            initialize_persistent_agent_manager()
            logger.info("Persistence layer initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize persistence layer: %s", e)
```

### Manual Usage

```python
from services.persistence import PersistenceManager
from models.config import PersistenceConfiguration

# Create configuration
config = PersistenceConfiguration(
    type="postgresql",
    database=DatabaseConfiguration(
        host="localhost",
        port=5432,
        name="lightspeed_stack",
        username="postgres",
        password="password"
    )
)

# Initialize persistence manager
persistence_manager = PersistenceManager(config)
persistence_manager.initialize()

# Use services
conversation_service = persistence_manager.get_conversation_service()
agent_state_service = persistence_manager.get_agent_state_service()
```

## API Changes

### Query Endpoint

The `/query` endpoint now:
- Stores conversation turns in persistent storage
- Supports agent rehydration from database
- Maintains backward compatibility with in-memory cache

### Conversations Endpoint

The `/conversations/{conversation_id}` endpoint now:
- Retrieves conversations from persistent storage first
- Falls back to llama-stack session retrieval
- Supports conversation deletion from persistent storage

## Multi-Replica Support

The persistence implementation supports multiple LCS replicas by:

1. **Shared Database**: All replicas connect to the same PostgreSQL database
2. **Connection Pooling**: Each replica maintains its own connection pool
3. **Session Independence**: Agent sessions are independent across replicas
4. **Consistent State**: Database ensures consistent conversation state

## Monitoring and Maintenance

### Database Monitoring

Monitor the following metrics:
- Connection pool utilization
- Query performance
- Database size and growth
- Index usage

### Cleanup Operations

The system includes automatic cleanup capabilities:

```python
# Clean up old conversations
persistent_manager.cleanup_old_conversations()
```

### Backup Strategy

Implement regular PostgreSQL backups:
- Full database backups
- Point-in-time recovery
- Transaction log backups

## Migration from In-Memory

### Gradual Migration

The implementation supports gradual migration:

1. **Dual Mode**: Both persistent and in-memory storage are supported
2. **Fallback**: If persistence fails, the system falls back to in-memory
3. **Configuration**: Enable persistence via configuration

### Data Migration

To migrate existing conversations:

```python
# Export existing conversations
# Import to persistent storage
# Update configuration to enable persistence
```

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Check database connectivity
   - Verify credentials
   - Check firewall settings

2. **Performance Issues**
   - Monitor connection pool usage
   - Check database indexes
   - Review query performance

3. **Data Consistency**
   - Check for duplicate conversations
   - Verify agent state consistency
   - Monitor transaction logs

### Logging

Enable debug logging for persistence operations:

```python
import logging
logging.getLogger("services.persistence").setLevel(logging.DEBUG)
```

## Future Enhancements

1. **MongoDB Support**: Add MongoDB as an alternative database
2. **Firestore Support**: Add Google Firestore support
3. **Archival**: Implement conversation archival to cheaper storage
4. **Compression**: Add conversation data compression
5. **Analytics**: Add conversation analytics and reporting
6. **Encryption**: Add field-level encryption for sensitive data

## Testing

### Unit Tests

```bash
pytest tests/test_persistence.py
```

### Integration Tests

```bash
# Start PostgreSQL container
docker run -d --name postgres-test -e POSTGRES_PASSWORD=test -p 5432:5432 postgres:15

# Run integration tests
pytest tests/test_integration_persistence.py
```

### Performance Tests

```bash
# Run performance benchmarks
pytest tests/test_performance_persistence.py
```

## Security Considerations

1. **Database Security**
   - Use SSL connections
   - Implement proper access controls
   - Regular security updates

2. **Data Protection**
   - Encrypt sensitive data
   - Implement data retention policies
   - Audit access logs

3. **Network Security**
   - Use VPN for database connections
   - Implement network segmentation
   - Monitor network traffic 