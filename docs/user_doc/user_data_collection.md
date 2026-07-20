# Lightspeed Stack user data collection

## Overview
This document outlines the process of capturing user interactions and system responses in the Lightspeed Core Stack service. Understanding this process will help optimize the system for better responses and outcomes.

## Components

### Lightspeed Core Stack
- Every user interaction results in the storage of its transcript as a JSON file on the local disk.
- When a user provides feedback (whether the LLM answer was satisfactory or not), the data is posted to the `/feedback` endpoint. This action also results in the creation of a JSON file.
- Both transcripts and feedback are stored in configurable local directories with unique filenames.

### Data Export Integration
- The Lightspeed Core Stack integrates with the [lightspeed-to-dataverse-exporter](https://github.com/lightspeed-core/lightspeed-to-dataverse-exporter) service to automatically export various types of user interaction data to Red Hat's Dataverse for analysis.
- The exporter service acts as a sidecar that periodically scans the configured data directories for new JSON files (transcripts and feedback).
- It packages these data into archives and uploads them to the appropriate ingress endpoints.

### Red Hat Dataverse Integration
- The exporter service uploads data to Red Hat's Dataverse for analysis and system improvement.
- Data flows through the same pipeline as other Red Hat services for consistent processing and analysis.

## Configuration

User data collection is configured in the `user_data_collection` section of the configuration file:

```yaml
user_data_collection:
  feedback_enabled: true
  feedback_storage: "/tmp/data/feedback"
  transcripts_enabled: true
  transcripts_storage: "/tmp/data/transcripts"
  data_collector:
    enabled: false
    ingress_server_url: null
    ingress_server_auth_token: null
    ingress_content_service_name: null
    collection_interval: 7200  # 2 hours in seconds
    cleanup_after_send: true
    connection_timeout_seconds: 30
```

### Configuration Options

#### Basic Data Collection
- `feedback_enabled`: Enable/disable collection of user feedback data
- `feedback_storage`: Directory path where feedback JSON files are stored
- `transcripts_enabled`: Enable/disable collection of conversation transcripts
- `transcripts_storage`: Directory path where transcript JSON files are stored

#### Data Collector Service (Advanced)
- `enabled`: Enable/disable the data collector service that uploads data to ingress
- `ingress_server_url`: URL of the ingress server for data upload
- `ingress_server_auth_token`: Authentication token for the ingress server
- `ingress_content_service_name`: Service name identifier for the ingress server
- `collection_interval`: Interval in seconds between data collection cycles (default: 7200 = 2 hours)
- `cleanup_after_send`: Whether to delete local files after successful upload (default: true)
- `connection_timeout_seconds`: Timeout for connection to ingress server (default: 30)

## Data Storage

### Feedback Data
Feedback data is stored as JSON files in the configured `feedback_storage` directory. Each file contains:

```json
{
  "user_id": "user-uuid",
  "timestamp": "2024-01-01T12:00:00Z",
  "conversation_id": "conversation-uuid",
  "user_question": "What is Kubernetes?",
  "llm_response": "Kubernetes is an open-source container orchestration system...",
  "sentiment": 1,
  "user_feedback": "This response was very helpful",
  "categories": ["helpful"]
}
```

### Transcript Data
Transcript data is stored as JSON files in the configured `transcripts_storage` directory, organized by user and conversation:

```
/transcripts_storage/
  /{user_id}/
    /{conversation_id}/
      /{unique_id}.json
```

Each transcript file contains:

```json
{
  "metadata": {
    "provider": "openai",
    "model": "gpt-4",
    "query_provider": "openai",
    "query_model": "gpt-4",
    "user_id": "user-uuid",
    "conversation_id": "conversation-uuid",
    "timestamp": "2024-01-01T12:00:00Z"
  },
  "redacted_query": "What is Kubernetes?",
  "query_is_valid": true,
  "llm_response": "Kubernetes is an open-source container orchestration system...",
  "rag_chunks": [],
  "truncated": false,
  "attachments": []
}
```

## Data Flow

1. **User Interaction**: User submits a query to the `/query` or `/streaming_query` endpoint
2. **Transcript Storage**: If transcripts are enabled, the interaction is stored as a JSON file
3. **Feedback Collection**: User can submit feedback via the `/feedback` endpoint
4. **Feedback Storage**: If feedback is enabled, the feedback is stored as a JSON file
5. **Data Export**: The exporter service (if enabled) periodically scans for new files and uploads them to the ingress server

## How to Test Locally

### Basic Data Collection Testing

1. **Enable data collection** in your `lightspeed-stack.yaml`:
   ```yaml
   user_data_collection:
     feedback_enabled: true
     feedback_storage: "/tmp/data/feedback"
     transcripts_enabled: true
     transcripts_storage: "/tmp/data/transcripts"
   ```

2. **Start the Lightspeed Core Stack**:
   ```bash
   python -m src.app.main
   ```

3. **Submit a query** to generate transcript data:
   ```bash
   curl -X POST "http://localhost:8080/query" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "What is Kubernetes?",
       "provider": "openai",
       "model": "gpt-4"
     }'
   ```

4. **Submit feedback** to generate feedback data:
   ```bash
   curl -X POST "http://localhost:8080/feedback" \
     -H "Content-Type: application/json" \
     -d '{
       "conversation_id": "your-conversation-id",
       "user_question": "What is Kubernetes?",
       "llm_response": "Kubernetes is...",
       "sentiment": 1,
       "user_feedback": "Very helpful response"
     }'
   ```

5. **Check stored data**:
   ```bash
   ls -la /tmp/data/feedback/
   ls -la /tmp/data/transcripts/
   ```

### Advanced Data Collector Testing

1. **Enable data collector** in your configuration:
   ```yaml
   user_data_collection:
     feedback_enabled: true
     feedback_storage: "/tmp/data/feedback"
     transcripts_enabled: true
     transcripts_storage: "/tmp/data/transcripts"
     data_collector:
       enabled: true
       ingress_server_url: "https://your-ingress-server.com/upload"
       ingress_server_auth_token: "your-auth-token"
       ingress_content_service_name: "lightspeed-stack"
       collection_interval: 60  # 1 minute for testing
       cleanup_after_send: true
       connection_timeout_seconds: 30
   ```

2. **Deploy the exporter service** pointing to the same data directories

3. **Monitor the data collection** by checking the logs and verifying that files are being uploaded and cleaned up

## Security Considerations

- **Data Privacy**: All user data is stored locally and can be configured to be cleaned up after upload
- **Authentication**: The data collector service uses authentication tokens for secure uploads
- **Data Redaction**: Query data is stored as "redacted_query" to ensure sensitive information is not captured
- **Access Control**: Data directories should be properly secured with appropriate file permissions

## Troubleshooting

### Common Issues

1. **Data not being stored**: Check that the storage directories exist and are writable
2. **Data collector not uploading**: Verify the ingress server URL and authentication token
3. **Permission errors**: Ensure the service has write permissions to the configured directories
4. **Connection timeouts**: Adjust the `connection_timeout_seconds` setting if needed

### Logging

Enable debug logging to troubleshoot data collection issues:

```yaml
service:
  log_level: debug
```

This will provide detailed information about data collection, storage, and upload processes.

## Integration with Red Hat Dataverse

For production deployments, the Lightspeed Core Stack integrates with Red Hat's Dataverse through the exporter service. This provides:

- Centralized data collection and analysis
- Consistent data processing pipeline
- Integration with other Red Hat services
- Automated data export and cleanup

For complete integration setup, deployment options, and configuration details, see the [exporter repository](https://github.com/lightspeed-core/lightspeed-to-dataverse-exporter).
