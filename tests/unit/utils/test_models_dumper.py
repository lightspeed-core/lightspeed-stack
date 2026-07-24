"""Unit tests for utils/models_dumper module."""

# pylint: disable=too-many-lines,line-too-long

from json import load
from pathlib import Path

from utils.models_dumper import dump_models


def test_dump_models(tmpdir: Path) -> None:
    """Test that models can be dump into a JSON file.

    An example of schema dump:
    {
        "openapi": "3.0.0",
        "info": {
            "title": "Lightspeed Core Stack",
            "version": "0.3.0"
        },
        "components": {
            "schemas": {
                "A2AStateConfiguration": {
                    "additionalProperties": false,
                    "description": "A2A protocol persistent state configuration.\n\nConfigures how A2A task state and context-to-conversation mappings are\nstored. For multi-worker deployments, use SQLite or PostgreSQL to ensure\nstate is shared across all workers.\n\nIf no configuration is provided, in-memory storage is used (default).\nThis is suitable for single-worker deployments but state will be lost\non restarts and not shared across workers.\n\nAttributes:\n    sqlite: SQLite database configuration for A2A state storage.\n    postgres: PostgreSQL database configuration for A2A state storage.",
                    "properties": {
                        "sqlite": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SQLiteDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "SQLite database configuration for A2A state storage.",
                            "title": "SQLite configuration"
                        },
                        "postgres": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`PostgreSQLDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "PostgreSQL database configuration for A2A state storage.",
                            "title": "PostgreSQL configuration"
                        }
                    },
                    "title": "A2AStateConfiguration",
                    "type": "object"
                },
                "APIKeyTokenConfiguration": {
                    "additionalProperties": false,
                    "description": "API Key Token configuration.",
                    "properties": {
                        "api_key": {
                            "examples": [
                                "some-api-key"
                            ],
                            "format": "password",
                            "minLength": 1,
                            "title": "API key",
                            "type": "string",
                            "writeOnly": true
                        }
                    },
                    "required": [
                        "api_key"
                    ],
                    "title": "APIKeyTokenConfiguration",
                    "type": "object"
                },
                "AbstractErrorResponse": {
                    "description": "Base class for error responses.\n\nAttributes:\n    status_code: HTTP status code for the error response.\n    detail: The detail model containing error summary and cause.",
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "AbstractErrorResponse",
                    "type": "object"
                },
                "AccessRule": {
                    "additionalProperties": false,
                    "description": "Rule defining what actions a role can perform.",
                    "properties": {
                        "role": {
                            "description": "Name of the role",
                            "title": "Role name",
                            "type": "string"
                        },
                        "actions": {
                            "description": "Allowed actions for this role",
                            "items": {
                                "$ref": "`#/components/schemas/`Action"
                            },
                            "title": "Allowed actions",
                            "type": "array"
                        }
                    },
                    "required": [
                        "role",
                        "actions"
                    ],
                    "title": "AccessRule",
                    "type": "object"
                },
                "Action": {
                    "description": "Available actions in the system.\n\nNote: this is not a real model, just an enumeration of all action names.",
                    "enum": [
                        "admin",
                        "list_other_conversations",
                        "read_other_conversations",
                        "query_other_conversations",
                        "delete_other_conversations",
                        "query",
                        "responses",
                        "streaming_query",
                        "get_conversation",
                        "list_conversations",
                        "delete_conversation",
                        "update_conversation",
                        "feedback",
                        "get_models",
                        "get_tools",
                        "get_shields",
                        "list_providers",
                        "get_provider",
                        "list_rags",
                        "get_rag",
                        "get_metrics",
                        "get_config",
                        "info",
                        "model_override",
                        "rlsapi_v1_infer",
                        "register_mcp_server",
                        "list_mcp_servers",
                        "delete_mcp_server",
                        "a2a_agent_card",
                        "a2a_task_execution",
                        "a2a_message",
                        "a2a_jsonrpc",
                        "manage_vector_stores",
                        "read_vector_stores",
                        "manage_files",
                        "manage_prompts",
                        "read_prompts"
                    ],
                    "title": "Action",
                    "type": "string"
                },
                "AllowedToolsFilter": {
                    "description": "Filter configuration for restricting which MCP tools can be used.\n\n:param tool_names: (Optional) List of specific tool names that are allowed",
                    "properties": {
                        "tool_names": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Tool Names"
                        }
                    },
                    "title": "AllowedToolsFilter",
                    "type": "object"
                },
                "ApprovalsConfiguration": {
                    "additionalProperties": false,
                    "description": "Configuration for human-in-the-loop approvals.\n\nAttributes:\n    approval_timeout_seconds: How long approval requests remain pending\n        before expiring.\n    approval_retention_days: How long to retain decided approvals for audit\n        purposes before cleanup.",
                    "properties": {
                        "approval_timeout_seconds": {
                            "default": 300,
                            "description": "Seconds before pending approval requests expire",
                            "minimum": 0,
                            "title": "Approval timeout",
                            "type": "integer"
                        },
                        "approval_retention_days": {
                            "default": 30,
                            "description": "Days to retain decided approvals before cleanup",
                            "minimum": 0,
                            "title": "Retention period",
                            "type": "integer"
                        }
                    },
                    "title": "ApprovalsConfiguration",
                    "type": "object"
                },
                "Attachment": {
                    "additionalProperties": false,
                    "description": "Model representing an attachment that can be sent from the UI as part of query.\n\nA list of attachments can be an optional part of 'query' request.\n\nAttributes:\n    attachment_type: The attachment type, like \"log\", \"configuration\" etc.\n    content_type: The content type as defined in MIME standard\n    content: The actual attachment content",
                    "examples": [
                        {
                            "attachment_type": "log",
                            "content": "this is attachment",
                            "content_type": "text/plain"
                        },
                        {
                            "attachment_type": "configuration",
                            "content": "kind: Pod\n metadata:\n name:    private-reg",
                            "content_type": "application/yaml"
                        },
                        {
                            "attachment_type": "configuration",
                            "content": "foo: bar",
                            "content_type": "application/yaml"
                        }
                    ],
                    "properties": {
                        "attachment_type": {
                            "description": "The attachment type, like 'log', 'configuration' etc.",
                            "examples": [
                                "log"
                            ],
                            "title": "Attachment Type",
                            "type": "string"
                        },
                        "content_type": {
                            "description": "The content type as defined in MIME standard",
                            "examples": [
                                "text/plain"
                            ],
                            "title": "Content Type",
                            "type": "string"
                        },
                        "content": {
                            "description": "The actual attachment content",
                            "examples": [
                                "warning: quota exceeded"
                            ],
                            "title": "Content",
                            "type": "string"
                        }
                    },
                    "required": [
                        "attachment_type",
                        "content_type",
                        "content"
                    ],
                    "title": "Attachment",
                    "type": "object"
                },
                "AuthenticationConfiguration": {
                    "additionalProperties": false,
                    "description": "Authentication configuration.",
                    "properties": {
                        "module": {
                            "default": "noop",
                            "title": "Module",
                            "type": "string"
                        },
                        "skip_tls_verification": {
                            "default": false,
                            "title": "Skip Tls Verification",
                            "type": "boolean"
                        },
                        "skip_for_health_probes": {
                            "default": false,
                            "description": "Skip authorization for readiness and liveness probes",
                            "title": "Skip authorization for probes",
                            "type": "boolean"
                        },
                        "skip_for_metrics": {
                            "default": false,
                            "description": "Skip authorization for the /metrics endpoint",
                            "title": "Skip authorization for metrics",
                            "type": "boolean"
                        },
                        "k8s_cluster_api": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "K8S Cluster Api"
                        },
                        "k8s_ca_cert_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "K8S Ca Cert Path"
                        },
                        "jwk_config": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`JwkConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "api_key_config": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`APIKeyTokenConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "rh_identity_config": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`RHIdentityConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "trusted_proxy_config": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`TrustedProxyConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        }
                    },
                    "title": "AuthenticationConfiguration",
                    "type": "object"
                },
                "AuthorizationConfiguration": {
                    "additionalProperties": false,
                    "description": "Authorization configuration.",
                    "properties": {
                        "access_rules": {
                            "description": "Rules for role-based access control",
                            "items": {
                                "$ref": "`#/components/schemas/`AccessRule"
                            },
                            "title": "Access rules",
                            "type": "array"
                        }
                    },
                    "title": "AuthorizationConfiguration",
                    "type": "object"
                },
                "AuthorizedResponse": {
                    "description": "Model representing a response to an authorization request.\n\nAttributes:\n    user_id: The ID of the logged in user.\n    username: The name of the logged in user.\n    skip_userid_check: Whether to skip the user ID check.",
                    "examples": [
                        {
                            "skip_userid_check": false,
                            "user_id": "123e4567-e89b-12d3-a456-426614174000",
                            "username": "user1"
                        }
                    ],
                    "properties": {
                        "user_id": {
                            "description": "User ID, for example UUID",
                            "examples": [
                                "c5260aec-4d82-4370-9fdf-05cf908b3f16"
                            ],
                            "title": "User Id",
                            "type": "string"
                        },
                        "username": {
                            "description": "User name",
                            "examples": [
                                "John Doe",
                                "Adam Smith"
                            ],
                            "title": "Username",
                            "type": "string"
                        },
                        "skip_userid_check": {
                            "description": "Whether to skip the user ID check",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Skip Userid Check",
                            "type": "boolean"
                        }
                    },
                    "required": [
                        "user_id",
                        "username",
                        "skip_userid_check"
                    ],
                    "title": "AuthorizedResponse",
                    "type": "object"
                },
                "AzureEntraIdConfiguration": {
                    "additionalProperties": false,
                    "description": "Microsoft Entra ID authentication attributes for Azure.",
                    "properties": {
                        "tenant_id": {
                            "format": "password",
                            "title": "Tenant Id",
                            "type": "string",
                            "writeOnly": true
                        },
                        "client_id": {
                            "format": "password",
                            "title": "Client Id",
                            "type": "string",
                            "writeOnly": true
                        },
                        "client_secret": {
                            "format": "password",
                            "title": "Client Secret",
                            "type": "string",
                            "writeOnly": true
                        },
                        "scope": {
                            "default": "https://cognitiveservices.azure.com/.default",
                            "description": "Azure Cognitive Services scope for token requests. Override only if using a different Azure service.",
                            "title": "Token scope",
                            "type": "string"
                        }
                    },
                    "required": [
                        "tenant_id",
                        "client_id",
                        "client_secret"
                    ],
                    "title": "AzureEntraIdConfiguration",
                    "type": "object"
                },
                "BadRequestResponse": {
                    "description": "400 Bad Request. Invalid resource identifier.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "The conversation ID 123e4567-e89b-12d3-a456-426614174000 has invalid format.",
                                "response": "Invalid conversation ID format"
                            },
                            "label": "conversation_id"
                        },
                        {
                            "detail": {
                                "cause": "The prompt ID pmpt_1234567890abcdef has invalid format.",
                                "response": "Invalid prompt ID format"
                            },
                            "label": "prompt_id"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "BadRequestResponse",
                    "type": "object"
                },
                "ByokRag": {
                    "additionalProperties": false,
                    "description": "BYOK (Bring Your Own Knowledge) RAG configuration.",
                    "properties": {
                        "rag_id": {
                            "description": "Unique RAG ID",
                            "minLength": 1,
                            "title": "RAG ID",
                            "type": "string"
                        },
                        "rag_type": {
                            "default": "inline::faiss",
                            "description": "Type of RAG database (e.g. 'inline::faiss', 'remote::pgvector').",
                            "minLength": 1,
                            "title": "RAG type",
                            "type": "string"
                        },
                        "embedding_model": {
                            "default": "sentence-transformers/all-mpnet-base-v2",
                            "description": "Embedding model identification",
                            "minLength": 1,
                            "title": "Embedding model",
                            "type": "string"
                        },
                        "embedding_dimension": {
                            "default": 768,
                            "description": "Dimensionality of embedding vectors.",
                            "minimum": 0,
                            "title": "Embedding dimension",
                            "type": "integer"
                        },
                        "vector_db_id": {
                            "description": "Vector database identification.",
                            "minLength": 1,
                            "title": "Vector DB ID",
                            "type": "string"
                        },
                        "db_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to RAG database. Required for inline::faiss.",
                            "title": "DB path"
                        },
                        "score_multiplier": {
                            "default": 1.0,
                            "description": "Multiplier applied to relevance scores from this vector store. Used to weight results when querying multiple knowledge sources. Values > 1 boost this store's results; values < 1 reduce them.",
                            "minimum": 0,
                            "title": "Score multiplier",
                            "type": "number"
                        },
                        "host": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "PostgreSQL host for remote::pgvector. Defaults to ${env.POSTGRES_HOST} when rag_type is remote::pgvector.",
                            "title": "PostgreSQL host"
                        },
                        "port": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "PostgreSQL port for remote::pgvector. Defaults to ${env.POSTGRES_PORT} when rag_type is remote::pgvector.",
                            "title": "PostgreSQL port"
                        },
                        "db": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "PostgreSQL database name for remote::pgvector. Defaults to ${env.POSTGRES_DATABASE} when rag_type is remote::pgvector.",
                            "title": "PostgreSQL database"
                        },
                        "user": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "PostgreSQL user for remote::pgvector. Defaults to ${env.POSTGRES_USER} when rag_type is remote::pgvector.",
                            "title": "PostgreSQL user"
                        },
                        "password": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "PostgreSQL password for remote::pgvector. Defaults to ${env.POSTGRES_PASSWORD} when rag_type is remote::pgvector.",
                            "title": "PostgreSQL password"
                        }
                    },
                    "required": [
                        "rag_id",
                        "vector_db_id"
                    ],
                    "title": "ByokRag",
                    "type": "object"
                },
                "CORSConfiguration": {
                    "additionalProperties": false,
                    "description": "CORS configuration.\n\nCORS or 'Cross-Origin Resource Sharing' refers to the situations when a\nfrontend running in a browser has JavaScript code that communicates with a\nbackend, and the backend is in a different 'origin' than the frontend.\n\nUseful resources:\n\n  - [CORS in FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)\n  - [Wikipedia article](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing)\n  - [What is CORS?](https://dev.to/akshay_chauhan/what-is-cors-explained-8f1)",
                    "properties": {
                        "allow_origins": {
                            "default": [
                                "*"
                            ],
                            "description": "A list of origins allowed for cross-origin requests. An origin is the combination of protocol (http, https), domain (myapp.com, localhost, localhost.tiangolo.com), and port (80, 443, 8080). Use ['*'] to allow all origins.",
                            "items": {
                                "type": "string"
                            },
                            "title": "Allow origins",
                            "type": "array"
                        },
                        "allow_credentials": {
                            "default": false,
                            "description": "Indicate that cookies should be supported for cross-origin requests",
                            "title": "Allow credentials",
                            "type": "boolean"
                        },
                        "allow_methods": {
                            "default": [
                                "*"
                            ],
                            "description": "A list of HTTP methods that should be allowed for cross-origin requests. You can use ['*'] to allow all standard methods.",
                            "items": {
                                "type": "string"
                            },
                            "title": "Allow methods",
                            "type": "array"
                        },
                        "allow_headers": {
                            "default": [
                                "*"
                            ],
                            "description": "A list of HTTP request headers that should be supported for cross-origin requests. You can use ['*'] to allow all headers. The Accept, Accept-Language, Content-Language and Content-Type headers are always allowed for simple CORS requests.",
                            "items": {
                                "type": "string"
                            },
                            "title": "Allow headers",
                            "type": "array"
                        }
                    },
                    "title": "CORSConfiguration",
                    "type": "object"
                },
                "CompactionConfiguration": {
                    "additionalProperties": false,
                    "description": "Configuration for conversation history compaction.\n\nCompaction summarizes older conversation turns when their estimated\ntoken count approaches the context window limit, keeping the\nconversation usable instead of failing with HTTP 413. The\nconfiguration here controls when compaction triggers and how much\nrecent context is preserved verbatim.\n\nAttributes:\n    enabled: Master switch. When False, compaction never triggers\n        and other fields are inert.\n    threshold_ratio: Trigger compaction when estimated input tokens\n        exceed this fraction of the model's context window\n        (clamped to 0.0..1.0).\n    token_floor: Minimum estimated token count before compaction\n        can trigger, regardless of threshold_ratio. Prevents\n        triggering on very small context windows.\n    buffer_turns: Initial number of recent turns to keep verbatim.\n        The runtime applies a degrading guard \u2014 if these turns\n        exceed the available budget, it reduces buffer_turns by\n        one repeatedly until the budget fits, down to zero.\n    buffer_max_ratio: Hard cap on the fraction of the context\n        window the buffer zone may occupy, regardless of\n        buffer_turns.",
                    "properties": {
                        "enabled": {
                            "default": false,
                            "description": "When true, older conversation turns are summarized when estimated tokens approach the context window limit.",
                            "title": "Enable compaction",
                            "type": "boolean"
                        },
                        "threshold_ratio": {
                            "default": 0.7,
                            "description": "Trigger compaction when estimated tokens exceed this fraction of the model's context window (0.0-1.0).",
                            "title": "Threshold ratio",
                            "type": "number"
                        },
                        "token_floor": {
                            "default": 4096,
                            "description": "Minimum token count before compaction can trigger. Prevents triggering on very small context windows.",
                            "minimum": 0,
                            "title": "Token floor",
                            "type": "integer"
                        },
                        "buffer_turns": {
                            "default": 4,
                            "description": "Number of recent turns to keep verbatim.",
                            "minimum": 0,
                            "title": "Buffer turns",
                            "type": "integer"
                        },
                        "buffer_max_ratio": {
                            "default": 0.3,
                            "description": "Maximum fraction of context window the buffer zone can occupy, regardless of buffer_turns.",
                            "title": "Buffer max ratio",
                            "type": "number"
                        }
                    },
                    "title": "CompactionConfiguration",
                    "type": "object"
                },
                "Configuration": {
                    "additionalProperties": false,
                    "description": "Global service configuration.",
                    "properties": {
                        "name": {
                            "description": "Name of the service. That value will be used in REST API endpoints.",
                            "title": "Service name",
                            "type": "string"
                        },
                        "service": {
                            "$ref": "`#/components/schemas/`ServiceConfiguration",
                            "description": "This section contains Lightspeed Core Stack service configuration.",
                            "title": "Service configuration"
                        },
                        "llama_stack": {
                            "$ref": "`#/components/schemas/`LlamaStackConfiguration",
                            "description": "This section contains Llama Stack configuration. Lightspeed Core Stack service can call Llama Stack in library mode or in server mode.",
                            "title": "Llama Stack configuration"
                        },
                        "user_data_collection": {
                            "$ref": "`#/components/schemas/`UserDataCollection",
                            "description": "This section contains configuration for subsystem that collects user data(transcription history and feedbacks).",
                            "title": "User data collection configuration"
                        },
                        "database": {
                            "$ref": "`#/components/schemas/`DatabaseConfiguration",
                            "description": "Configuration for database to store conversation IDs and other runtime data",
                            "title": "Database Configuration"
                        },
                        "mcp_servers": {
                            "description": "MCP (Model Context Protocol) servers provide tools and capabilities to the AI agents. These are configured in this section. Only MCP servers defined in the lightspeed-stack.yaml configuration are available to the agents. Tools configured in the llama-stack run.yaml are not accessible to lightspeed-core agents.",
                            "items": {
                                "$ref": "`#/components/schemas/`ModelContextProtocolServer"
                            },
                            "title": "Model Context Protocol Server and tools configuration",
                            "type": "array"
                        },
                        "authentication": {
                            "$ref": "`#/components/schemas/`AuthenticationConfiguration",
                            "description": "Authentication configuration",
                            "title": "Authentication configuration"
                        },
                        "authorization": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`AuthorizationConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Lightspeed Core Stack implements a modular authentication and authorization system with multiple authentication methods. Authorization is configurable through role-based access control. Authentication is handled through selectable modules configured via the module field in the authentication configuration.",
                            "title": "Authorization configuration"
                        },
                        "customization": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`Customization"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "It is possible to customize Lightspeed Core Stack via this section. System prompt can be customized and also different parts of the service can be replaced by custom Python modules.",
                            "title": "Custom profile configuration"
                        },
                        "inference": {
                            "$ref": "`#/components/schemas/`InferenceConfiguration",
                            "description": "One LLM provider and one its model might be selected as default ones. When no provider+model pair is specified in REST API calls (query endpoints), the default provider and model are used.",
                            "title": "Inference configuration"
                        },
                        "conversation_cache": {
                            "$ref": "`#/components/schemas/`ConversationHistoryConfiguration",
                            "title": "Conversation history configuration"
                        },
                        "compaction": {
                            "$ref": "`#/components/schemas/`CompactionConfiguration",
                            "description": "Controls when conversation history is summarized to keep the model's input below the context window limit. Disabled by default \u2014 when disabled, requests that exceed the window continue to surface as HTTP 413.",
                            "title": "Conversation compaction configuration"
                        },
                        "approvals": {
                            "$ref": "`#/components/schemas/`ApprovalsConfiguration",
                            "description": "Settings for human-in-the-loop approval of MCP tool invocations",
                            "title": "Approvals configuration"
                        },
                        "byok_rag": {
                            "description": "BYOK RAG configuration. This configuration can be used to reconfigure Llama Stack through its run.yaml configuration file",
                            "items": {
                                "$ref": "`#/components/schemas/`ByokRag"
                            },
                            "title": "BYOK RAG configuration",
                            "type": "array"
                        },
                        "a2a_state": {
                            "$ref": "`#/components/schemas/`A2AStateConfiguration",
                            "description": "Configuration for A2A protocol persistent state storage.",
                            "title": "A2A state configuration"
                        },
                        "quota_handlers": {
                            "$ref": "`#/components/schemas/`QuotaHandlersConfiguration",
                            "description": "Quota handlers configuration",
                            "title": "Quota handlers"
                        },
                        "azure_entra_id": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`AzureEntraIdConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "rlsapi_v1": {
                            "$ref": "`#/components/schemas/`RlsapiV1Configuration",
                            "description": "Configuration for the rlsapi v1 /infer endpoint used by the RHEL Lightspeed Command Line Assistant (CLA).",
                            "title": "rlsapi v1 configuration"
                        },
                        "splunk": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SplunkConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Splunk HEC configuration for sending telemetry events.",
                            "title": "Splunk configuration"
                        },
                        "deployment_environment": {
                            "default": "development",
                            "description": "Deployment environment name (e.g., 'development', 'staging', 'production'). Used in telemetry events.",
                            "title": "Deployment environment",
                            "type": "string"
                        },
                        "rag": {
                            "$ref": "`#/components/schemas/`RagConfiguration",
                            "description": "Configuration for all RAG strategies (inline and tool-based).",
                            "title": "RAG configuration"
                        },
                        "okp": {
                            "$ref": "`#/components/schemas/`OkpConfiguration",
                            "description": "OKP provider settings. Only used when 'okp' is listed in rag.inline or rag.tool.",
                            "title": "OKP configuration"
                        },
                        "reranker": {
                            "$ref": "`#/components/schemas/`RerankerConfiguration",
                            "description": "Configuration for neural reranking of RAG chunks using cross-encoder.",
                            "title": "Reranker configuration"
                        },
                        "skills": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SkillsConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Agent skills configuration. Specifies paths to skill directories.",
                            "title": "Agent skills"
                        },
                        "saved_prompts": {
                            "$ref": "`#/components/schemas/`SavedPromptsConfiguration",
                            "description": "Configuration for saved prompts feature limits including maximum prompts per user, display name length, and content length.",
                            "title": "Saved prompts configuration"
                        }
                    },
                    "required": [
                        "name",
                        "service",
                        "llama_stack",
                        "user_data_collection"
                    ],
                    "title": "Configuration",
                    "type": "object"
                },
                "ConfigurationResponse": {
                    "description": "Success response model for the config endpoint.\n\nAttributes:\n    configuration: Parsed application configuration returned to the client.",
                    "examples": [
                        {
                            "configuration": {
                                "authentication": {
                                    "module": "noop",
                                    "skip_tls_verification": false
                                },
                                "authorization": {
                                    "access_rules": []
                                },
                                "byok_rag": [],
                                "conversation_cache": {
                                    "memory": null,
                                    "postgres": null,
                                    "sqlite": null,
                                    "type": null
                                },
                                "customization": null,
                                "database": {
                                    "postgres": null,
                                    "sqlite": {
                                        "db_path": "/tmp/lightspeed-stack.db"
                                    }
                                },
                                "inference": {
                                    "default_model": "gpt-4-turbo",
                                    "default_provider": "openai"
                                },
                                "llama_stack": {
                                    "api_key": "*****",
                                    "library_client_config_path": null,
                                    "url": "http://localhost:8321",
                                    "use_as_library_client": false
                                },
                                "mcp_servers": [
                                    {
                                        "name": "server1",
                                        "provider_id": "provider1",
                                        "url": "http://url.com:1"
                                    }
                                ],
                                "name": "lightspeed-stack",
                                "quota_handlers": {
                                    "enable_token_history": false,
                                    "limiters": [],
                                    "postgres": null,
                                    "scheduler": {
                                        "period": 1
                                    },
                                    "sqlite": null
                                },
                                "service": {
                                    "access_log": true,
                                    "auth_enabled": false,
                                    "color_log": true,
                                    "cors": {
                                        "allow_credentials": false,
                                        "allow_headers": [
                                            "*"
                                        ],
                                        "allow_methods": [
                                            "*"
                                        ],
                                        "allow_origins": [
                                            "*"
                                        ]
                                    },
                                    "host": "localhost",
                                    "port": 8080,
                                    "tls_config": {
                                        "tls_certificate_path": null,
                                        "tls_key_password": null,
                                        "tls_key_path": null
                                    },
                                    "workers": 1
                                },
                                "user_data_collection": {
                                    "feedback_enabled": true,
                                    "feedback_storage": "/tmp/data/feedback",
                                    "transcripts_enabled": false,
                                    "transcripts_storage": "/tmp/data/transcripts"
                                }
                            }
                        }
                    ],
                    "properties": {
                        "configuration": {
                            "$ref": "`#/components/schemas/`Configuration"
                        }
                    },
                    "required": [
                        "configuration"
                    ],
                    "title": "ConfigurationResponse",
                    "type": "object"
                },
                "ConflictResponse": {
                    "description": "409 Conflict - Resource already exists.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "Mcp Server with name 'test-mcp-server' is already registered",
                                "response": "Mcp Server already exists"
                            },
                            "label": "mcp server"
                        },
                        {
                            "detail": {
                                "cause": "Client MCP tool with server_label 'my-server' conflicts with a server-configured MCP tool. Rename the client tool to avoid the conflict.",
                                "response": "Tool conflict"
                            },
                            "label": "mcp tool conflict"
                        },
                        {
                            "detail": {
                                "cause": "Client file_search tool conflicts with a server-configured file_search tool. Remove the client file_search to use the server's configuration.",
                                "response": "Tool conflict"
                            },
                            "label": "file search conflict"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "ConflictResponse",
                    "type": "object"
                },
                "ConversationData": {
                    "description": "Model representing conversation data returned by cache list operations.\n\nAttributes:\n    conversation_id: The conversation ID\n    topic_summary: The topic summary for the conversation (can be None)\n    last_message_timestamp: The timestamp of the last message in the conversation",
                    "properties": {
                        "conversation_id": {
                            "title": "Conversation Id",
                            "type": "string"
                        },
                        "topic_summary": {
                            "type": "string",
                            "nullable": true,
                            "title": "Topic Summary"
                        },
                        "last_message_timestamp": {
                            "title": "Last Message Timestamp",
                            "type": "number"
                        }
                    },
                    "required": [
                        "conversation_id",
                        "topic_summary",
                        "last_message_timestamp"
                    ],
                    "title": "ConversationData",
                    "type": "object"
                },
                "ConversationDeleteResponse": {
                    "description": "Response for deleting a conversation.",
                    "examples": [
                        {
                            "label": "deleted",
                            "value": {
                                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                                "deleted": true,
                                "response": "Conversation deleted successfully"
                            }
                        },
                        {
                            "label": "not found",
                            "value": {
                                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                                "deleted": false,
                                "response": "Conversation not found"
                            }
                        }
                    ],
                    "properties": {
                        "deleted": {
                            "description": "Whether the deletion was successful.",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Deleted",
                            "type": "boolean"
                        },
                        "conversation_id": {
                            "description": "Conversation identifier that was passed to delete.",
                            "examples": [
                                "123e4567-e89b-12d3-a456-426614174000"
                            ],
                            "title": "Conversation Id",
                            "type": "string"
                        }
                    },
                    "required": [
                        "deleted",
                        "conversation_id"
                    ],
                    "title": "ConversationDeleteResponse",
                    "type": "object"
                },
                "ConversationDetails": {
                    "description": "Model representing the details of a user conversation.\n\nAttributes:\n    conversation_id: The conversation ID (UUID).\n    created_at: When the conversation was created.\n    last_message_at: When the last message was sent.\n    message_count: Number of user messages in the conversation.\n    last_used_model: The last model used for the conversation.\n    last_used_provider: The provider of the last used model.\n    topic_summary: The topic summary for the conversation.\n\nExample:\n    ```python\n    conversation = ConversationDetails(\n        conversation_id=\"123e4567-e89b-12d3-a456-426614174000\",\n        created_at=\"2024-01-01T00:00:00Z\",\n        last_message_at=\"2024-01-01T00:05:00Z\",\n        message_count=5,\n        last_used_model=\"gemini/gemini-2.0-flash\",\n        last_used_provider=\"gemini\",\n        topic_summary=\"Openshift Microservices Deployment Strategies\",\n    )\n    ```",
                    "properties": {
                        "conversation_id": {
                            "description": "Conversation ID (UUID)",
                            "examples": [
                                "c5260aec-4d82-4370-9fdf-05cf908b3f16"
                            ],
                            "title": "Conversation Id",
                            "type": "string"
                        },
                        "created_at": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "When the conversation was created",
                            "examples": [
                                "2024-01-01T01:00:00Z"
                            ],
                            "title": "Created At"
                        },
                        "last_message_at": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "When the last message was sent",
                            "examples": [
                                "2024-01-01T01:00:00Z"
                            ],
                            "title": "Last Message At"
                        },
                        "message_count": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Number of user messages in the conversation",
                            "examples": [
                                42
                            ],
                            "title": "Message Count"
                        },
                        "last_used_model": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Identification of the last model used for the conversation",
                            "examples": [
                                "gpt-4-turbo",
                                "gpt-3.5-turbo-0125"
                            ],
                            "title": "Last Used Model"
                        },
                        "last_used_provider": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Identification of the last provider used for the conversation",
                            "examples": [
                                "openai",
                                "gemini"
                            ],
                            "title": "Last Used Provider"
                        },
                        "topic_summary": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Topic summary for the conversation",
                            "examples": [
                                "Openshift Microservices Deployment Strategies"
                            ],
                            "title": "Topic Summary"
                        }
                    },
                    "required": [
                        "conversation_id"
                    ],
                    "title": "ConversationDetails",
                    "type": "object"
                },
                "ConversationHistoryConfiguration": {
                    "additionalProperties": false,
                    "description": "Conversation history configuration.",
                    "properties": {
                        "type": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Type of database where the conversation history is to be stored.",
                            "title": "Conversation history database type"
                        },
                        "memory": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`InMemoryCacheConfig"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "In-memory cache configuration",
                            "title": "In-memory cache configuration"
                        },
                        "sqlite": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SQLiteDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "SQLite database configuration",
                            "title": "SQLite configuration"
                        },
                        "postgres": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`PostgreSQLDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "PostgreSQL database configuration",
                            "title": "PostgreSQL configuration"
                        }
                    },
                    "title": "ConversationHistoryConfiguration",
                    "type": "object"
                },
                "ConversationResponse": {
                    "description": "Model representing a response for retrieving a conversation.\n\nAttributes:\n    conversation_id: The conversation ID (UUID).\n    chat_history: The chat history as a list of conversation turns.",
                    "examples": [
                        {
                            "chat_history": [
                                {
                                    "completed_at": "2024-01-01T00:01:05Z",
                                    "messages": [
                                        {
                                            "content": "Hello",
                                            "type": "user"
                                        },
                                        {
                                            "content": "Hi there!",
                                            "type": "assistant"
                                        }
                                    ],
                                    "model": "gpt-4o-mini",
                                    "provider": "openai",
                                    "started_at": "2024-01-01T00:01:00Z",
                                    "tool_calls": [],
                                    "tool_results": []
                                }
                            ],
                            "conversation_id": "123e4567-e89b-12d3-a456-426614174000"
                        }
                    ],
                    "properties": {
                        "conversation_id": {
                            "description": "Conversation ID (UUID)",
                            "examples": [
                                "c5260aec-4d82-4370-9fdf-05cf908b3f16"
                            ],
                            "title": "Conversation Id",
                            "type": "string"
                        },
                        "chat_history": {
                            "description": "The simplified chat history as a list of conversation turns",
                            "examples": [
                                {
                                    "completed_at": "2024-01-01T00:01:05Z",
                                    "messages": [
                                        {
                                            "content": "Hello",
                                            "type": "user"
                                        },
                                        {
                                            "content": "Hi there!",
                                            "type": "assistant"
                                        }
                                    ],
                                    "model": "gpt-4o-mini",
                                    "provider": "openai",
                                    "started_at": "2024-01-01T00:01:00Z",
                                    "tool_calls": [],
                                    "tool_results": []
                                }
                            ],
                            "items": {
                                "$ref": "`#/components/schemas/`ConversationTurn"
                            },
                            "title": "Chat History",
                            "type": "array"
                        }
                    },
                    "required": [
                        "conversation_id",
                        "chat_history"
                    ],
                    "title": "ConversationResponse",
                    "type": "object"
                },
                "ConversationSummary": {
                    "description": "A single compaction-produced summary chunk.\n\nAttributes:\n    summary_text: The natural-language summary produced by the\n        summarization LLM call. Used directly as context for\n        subsequent requests (alongside any later summary chunks\n        and the buffer of recent turns kept verbatim).\n    summarized_through_turn: Running total of conversation items\n        consumed by this and all preceding summaries. Used by the\n        caller to advance the partition boundary on the next\n        compaction so the new summary only covers items that\n        have not yet been summarized.\n    token_count: Number of tokens in ``summary_text``. Tracked so\n        the recursive-resummarize fallback can decide when the\n        cumulative summary size itself approaches the context\n        limit without re-tokenizing.\n    created_at: ISO 8601 timestamp recording when this summary was\n        produced. Kept as a string (not datetime) to match the\n        cache schema convention used elsewhere in the codebase.\n    model_used: Fully-qualified model identifier used for the\n        summarization LLM call (e.g., ``\"openai/gpt-4o-mini\"``).\n        Preserved for audit and for diagnostics when summary\n        quality varies between models.",
                    "properties": {
                        "summary_text": {
                            "description": "Natural-language summary produced by the summarization LLM call.",
                            "title": "Summary text",
                            "type": "string"
                        },
                        "summarized_through_turn": {
                            "description": "Running total of conversation items consumed by this and all preceding summaries.",
                            "minimum": 0,
                            "title": "Summarized through turn",
                            "type": "integer"
                        },
                        "token_count": {
                            "description": "Number of tokens in summary_text.",
                            "minimum": 0,
                            "title": "Token count",
                            "type": "integer"
                        },
                        "created_at": {
                            "description": "ISO 8601 timestamp recording when this summary was produced.",
                            "title": "Created at",
                            "type": "string"
                        },
                        "model_used": {
                            "description": "Fully-qualified model identifier used for the summarization call.",
                            "title": "Model used",
                            "type": "string"
                        }
                    },
                    "required": [
                        "summary_text",
                        "summarized_through_turn",
                        "token_count",
                        "created_at",
                        "model_used"
                    ],
                    "title": "ConversationSummary",
                    "type": "object"
                },
                "ConversationTurn": {
                    "description": "Model representing a single conversation turn.\n\nAttributes:\n    messages: List of messages in this turn.\n    tool_calls: List of tool calls made in this turn.\n    tool_results: List of tool results from this turn.\n    provider: Provider identifier used for this turn.\n    model: Model identifier used for this turn.\n    started_at: ISO 8601 timestamp when the turn started.\n    completed_at: ISO 8601 timestamp when the turn completed.",
                    "properties": {
                        "messages": {
                            "description": "List of messages in this turn",
                            "items": {
                                "$ref": "`#/components/schemas/`Message"
                            },
                            "title": "Messages",
                            "type": "array"
                        },
                        "tool_calls": {
                            "description": "List of tool calls made in this turn",
                            "items": {
                                "$ref": "`#/components/schemas/`ToolCallSummary"
                            },
                            "title": "Tool Calls",
                            "type": "array"
                        },
                        "tool_results": {
                            "description": "List of tool results from this turn",
                            "items": {
                                "$ref": "`#/components/schemas/`ToolResultSummary"
                            },
                            "title": "Tool Results",
                            "type": "array"
                        },
                        "provider": {
                            "description": "Provider identifier used for this turn",
                            "examples": [
                                "openai"
                            ],
                            "title": "Provider",
                            "type": "string"
                        },
                        "model": {
                            "description": "Model identifier used for this turn",
                            "examples": [
                                "gpt-4o-mini"
                            ],
                            "title": "Model",
                            "type": "string"
                        },
                        "started_at": {
                            "description": "ISO 8601 timestamp when the turn started",
                            "examples": [
                                "2024-01-01T00:01:00Z"
                            ],
                            "title": "Started At",
                            "type": "string"
                        },
                        "completed_at": {
                            "description": "ISO 8601 timestamp when the turn completed",
                            "examples": [
                                "2024-01-01T00:01:05Z"
                            ],
                            "title": "Completed At",
                            "type": "string"
                        }
                    },
                    "required": [
                        "provider",
                        "model",
                        "started_at",
                        "completed_at"
                    ],
                    "title": "ConversationTurn",
                    "type": "object"
                },
                "ConversationUpdateRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a request to update a conversation topic summary.\n\nAttributes:\n    topic_summary: The new topic summary for the conversation.",
                    "properties": {
                        "topic_summary": {
                            "description": "The new topic summary for the conversation",
                            "examples": [
                                "Discussion about machine learning algorithms"
                            ],
                            "maxLength": 1000,
                            "minLength": 1,
                            "title": "Topic Summary",
                            "type": "string"
                        }
                    },
                    "required": [
                        "topic_summary"
                    ],
                    "title": "ConversationUpdateRequest",
                    "type": "object"
                },
                "ConversationUpdateResponse": {
                    "description": "Model representing a response for updating a conversation topic summary.\n\nAttributes:\n    conversation_id: The conversation ID (UUID) that was updated.\n    success: Whether the update was successful.\n    message: A message about the update result.",
                    "examples": [
                        {
                            "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                            "message": "Topic summary updated successfully",
                            "success": true
                        }
                    ],
                    "properties": {
                        "conversation_id": {
                            "description": "The conversation ID (UUID) that was updated",
                            "examples": [
                                "123e4567-e89b-12d3-a456-426614174000"
                            ],
                            "title": "Conversation Id",
                            "type": "string"
                        },
                        "success": {
                            "description": "Whether the update was successful",
                            "examples": [
                                true
                            ],
                            "title": "Success",
                            "type": "boolean"
                        },
                        "message": {
                            "description": "A message about the update result",
                            "examples": [
                                "Topic summary updated successfully"
                            ],
                            "title": "Message",
                            "type": "string"
                        }
                    },
                    "required": [
                        "conversation_id",
                        "success",
                        "message"
                    ],
                    "title": "ConversationUpdateResponse",
                    "type": "object"
                },
                "ConversationsListResponse": {
                    "description": "Model representing a response for listing conversations of a user.\n\nAttributes:\n    conversations: List of conversation details associated with the user.",
                    "examples": [
                        {
                            "conversations": [
                                {
                                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                                    "created_at": "2024-01-01T00:00:00Z",
                                    "last_message_at": "2024-01-01T00:05:00Z",
                                    "last_used_model": "gemini/gemini-2.0-flash",
                                    "last_used_provider": "gemini",
                                    "message_count": 5,
                                    "topic_summary": "Openshift Microservices Deployment Strategies"
                                },
                                {
                                    "conversation_id": "456e7890-e12b-34d5-a678-901234567890",
                                    "created_at": "2024-01-01T01:00:00Z",
                                    "last_used_model": "gemini/gemini-2.5-flash",
                                    "last_used_provider": "gemini",
                                    "message_count": 2,
                                    "topic_summary": "RHDH Purpose Summary"
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "conversations": {
                            "items": {
                                "$ref": "`#/components/schemas/`ConversationDetails"
                            },
                            "title": "Conversations",
                            "type": "array"
                        }
                    },
                    "required": [
                        "conversations"
                    ],
                    "title": "ConversationsListResponse",
                    "type": "object"
                },
                "ConversationsListResponseV2": {
                    "description": "Model representing a response for listing conversations of a user.\n\nAttributes:\n    conversations: List of conversation data associated with the user.",
                    "examples": [
                        {
                            "conversations": [
                                {
                                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                                    "last_message_timestamp": 1704067200.0,
                                    "topic_summary": "Openshift Microservices Deployment Strategies"
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "conversations": {
                            "items": {
                                "$ref": "`#/components/schemas/`ConversationData"
                            },
                            "title": "Conversations",
                            "type": "array"
                        }
                    },
                    "required": [
                        "conversations"
                    ],
                    "title": "ConversationsListResponseV2",
                    "type": "object"
                },
                "CustomProfile": {
                    "description": "Custom profile customization for prompts and validation.",
                    "properties": {
                        "path": {
                            "description": "Path to Python modules containing custom profile.",
                            "title": "Path to custom profile",
                            "type": "string"
                        },
                        "prompts": {
                            "additionalProperties": {
                                "type": "string"
                            },
                            "default": {},
                            "description": "Dictionary containing map of system prompts",
                            "title": "System prompts",
                            "type": "object"
                        }
                    },
                    "required": [
                        "path"
                    ],
                    "title": "CustomProfile",
                    "type": "object"
                },
                "Customization": {
                    "additionalProperties": false,
                    "description": "Service customization.",
                    "properties": {
                        "profile_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Profile Path"
                        },
                        "disable_query_system_prompt": {
                            "default": false,
                            "title": "Disable Query System Prompt",
                            "type": "boolean"
                        },
                        "disable_shield_ids_override": {
                            "default": false,
                            "title": "Disable Shield Ids Override",
                            "type": "boolean"
                        },
                        "system_prompt_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "System Prompt Path"
                        },
                        "system_prompt": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "System Prompt"
                        },
                        "agent_card_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Agent Card Path"
                        },
                        "agent_card_config": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "title": "Agent Card Config"
                        },
                        "custom_profile": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`CustomProfile"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        }
                    },
                    "title": "Customization",
                    "type": "object"
                },
                "DatabaseConfiguration": {
                    "additionalProperties": false,
                    "description": "Database configuration.",
                    "properties": {
                        "sqlite": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SQLiteDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "SQLite database configuration",
                            "title": "SQLite configuration"
                        },
                        "postgres": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`PostgreSQLDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "PostgreSQL database configuration",
                            "title": "PostgreSQL configuration"
                        }
                    },
                    "title": "DatabaseConfiguration",
                    "type": "object"
                },
                "DetailModel": {
                    "description": "Nested detail model for error responses.",
                    "properties": {
                        "response": {
                            "description": "Short summary of the error",
                            "title": "Response",
                            "type": "string"
                        },
                        "cause": {
                            "description": "Detailed explanation of what caused the error",
                            "title": "Cause",
                            "type": "string"
                        }
                    },
                    "required": [
                        "response",
                        "cause"
                    ],
                    "title": "DetailModel",
                    "type": "object"
                },
                "EndEventData": {
                    "description": "Nested data for event: \"end\".",
                    "properties": {
                        "referenced_documents": {
                            "items": {
                                "$ref": "`#/components/schemas/`ReferencedDocument"
                            },
                            "title": "Referenced Documents",
                            "type": "array"
                        },
                        "truncated": {
                            "type": "boolean",
                            "nullable": true,
                            "title": "Truncated"
                        },
                        "input_tokens": {
                            "title": "Input Tokens",
                            "type": "integer"
                        },
                        "output_tokens": {
                            "title": "Output Tokens",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "referenced_documents",
                        "truncated",
                        "input_tokens",
                        "output_tokens"
                    ],
                    "title": "EndEventData",
                    "type": "object"
                },
                "EndStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE end-of-stream body (includes available_quotas beside data).",
                    "properties": {
                        "event": {
                            "const": "end",
                            "default": "end",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`EndEventData"
                        },
                        "available_quotas": {
                            "additionalProperties": {
                                "type": "integer"
                            },
                            "title": "Available Quotas",
                            "type": "object"
                        }
                    },
                    "required": [
                        "data",
                        "available_quotas"
                    ],
                    "title": "EndStreamPayload",
                    "type": "object"
                },
                "ErrorEventData": {
                    "description": "Payload for event: \"error\".",
                    "properties": {
                        "status_code": {
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "response": {
                            "title": "Response",
                            "type": "string"
                        },
                        "cause": {
                            "title": "Cause",
                            "type": "string"
                        }
                    },
                    "required": [
                        "status_code",
                        "response",
                        "cause"
                    ],
                    "title": "ErrorEventData",
                    "type": "object"
                },
                "ErrorStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE error event body (event + typed data).",
                    "properties": {
                        "event": {
                            "const": "error",
                            "default": "error",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`ErrorEventData"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "ErrorStreamPayload",
                    "type": "object"
                },
                "FeedbackCategory": {
                    "description": "Enum representing predefined feedback categories for AI responses.\n\nThese categories help provide structured feedback about AI inference quality\nwhen users provide negative feedback (thumbs down). Multiple categories can\nbe selected to provide comprehensive feedback about response issues.",
                    "enum": [
                        "incorrect",
                        "not_relevant",
                        "incomplete",
                        "outdated_information",
                        "unsafe",
                        "other"
                    ],
                    "title": "FeedbackCategory",
                    "type": "string"
                },
                "FeedbackRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a feedback request.\n\nAttributes:\n    conversation_id: The required conversation ID (UUID).\n    user_question: The required user question.\n    llm_response: The required LLM response.\n    sentiment: The optional sentiment.\n    user_feedback: The optional user feedback.\n    categories: The optional list of feedback categories (multi-select for negative feedback).",
                    "examples": [
                        {
                            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
                            "llm_response": "bar",
                            "sentiment": -1,
                            "user_feedback": "Not satisfied with the response quality.",
                            "user_question": "foo"
                        },
                        {
                            "categories": [
                                "incorrect"
                            ],
                            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
                            "llm_response": "The capital of France is Berlin.",
                            "sentiment": -1,
                            "user_question": "What is the capital of France?"
                        },
                        {
                            "categories": [
                                "incomplete",
                                "not_relevant"
                            ],
                            "conversation_id": "12345678-abcd-0000-0123-456789abcdef",
                            "llm_response": "Use Docker.",
                            "sentiment": -1,
                            "user_feedback": "This response is too general and doesn't provide specific steps.",
                            "user_question": "How do I deploy a web app?"
                        }
                    ],
                    "properties": {
                        "conversation_id": {
                            "description": "The required conversation ID (UUID)",
                            "examples": [
                                "c5260aec-4d82-4370-9fdf-05cf908b3f16"
                            ],
                            "title": "Conversation Id",
                            "type": "string"
                        },
                        "user_question": {
                            "description": "User question (the query string)",
                            "examples": [
                                "What is Kubernetes?"
                            ],
                            "title": "User Question",
                            "type": "string"
                        },
                        "llm_response": {
                            "description": "Response from LLM",
                            "examples": [
                                "Kubernetes is an open-source container orchestration system for automating ..."
                            ],
                            "title": "Llm Response",
                            "type": "string"
                        },
                        "sentiment": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "User sentiment, if provided must be -1 or 1",
                            "examples": [
                                -1,
                                1
                            ],
                            "title": "Sentiment"
                        },
                        "user_feedback": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Feedback on the LLM response.",
                            "examples": [
                                "I'm not satisfied with the response because it is too vague."
                            ],
                            "title": "User Feedback"
                        },
                        "categories": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "List of feedback categories that describe issues with the LLM response (for negative feedback).",
                            "examples": [
                                [
                                    "incorrect",
                                    "incomplete"
                                ]
                            ],
                            "title": "Categories"
                        }
                    },
                    "required": [
                        "conversation_id",
                        "user_question",
                        "llm_response"
                    ],
                    "title": "FeedbackRequest",
                    "type": "object"
                },
                "FeedbackResponse": {
                    "description": "Model representing a response to a feedback request.\n\nAttributes:\n    response: The response of the feedback request.",
                    "examples": [
                        {
                            "response": "feedback received"
                        }
                    ],
                    "properties": {
                        "response": {
                            "description": "The response of the feedback request.",
                            "examples": [
                                "feedback received"
                            ],
                            "title": "Response",
                            "type": "string"
                        }
                    },
                    "required": [
                        "response"
                    ],
                    "title": "FeedbackResponse",
                    "type": "object"
                },
                "FeedbackStatusUpdateRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a feedback status update request.\n\nAttributes:\n    status: Value of the desired feedback enabled state.",
                    "properties": {
                        "status": {
                            "default": false,
                            "description": "Desired state of feedback enablement, must be False or True",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Status",
                            "type": "boolean"
                        }
                    },
                    "title": "FeedbackStatusUpdateRequest",
                    "type": "object"
                },
                "FeedbackStatusUpdateResponse": {
                    "description": "Model representing a response to a feedback status update request.\n\nAttributes:\n    status: The previous and current status of the service and who updated it.",
                    "examples": [
                        {
                            "status": {
                                "previous_status": true,
                                "timestamp": "2023-03-15 12:34:56",
                                "updated_by": "user/test",
                                "updated_status": false
                            }
                        }
                    ],
                    "properties": {
                        "status": {
                            "additionalProperties": true,
                            "title": "Status",
                            "type": "object"
                        }
                    },
                    "required": [
                        "status"
                    ],
                    "title": "FeedbackStatusUpdateResponse",
                    "type": "object"
                },
                "FileResponse": {
                    "additionalProperties": false,
                    "description": "Response model containing a file object.\n\nAttributes:\n    id: File ID.\n    filename: File name.\n    bytes: File size in bytes.\n    created_at: Unix timestamp when created.\n    purpose: File purpose.\n    object: Object type (always \"file\").",
                    "examples": [
                        {
                            "bytes": 524288,
                            "created_at": 1704067200,
                            "filename": "documentation.pdf",
                            "id": "file_abc123",
                            "object": "file",
                            "purpose": "assistants"
                        }
                    ],
                    "properties": {
                        "id": {
                            "description": "File ID",
                            "title": "Id",
                            "type": "string"
                        },
                        "filename": {
                            "description": "File name",
                            "title": "Filename",
                            "type": "string"
                        },
                        "bytes": {
                            "description": "File size in bytes",
                            "title": "Bytes",
                            "type": "integer"
                        },
                        "created_at": {
                            "description": "Unix timestamp when created",
                            "title": "Created At",
                            "type": "integer"
                        },
                        "purpose": {
                            "default": "assistants",
                            "description": "File purpose",
                            "title": "Purpose",
                            "type": "string"
                        },
                        "object": {
                            "default": "file",
                            "description": "Object type",
                            "title": "Object",
                            "type": "string"
                        }
                    },
                    "required": [
                        "id",
                        "filename",
                        "bytes",
                        "created_at"
                    ],
                    "title": "FileResponse",
                    "type": "object"
                },
                "FileTooLargeResponse": {
                    "description": "413 Content Too Large - File upload exceeds size limit.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "File size 150000000 bytes exceeds maximum allowed size of 104857600 bytes (100 MB)",
                                "response": "File too large"
                            },
                            "label": "file upload"
                        },
                        {
                            "detail": {
                                "cause": "File upload rejected: File size exceeds limit",
                                "response": "Invalid file upload"
                            },
                            "label": "backend rejection"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "FileTooLargeResponse",
                    "type": "object"
                },
                "ForbiddenResponse": {
                    "description": "403 Forbidden. Access denied.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "User 6789 does not have permission to read conversation with ID 123e4567-e89b-12d3-a456-426614174000",
                                "response": "User does not have permission to perform this action"
                            },
                            "label": "conversation read"
                        },
                        {
                            "detail": {
                                "cause": "User 6789 does not have permission to delete conversation with ID 123e4567-e89b-12d3-a456-426614174000",
                                "response": "User does not have permission to perform this action"
                            },
                            "label": "conversation delete"
                        },
                        {
                            "detail": {
                                "cause": "User 6789 is not authorized to access this endpoint.",
                                "response": "User does not have permission to access this endpoint"
                            },
                            "label": "endpoint"
                        },
                        {
                            "detail": {
                                "cause": "User 6789 does not have permission to list or read stored prompts (missing permission: read_prompts).",
                                "response": "User does not have permission to perform this action"
                            },
                            "label": "prompt read"
                        },
                        {
                            "detail": {
                                "cause": "User 6789 does not have permission to create, update, or delete stored prompts (missing permission: manage_prompts).",
                                "response": "User does not have permission to perform this action"
                            },
                            "label": "prompt manage"
                        },
                        {
                            "detail": {
                                "cause": "Storing feedback is disabled.",
                                "response": "Storing feedback is disabled"
                            },
                            "label": "feedback"
                        },
                        {
                            "detail": {
                                "cause": "User lacks model_override permission required to override model/provider.",
                                "response": "This instance does not permit overriding model/provider in the query request (missing permission: model_override). Please remove the model and provider fields from your request."
                            },
                            "label": "model override"
                        },
                        {
                            "detail": {
                                "cause": "MCP server 'my-mcp' is defined in configuration and cannot be removed via the API.",
                                "response": "Cannot delete statically configured MCP server"
                            },
                            "label": "mcp server static"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "ForbiddenResponse",
                    "type": "object"
                },
                "HealthStatus": {
                    "description": "Health status enum for provider and service health checks.\n\nThis enum serves two purposes:\n\n1. Provider-level health (returned by Llama Stack providers):\n   - OK: Provider is healthy and operational\n   - ERROR: Provider is unhealthy or failed health check\n   - NOT_IMPLEMENTED: Provider does not implement health checks\n   - UNKNOWN: Fallback when provider status cannot be determined\n\n2. Service-level health (overall LCORE status):\n   - HEALTHY: All systems operational, LLS connected, all providers healthy\n   - DEGRADED: Service running with reduced functionality (e.g., LLS unavailable)\n   - UNHEALTHY: Service connected but one or more providers are unhealthy",
                    "enum": [
                        "ok",
                        "error",
                        "not_implemented",
                        "unknown",
                        "healthy",
                        "degraded",
                        "unhealthy"
                    ],
                    "title": "HealthStatus",
                    "type": "string"
                },
                "InMemoryCacheConfig": {
                    "additionalProperties": false,
                    "description": "In-memory cache configuration.",
                    "properties": {
                        "max_entries": {
                            "description": "Maximum number of entries stored in the in-memory cache",
                            "minimum": 0,
                            "title": "Max entries",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "max_entries"
                    ],
                    "title": "InMemoryCacheConfig",
                    "type": "object"
                },
                "IncludeParameter": {
                    "enum": [
                        "web_search_call.action.sources",
                        "code_interpreter_call.outputs",
                        "computer_call_output.output.image_url",
                        "file_search_call.results",
                        "message.input_image.image_url",
                        "message.output_text.logprobs"
                    ],
                    "type": "string"
                },
                "InferenceConfiguration": {
                    "additionalProperties": false,
                    "description": "Inference configuration.",
                    "properties": {
                        "default_model": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Identification of default model used when no other model is specified.",
                            "title": "Default model"
                        },
                        "default_provider": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Identification of default provider used when no other model is specified.",
                            "title": "Default provider"
                        },
                        "context_windows": {
                            "additionalProperties": {
                                "minimum": 0,
                                "type": "integer"
                            },
                            "description": "Map of fully-qualified model identifier (e.g., \"openai/gpt-4o-mini\") to context window size in tokens. Used by the conversation compaction trigger to decide when older turns must be summarized before the input exceeds the window. Models absent from this map have no registered window \u2014 callers fall back to their own default or skip the token-based trigger.",
                            "title": "Per-model context window sizes (tokens)",
                            "type": "object"
                        },
                        "providers": {
                            "description": "Unified-mode synthesis input (Decision S5): a high-level, backend-agnostic list of inference providers the synthesizer expands into Llama Stack provider entries. Lives at the configuration root so it survives a future backend change. A non-empty list signals unified mode. Empty (the default) leaves legacy/remote modes unaffected. The sibling default_model / default_provider keep their query-time routing meaning and are independent of this list.",
                            "items": {
                                "$ref": "`#/components/schemas/`UnifiedInferenceProvider"
                            },
                            "title": "High-level inference providers",
                            "type": "array"
                        },
                        "max_infer_iters": {
                            "type": "integer",
                            "nullable": true,
                            "default": 10,
                            "description": "Server-side default for the maximum number of inference iterations a model can perform in a single request. Prevents small models from looping indefinitely on tool calls. Per-request values take precedence over this default. Set to None to disable the limit.",
                            "title": "Default max inference iterations"
                        },
                        "max_tool_calls": {
                            "type": "integer",
                            "nullable": true,
                            "default": 30,
                            "description": "Server-side default for the maximum number of tool calls allowed in a single response. Prevents small models from exhausting the context window with repeated tool calls. Per-request values take precedence over this default. Set to None to disable the limit.",
                            "title": "Default max tool calls"
                        }
                    },
                    "title": "InferenceConfiguration",
                    "type": "object"
                },
                "InfoResponse": {
                    "description": "Model representing a response to an info request.\n\nAttributes:\n    name: Service name.\n    service_version: Service version.\n    llama_stack_version: Llama Stack version.",
                    "examples": [
                        {
                            "llama_stack_version": "1.0.0",
                            "name": "Lightspeed Stack",
                            "service_version": "1.0.0"
                        }
                    ],
                    "properties": {
                        "name": {
                            "description": "Service name",
                            "examples": [
                                "Lightspeed Stack"
                            ],
                            "title": "Name",
                            "type": "string"
                        },
                        "service_version": {
                            "description": "Service version",
                            "examples": [
                                "0.1.0",
                                "0.2.0",
                                "1.0.0"
                            ],
                            "title": "Service Version",
                            "type": "string"
                        },
                        "llama_stack_version": {
                            "description": "Llama Stack version",
                            "examples": [
                                "0.2.1",
                                "0.2.2",
                                "0.2.18",
                                "0.2.21",
                                "0.2.22"
                            ],
                            "title": "Llama Stack Version",
                            "type": "string"
                        }
                    },
                    "required": [
                        "name",
                        "service_version",
                        "llama_stack_version"
                    ],
                    "title": "InfoResponse",
                    "type": "object"
                },
                "InputToolMCP": {
                    "description": "MCP input tool with authorization included when serializing request bodies.",
                    "properties": {
                        "type": {
                            "const": "mcp",
                            "default": "mcp",
                            "title": "Type",
                            "type": "string"
                        },
                        "server_label": {
                            "title": "Server Label",
                            "type": "string"
                        },
                        "connector_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Connector Id"
                        },
                        "server_url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Server Url"
                        },
                        "headers": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "title": "Headers"
                        },
                        "authorization": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Authorization"
                        },
                        "require_approval": {
                            "anyOf": [
                                {
                                    "const": "always",
                                    "type": "string"
                                },
                                {
                                    "const": "never",
                                    "type": "string"
                                },
                                {
                                    "$ref": "`#/components/schemas/`ogx_api__openai_responses__ApprovalFilter"
                                }
                            ],
                            "default": "never",
                            "title": "Require Approval"
                        },
                        "allowed_tools": {
                            "anyOf": [
                                {
                                    "items": {
                                        "type": "string"
                                    },
                                    "type": "array"
                                },
                                {
                                    "$ref": "`#/components/schemas/`AllowedToolsFilter"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "title": "Allowed Tools"
                        }
                    },
                    "required": [
                        "server_label"
                    ],
                    "title": "InputToolMCP",
                    "type": "object"
                },
                "InternalServerErrorResponse": {
                    "description": "500 Internal Server Error.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "An unexpected error occurred while processing the request.",
                                "response": "Internal server error"
                            },
                            "label": "internal"
                        },
                        {
                            "detail": {
                                "cause": "Lightspeed Stack configuration has not been initialized.",
                                "response": "Configuration is not loaded"
                            },
                            "label": "configuration"
                        },
                        {
                            "detail": {
                                "cause": "Failed to store feedback at directory: /path/example",
                                "response": "Failed to store feedback"
                            },
                            "label": "feedback storage"
                        },
                        {
                            "detail": {
                                "cause": "Failed to call backend API",
                                "response": "Error while processing query"
                            },
                            "label": "query"
                        },
                        {
                            "detail": {
                                "cause": "Conversation cache is not configured or unavailable.",
                                "response": "Conversation cache not configured"
                            },
                            "label": "conversation cache"
                        },
                        {
                            "detail": {
                                "cause": "Failed to query the database",
                                "response": "Database query failed"
                            },
                            "label": "database"
                        },
                        {
                            "detail": {
                                "cause": "ClusterVersion 'version' resource not found in OpenShift cluster",
                                "response": "Internal server error"
                            },
                            "label": "cluster version not found"
                        },
                        {
                            "detail": {
                                "cause": "Insufficient permissions to read ClusterVersion resource",
                                "response": "Internal server error"
                            },
                            "label": "cluster version permission denied"
                        },
                        {
                            "detail": {
                                "cause": "Missing or invalid 'clusterID' in ClusterVersion",
                                "response": "Internal server error"
                            },
                            "label": "invalid cluster version"
                        },
                        {
                            "detail": {
                                "cause": "Could not register the MCP server with the remote service.",
                                "response": "Failed to register MCP server"
                            },
                            "label": "mcp server registration"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "InternalServerErrorResponse",
                    "type": "object"
                },
                "InterruptedEventData": {
                    "description": "Payload for event: \"interrupted\".",
                    "properties": {
                        "request_id": {
                            "title": "Request Id",
                            "type": "string"
                        }
                    },
                    "required": [
                        "request_id"
                    ],
                    "title": "InterruptedEventData",
                    "type": "object"
                },
                "InterruptedStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE interrupted stream body.",
                    "properties": {
                        "event": {
                            "const": "interrupted",
                            "default": "interrupted",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`InterruptedEventData"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "InterruptedStreamPayload",
                    "type": "object"
                },
                "JsonPathOperator": {
                    "description": "Supported operators for JSONPath evaluation.\n\nNote: this is not a real model, just an enumeration of all supported JSONPath operators.",
                    "enum": [
                        "equals",
                        "contains",
                        "in",
                        "match"
                    ],
                    "title": "JsonPathOperator",
                    "type": "string"
                },
                "JwkConfiguration": {
                    "additionalProperties": false,
                    "description": "JWK (JSON Web Key) configuration.\n\nA JSON Web Key (JWK) is a JavaScript Object Notation (JSON) data structure\nthat represents a cryptographic key.\n\nUseful resources:\n\n  - [JSON Web Key](https://openid.net/specs/draft-jones-json-web-key-03.html)\n  - [RFC 7517](https://www.rfc-editor.org/rfc/rfc7517)",
                    "properties": {
                        "url": {
                            "description": "HTTPS URL of the JWK (JSON Web Key) set used to validate JWTs.",
                            "format": "uri",
                            "minLength": 1,
                            "title": "URL",
                            "type": "string"
                        },
                        "jwt_configuration": {
                            "$ref": "`#/components/schemas/`JwtConfiguration",
                            "description": "JWT (JSON Web Token) configuration",
                            "title": "JWT configuration"
                        }
                    },
                    "required": [
                        "url"
                    ],
                    "title": "JwkConfiguration",
                    "type": "object"
                },
                "JwtConfiguration": {
                    "additionalProperties": false,
                    "description": "JWT (JSON Web Token) configuration.\n\nJSON Web Token (JWT) is a compact, URL-safe means of representing\nclaims to be transferred between two parties.  The claims in a JWT\nare encoded as a JSON object that is used as the payload of a JSON\nWeb Signature (JWS) structure or as the plaintext of a JSON Web\nEncryption (JWE) structure, enabling the claims to be digitally\nsigned or integrity protected with a Message Authentication Code\n(MAC) and/or encrypted.\n\nUseful resources:\n\n  - [JSON Web Token](https://en.wikipedia.org/wiki/JSON_Web_Token)\n  - [RFC 7519](https://datatracker.ietf.org/doc/html/rfc7519)\n  - [JSON Web Tokens](https://auth0.com/docs/secure/tokens/json-web-tokens)",
                    "properties": {
                        "user_id_claim": {
                            "default": "user_id",
                            "description": "JWT claim name that uniquely identifies the user (subject ID).",
                            "title": "User ID claim",
                            "type": "string"
                        },
                        "username_claim": {
                            "default": "username",
                            "description": "JWT claim name that provides the human-readable username.",
                            "title": "Username claim",
                            "type": "string"
                        },
                        "role_rules": {
                            "description": "Rules for extracting roles from JWT claims",
                            "items": {
                                "$ref": "`#/components/schemas/`JwtRoleRule"
                            },
                            "title": "Role rules",
                            "type": "array"
                        }
                    },
                    "title": "JwtConfiguration",
                    "type": "object"
                },
                "JwtRoleRule": {
                    "additionalProperties": false,
                    "description": "Rule for extracting roles from JWT claims.",
                    "properties": {
                        "jsonpath": {
                            "description": "JSONPath expression to evaluate against the JWT payload",
                            "title": "JSON path",
                            "type": "string"
                        },
                        "operator": {
                            "$ref": "`#/components/schemas/`JsonPathOperator",
                            "description": "JSON path comparison operator",
                            "title": "Operator"
                        },
                        "negate": {
                            "default": false,
                            "description": "If set to true, the meaning of the rule is negated",
                            "title": "Negate rule",
                            "type": "boolean"
                        },
                        "value": {
                            "description": "Value to compare against",
                            "title": "Value"
                        },
                        "roles": {
                            "description": "Roles to be assigned if the rule matches",
                            "items": {
                                "type": "string"
                            },
                            "title": "List of roles",
                            "type": "array"
                        }
                    },
                    "required": [
                        "jsonpath",
                        "operator",
                        "value",
                        "roles"
                    ],
                    "title": "JwtRoleRule",
                    "type": "object"
                },
                "LivenessResponse": {
                    "description": "Model representing a response to a liveness request.\n\nAttributes:\n    alive: If app is alive.",
                    "examples": [
                        {
                            "alive": true
                        }
                    ],
                    "properties": {
                        "alive": {
                            "description": "Flag indicating that the app is alive",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Alive",
                            "type": "boolean"
                        }
                    },
                    "required": [
                        "alive"
                    ],
                    "title": "LivenessResponse",
                    "type": "object"
                },
                "LlamaStackConfiguration": {
                    "additionalProperties": false,
                    "description": "Llama stack configuration.\n\nLlama Stack is a comprehensive system that provides a uniform set of tools\nfor building, scaling, and deploying generative AI applications, enabling\ndevelopers to create, integrate, and orchestrate multiple AI services and\ncapabilities into an adaptable setup.\n\nUseful resources:\n\n  - [Llama Stack](https://www.llama.com/products/llama-stack/)\n  - [Python Llama Stack client](https://github.com/llamastack/llama-stack-client-python)\n  - [Build AI Applications with Llama Stack](https://llamastack.github.io/)",
                    "properties": {
                        "url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "URL to Llama Stack service; used when library mode is disabled. Must be a valid HTTP or HTTPS URL.",
                            "title": "Llama Stack URL"
                        },
                        "api_key": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "API key to access Llama Stack service",
                            "title": "API key"
                        },
                        "use_as_library_client": {
                            "type": "boolean",
                            "nullable": true,
                            "default": null,
                            "description": "When set to true Llama Stack will be used in library mode, not in server mode (default)",
                            "title": "Use as library"
                        },
                        "library_client_config_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to configuration file used when Llama Stack is run in library mode",
                            "title": "Llama Stack configuration path"
                        },
                        "timeout": {
                            "default": 180,
                            "description": "Timeout in seconds for requests to Llama Stack service. Default is 180 seconds (3 minutes) to accommodate long-running RAG queries.",
                            "minimum": 0,
                            "title": "Request timeout",
                            "type": "integer"
                        },
                        "max_retries": {
                            "default": 5,
                            "description": "Maximum number of connection attempts before giving up. Used on startup to connect to Llama Stack and retrieve its version. Connection attempts are retried with a fixed delay to handle the case where Llama Stack is still starting up (e.g., when running as a sidecar in the same pod).",
                            "minimum": 0,
                            "title": "Maximum number of connection attempts before giving up",
                            "type": "integer"
                        },
                        "retry_delay": {
                            "default": 2,
                            "description": "Delay in seconds between retry attempts. Used on startup to connect to Llama Stack and retrieve its version. Connection attempts are retried with a fixed delay to handle the case where Llama Stack is still starting up (e.g., when running as a sidecar in the same pod).",
                            "minimum": 0,
                            "title": "Delay in seconds between retry attempts",
                            "type": "integer"
                        },
                        "allow_degraded_mode": {
                            "type": "boolean",
                            "nullable": true,
                            "default": false,
                            "description": "If enabled, Lightspeed Core can be started even when Llama Stack is not accessible (valid for server mode only)",
                            "title": "Allow degraded mode"
                        },
                        "config": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`UnifiedLlamaStackConfig"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Backend-specific knobs for unified mode, where LCORE synthesizes the Llama Stack run.yaml instead of reading an external file. Holds the baseline selector, an optional profile path, and a raw native_override escape hatch. Backend-agnostic high-level sections (e.g. inference.providers) live at the configuration root, not here. Mutually exclusive with library_client_config_path; that cross-field check lives on the root Configuration model. When set in library mode, library_client_config_path is not required.",
                            "title": "Unified Llama Stack configuration"
                        }
                    },
                    "title": "LlamaStackConfiguration",
                    "type": "object"
                },
                "MCPClientAuthOptionsResponse": {
                    "description": "Response containing MCP servers that accept client-provided authorization.\n\nAttributes:\n    servers: MCP servers that declare client authentication headers.",
                    "examples": [
                        {
                            "servers": [
                                {
                                    "client_auth_headers": [
                                        "Authorization"
                                    ],
                                    "name": "github"
                                },
                                {
                                    "client_auth_headers": [
                                        "Authorization",
                                        "X-API-Key"
                                    ],
                                    "name": "gitlab"
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "servers": {
                            "description": "List of MCP servers that accept client-provided authorization",
                            "items": {
                                "$ref": "`#/components/schemas/`MCPServerAuthInfo"
                            },
                            "title": "Servers",
                            "type": "array"
                        }
                    },
                    "title": "MCPClientAuthOptionsResponse",
                    "type": "object"
                },
                "MCPListToolsSummary": {
                    "description": "Model representing MCP list tools payload serialized into tool results.",
                    "properties": {
                        "server_label": {
                            "description": "MCP server label associated with the tool list",
                            "title": "Server Label",
                            "type": "string"
                        },
                        "tools": {
                            "description": "Tools exposed by the MCP server",
                            "items": {
                                "$ref": "`#/components/schemas/`ToolInfoSummary"
                            },
                            "title": "Tools",
                            "type": "array"
                        }
                    },
                    "required": [
                        "server_label"
                    ],
                    "title": "MCPListToolsSummary",
                    "type": "object"
                },
                "MCPListToolsTool": {
                    "description": "Tool definition returned by MCP list tools operation.\n\n:param input_schema: JSON schema defining the tool's input parameters\n:param name: Name of the tool\n:param description: (Optional) Description of what the tool does",
                    "properties": {
                        "input_schema": {
                            "additionalProperties": true,
                            "title": "Input Schema",
                            "type": "object"
                        },
                        "name": {
                            "title": "Name",
                            "type": "string"
                        },
                        "description": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Description"
                        }
                    },
                    "required": [
                        "input_schema",
                        "name"
                    ],
                    "title": "MCPListToolsTool",
                    "type": "object"
                },
                "MCPServerAuthInfo": {
                    "description": "Information about MCP server client authentication options.",
                    "properties": {
                        "name": {
                            "description": "MCP server name",
                            "title": "Name",
                            "type": "string"
                        },
                        "client_auth_headers": {
                            "description": "List of authentication header names for client-provided tokens",
                            "items": {
                                "type": "string"
                            },
                            "title": "Client Auth Headers",
                            "type": "array"
                        }
                    },
                    "required": [
                        "name",
                        "client_auth_headers"
                    ],
                    "title": "MCPServerAuthInfo",
                    "type": "object"
                },
                "MCPServerDeleteResponse": {
                    "description": "Response indicating the outcome of an MCP server delete operation.\n\nAttributes:\n    name: Name of the MCP server targeted for deletion.\n    deleted: Whether the server was successfully deleted (True) or not found (False).\n    response: Description of the result, e.g. \"MCP server deleted successfully\".",
                    "examples": [
                        {
                            "label": "deleted",
                            "value": {
                                "deleted": true,
                                "name": "mcp-server",
                                "response": "MCP server deleted successfully"
                            }
                        },
                        {
                            "label": "not found",
                            "value": {
                                "deleted": false,
                                "name": "mcp-server",
                                "response": "MCP server not found"
                            }
                        }
                    ],
                    "properties": {
                        "deleted": {
                            "description": "Whether the deletion was successful.",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Deleted",
                            "type": "boolean"
                        },
                        "name": {
                            "description": "MCP server name that was passed to delete.",
                            "examples": [
                                "test-mcp-server"
                            ],
                            "title": "Name",
                            "type": "string"
                        }
                    },
                    "required": [
                        "deleted",
                        "name"
                    ],
                    "title": "MCPServerDeleteResponse",
                    "type": "object"
                },
                "MCPServerInfo": {
                    "description": "Information about a registered MCP server.\n\nAttributes:\n    name: Unique name of the MCP server.\n    url: URL of the MCP server endpoint.\n    provider_id: MCP provider identification.\n    source: Whether the server was registered statically (config) or dynamically (api).",
                    "properties": {
                        "name": {
                            "description": "MCP server name",
                            "title": "Name",
                            "type": "string"
                        },
                        "url": {
                            "description": "MCP server URL",
                            "title": "Url",
                            "type": "string"
                        },
                        "provider_id": {
                            "description": "MCP provider identification",
                            "title": "Provider Id",
                            "type": "string"
                        },
                        "source": {
                            "description": "How the server was registered: 'config' (static) or 'api' (dynamic)",
                            "examples": [
                                "config",
                                "api"
                            ],
                            "title": "Source",
                            "type": "string"
                        }
                    },
                    "required": [
                        "name",
                        "url",
                        "provider_id",
                        "source"
                    ],
                    "title": "MCPServerInfo",
                    "type": "object"
                },
                "MCPServerListResponse": {
                    "description": "Response listing all registered MCP servers.\n\nAttributes:\n    servers: All registered MCP servers (static and dynamic).",
                    "examples": [
                        {
                            "servers": [
                                {
                                    "name": "mcp-integration-tools",
                                    "provider_id": "model-context-protocol",
                                    "source": "config",
                                    "url": "http://host.docker.internal:7008/api/mcp-actions/v1"
                                },
                                {
                                    "name": "test-mcp-server",
                                    "provider_id": "model-context-protocol",
                                    "source": "api",
                                    "url": "http://host.docker.internal:8888/mcp"
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "servers": {
                            "description": "List of all registered MCP servers (static and dynamic)",
                            "items": {
                                "$ref": "`#/components/schemas/`MCPServerInfo"
                            },
                            "title": "Servers",
                            "type": "array"
                        }
                    },
                    "title": "MCPServerListResponse",
                    "type": "object"
                },
                "MCPServerRegistrationRequest": {
                    "additionalProperties": false,
                    "description": "Request model for dynamically registering an MCP server.\n\nAttributes:\n    name: Unique name for the MCP server.\n    url: URL of the MCP server endpoint.\n    provider_id: MCP provider identification (defaults to \"model-context-protocol\").\n    authorization_headers: Optional headers to send to the MCP server.\n    headers: Optional list of HTTP header names to forward from incoming requests.\n    timeout: Optional request timeout in seconds.",
                    "examples": [
                        {
                            "authorization_headers": {
                                "Authorization": "client"
                            },
                            "name": "mcp-integration-tools",
                            "url": "http://host.docker.internal:7008/api/mcp-actions/v1"
                        },
                        {
                            "authorization_headers": {
                                "Authorization": "kubernetes"
                            },
                            "name": "k8s-internal-service",
                            "url": "http://internal-mcp.default.svc.cluster.local:8080"
                        },
                        {
                            "authorization_headers": {
                                "Authorization": "oauth"
                            },
                            "name": "oauth-mcp-server",
                            "url": "https://mcp.example.com/api"
                        },
                        {
                            "headers": [
                                "x-rh-identity"
                            ],
                            "name": "test-mcp-server",
                            "provider_id": "model-context-protocol",
                            "timeout": 30,
                            "url": "http://host.docker.internal:8888/mcp"
                        }
                    ],
                    "properties": {
                        "name": {
                            "description": "Unique name for the MCP server",
                            "examples": [
                                "my-mcp-tools"
                            ],
                            "maxLength": 256,
                            "minLength": 1,
                            "title": "Name",
                            "type": "string"
                        },
                        "url": {
                            "description": "URL of the MCP server endpoint",
                            "examples": [
                                "http://host.docker.internal:7008/api/mcp-actions/v1"
                            ],
                            "title": "Url",
                            "type": "string"
                        },
                        "provider_id": {
                            "default": "model-context-protocol",
                            "description": "MCP provider identification",
                            "examples": [
                                "model-context-protocol"
                            ],
                            "title": "Provider Id",
                            "type": "string"
                        },
                        "authorization_headers": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Headers to send to the MCP server. Values must be one of the supported token resolution keywords: 'client' - forward the caller's token provided via MCP-HEADERS, 'kubernetes' - use the authenticated user's Kubernetes token, 'oauth' - use an OAuth token provided via MCP-HEADERS. File-path based secrets (used in static YAML config) are not supported for dynamically registered servers.",
                            "examples": [
                                {
                                    "Authorization": "client"
                                },
                                {
                                    "Authorization": "kubernetes"
                                },
                                {
                                    "Authorization": "oauth"
                                }
                            ],
                            "title": "Authorization Headers"
                        },
                        "headers": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "List of HTTP header names to forward from incoming requests",
                            "examples": [
                                [
                                    "x-rh-identity"
                                ]
                            ],
                            "title": "Headers"
                        },
                        "timeout": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Request timeout in seconds for the MCP server",
                            "examples": [
                                30
                            ],
                            "title": "Timeout"
                        }
                    },
                    "required": [
                        "name",
                        "url"
                    ],
                    "title": "MCPServerRegistrationRequest",
                    "type": "object"
                },
                "MCPServerRegistrationResponse": {
                    "description": "Response for a successful MCP server registration.\n\nAttributes:\n    name: Registered MCP server name.\n    url: Registered MCP server URL.\n    provider_id: MCP provider identification.\n    message: Status message.",
                    "examples": [
                        {
                            "message": "MCP server 'mcp-integration-tools' registered successfully",
                            "name": "mcp-integration-tools",
                            "provider_id": "model-context-protocol",
                            "url": "http://host.docker.internal:7008/api/mcp-actions/v1"
                        }
                    ],
                    "properties": {
                        "name": {
                            "description": "Registered MCP server name",
                            "title": "Name",
                            "type": "string"
                        },
                        "url": {
                            "description": "Registered MCP server URL",
                            "title": "Url",
                            "type": "string"
                        },
                        "provider_id": {
                            "description": "MCP provider identification",
                            "title": "Provider Id",
                            "type": "string"
                        },
                        "message": {
                            "description": "Status message",
                            "title": "Message",
                            "type": "string"
                        }
                    },
                    "required": [
                        "name",
                        "url",
                        "provider_id",
                        "message"
                    ],
                    "title": "MCPServerRegistrationResponse",
                    "type": "object"
                },
                "Message": {
                    "description": "Model representing a message in a conversation turn.\n\nAttributes:\n    content: The message content.\n    type: The type of message.\n    referenced_documents: Optional list of documents referenced in an assistant response.",
                    "properties": {
                        "content": {
                            "description": "The message content",
                            "examples": [
                                "Hello, how can I help you?"
                            ],
                            "title": "Content",
                            "type": "string"
                        },
                        "type": {
                            "description": "The type of message",
                            "enum": [
                                "user",
                                "assistant",
                                "system",
                                "developer"
                            ],
                            "examples": [
                                "user",
                                "assistant",
                                "system",
                                "developer"
                            ],
                            "title": "Type",
                            "type": "string"
                        },
                        "referenced_documents": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "List of documents referenced in the response (assistant messages only)",
                            "title": "Referenced Documents"
                        }
                    },
                    "required": [
                        "content",
                        "type"
                    ],
                    "title": "Message",
                    "type": "object"
                },
                "ModelContextProtocolServer": {
                    "additionalProperties": false,
                    "description": "Model context protocol server configuration.\n\nMCP (Model Context Protocol) servers provide tools and capabilities to the\nAI agents. These are configured by this structure. Only MCP servers\ndefined in the lightspeed-stack.yaml configuration are available to the\nagents. Tools configured in the llama-stack run.yaml are not accessible to\nlightspeed-core agents.\n\nUseful resources:\n\n- [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)\n- [MCP FAQs](https://modelcontextprotocol.io/faqs)\n- [Wikipedia article](https://en.wikipedia.org/wiki/Model_Context_Protocol)",
                    "properties": {
                        "name": {
                            "description": "MCP server name that must be unique",
                            "title": "MCP name",
                            "type": "string"
                        },
                        "provider_id": {
                            "default": "model-context-protocol",
                            "description": "MCP provider identification",
                            "title": "Provider ID",
                            "type": "string"
                        },
                        "url": {
                            "description": "URL of the MCP server",
                            "title": "MCP server URL",
                            "type": "string"
                        },
                        "authorization_headers": {
                            "additionalProperties": {
                                "type": "string"
                            },
                            "description": "Headers to send to the MCP server. The map contains the header name and the path to a file containing the header value (secret). There are 3 special cases: 1. Usage of the kubernetes token in the header. To specify this use a string 'kubernetes' instead of the file path. 2. Usage of the client-provided token in the header. To specify this use a string 'client' instead of the file path. 3. Usage of the oauth token in the header. To specify this use a string 'oauth' instead of the file path. ",
                            "title": "Authorization headers",
                            "type": "object"
                        },
                        "headers": {
                            "description": "List of HTTP header names to automatically forward from the incoming request to this MCP server. Headers listed here are extracted from the original client request and included when calling the MCP server. This is useful when infrastructure components (e.g. API gateways) inject headers that MCP servers need, such as x-rh-identity in HCC. Header matching is case-insensitive. These headers are additive with authorization_headers and MCP-HEADERS.",
                            "items": {
                                "type": "string"
                            },
                            "title": "Propagated headers",
                            "type": "array"
                        },
                        "require_approval": {
                            "anyOf": [
                                {
                                    "enum": [
                                        "always",
                                        "never"
                                    ],
                                    "type": "string"
                                },
                                {
                                    "$ref": "`#/components/schemas/`models__config__ApprovalFilter"
                                }
                            ],
                            "default": "never",
                            "description": "When to require human approval for tool invocations. 'always' requires approval for all tools, 'never' auto-approves, or use ApprovalFilter for granular control.",
                            "title": "Approval requirement"
                        },
                        "timeout": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Timeout in seconds for requests to the MCP server. If not specified, the default timeout from Llama Stack will be used. Note: This field is reserved for future use when Llama Stack adds timeout support.",
                            "title": "Request timeout"
                        }
                    },
                    "required": [
                        "name",
                        "url"
                    ],
                    "title": "ModelContextProtocolServer",
                    "type": "object"
                },
                "ModelFilter": {
                    "additionalProperties": false,
                    "description": "Model representing a query parameter to select models by its type.\n\nAttributes:\n    model_type: Required model type, such as 'llm', 'embeddings' etc.",
                    "properties": {
                        "model_type": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Optional filter to return only models matching this type",
                            "examples": [
                                "llm",
                                "embeddings"
                            ],
                            "title": "Model Type"
                        }
                    },
                    "title": "ModelFilter",
                    "type": "object"
                },
                "ModelsResponse": {
                    "description": "Model representing a response to models request.",
                    "examples": [
                        {
                            "models": [
                                {
                                    "api_model_type": "llm",
                                    "identifier": "openai/gpt-4-turbo",
                                    "metadata": {},
                                    "model_type": "llm",
                                    "provider_id": "openai",
                                    "provider_resource_id": "gpt-4-turbo",
                                    "type": "model"
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "models": {
                            "description": "List of models available",
                            "items": {
                                "additionalProperties": true,
                                "type": "object"
                            },
                            "title": "Models",
                            "type": "array"
                        }
                    },
                    "required": [
                        "models"
                    ],
                    "title": "ModelsResponse",
                    "type": "object"
                },
                "NotFoundResponse": {
                    "description": "404 Not Found - Resource does not exist.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "Conversation with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
                                "response": "Conversation not found"
                            },
                            "label": "conversation"
                        },
                        {
                            "detail": {
                                "cause": "Provider with ID openai does not exist",
                                "response": "Provider not found"
                            },
                            "label": "provider"
                        },
                        {
                            "detail": {
                                "cause": "Model with ID gpt-4o-mini does not exist",
                                "response": "Model not found"
                            },
                            "label": "model"
                        },
                        {
                            "detail": {
                                "cause": "Rag with ID vs_7b52a8cf-0fa3-489c-beab-27e061d102f3 does not exist",
                                "response": "Rag not found"
                            },
                            "label": "rag"
                        },
                        {
                            "detail": {
                                "cause": "Streaming Request with ID 123e4567-e89b-12d3-a456-426614174000 does not exist",
                                "response": "Streaming Request not found"
                            },
                            "label": "streaming request"
                        },
                        {
                            "detail": {
                                "cause": "Mcp Server with ID test-mcp-server does not exist",
                                "response": "Mcp Server not found"
                            },
                            "label": "mcp server"
                        },
                        {
                            "detail": {
                                "cause": "Vector Store with ID vs_abc123 does not exist",
                                "response": "Vector Store not found"
                            },
                            "label": "vector store"
                        },
                        {
                            "detail": {
                                "cause": "File with ID file_abc123 does not exist",
                                "response": "File not found"
                            },
                            "label": "file"
                        },
                        {
                            "detail": {
                                "cause": "Prompt with ID pmpt_0123456789abcdef0123456789abcdef01234567 does not exist",
                                "response": "Prompt not found"
                            },
                            "label": "prompt"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "NotFoundResponse",
                    "type": "object"
                },
                "OkpConfiguration": {
                    "additionalProperties": false,
                    "description": "OKP (Offline Knowledge Portal) provider configuration.\n\nControls provider-specific behaviour for the OKP vector store.\nOnly relevant when ``\"okp\"`` is listed in ``rag.inline`` or ``rag.tool``.",
                    "properties": {
                        "rhokp_url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Base URL for the OKP server (http or https). Set to `${env.RH_SERVER_OKP}` in YAML to use the environment variable. When unset, the default from constants is used.",
                            "title": "OKP base URL"
                        },
                        "offline": {
                            "default": true,
                            "description": "When True, use parent_id for OKP chunk source URLs. When False, use reference_url for chunk source URLs.",
                            "title": "OKP offline mode",
                            "type": "boolean"
                        },
                        "chunk_filter_query": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Additional OKP filter query applied to every OKP search request. Use Solr boolean syntax, e.g. 'product:ansible AND product:*openshift*'.",
                            "title": "OKP chunk filter query"
                        }
                    },
                    "title": "OkpConfiguration",
                    "type": "object"
                },
                "OpenAIResponseAnnotationCitation": {
                    "description": "URL citation annotation for referencing external web resources.\n\n:param type: Annotation type identifier, always \"url_citation\"\n:param end_index: End position of the citation span in the content\n:param start_index: Start position of the citation span in the content\n:param title: Title of the referenced web resource\n:param url: URL of the referenced web resource",
                    "properties": {
                        "type": {
                            "const": "url_citation",
                            "default": "url_citation",
                            "title": "Type",
                            "type": "string"
                        },
                        "end_index": {
                            "title": "End Index",
                            "type": "integer"
                        },
                        "start_index": {
                            "title": "Start Index",
                            "type": "integer"
                        },
                        "title": {
                            "title": "Title",
                            "type": "string"
                        },
                        "url": {
                            "title": "Url",
                            "type": "string"
                        }
                    },
                    "required": [
                        "end_index",
                        "start_index",
                        "title",
                        "url"
                    ],
                    "title": "OpenAIResponseAnnotationCitation",
                    "type": "object"
                },
                "OpenAIResponseAnnotationContainerFileCitation": {
                    "properties": {
                        "type": {
                            "const": "container_file_citation",
                            "default": "container_file_citation",
                            "title": "Type",
                            "type": "string"
                        },
                        "container_id": {
                            "title": "Container Id",
                            "type": "string"
                        },
                        "end_index": {
                            "title": "End Index",
                            "type": "integer"
                        },
                        "file_id": {
                            "title": "File Id",
                            "type": "string"
                        },
                        "filename": {
                            "title": "Filename",
                            "type": "string"
                        },
                        "start_index": {
                            "title": "Start Index",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "container_id",
                        "end_index",
                        "file_id",
                        "filename",
                        "start_index"
                    ],
                    "title": "OpenAIResponseAnnotationContainerFileCitation",
                    "type": "object"
                },
                "OpenAIResponseAnnotationFileCitation": {
                    "description": "File citation annotation for referencing specific files in response content.\n\n:param type: Annotation type identifier, always \"file_citation\"\n:param file_id: Unique identifier of the referenced file\n:param filename: Name of the referenced file\n:param index: Position index of the citation within the content",
                    "properties": {
                        "type": {
                            "const": "file_citation",
                            "default": "file_citation",
                            "title": "Type",
                            "type": "string"
                        },
                        "file_id": {
                            "title": "File Id",
                            "type": "string"
                        },
                        "filename": {
                            "title": "Filename",
                            "type": "string"
                        },
                        "index": {
                            "title": "Index",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "file_id",
                        "filename",
                        "index"
                    ],
                    "title": "OpenAIResponseAnnotationFileCitation",
                    "type": "object"
                },
                "OpenAIResponseAnnotationFilePath": {
                    "properties": {
                        "type": {
                            "const": "file_path",
                            "default": "file_path",
                            "title": "Type",
                            "type": "string"
                        },
                        "file_id": {
                            "title": "File Id",
                            "type": "string"
                        },
                        "index": {
                            "title": "Index",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "file_id",
                        "index"
                    ],
                    "title": "OpenAIResponseAnnotationFilePath",
                    "type": "object"
                },
                "OpenAIResponseContentPartRefusal": {
                    "description": "Refusal content within a streamed response part.\n\n:param type: Content part type identifier, always \"refusal\"\n:param refusal: Refusal text supplied by the model",
                    "properties": {
                        "type": {
                            "const": "refusal",
                            "default": "refusal",
                            "title": "Type",
                            "type": "string"
                        },
                        "refusal": {
                            "title": "Refusal",
                            "type": "string"
                        }
                    },
                    "required": [
                        "refusal"
                    ],
                    "title": "OpenAIResponseContentPartRefusal",
                    "type": "object"
                },
                "OpenAIResponseError": {
                    "description": "Error details for failed OpenAI response requests.\n\n:param code: Error code identifying the type of failure\n:param message: Human-readable error message describing the failure",
                    "properties": {
                        "code": {
                            "title": "Code",
                            "type": "string"
                        },
                        "message": {
                            "title": "Message",
                            "type": "string"
                        }
                    },
                    "required": [
                        "code",
                        "message"
                    ],
                    "title": "OpenAIResponseError",
                    "type": "object"
                },
                "OpenAIResponseInputFunctionToolCallOutput": {
                    "description": "This represents the output of a function call that gets passed back to the model.",
                    "properties": {
                        "call_id": {
                            "title": "Call Id",
                            "type": "string"
                        },
                        "output": {
                            "anyOf": [
                                {
                                    "type": "string"
                                },
                                {
                                    "items": {
                                        "discriminator": {
                                            "mapping": {
                                                "input_file": "`#/components/schemas/`OpenAIResponseInputMessageContentFile",
                                                "input_image": "`#/components/schemas/`OpenAIResponseInputMessageContentImage",
                                                "input_text": "`#/components/schemas/`OpenAIResponseInputMessageContentText"
                                            },
                                            "propertyName": "type"
                                        },
                                        "oneOf": [
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseInputMessageContentText"
                                            },
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseInputMessageContentImage"
                                            },
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseInputMessageContentFile"
                                            }
                                        ]
                                    },
                                    "type": "array"
                                }
                            ],
                            "title": "Output"
                        },
                        "type": {
                            "const": "function_call_output",
                            "default": "function_call_output",
                            "title": "Type",
                            "type": "string"
                        },
                        "id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Id"
                        },
                        "status": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Status"
                        }
                    },
                    "required": [
                        "call_id",
                        "output"
                    ],
                    "title": "OpenAIResponseInputFunctionToolCallOutput",
                    "type": "object"
                },
                "OpenAIResponseInputMessageContentFile": {
                    "description": "File content for input messages in OpenAI response format.\n\n:param type: The type of the input item. Always `input_file`.\n:param file_data: The data of the file to be sent to the model.\n:param file_id: (Optional) The ID of the file to be sent to the model.\n:param file_url: The URL of the file to be sent to the model.\n:param filename: The name of the file to be sent to the model.",
                    "properties": {
                        "type": {
                            "const": "input_file",
                            "default": "input_file",
                            "title": "Type",
                            "type": "string"
                        },
                        "file_data": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "File Data"
                        },
                        "file_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "File Id"
                        },
                        "file_url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "File Url"
                        },
                        "filename": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Filename"
                        }
                    },
                    "title": "OpenAIResponseInputMessageContentFile",
                    "type": "object"
                },
                "OpenAIResponseInputMessageContentImage": {
                    "description": "Image content for input messages in OpenAI response format.\n\n:param detail: Level of detail for image processing, can be \"low\", \"high\", or \"auto\"\n:param type: Content type identifier, always \"input_image\"\n:param file_id: (Optional) The ID of the file to be sent to the model.\n:param image_url: (Optional) URL of the image content",
                    "properties": {
                        "detail": {
                            "anyOf": [
                                {
                                    "const": "low",
                                    "type": "string"
                                },
                                {
                                    "const": "high",
                                    "type": "string"
                                },
                                {
                                    "const": "auto",
                                    "type": "string"
                                }
                            ],
                            "default": "auto",
                            "title": "Detail"
                        },
                        "type": {
                            "const": "input_image",
                            "default": "input_image",
                            "title": "Type",
                            "type": "string"
                        },
                        "file_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "File Id"
                        },
                        "image_url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Image Url"
                        }
                    },
                    "title": "OpenAIResponseInputMessageContentImage",
                    "type": "object"
                },
                "OpenAIResponseInputMessageContentText": {
                    "description": "Text content for input messages in OpenAI response format.\n\n:param text: The text content of the input message\n:param type: Content type identifier, always \"input_text\"",
                    "properties": {
                        "text": {
                            "title": "Text",
                            "type": "string"
                        },
                        "type": {
                            "const": "input_text",
                            "default": "input_text",
                            "title": "Type",
                            "type": "string"
                        }
                    },
                    "required": [
                        "text"
                    ],
                    "title": "OpenAIResponseInputMessageContentText",
                    "type": "object"
                },
                "OpenAIResponseInputToolChoiceAllowedTools": {
                    "description": "Constrains the tools available to the model to a pre-defined set.\n\n:param mode: Constrains the tools available to the model to a pre-defined set\n:param tools: A list of tool definitions that the model should be allowed to call\n:param type: Tool choice type identifier, always \"allowed_tools\"",
                    "properties": {
                        "mode": {
                            "default": "auto",
                            "enum": [
                                "auto",
                                "required"
                            ],
                            "title": "Mode",
                            "type": "string"
                        },
                        "tools": {
                            "items": {
                                "additionalProperties": {
                                    "type": "string"
                                },
                                "type": "object"
                            },
                            "title": "Tools",
                            "type": "array"
                        },
                        "type": {
                            "const": "allowed_tools",
                            "default": "allowed_tools",
                            "title": "Type",
                            "type": "string"
                        }
                    },
                    "required": [
                        "tools"
                    ],
                    "title": "OpenAIResponseInputToolChoiceAllowedTools",
                    "type": "object"
                },
                "OpenAIResponseInputToolChoiceCustomTool": {
                    "description": "Forces the model to call a custom tool.\n\n:param type: Tool choice type identifier, always \"custom\"\n:param name: The name of the custom tool to call.",
                    "properties": {
                        "type": {
                            "const": "custom",
                            "default": "custom",
                            "title": "Type",
                            "type": "string"
                        },
                        "name": {
                            "title": "Name",
                            "type": "string"
                        }
                    },
                    "required": [
                        "name"
                    ],
                    "title": "OpenAIResponseInputToolChoiceCustomTool",
                    "type": "object"
                },
                "OpenAIResponseInputToolChoiceFileSearch": {
                    "description": "Indicates that the model should use file search to generate a response.\n\n:param type: Tool choice type identifier, always \"file_search\"",
                    "properties": {
                        "type": {
                            "const": "file_search",
                            "default": "file_search",
                            "title": "Type",
                            "type": "string"
                        }
                    },
                    "title": "OpenAIResponseInputToolChoiceFileSearch",
                    "type": "object"
                },
                "OpenAIResponseInputToolChoiceFunctionTool": {
                    "description": "Forces the model to call a specific function.\n\n:param name: The name of the function to call\n:param type: Tool choice type identifier, always \"function\"",
                    "properties": {
                        "name": {
                            "title": "Name",
                            "type": "string"
                        },
                        "type": {
                            "const": "function",
                            "default": "function",
                            "title": "Type",
                            "type": "string"
                        }
                    },
                    "required": [
                        "name"
                    ],
                    "title": "OpenAIResponseInputToolChoiceFunctionTool",
                    "type": "object"
                },
                "OpenAIResponseInputToolChoiceMCPTool": {
                    "description": "Forces the model to call a specific tool on a remote MCP server\n\n:param server_label: The label of the MCP server to use.\n:param type: Tool choice type identifier, always \"mcp\"\n:param name: (Optional) The name of the tool to call on the server.",
                    "properties": {
                        "server_label": {
                            "title": "Server Label",
                            "type": "string"
                        },
                        "type": {
                            "const": "mcp",
                            "default": "mcp",
                            "title": "Type",
                            "type": "string"
                        },
                        "name": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Name"
                        }
                    },
                    "required": [
                        "server_label"
                    ],
                    "title": "OpenAIResponseInputToolChoiceMCPTool",
                    "type": "object"
                },
                "OpenAIResponseInputToolChoiceMode": {
                    "enum": [
                        "auto",
                        "required",
                        "none"
                    ],
                    "title": "OpenAIResponseInputToolChoiceMode",
                    "type": "string"
                },
                "OpenAIResponseInputToolChoiceWebSearch": {
                    "description": "Indicates that the model should use web search to generate a response\n\n:param type: Web search tool type variant to use",
                    "properties": {
                        "type": {
                            "anyOf": [
                                {
                                    "const": "web_search",
                                    "type": "string"
                                },
                                {
                                    "const": "web_search_preview",
                                    "type": "string"
                                },
                                {
                                    "const": "web_search_preview_2025_03_11",
                                    "type": "string"
                                },
                                {
                                    "const": "web_search_2025_08_26",
                                    "type": "string"
                                }
                            ],
                            "default": "web_search",
                            "title": "Type"
                        }
                    },
                    "title": "OpenAIResponseInputToolChoiceWebSearch",
                    "type": "object"
                },
                "OpenAIResponseInputToolFileSearch": {
                    "description": "File search tool configuration for OpenAI response inputs.\n\n:param type: Tool type identifier, always \"file_search\"\n:param vector_store_ids: List of vector store identifiers to search within\n:param filters: (Optional) Additional filters to apply to the search\n:param max_num_results: (Optional) Maximum number of search results to return (1-50)\n:param ranking_options: (Optional) Options for ranking and scoring search results",
                    "properties": {
                        "type": {
                            "const": "file_search",
                            "default": "file_search",
                            "title": "Type",
                            "type": "string"
                        },
                        "vector_store_ids": {
                            "items": {
                                "type": "string"
                            },
                            "title": "Vector Store Ids",
                            "type": "array"
                        },
                        "filters": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "title": "Filters"
                        },
                        "max_num_results": {
                            "type": "integer",
                            "nullable": true,
                            "default": 10,
                            "title": "Max Num Results"
                        },
                        "ranking_options": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SearchRankingOptions"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        }
                    },
                    "required": [
                        "vector_store_ids"
                    ],
                    "title": "OpenAIResponseInputToolFileSearch",
                    "type": "object"
                },
                "OpenAIResponseInputToolFunction": {
                    "description": "Function tool configuration for OpenAI response inputs.\n\n:param type: Tool type identifier, always \"function\"\n:param name: Name of the function that can be called\n:param description: (Optional) Description of what the function does\n:param parameters: (Optional) JSON schema defining the function's parameters\n:param strict: (Optional) Whether to enforce strict parameter validation",
                    "properties": {
                        "type": {
                            "const": "function",
                            "default": "function",
                            "title": "Type",
                            "type": "string"
                        },
                        "name": {
                            "title": "Name",
                            "type": "string"
                        },
                        "description": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Description"
                        },
                        "parameters": {
                            "type": "object",
                            "nullable": true,
                            "title": "Parameters"
                        },
                        "strict": {
                            "type": "boolean",
                            "nullable": true,
                            "default": null,
                            "title": "Strict"
                        }
                    },
                    "required": [
                        "name",
                        "parameters"
                    ],
                    "title": "OpenAIResponseInputToolFunction",
                    "type": "object"
                },
                "OpenAIResponseInputToolWebSearch": {
                    "description": "Web search tool configuration for OpenAI response inputs.\n\n:param type: Web search tool type variant to use\n:param search_context_size: (Optional) Size of search context, must be \"low\", \"medium\", or \"high\"",
                    "properties": {
                        "type": {
                            "anyOf": [
                                {
                                    "const": "web_search",
                                    "type": "string"
                                },
                                {
                                    "const": "web_search_preview",
                                    "type": "string"
                                },
                                {
                                    "const": "web_search_preview_2025_03_11",
                                    "type": "string"
                                },
                                {
                                    "const": "web_search_2025_08_26",
                                    "type": "string"
                                }
                            ],
                            "default": "web_search",
                            "title": "Type"
                        },
                        "search_context_size": {
                            "type": "string",
                            "nullable": true,
                            "default": "medium",
                            "title": "Search Context Size"
                        }
                    },
                    "title": "OpenAIResponseInputToolWebSearch",
                    "type": "object"
                },
                "OpenAIResponseMCPApprovalRequest": {
                    "description": "A request for human approval of a tool invocation.",
                    "properties": {
                        "arguments": {
                            "title": "Arguments",
                            "type": "string"
                        },
                        "id": {
                            "title": "Id",
                            "type": "string"
                        },
                        "name": {
                            "title": "Name",
                            "type": "string"
                        },
                        "server_label": {
                            "title": "Server Label",
                            "type": "string"
                        },
                        "type": {
                            "const": "mcp_approval_request",
                            "default": "mcp_approval_request",
                            "title": "Type",
                            "type": "string"
                        }
                    },
                    "required": [
                        "arguments",
                        "id",
                        "name",
                        "server_label"
                    ],
                    "title": "OpenAIResponseMCPApprovalRequest",
                    "type": "object"
                },
                "OpenAIResponseMCPApprovalResponse": {
                    "description": "A response to an MCP approval request.",
                    "properties": {
                        "approval_request_id": {
                            "title": "Approval Request Id",
                            "type": "string"
                        },
                        "approve": {
                            "title": "Approve",
                            "type": "boolean"
                        },
                        "type": {
                            "const": "mcp_approval_response",
                            "default": "mcp_approval_response",
                            "title": "Type",
                            "type": "string"
                        },
                        "id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Id"
                        },
                        "reason": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Reason"
                        }
                    },
                    "required": [
                        "approval_request_id",
                        "approve"
                    ],
                    "title": "OpenAIResponseMCPApprovalResponse",
                    "type": "object"
                },
                "OpenAIResponseMessage": {
                    "description": "Corresponds to the various Message types in the Responses API.\nThey are all under one type because the Responses API gives them all\nthe same \"type\" value, and there is no way to tell them apart in certain\nscenarios.",
                    "properties": {
                        "content": {
                            "anyOf": [
                                {
                                    "type": "string"
                                },
                                {
                                    "items": {
                                        "discriminator": {
                                            "mapping": {
                                                "input_file": "`#/components/schemas/`OpenAIResponseInputMessageContentFile",
                                                "input_image": "`#/components/schemas/`OpenAIResponseInputMessageContentImage",
                                                "input_text": "`#/components/schemas/`OpenAIResponseInputMessageContentText"
                                            },
                                            "propertyName": "type"
                                        },
                                        "oneOf": [
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseInputMessageContentText"
                                            },
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseInputMessageContentImage"
                                            },
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseInputMessageContentFile"
                                            }
                                        ]
                                    },
                                    "type": "array"
                                },
                                {
                                    "items": {
                                        "discriminator": {
                                            "mapping": {
                                                "output_text": "`#/components/schemas/`OpenAIResponseOutputMessageContentOutputText",
                                                "refusal": "`#/components/schemas/`OpenAIResponseContentPartRefusal"
                                            },
                                            "propertyName": "type"
                                        },
                                        "oneOf": [
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageContentOutputText"
                                            },
                                            {
                                                "$ref": "`#/components/schemas/`OpenAIResponseContentPartRefusal"
                                            }
                                        ]
                                    },
                                    "type": "array"
                                }
                            ],
                            "title": "Content"
                        },
                        "role": {
                            "anyOf": [
                                {
                                    "const": "system",
                                    "type": "string"
                                },
                                {
                                    "const": "developer",
                                    "type": "string"
                                },
                                {
                                    "const": "user",
                                    "type": "string"
                                },
                                {
                                    "const": "assistant",
                                    "type": "string"
                                }
                            ],
                            "title": "Role"
                        },
                        "type": {
                            "const": "message",
                            "default": "message",
                            "title": "Type",
                            "type": "string"
                        },
                        "id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Id"
                        },
                        "status": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Status"
                        }
                    },
                    "required": [
                        "content",
                        "role"
                    ],
                    "title": "OpenAIResponseMessage",
                    "type": "object"
                },
                "OpenAIResponseOutputMessageContentOutputText": {
                    "properties": {
                        "text": {
                            "title": "Text",
                            "type": "string"
                        },
                        "type": {
                            "const": "output_text",
                            "default": "output_text",
                            "title": "Type",
                            "type": "string"
                        },
                        "annotations": {
                            "items": {
                                "discriminator": {
                                    "mapping": {
                                        "container_file_citation": "`#/components/schemas/`OpenAIResponseAnnotationContainerFileCitation",
                                        "file_citation": "`#/components/schemas/`OpenAIResponseAnnotationFileCitation",
                                        "file_path": "`#/components/schemas/`OpenAIResponseAnnotationFilePath",
                                        "url_citation": "`#/components/schemas/`OpenAIResponseAnnotationCitation"
                                    },
                                    "propertyName": "type"
                                },
                                "oneOf": [
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseAnnotationFileCitation"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseAnnotationCitation"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseAnnotationContainerFileCitation"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseAnnotationFilePath"
                                    }
                                ]
                            },
                            "title": "Annotations",
                            "type": "array"
                        },
                        "logprobs": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Logprobs"
                        }
                    },
                    "required": [
                        "text"
                    ],
                    "title": "OpenAIResponseOutputMessageContentOutputText",
                    "type": "object"
                },
                "OpenAIResponseOutputMessageFileSearchToolCall": {
                    "description": "File search tool call output message for OpenAI responses.\n\n:param id: Unique identifier for this tool call\n:param queries: List of search queries executed\n:param status: Current status of the file search operation\n:param type: Tool call type identifier, always \"file_search_call\"\n:param results: (Optional) Search results returned by the file search operation",
                    "properties": {
                        "id": {
                            "title": "Id",
                            "type": "string"
                        },
                        "queries": {
                            "items": {
                                "type": "string"
                            },
                            "title": "Queries",
                            "type": "array"
                        },
                        "status": {
                            "title": "Status",
                            "type": "string"
                        },
                        "type": {
                            "const": "file_search_call",
                            "default": "file_search_call",
                            "title": "Type",
                            "type": "string"
                        },
                        "results": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Results"
                        }
                    },
                    "required": [
                        "id",
                        "queries",
                        "status"
                    ],
                    "title": "OpenAIResponseOutputMessageFileSearchToolCall",
                    "type": "object"
                },
                "OpenAIResponseOutputMessageFileSearchToolCallResults": {
                    "description": "Search results returned by the file search operation.\n\n:param attributes: (Optional) Key-value attributes associated with the file\n:param file_id: Unique identifier of the file containing the result\n:param filename: Name of the file containing the result\n:param score: Relevance score for this search result (between 0 and 1)\n:param text: Text content of the search result",
                    "properties": {
                        "attributes": {
                            "additionalProperties": true,
                            "title": "Attributes",
                            "type": "object"
                        },
                        "file_id": {
                            "title": "File Id",
                            "type": "string"
                        },
                        "filename": {
                            "title": "Filename",
                            "type": "string"
                        },
                        "score": {
                            "title": "Score",
                            "type": "number"
                        },
                        "text": {
                            "title": "Text",
                            "type": "string"
                        }
                    },
                    "required": [
                        "attributes",
                        "file_id",
                        "filename",
                        "score",
                        "text"
                    ],
                    "title": "OpenAIResponseOutputMessageFileSearchToolCallResults",
                    "type": "object"
                },
                "OpenAIResponseOutputMessageFunctionToolCall": {
                    "description": "Function tool call output message for OpenAI responses.\n\n:param call_id: Unique identifier for the function call\n:param name: Name of the function being called\n:param arguments: JSON string containing the function arguments\n:param type: Tool call type identifier, always \"function_call\"\n:param id: (Optional) Additional identifier for the tool call\n:param status: (Optional) Current status of the function call execution",
                    "properties": {
                        "call_id": {
                            "title": "Call Id",
                            "type": "string"
                        },
                        "name": {
                            "title": "Name",
                            "type": "string"
                        },
                        "arguments": {
                            "title": "Arguments",
                            "type": "string"
                        },
                        "type": {
                            "const": "function_call",
                            "default": "function_call",
                            "title": "Type",
                            "type": "string"
                        },
                        "id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Id"
                        },
                        "status": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Status"
                        }
                    },
                    "required": [
                        "call_id",
                        "name",
                        "arguments"
                    ],
                    "title": "OpenAIResponseOutputMessageFunctionToolCall",
                    "type": "object"
                },
                "OpenAIResponseOutputMessageMCPCall": {
                    "description": "Model Context Protocol (MCP) call output message for OpenAI responses.\n\n:param id: Unique identifier for this MCP call\n:param type: Tool call type identifier, always \"mcp_call\"\n:param arguments: JSON string containing the MCP call arguments\n:param name: Name of the MCP method being called\n:param server_label: Label identifying the MCP server handling the call\n:param error: (Optional) Error message if the MCP call failed\n:param output: (Optional) Output result from the successful MCP call",
                    "properties": {
                        "id": {
                            "title": "Id",
                            "type": "string"
                        },
                        "type": {
                            "const": "mcp_call",
                            "default": "mcp_call",
                            "title": "Type",
                            "type": "string"
                        },
                        "arguments": {
                            "title": "Arguments",
                            "type": "string"
                        },
                        "name": {
                            "title": "Name",
                            "type": "string"
                        },
                        "server_label": {
                            "title": "Server Label",
                            "type": "string"
                        },
                        "error": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Error"
                        },
                        "output": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Output"
                        }
                    },
                    "required": [
                        "id",
                        "arguments",
                        "name",
                        "server_label"
                    ],
                    "title": "OpenAIResponseOutputMessageMCPCall",
                    "type": "object"
                },
                "OpenAIResponseOutputMessageMCPListTools": {
                    "description": "MCP list tools output message containing available tools from an MCP server.\n\n:param id: Unique identifier for this MCP list tools operation\n:param type: Tool call type identifier, always \"mcp_list_tools\"\n:param server_label: Label identifying the MCP server providing the tools\n:param tools: List of available tools provided by the MCP server",
                    "properties": {
                        "id": {
                            "title": "Id",
                            "type": "string"
                        },
                        "type": {
                            "const": "mcp_list_tools",
                            "default": "mcp_list_tools",
                            "title": "Type",
                            "type": "string"
                        },
                        "server_label": {
                            "title": "Server Label",
                            "type": "string"
                        },
                        "tools": {
                            "items": {
                                "$ref": "`#/components/schemas/`MCPListToolsTool"
                            },
                            "title": "Tools",
                            "type": "array"
                        }
                    },
                    "required": [
                        "id",
                        "server_label",
                        "tools"
                    ],
                    "title": "OpenAIResponseOutputMessageMCPListTools",
                    "type": "object"
                },
                "OpenAIResponseOutputMessageWebSearchToolCall": {
                    "description": "Web search tool call output message for OpenAI responses.\n\n:param id: Unique identifier for this tool call\n:param status: Current status of the web search operation\n:param type: Tool call type identifier, always \"web_search_call\"",
                    "properties": {
                        "id": {
                            "title": "Id",
                            "type": "string"
                        },
                        "status": {
                            "title": "Status",
                            "type": "string"
                        },
                        "type": {
                            "const": "web_search_call",
                            "default": "web_search_call",
                            "title": "Type",
                            "type": "string"
                        }
                    },
                    "required": [
                        "id",
                        "status"
                    ],
                    "title": "OpenAIResponseOutputMessageWebSearchToolCall",
                    "type": "object"
                },
                "OpenAIResponsePrompt": {
                    "description": "OpenAI compatible Prompt object that is used in OpenAI responses.\n\n:param id: Unique identifier of the prompt template\n:param variables: Dictionary of variable names to OpenAIResponseInputMessageContent structure for template substitution. The substitution values can either be strings, or other Response input types\nlike images or files.\n:param version: Version number of the prompt to use (defaults to latest if not specified)",
                    "properties": {
                        "id": {
                            "title": "Id",
                            "type": "string"
                        },
                        "variables": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "title": "Variables"
                        },
                        "version": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Version"
                        }
                    },
                    "required": [
                        "id"
                    ],
                    "title": "OpenAIResponsePrompt",
                    "type": "object"
                },
                "OpenAIResponseReasoning": {
                    "description": "Configuration for reasoning effort in OpenAI responses.\n\nControls how much reasoning the model performs before generating a response.\n\n:param effort: The effort level for reasoning. \"low\" favors speed and economical token usage,\n               \"high\" favors more complete reasoning, \"medium\" is a balance between the two.",
                    "properties": {
                        "effort": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Effort"
                        }
                    },
                    "title": "OpenAIResponseReasoning",
                    "type": "object"
                },
                "OpenAIResponseText": {
                    "description": "Text response configuration for OpenAI responses.\n\n:param format: (Optional) Text format configuration specifying output format requirements",
                    "properties": {
                        "format": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseTextFormat"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        }
                    },
                    "title": "OpenAIResponseText",
                    "type": "object"
                },
                "OpenAIResponseTextFormat": {
                    "description": "Configuration for Responses API text format.\n\n:param type: Must be \"text\", \"json_schema\", or \"json_object\" to identify the format type\n:param name: The name of the response format. Only used for json_schema.\n:param schema: The JSON schema the response should conform to. In a Python SDK, this is often a `pydantic` model. Only used for json_schema.\n:param description: (Optional) A description of the response format. Only used for json_schema.\n:param strict: (Optional) Whether to strictly enforce the JSON schema. If true, the response must match the schema exactly. Only used for json_schema.",
                    "properties": {
                        "type": {
                            "anyOf": [
                                {
                                    "const": "text",
                                    "type": "string"
                                },
                                {
                                    "const": "json_schema",
                                    "type": "string"
                                },
                                {
                                    "const": "json_object",
                                    "type": "string"
                                }
                            ],
                            "title": "Type"
                        },
                        "name": {
                            "type": "string",
                            "nullable": true,
                            "title": "Name"
                        },
                        "schema": {
                            "type": "object",
                            "nullable": true,
                            "title": "Schema"
                        },
                        "description": {
                            "type": "string",
                            "nullable": true,
                            "title": "Description"
                        },
                        "strict": {
                            "type": "boolean",
                            "nullable": true,
                            "title": "Strict"
                        }
                    },
                    "title": "OpenAIResponseTextFormat",
                    "type": "object"
                },
                "OpenAIResponseToolMCP": {
                    "description": "Model Context Protocol (MCP) tool configuration for OpenAI response object.\n\n:param type: Tool type identifier, always \"mcp\"\n:param server_label: Label to identify this MCP server\n:param allowed_tools: (Optional) Restriction on which tools can be used from this server",
                    "properties": {
                        "type": {
                            "const": "mcp",
                            "default": "mcp",
                            "title": "Type",
                            "type": "string"
                        },
                        "server_label": {
                            "title": "Server Label",
                            "type": "string"
                        },
                        "allowed_tools": {
                            "anyOf": [
                                {
                                    "items": {
                                        "type": "string"
                                    },
                                    "type": "array"
                                },
                                {
                                    "$ref": "`#/components/schemas/`AllowedToolsFilter"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "title": "Allowed Tools"
                        }
                    },
                    "required": [
                        "server_label"
                    ],
                    "title": "OpenAIResponseToolMCP",
                    "type": "object"
                },
                "OpenAIResponseUsage": {
                    "description": "Usage information for OpenAI response.\n\n:param input_tokens: Number of tokens in the input\n:param output_tokens: Number of tokens in the output\n:param total_tokens: Total tokens used (input + output)\n:param input_tokens_details: Detailed breakdown of input token usage\n:param output_tokens_details: Detailed breakdown of output token usage",
                    "properties": {
                        "input_tokens": {
                            "title": "Input Tokens",
                            "type": "integer"
                        },
                        "output_tokens": {
                            "title": "Output Tokens",
                            "type": "integer"
                        },
                        "total_tokens": {
                            "title": "Total Tokens",
                            "type": "integer"
                        },
                        "input_tokens_details": {
                            "$ref": "`#/components/schemas/`OpenAIResponseUsageInputTokensDetails"
                        },
                        "output_tokens_details": {
                            "$ref": "`#/components/schemas/`OpenAIResponseUsageOutputTokensDetails"
                        }
                    },
                    "required": [
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                        "input_tokens_details",
                        "output_tokens_details"
                    ],
                    "title": "OpenAIResponseUsage",
                    "type": "object"
                },
                "OpenAIResponseUsageInputTokensDetails": {
                    "description": "Token details for input tokens in OpenAI response usage.\n\n:param cached_tokens: Number of tokens retrieved from cache",
                    "properties": {
                        "cached_tokens": {
                            "title": "Cached Tokens",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "cached_tokens"
                    ],
                    "title": "OpenAIResponseUsageInputTokensDetails",
                    "type": "object"
                },
                "OpenAIResponseUsageOutputTokensDetails": {
                    "description": "Token details for output tokens in OpenAI response usage.\n\n:param reasoning_tokens: Number of tokens used for reasoning (o1/o3 models)",
                    "properties": {
                        "reasoning_tokens": {
                            "title": "Reasoning Tokens",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "reasoning_tokens"
                    ],
                    "title": "OpenAIResponseUsageOutputTokensDetails",
                    "type": "object"
                },
                "OpenAITokenLogProb": {
                    "description": "The log probability for a token from an OpenAI-compatible chat completion response.",
                    "properties": {
                        "token": {
                            "description": "The token.",
                            "title": "Token",
                            "type": "string"
                        },
                        "bytes": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "The bytes for the token.",
                            "title": "Bytes"
                        },
                        "logprob": {
                            "description": "The log probability of the token.",
                            "title": "Logprob",
                            "type": "number"
                        },
                        "top_logprobs": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "The top log probabilities for the token.",
                            "title": "Top Logprobs"
                        }
                    },
                    "required": [
                        "token",
                        "logprob"
                    ],
                    "title": "OpenAITokenLogProb",
                    "type": "object"
                },
                "OpenAITopLogProb": {
                    "description": "The top log probability for a token from an OpenAI-compatible chat completion response.",
                    "properties": {
                        "token": {
                            "description": "The token.",
                            "title": "Token",
                            "type": "string"
                        },
                        "bytes": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "The bytes for the token.",
                            "title": "Bytes"
                        },
                        "logprob": {
                            "description": "The log probability of the token.",
                            "title": "Logprob",
                            "type": "number"
                        }
                    },
                    "required": [
                        "token",
                        "logprob"
                    ],
                    "title": "OpenAITopLogProb",
                    "type": "object"
                },
                "PostgreSQLDatabaseConfiguration": {
                    "additionalProperties": false,
                    "description": "PostgreSQL database configuration.\n\nPostgreSQL database is used by Lightspeed Core Stack service for storing\ninformation about conversation IDs. It can also be leveraged to store\nconversation history and information about quota usage.\n\nUseful resources:\n\n- [Psycopg: connection classes](https://www.psycopg.org/psycopg3/docs/api/connections.html)\n- [PostgreSQL connection strings](https://www.connectionstrings.com/postgresql/)\n- [How to Use PostgreSQL in Python](https://www.freecodecamp.org/news/postgresql-in-python/)",
                    "properties": {
                        "host": {
                            "default": "localhost",
                            "description": "Database server host or socket directory",
                            "title": "Hostname",
                            "type": "string"
                        },
                        "port": {
                            "default": 5432,
                            "description": "Database server port",
                            "minimum": 0,
                            "title": "Port",
                            "type": "integer"
                        },
                        "db": {
                            "description": "Database name to connect to",
                            "title": "Database name",
                            "type": "string"
                        },
                        "user": {
                            "description": "Database user name used to authenticate",
                            "title": "User name",
                            "type": "string"
                        },
                        "password": {
                            "description": "Password used to authenticate",
                            "format": "password",
                            "title": "Password",
                            "type": "string",
                            "writeOnly": true
                        },
                        "namespace": {
                            "type": "string",
                            "nullable": true,
                            "default": "public",
                            "description": "Database namespace",
                            "title": "Name space"
                        },
                        "ssl_mode": {
                            "default": "prefer",
                            "description": "SSL mode",
                            "enum": [
                                "disable",
                                "allow",
                                "prefer",
                                "require",
                                "verify-ca",
                                "verify-full"
                            ],
                            "title": "SSL mode",
                            "type": "string"
                        },
                        "gss_encmode": {
                            "default": "prefer",
                            "description": "This option determines whether or with what priority a secure GSS TCP/IP connection will be negotiated with the server.",
                            "enum": [
                                "disable",
                                "prefer",
                                "require"
                            ],
                            "title": "GSS encmode",
                            "type": "string"
                        },
                        "ca_cert_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to CA certificate",
                            "title": "CA certificate path"
                        }
                    },
                    "required": [
                        "db",
                        "user",
                        "password"
                    ],
                    "title": "PostgreSQLDatabaseConfiguration",
                    "type": "object"
                },
                "PromptCreateRequest": {
                    "additionalProperties": false,
                    "description": "Request body to create a stored prompt template in Llama Stack.\n\nAttributes:\n    prompt: Prompt text with variable placeholders.\n    variables: Variable names allowed in the template.",
                    "examples": [
                        {
                            "prompt": "Summarize: {{text}}",
                            "variables": [
                                "text"
                            ]
                        }
                    ],
                    "properties": {
                        "prompt": {
                            "description": "Prompt text with variable placeholders",
                            "examples": [
                                "Summarize: {{text}}"
                            ],
                            "minLength": 1,
                            "title": "Prompt",
                            "type": "string"
                        },
                        "variables": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Variable names allowed in the template",
                            "examples": [
                                [
                                    "text"
                                ]
                            ],
                            "title": "Variables"
                        }
                    },
                    "required": [
                        "prompt"
                    ],
                    "title": "PromptCreateRequest",
                    "type": "object"
                },
                "PromptDeleteResponse": {
                    "description": "Result of deleting a stored prompt (always HTTP 200, like conversations v2).\n\nAttributes:\n    prompt_id: Prompt identifier that was passed to delete.\n    deleted: Whether the prompt was deleted successfully\n    response: Human readable response",
                    "examples": [
                        {
                            "label": "deleted",
                            "value": {
                                "deleted": true,
                                "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                                "response": "Prompt deleted successfully"
                            }
                        },
                        {
                            "label": "not found",
                            "value": {
                                "deleted": false,
                                "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                                "response": "Prompt not found"
                            }
                        }
                    ],
                    "properties": {
                        "deleted": {
                            "description": "Whether the deletion was successful.",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Deleted",
                            "type": "boolean"
                        },
                        "prompt_id": {
                            "description": "Prompt identifier that was passed to delete.",
                            "examples": [
                                "pmpt_0123456789abcdef0123456789abcdef01234567"
                            ],
                            "title": "Prompt Id",
                            "type": "string"
                        }
                    },
                    "required": [
                        "deleted",
                        "prompt_id"
                    ],
                    "title": "PromptDeleteResponse",
                    "type": "object"
                },
                "PromptResourceResponse": {
                    "additionalProperties": false,
                    "description": "A stored prompt template as returned by Llama Stack.\n\nAttributes:\n    prompt_id: Prompt identifier from Llama Stack.\n    version: Version number for this prompt.\n    is_default: Whether this version is the default.\n    prompt: Prompt text with placeholders.\n    variables: Variable names used in the template.",
                    "examples": [
                        {
                            "is_default": true,
                            "prompt": "Summarize: {{text}}",
                            "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                            "variables": [
                                "text"
                            ],
                            "version": 1
                        }
                    ],
                    "properties": {
                        "prompt_id": {
                            "description": "Prompt identifier from Llama Stack",
                            "title": "Prompt Id",
                            "type": "string"
                        },
                        "version": {
                            "description": "Version number for this prompt",
                            "title": "Version",
                            "type": "integer"
                        },
                        "is_default": {
                            "type": "boolean",
                            "nullable": true,
                            "default": null,
                            "description": "Whether this version is the default",
                            "title": "Is Default"
                        },
                        "prompt": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Prompt text with placeholders",
                            "title": "Prompt"
                        },
                        "variables": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Variable names used in the template",
                            "title": "Variables"
                        }
                    },
                    "required": [
                        "prompt_id",
                        "version"
                    ],
                    "title": "PromptResourceResponse",
                    "type": "object"
                },
                "PromptTooLongResponse": {
                    "description": "413 Payload Too Large - Prompt is too long.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "The input exceeds the context window size of model 'gpt-4o-mini'.",
                                "response": "Context window exceeded"
                            },
                            "label": "context window exceeded"
                        },
                        {
                            "detail": {
                                "cause": "The prompt exceeds the maximum allowed length.",
                                "response": "Prompt is too long"
                            },
                            "label": "prompt too long"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "PromptTooLongResponse",
                    "type": "object"
                },
                "PromptUpdateRequest": {
                    "additionalProperties": false,
                    "description": "Request body to update a stored prompt (creates a new version).\n\nAttributes:\n    prompt: Updated prompt text.\n    version: Current version being updated.\n    set_as_default: Whether the new version becomes the default.\n    variables: Updated allowed variable names.",
                    "examples": [
                        {
                            "prompt": "Summarize in bullet points: {{text}}",
                            "set_as_default": true,
                            "variables": [
                                "text"
                            ],
                            "version": 1
                        }
                    ],
                    "properties": {
                        "prompt": {
                            "description": "Updated prompt text",
                            "examples": [
                                "Summarize in bullet points: {{text}}"
                            ],
                            "minLength": 1,
                            "title": "Prompt",
                            "type": "string"
                        },
                        "version": {
                            "description": "Current version being updated",
                            "examples": [
                                1
                            ],
                            "minimum": 0,
                            "title": "Version",
                            "type": "integer"
                        },
                        "set_as_default": {
                            "type": "boolean",
                            "nullable": true,
                            "default": null,
                            "description": "Whether the new version becomes the default",
                            "examples": [
                                true
                            ],
                            "title": "Set As Default"
                        },
                        "variables": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Updated allowed variable names",
                            "examples": [
                                [
                                    "text"
                                ]
                            ],
                            "title": "Variables"
                        }
                    },
                    "required": [
                        "prompt",
                        "version"
                    ],
                    "title": "PromptUpdateRequest",
                    "type": "object"
                },
                "PromptsListResponse": {
                    "additionalProperties": false,
                    "description": "List of stored prompt templates returned by Llama Stack.\n\nAttributes:\n    data: Prompt entries as returned by the Llama Stack list API.",
                    "examples": [
                        {
                            "data": [
                                {
                                    "is_default": true,
                                    "prompt": "Summarize: {{text}}",
                                    "prompt_id": "pmpt_0123456789abcdef0123456789abcdef01234567",
                                    "variables": [
                                        "text"
                                    ],
                                    "version": 1
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "data": {
                            "description": "Prompt entries (as returned by Llama Stack list)",
                            "items": {
                                "$ref": "`#/components/schemas/`PromptResourceResponse"
                            },
                            "title": "Data",
                            "type": "array"
                        }
                    },
                    "title": "PromptsListResponse",
                    "type": "object"
                },
                "ProviderHealthStatus": {
                    "description": "Model representing the health status of a provider.\n\nAttributes:\n    provider_id: The ID of the provider.\n    status: The health status ('ok', 'unhealthy', 'not_implemented').\n    message: Optional message about the health status.",
                    "properties": {
                        "provider_id": {
                            "description": "The ID of the provider",
                            "title": "Provider Id",
                            "type": "string"
                        },
                        "status": {
                            "description": "The health status",
                            "examples": [
                                "ok",
                                "unhealthy",
                                "not_implemented"
                            ],
                            "title": "Status",
                            "type": "string"
                        },
                        "message": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Optional message about the health status",
                            "examples": [
                                "All systems operational",
                                "Provider is unavailable"
                            ],
                            "title": "Message"
                        }
                    },
                    "required": [
                        "provider_id",
                        "status"
                    ],
                    "title": "ProviderHealthStatus",
                    "type": "object"
                },
                "ProviderResponse": {
                    "description": "Model representing a response to get specific provider request.",
                    "examples": [
                        {
                            "api": "inference",
                            "config": {
                                "api_key": "********"
                            },
                            "health": {
                                "message": "Healthy",
                                "status": "OK"
                            },
                            "provider_id": "openai",
                            "provider_type": "remote::openai"
                        }
                    ],
                    "properties": {
                        "api": {
                            "description": "The API this provider implements",
                            "title": "Api",
                            "type": "string"
                        },
                        "config": {
                            "additionalProperties": true,
                            "description": "Provider configuration parameters",
                            "title": "Config",
                            "type": "object"
                        },
                        "health": {
                            "additionalProperties": true,
                            "description": "Current health status of the provider",
                            "title": "Health",
                            "type": "object"
                        },
                        "provider_id": {
                            "description": "Unique provider identifier",
                            "title": "Provider Id",
                            "type": "string"
                        },
                        "provider_type": {
                            "description": "Provider implementation type",
                            "title": "Provider Type",
                            "type": "string"
                        }
                    },
                    "required": [
                        "api",
                        "config",
                        "health",
                        "provider_id",
                        "provider_type"
                    ],
                    "title": "ProviderResponse",
                    "type": "object"
                },
                "ProvidersListResponse": {
                    "description": "Model representing a response to providers request.",
                    "examples": [
                        {
                            "providers": {
                                "agents": [
                                    {
                                        "provider_id": "meta-reference",
                                        "provider_type": "inline::meta-reference"
                                    }
                                ],
                                "inference": [
                                    {
                                        "provider_id": "sentence-transformers",
                                        "provider_type": "inline::sentence-transformers"
                                    },
                                    {
                                        "provider_id": "openai",
                                        "provider_type": "remote::openai"
                                    }
                                ]
                            }
                        }
                    ],
                    "properties": {
                        "providers": {
                            "additionalProperties": {
                                "items": {
                                    "additionalProperties": true,
                                    "type": "object"
                                },
                                "type": "array"
                            },
                            "description": "List of available API types and their corresponding providers",
                            "title": "Providers",
                            "type": "object"
                        }
                    },
                    "required": [
                        "providers"
                    ],
                    "title": "ProvidersListResponse",
                    "type": "object"
                },
                "QueryRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a request for the LLM (Language Model).\n\nAttributes:\n    query: The query string.\n    conversation_id: The optional conversation ID (UUID).\n    provider: The optional provider.\n    model: The optional model.\n    system_prompt: The optional system prompt.\n    attachments: The optional attachments.\n    no_tools: Whether to bypass all tools and MCP servers (default: False).\n    generate_topic_summary: Whether to generate topic summary for new conversations.\n    media_type: The optional media type for response format (application/json or text/plain).\n    vector_store_ids: The optional list of specific vector store IDs to query for RAG.\n    shield_ids: The optional list of safety shield IDs to apply.\n    solr: Optional Solr inline RAG options (mode, filters) or legacy filter-only dict.",
                    "examples": [
                        {
                            "attachments": [
                                {
                                    "attachment_type": "log",
                                    "content": "this is attachment",
                                    "content_type": "text/plain"
                                },
                                {
                                    "attachment_type": "configuration",
                                    "content": "kind: Pod\n metadata:\n    name: private-reg",
                                    "content_type": "application/yaml"
                                },
                                {
                                    "attachment_type": "configuration",
                                    "content": "foo: bar",
                                    "content_type": "application/yaml"
                                }
                            ],
                            "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                            "generate_topic_summary": true,
                            "model": "model-name",
                            "no_tools": false,
                            "provider": "openai",
                            "query": "write a deployment yaml for the mongodb image",
                            "system_prompt": "You are a helpful assistant",
                            "vector_store_ids": [
                                "ocp_docs",
                                "knowledge_base"
                            ]
                        }
                    ],
                    "properties": {
                        "query": {
                            "description": "The query string",
                            "examples": [
                                "What is Kubernetes?"
                            ],
                            "title": "Query",
                            "type": "string"
                        },
                        "conversation_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "The optional conversation ID (UUID)",
                            "examples": [
                                "c5260aec-4d82-4370-9fdf-05cf908b3f16"
                            ],
                            "title": "Conversation Id"
                        },
                        "provider": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "The optional provider",
                            "examples": [
                                "openai",
                                "watsonx"
                            ],
                            "title": "Provider"
                        },
                        "model": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "The optional model",
                            "examples": [
                                "gpt4mini"
                            ],
                            "title": "Model"
                        },
                        "system_prompt": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "The optional system prompt.",
                            "examples": [
                                "You are OpenShift assistant.",
                                "You are Ansible assistant."
                            ],
                            "title": "System Prompt"
                        },
                        "attachments": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "The optional list of attachments.",
                            "examples": [
                                {
                                    "attachment_type": "log",
                                    "content": "this is attachment",
                                    "content_type": "text/plain"
                                },
                                {
                                    "attachment_type": "configuration",
                                    "content": "kind: Pod\n metadata:\n name:    private-reg",
                                    "content_type": "application/yaml"
                                },
                                {
                                    "attachment_type": "configuration",
                                    "content": "foo: bar",
                                    "content_type": "application/yaml"
                                }
                            ],
                            "title": "Attachments"
                        },
                        "no_tools": {
                            "type": "boolean",
                            "nullable": true,
                            "default": false,
                            "description": "Whether to bypass all tools and MCP servers",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "No Tools"
                        },
                        "generate_topic_summary": {
                            "type": "boolean",
                            "nullable": true,
                            "default": true,
                            "description": "Whether to generate topic summary for new conversations",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Generate Topic Summary"
                        },
                        "media_type": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Media type for the response format",
                            "examples": [
                                "application/json",
                                "text/plain"
                            ],
                            "title": "Media Type"
                        },
                        "vector_store_ids": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Optional list of specific vector store IDs to query for RAG. If not provided, all available vector stores will be queried.",
                            "examples": [
                                "ocp_docs",
                                "knowledge_base",
                                "vector_db_1"
                            ],
                            "title": "Vector Store Ids"
                        },
                        "shield_ids": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Optional list of safety shield IDs to apply. If None, all configured shields are used. ",
                            "examples": [
                                "llama-guard",
                                "custom-shield"
                            ],
                            "title": "Shield Ids"
                        },
                        "solr": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SolrVectorSearchRequest"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Solr inline RAG config: mode (semantic, hybrid, lexical) and filters; a legacy filter-only object (e.g. fq) is still accepted.",
                            "examples": [
                                {
                                    "filters": {
                                        "fq": [
                                            "product:*openshift*"
                                        ]
                                    },
                                    "mode": "hybrid"
                                },
                                {
                                    "filters": {
                                        "fq": [
                                            "product:*openshift*",
                                            "product_version:*4.16*"
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    "required": [
                        "query"
                    ],
                    "title": "QueryRequest",
                    "type": "object"
                },
                "QueryResponse": {
                    "description": "Model representing LLM response to a query.\n\nAttributes:\n    conversation_id: The optional conversation ID (UUID).\n    response: The response.\n    rag_chunks: Deprecated. List of RAG chunks used to generate the response.\n        This information is now available in tool_results under file_search_call type.\n    referenced_documents: The URLs and titles for the documents used to generate the response.\n    tool_calls: List of tool calls made during response generation.\n    tool_results: List of tool results.\n    truncated: Whether conversation history was truncated.\n    input_tokens: Number of tokens sent to LLM.\n    output_tokens: Number of tokens received from LLM.\n    available_quotas: Quota available as measured by all configured quota limiters.",
                    "examples": [
                        {
                            "available_quotas": {
                                "ClusterQuotaLimiter": 998911,
                                "UserQuotaLimiter": 998911
                            },
                            "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                            "input_tokens": 123,
                            "output_tokens": 456,
                            "referenced_documents": [
                                {
                                    "doc_title": "Operator Lifecycle Manager concepts and resources",
                                    "doc_url": "https://docs.openshift.com/container-platform/4.15/operators/understanding/olm/olm-understanding-olm.html"
                                }
                            ],
                            "response": "Operator Lifecycle Manager (OLM) helps users install...",
                            "tool_calls": [
                                {
                                    "args": {},
                                    "id": "1",
                                    "name": "tool1",
                                    "type": "tool_call"
                                }
                            ],
                            "tool_results": [
                                {
                                    "content": "bla",
                                    "id": "1",
                                    "round": 1,
                                    "status": "success",
                                    "type": "tool_result"
                                }
                            ],
                            "truncated": false
                        }
                    ],
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "The optional conversation ID (UUID)",
                            "examples": [
                                "c5260aec-4d82-4370-9fdf-05cf908b3f16"
                            ],
                            "title": "Conversation Id"
                        },
                        "response": {
                            "description": "Response from LLM",
                            "examples": [
                                "Kubernetes is an open-source container orchestration system for automating ..."
                            ],
                            "title": "Response",
                            "type": "string"
                        },
                        "rag_chunks": {
                            "description": "Deprecated: List of RAG chunks used to generate the response.",
                            "items": {
                                "$ref": "`#/components/schemas/`RAGChunk"
                            },
                            "title": "Rag Chunks",
                            "type": "array"
                        },
                        "referenced_documents": {
                            "description": "List of documents referenced in generating the response",
                            "examples": [
                                [
                                    {
                                        "doc_title": "Operator Lifecycle Manager (OLM)",
                                        "doc_url": "https://docs.openshift.com/container-platform/4.15/operators/olm/index.html"
                                    }
                                ]
                            ],
                            "items": {
                                "$ref": "`#/components/schemas/`ReferencedDocument"
                            },
                            "title": "Referenced Documents",
                            "type": "array"
                        },
                        "truncated": {
                            "default": false,
                            "description": "Deprecated: whether conversation history was truncated",
                            "examples": [
                                false,
                                true
                            ],
                            "title": "Truncated",
                            "type": "boolean"
                        },
                        "input_tokens": {
                            "default": 0,
                            "description": "Number of tokens sent to LLM",
                            "examples": [
                                150,
                                250,
                                500
                            ],
                            "title": "Input Tokens",
                            "type": "integer"
                        },
                        "output_tokens": {
                            "default": 0,
                            "description": "Number of tokens received from LLM",
                            "examples": [
                                50,
                                100,
                                200
                            ],
                            "title": "Output Tokens",
                            "type": "integer"
                        },
                        "available_quotas": {
                            "additionalProperties": {
                                "type": "integer"
                            },
                            "description": "Quota available as measured by all configured quota limiters",
                            "examples": [
                                {
                                    "daily": 1000,
                                    "monthly": 50000
                                }
                            ],
                            "title": "Available Quotas",
                            "type": "object"
                        },
                        "tool_calls": {
                            "description": "List of tool calls made during response generation",
                            "items": {
                                "$ref": "`#/components/schemas/`ToolCallSummary"
                            },
                            "title": "Tool Calls",
                            "type": "array"
                        },
                        "tool_results": {
                            "description": "List of tool results",
                            "items": {
                                "$ref": "`#/components/schemas/`ToolResultSummary"
                            },
                            "title": "Tool Results",
                            "type": "array"
                        }
                    },
                    "required": [
                        "response"
                    ],
                    "title": "QueryResponse",
                    "type": "object"
                },
                "QuotaExceededResponse": {
                    "description": "429 Too Many Requests - Quota limit exceeded.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "The token quota for model gpt-4-turbo has been exceeded.",
                                "response": "The model quota has been exceeded"
                            },
                            "label": "model"
                        },
                        {
                            "detail": {
                                "cause": "User 123 has no available tokens",
                                "response": "The quota has been exceeded"
                            },
                            "label": "user none"
                        },
                        {
                            "detail": {
                                "cause": "Cluster has no available tokens",
                                "response": "The quota has been exceeded"
                            },
                            "label": "cluster none"
                        },
                        {
                            "detail": {
                                "cause": "Unknown subject 999 has no available tokens",
                                "response": "The quota has been exceeded"
                            },
                            "label": "subject none"
                        },
                        {
                            "detail": {
                                "cause": "User 123 has 5 tokens, but 10 tokens are needed",
                                "response": "The quota has been exceeded"
                            },
                            "label": "user insufficient"
                        },
                        {
                            "detail": {
                                "cause": "Cluster has 500 tokens, but 900 tokens are needed",
                                "response": "The quota has been exceeded"
                            },
                            "label": "cluster insufficient"
                        },
                        {
                            "detail": {
                                "cause": "Unknown subject 999 has 3 tokens, but 6 tokens are needed",
                                "response": "The quota has been exceeded"
                            },
                            "label": "subject insufficient"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "QuotaExceededResponse",
                    "type": "object"
                },
                "QuotaHandlersConfiguration": {
                    "additionalProperties": false,
                    "description": "Quota limiter configuration.\n\nIt is possible to limit quota usage per user or per service or services\n(that typically run in one cluster). Each limit is configured as a separate\n_quota limiter_. It can be of type `user_limiter` or `cluster_limiter`\n(which is name that makes sense in OpenShift deployment).",
                    "properties": {
                        "sqlite": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SQLiteDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "SQLite database configuration",
                            "title": "SQLite configuration"
                        },
                        "postgres": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`PostgreSQLDatabaseConfiguration"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "PostgreSQL database configuration",
                            "title": "PostgreSQL configuration"
                        },
                        "limiters": {
                            "description": "Quota limiters configuration",
                            "items": {
                                "$ref": "`#/components/schemas/`QuotaLimiterConfiguration"
                            },
                            "title": "Quota limiters",
                            "type": "array"
                        },
                        "scheduler": {
                            "$ref": "`#/components/schemas/`QuotaSchedulerConfiguration",
                            "description": "Quota scheduler configuration",
                            "title": "Quota scheduler"
                        },
                        "enable_token_history": {
                            "default": false,
                            "description": "Enables storing information about token usage history",
                            "title": "Enable token history",
                            "type": "boolean"
                        }
                    },
                    "title": "QuotaHandlersConfiguration",
                    "type": "object"
                },
                "QuotaLimiterConfiguration": {
                    "additionalProperties": false,
                    "description": "Configuration for one quota limiter.\n\nThere are three configuration options for each limiter:\n\n1. ``period`` is specified in a human-readable form, see\n   https://www.postgresql.org/docs/current/datatype-datetime.html#DATATYPE-INTERVAL-INPUT\n   for all possible options. When the end of the period is reached, the\n   quota is reset or increased.\n2. ``initial_quota`` is the value set at the beginning of the period.\n3. ``quota_increase`` is the value (if specified) used to increase the\n   quota when the period is reached.\n\nThere are two basic use cases:\n\n1. When the quota needs to be reset to a specific value periodically (for\n   example on a weekly or monthly basis), set ``initial_quota`` to the\n   required value.\n2. When the quota needs to be increased by a specific value periodically\n   (for example on a daily basis), set ``quota_increase``.",
                    "properties": {
                        "type": {
                            "description": "Quota limiter type, either user_limiter or cluster_limiter",
                            "enum": [
                                "user_limiter",
                                "cluster_limiter"
                            ],
                            "title": "Quota limiter type",
                            "type": "string"
                        },
                        "name": {
                            "description": "Human readable quota limiter name",
                            "title": "Quota limiter name",
                            "type": "string"
                        },
                        "initial_quota": {
                            "description": "Quota set at beginning of the period",
                            "minimum": 0,
                            "title": "Initial quota",
                            "type": "integer"
                        },
                        "quota_increase": {
                            "description": "Delta value used to increase quota when period is reached",
                            "minimum": 0,
                            "title": "Quota increase",
                            "type": "integer"
                        },
                        "period": {
                            "description": "Period specified in human readable form",
                            "title": "Period",
                            "type": "string"
                        }
                    },
                    "required": [
                        "type",
                        "name",
                        "initial_quota",
                        "quota_increase",
                        "period"
                    ],
                    "title": "QuotaLimiterConfiguration",
                    "type": "object"
                },
                "QuotaSchedulerConfiguration": {
                    "additionalProperties": false,
                    "description": "Quota scheduler configuration.",
                    "properties": {
                        "period": {
                            "default": 1,
                            "description": "Quota scheduler period specified in seconds",
                            "minimum": 0,
                            "title": "Period",
                            "type": "integer"
                        },
                        "database_reconnection_count": {
                            "default": 10,
                            "description": "Database reconnection count on startup. When database for quota is not available on startup, the service tries to reconnect N times with specified delay.",
                            "minimum": 0,
                            "title": "Database reconnection count on startup",
                            "type": "integer"
                        },
                        "database_reconnection_delay": {
                            "default": 1,
                            "description": "Database reconnection delay specified in seconds. When database for quota is not available on startup, the service tries to reconnect N times with specified delay.",
                            "minimum": 0,
                            "title": "Database reconnection delay",
                            "type": "integer"
                        }
                    },
                    "title": "QuotaSchedulerConfiguration",
                    "type": "object"
                },
                "RAGChunk": {
                    "description": "Model representing a RAG chunk used in the response.",
                    "properties": {
                        "content": {
                            "description": "The content of the chunk",
                            "title": "Content",
                            "type": "string"
                        },
                        "source": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Index name identifying the knowledge source from configuration",
                            "title": "Source"
                        },
                        "score": {
                            "type": "number",
                            "nullable": true,
                            "default": null,
                            "description": "Relevance score",
                            "title": "Score"
                        },
                        "attributes": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Document metadata from the RAG provider (e.g., url, title, author)",
                            "title": "Attributes"
                        }
                    },
                    "required": [
                        "content"
                    ],
                    "title": "RAGChunk",
                    "type": "object"
                },
                "RAGContext": {
                    "description": "Result of building RAG context from all enabled pre-query RAG sources.\n\nAttributes:\n    context_text: Formatted RAG context string for injection into the query.\n    rag_chunks: RAG chunks from pre-query sources (BYOK + Solr).\n    referenced_documents: Referenced documents from pre-query sources.",
                    "properties": {
                        "context_text": {
                            "default": "",
                            "description": "Formatted context for injection",
                            "title": "Context Text",
                            "type": "string"
                        },
                        "rag_chunks": {
                            "description": "RAG chunks from pre-query sources",
                            "items": {
                                "$ref": "`#/components/schemas/`RAGChunk"
                            },
                            "title": "Rag Chunks",
                            "type": "array"
                        },
                        "referenced_documents": {
                            "description": "Documents from pre-query sources",
                            "items": {
                                "$ref": "`#/components/schemas/`ReferencedDocument"
                            },
                            "title": "Referenced Documents",
                            "type": "array"
                        }
                    },
                    "title": "RAGContext",
                    "type": "object"
                },
                "RAGInfoResponse": {
                    "description": "Model representing a response with information about RAG DB.",
                    "examples": [
                        {
                            "created_at": 1763391371,
                            "expires_at": null,
                            "id": "vs_7b52a8cf-0fa3-489c-beab-27e061d102f3",
                            "last_active_at": 1763391371,
                            "name": "Faiss Store with Knowledge base",
                            "object": "vector_store",
                            "status": "completed",
                            "usage_bytes": 1024000
                        }
                    ],
                    "properties": {
                        "id": {
                            "description": "Vector DB unique ID",
                            "examples": [
                                "vs_00000000_0000_0000"
                            ],
                            "title": "Id",
                            "type": "string"
                        },
                        "name": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Human readable vector DB name",
                            "examples": [
                                "Faiss Store with Knowledge base"
                            ],
                            "title": "Name"
                        },
                        "created_at": {
                            "description": "When the vector store was created, represented as Unix time",
                            "examples": [
                                1763391371
                            ],
                            "title": "Created At",
                            "type": "integer"
                        },
                        "last_active_at": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "When the vector store was last active, represented as Unix time",
                            "examples": [
                                1763391371
                            ],
                            "title": "Last Active At"
                        },
                        "usage_bytes": {
                            "description": "Storage byte(s) used by this vector DB",
                            "examples": [
                                0
                            ],
                            "title": "Usage Bytes",
                            "type": "integer"
                        },
                        "expires_at": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "When the vector store expires, represented as Unix time",
                            "examples": [
                                1763391371
                            ],
                            "title": "Expires At"
                        },
                        "object": {
                            "description": "Object type",
                            "examples": [
                                "vector_store"
                            ],
                            "title": "Object",
                            "type": "string"
                        },
                        "status": {
                            "description": "Vector DB status",
                            "examples": [
                                "completed"
                            ],
                            "title": "Status",
                            "type": "string"
                        }
                    },
                    "required": [
                        "id",
                        "created_at",
                        "usage_bytes",
                        "object",
                        "status"
                    ],
                    "title": "RAGInfoResponse",
                    "type": "object"
                },
                "RAGListResponse": {
                    "description": "Model representing a response to list RAGs request.",
                    "examples": [
                        {
                            "rags": [
                                "vs_00000000-cafe-babe-0000-000000000000",
                                "vs_7b52a8cf-0fa3-489c-beab-27e061d102f3",
                                "vs_7b52a8cf-0fa3-489c-cafe-27e061d102f3"
                            ]
                        }
                    ],
                    "properties": {
                        "rags": {
                            "description": "List of RAG identifiers",
                            "examples": [
                                "vs_7b52a8cf-0fa3-489c-beab-27e061d102f3",
                                "vs_7b52a8cf-0fa3-489c-cafe-27e061d102f3"
                            ],
                            "items": {
                                "type": "string"
                            },
                            "title": "RAG list response",
                            "type": "array"
                        }
                    },
                    "required": [
                        "rags"
                    ],
                    "title": "RAGListResponse",
                    "type": "object"
                },
                "RHIdentityConfiguration": {
                    "additionalProperties": false,
                    "description": "Red Hat Identity authentication configuration.",
                    "properties": {
                        "required_entitlements": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "List of all required entitlements.",
                            "title": "Required entitlements"
                        },
                        "max_header_size": {
                            "default": 8192,
                            "description": "Maximum allowed size in bytes for the base64-encoded x-rh-identity header. Headers exceeding this size are rejected before decoding.",
                            "minimum": 0,
                            "title": "Maximum header size",
                            "type": "integer"
                        }
                    },
                    "title": "RHIdentityConfiguration",
                    "type": "object"
                },
                "RagConfiguration": {
                    "additionalProperties": false,
                    "description": "RAG strategy configuration.\n\nControls which RAG sources are used for inline and tool-based retrieval.\n\nEach strategy lists RAG IDs to include. The special ID ``\"okp\"`` defined in constants,\nactivates the OKP provider; all other IDs refer to entries in ``byok_rag``.\n\nBackward compatibility:\n    - ``inline`` defaults to ``[]`` (no inline RAG).\n    - ``tool`` defaults to ``[]`` (no tool RAG).\n\nIf no RAG strategy is defined (inline and tool are empty),\nthe RAG tool will register all stores available to llama-stack.",
                    "properties": {
                        "inline": {
                            "description": "RAG IDs whose sources are injected as context before the LLM call. Use 'okp' to enable OKP inline RAG. Empty by default (no inline RAG).",
                            "items": {
                                "type": "string"
                            },
                            "title": "Inline RAG IDs",
                            "type": "array"
                        },
                        "tool": {
                            "description": "RAG IDs made available to the LLM as a file_search tool. Use 'okp' to include the OKP vector store. When omitted, all registered BYOK vector stores are used (backward compatibility).",
                            "items": {
                                "type": "string"
                            },
                            "title": "Tool RAG IDs",
                            "type": "array"
                        }
                    },
                    "title": "RagConfiguration",
                    "type": "object"
                },
                "ReadinessResponse": {
                    "description": "Model representing response to a readiness request.\n\nAttributes:\n    ready: If service is ready to handle requests.\n    reason: The reason for the readiness status.\n    overall_status: Overall service health status (healthy/degraded/unhealthy).\n    impacts: Optional list of functional impacts when degraded or unhealthy.\n    providers: List of unhealthy providers (empty when all healthy).",
                    "examples": [
                        {
                            "impacts": null,
                            "overall_status": "healthy",
                            "providers": [],
                            "ready": true,
                            "reason": "All providers are healthy"
                        },
                        {
                            "impacts": [
                                "LLM inference unavailable",
                                "RAG functionality unavailable",
                                "Agent tools unavailable"
                            ],
                            "overall_status": "degraded",
                            "providers": [],
                            "ready": true,
                            "reason": "Service running in degraded mode"
                        }
                    ],
                    "properties": {
                        "ready": {
                            "description": "Flag indicating if service is ready to handle requests",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Ready",
                            "type": "boolean"
                        },
                        "reason": {
                            "description": "The reason for the readiness status",
                            "examples": [
                                "Service is ready"
                            ],
                            "title": "Reason",
                            "type": "string"
                        },
                        "overall_status": {
                            "$ref": "`#/components/schemas/`HealthStatus",
                            "description": "Overall service health status",
                            "examples": [
                                "healthy",
                                "degraded",
                                "unhealthy"
                            ]
                        },
                        "impacts": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "List of functional impacts when service is degraded or unhealthy",
                            "examples": [
                                [
                                    "LLM inference unavailable",
                                    "RAG functionality unavailable",
                                    "Agent tools unavailable"
                                ]
                            ],
                            "title": "Impacts"
                        },
                        "providers": {
                            "description": "List of unhealthy providers (empty when all healthy)",
                            "examples": [],
                            "items": {
                                "$ref": "`#/components/schemas/`ProviderHealthStatus"
                            },
                            "title": "Providers",
                            "type": "array"
                        }
                    },
                    "required": [
                        "ready",
                        "reason",
                        "overall_status",
                        "providers"
                    ],
                    "title": "ReadinessResponse",
                    "type": "object"
                },
                "ReferencedDocument": {
                    "description": "Model representing a document referenced in generating a response.\n\nAttributes:\n    doc_url: Url to the referenced doc.\n    doc_title: Title of the referenced doc.\n    document_id: Document ID for preserving identity during deduplication.",
                    "properties": {
                        "doc_url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "URL of the referenced document",
                            "title": "Doc Url"
                        },
                        "doc_title": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Title of the referenced document",
                            "title": "Doc Title"
                        },
                        "source": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Index name identifying the knowledge source from configuration",
                            "title": "Source"
                        },
                        "document_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Document ID for preserving identity during deduplication",
                            "title": "Document Id"
                        }
                    },
                    "title": "ReferencedDocument",
                    "type": "object"
                },
                "RerankerConfiguration": {
                    "additionalProperties": false,
                    "description": "Reranker configuration for RAG chunk reranking.",
                    "properties": {
                        "enabled": {
                            "default": false,
                            "description": "When True, reranking applied to RAG chunks. When False, reranking is disabled and original scoring used.",
                            "title": "Reranker enabled",
                            "type": "boolean"
                        },
                        "model": {
                            "default": "cross-encoder/ms-marco-MiniLM-L6-v2",
                            "description": "Cross-encoder model name for reranking RAG chunks. Defaults to 'cross-encoder/ms-marco-MiniLM-L6-v2' from sentence-transformers.",
                            "title": "Reranker model",
                            "type": "string"
                        }
                    },
                    "title": "RerankerConfiguration",
                    "type": "object"
                },
                "ResponseInput": {
                    "anyOf": [
                        {
                            "type": "string"
                        },
                        {
                            "items": {
                                "$ref": "`#/components/schemas/`ResponseItem"
                            },
                            "type": "array"
                        }
                    ]
                },
                "ResponseItem": {
                    "anyOf": [
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseMessage"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageWebSearchToolCall"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageFileSearchToolCall"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseInputFunctionToolCallOutput"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageMCPCall"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageMCPListTools"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseMCPApprovalRequest"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageFunctionToolCall"
                        },
                        {
                            "$ref": "`#/components/schemas/`OpenAIResponseMCPApprovalResponse"
                        }
                    ]
                },
                "ResponsesApiParams": {
                    "description": "Parameters for a Llama Stack Responses API request.\n\nAll fields accepted by the Llama Stack client responses.create() body are\nincluded so that dumped model can be passed directly to response create.",
                    "properties": {
                        "input": {
                            "$ref": "`#/components/schemas/`ResponseInput",
                            "description": "The input text or structured input items"
                        },
                        "model": {
                            "description": "The full model ID in format \"provider/model\"",
                            "title": "Model",
                            "type": "string"
                        },
                        "conversation": {
                            "description": "The conversation ID in llama-stack format",
                            "title": "Conversation",
                            "type": "string"
                        },
                        "include": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Output item types to include in the response",
                            "title": "Include"
                        },
                        "instructions": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "The resolved system prompt",
                            "title": "Instructions"
                        },
                        "max_infer_iters": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Maximum number of inference iterations",
                            "title": "Max Infer Iters"
                        },
                        "max_output_tokens": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Maximum number of tokens allowed in the response",
                            "title": "Max Output Tokens"
                        },
                        "max_tool_calls": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Maximum tool calls allowed in a single response",
                            "title": "Max Tool Calls"
                        },
                        "metadata": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Custom metadata for tracking or logging",
                            "title": "Metadata"
                        },
                        "parallel_tool_calls": {
                            "type": "boolean",
                            "nullable": true,
                            "default": null,
                            "description": "Whether the model can make multiple tool calls in parallel",
                            "title": "Parallel Tool Calls"
                        },
                        "previous_response_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Identifier of the previous response in a multi-turn conversation",
                            "title": "Previous Response Id"
                        },
                        "prompt": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponsePrompt"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Prompt template with variables for dynamic substitution"
                        },
                        "reasoning": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseReasoning"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Reasoning configuration for the response"
                        },
                        "safety_identifier": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Stable identifier for safety monitoring and abuse detection",
                            "title": "Safety Identifier"
                        },
                        "store": {
                            "description": "Whether to store the response",
                            "title": "Store",
                            "type": "boolean"
                        },
                        "stream": {
                            "description": "Whether to stream the response",
                            "title": "Stream",
                            "type": "boolean"
                        },
                        "temperature": {
                            "type": "number",
                            "nullable": true,
                            "default": null,
                            "description": "Sampling temperature (e.g. 0.0-2.0)",
                            "title": "Temperature"
                        },
                        "text": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseText"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Text response configuration (format constraints)"
                        },
                        "tool_choice": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceMode"
                                },
                                {
                                    "discriminator": {
                                        "mapping": {
                                            "allowed_tools": "`#/components/schemas/`OpenAIResponseInputToolChoiceAllowedTools",
                                            "custom": "`#/components/schemas/`OpenAIResponseInputToolChoiceCustomTool",
                                            "file_search": "`#/components/schemas/`OpenAIResponseInputToolChoiceFileSearch",
                                            "function": "`#/components/schemas/`OpenAIResponseInputToolChoiceFunctionTool",
                                            "mcp": "`#/components/schemas/`OpenAIResponseInputToolChoiceMCPTool",
                                            "web_search": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_2025_08_26": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_preview": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_preview_2025_03_11": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch"
                                        },
                                        "propertyName": "type"
                                    },
                                    "oneOf": [
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceAllowedTools"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceFileSearch"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceFunctionTool"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceMCPTool"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceCustomTool"
                                        }
                                    ]
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "description": "Tool selection strategy",
                            "title": "Tool Choice"
                        },
                        "tools": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Prepared tool groups for Responses API (same type as ResponsesRequest.tools)",
                            "title": "Tools"
                        },
                        "extra_headers": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Extra HTTP headers to send with the request (e.g. x-llamastack-provider-data)",
                            "title": "Extra Headers"
                        },
                        "omit_conversation": {
                            "default": false,
                            "description": "When True, the conversation parameter is dropped from the request body while remaining on the object for identity. Set by conversation compaction (LCORE-1572): once a conversation is compacted, lightspeed-stack supplies explicit input and must not let Llama Stack reload the full history via the conversation parameter.",
                            "title": "Omit Conversation",
                            "type": "boolean"
                        }
                    },
                    "required": [
                        "input",
                        "model",
                        "conversation",
                        "store",
                        "stream"
                    ],
                    "title": "ResponsesApiParams",
                    "type": "object"
                },
                "ResponsesRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a request for the Responses API following LCORE specification.\n\nAttributes:\n    input: Input text or structured input items containing the query.\n    model: Model identifier in format \"provider/model\". Auto-selected if not provided.\n    conversation: Conversation ID linking to an existing conversation. Accepts both\n        OpenAI and LCORE formats. Mutually exclusive with previous_response_id.\n    include: Explicitly specify output item types that are excluded by default but\n        should be included in the response.\n    instructions: System instructions or guidelines provided to the model (acts as\n        the system prompt).\n    max_infer_iters: Maximum number of inference iterations the model can perform.\n    max_output_tokens: Maximum number of tokens allowed in the response.\n    max_tool_calls: Maximum number of tool calls allowed in a single response.\n    metadata: Custom metadata dictionary with key-value pairs for tracking or logging.\n    parallel_tool_calls: Whether the model can make multiple tool calls in parallel.\n    previous_response_id: Identifier of the previous response in a multi-turn\n        conversation. Mutually exclusive with conversation.\n    prompt: Prompt object containing a template with variables for dynamic\n        substitution.\n    reasoning: Reasoning configuration for the response.\n    safety_identifier: Safety identifier for the response.\n    store: Whether to store the response in conversation history. Defaults to True.\n    stream: Whether to stream the response as it is generated. Defaults to False.\n    temperature: Sampling temperature controlling randomness (typically 0.0\u20132.0).\n    text: Text response configuration specifying output format constraints (JSON\n        schema, JSON object, or plain text).\n    tool_choice: Tool selection strategy (\"auto\", \"required\", \"none\", or specific\n        tool configuration).\n    tools: List of tools available to the model (file search, web search, function\n        calls, MCP tools). Defaults to all tools available to the model.\n    generate_topic_summary: LCORE-specific flag indicating whether to generate a\n        topic summary for new conversations. Defaults to True.\n    shield_ids: LCORE-specific list of safety shield IDs to apply. If None, all\n        configured shields are used.\n    solr: Optional Solr inline RAG options (mode, filters) or legacy filter-only dict.",
                    "examples": [
                        {
                            "generate_topic_summary": true,
                            "input": "Hello World!",
                            "instructions": "You are a helpful assistant",
                            "model": "openai/gpt-4o-mini",
                            "store": true,
                            "stream": false
                        }
                    ],
                    "properties": {
                        "input": {
                            "$ref": "`#/components/schemas/`ResponseInput"
                        },
                        "model": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Model"
                        },
                        "conversation": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Conversation"
                        },
                        "include": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Include"
                        },
                        "instructions": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Instructions"
                        },
                        "max_infer_iters": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "title": "Max Infer Iters"
                        },
                        "max_output_tokens": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "title": "Max Output Tokens"
                        },
                        "max_tool_calls": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "title": "Max Tool Calls"
                        },
                        "metadata": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "title": "Metadata"
                        },
                        "parallel_tool_calls": {
                            "type": "boolean",
                            "nullable": true,
                            "default": null,
                            "title": "Parallel Tool Calls"
                        },
                        "previous_response_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Previous Response Id"
                        },
                        "prompt": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponsePrompt"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "reasoning": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseReasoning"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "safety_identifier": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Safety Identifier"
                        },
                        "store": {
                            "default": true,
                            "title": "Store",
                            "type": "boolean"
                        },
                        "stream": {
                            "default": false,
                            "title": "Stream",
                            "type": "boolean"
                        },
                        "temperature": {
                            "type": "number",
                            "nullable": true,
                            "default": null,
                            "title": "Temperature"
                        },
                        "text": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseText"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "tool_choice": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceMode"
                                },
                                {
                                    "discriminator": {
                                        "mapping": {
                                            "allowed_tools": "`#/components/schemas/`OpenAIResponseInputToolChoiceAllowedTools",
                                            "custom": "`#/components/schemas/`OpenAIResponseInputToolChoiceCustomTool",
                                            "file_search": "`#/components/schemas/`OpenAIResponseInputToolChoiceFileSearch",
                                            "function": "`#/components/schemas/`OpenAIResponseInputToolChoiceFunctionTool",
                                            "mcp": "`#/components/schemas/`OpenAIResponseInputToolChoiceMCPTool",
                                            "web_search": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_2025_08_26": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_preview": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_preview_2025_03_11": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch"
                                        },
                                        "propertyName": "type"
                                    },
                                    "oneOf": [
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceAllowedTools"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceFileSearch"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceFunctionTool"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceMCPTool"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceCustomTool"
                                        }
                                    ]
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "title": "Tool Choice"
                        },
                        "tools": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Tools"
                        },
                        "generate_topic_summary": {
                            "type": "boolean",
                            "nullable": true,
                            "default": true,
                            "title": "Generate Topic Summary"
                        },
                        "shield_ids": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Shield Ids"
                        },
                        "solr": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`SolrVectorSearchRequest"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        }
                    },
                    "required": [
                        "input"
                    ],
                    "title": "ResponsesRequest",
                    "type": "object"
                },
                "ResponsesResponse": {
                    "description": "Model representing a response from the Responses API following LCORE specification.\n\nAttributes:\n    created_at: Unix timestamp when the response was created.\n    completed_at: Unix timestamp when the response was completed, if applicable.\n    error: Error details if the response failed or was blocked.\n    id: Unique identifier for this response.\n    model: Model identifier in \"provider/model\" format used for generation.\n    object: Object type identifier, always \"response\".\n    output: List of structured output items containing messages, tool calls, and\n        other content. This is the primary response content.\n    parallel_tool_calls: Whether the model can make multiple tool calls in parallel.\n    previous_response_id: Identifier of the previous response in a multi-turn\n        conversation.\n    prompt: The input prompt object that was sent to the model.\n    status: Current status of the response (e.g., \"completed\", \"blocked\",\n        \"in_progress\").\n    temperature: Temperature parameter used for generation (controls randomness).\n    text: Text response configuration object used for OpenAI responses.\n    top_p: Top-p sampling parameter used for generation.\n    tools: List of tools available to the model during generation.\n    tool_choice: Tool selection strategy used (e.g., \"auto\", \"required\", \"none\").\n    truncation: Strategy used for handling content that exceeds context limits.\n    usage: Token usage statistics including input_tokens, output_tokens, and\n        total_tokens.\n    instructions: System instructions or guidelines provided to the model.\n    max_tool_calls: Maximum number of tool calls allowed in a single response.\n    reasoning: Reasoning configuration (effort level) used for the response.\n    max_output_tokens: Upper bound for tokens generated in the response.\n    safety_identifier: Safety/guardrail identifier applied to the request.\n    metadata: Additional metadata dictionary with custom key-value pairs.\n    store: Whether the response was stored.\n    conversation: Conversation ID linking this response to a conversation thread\n        (LCORE-specific).\n    available_quotas: Remaining token quotas for the user (LCORE-specific).\n    output_text: Aggregated text output from all output_text items in the\n        output array.",
                    "examples": [
                        {
                            "available_quotas": {
                                "daily": 1000,
                                "monthly": 50000
                            },
                            "completed_at": 1704067250,
                            "conversation": "0d21ba731f21f798dc9680125d5d6f493e4a7ab79f25670e",
                            "created_at": 1704067200,
                            "id": "resp_abc123",
                            "instructions": "You are a helpful assistant",
                            "model": "openai/gpt-4-turbo",
                            "object": "response",
                            "output": [
                                {
                                    "content": [
                                        {
                                            "text": "Kubernetes is an open-source container orchestration system...",
                                            "type": "output_text"
                                        }
                                    ],
                                    "role": "assistant",
                                    "type": "message"
                                }
                            ],
                            "output_text": "Kubernetes is an open-source container orchestration system...",
                            "parallel_tool_calls": true,
                            "status": "completed",
                            "store": true,
                            "temperature": 0.7,
                            "text": {
                                "format": {
                                    "type": "text"
                                }
                            },
                            "usage": {
                                "input_tokens": 100,
                                "input_tokens_details": {
                                    "cached_tokens": 0
                                },
                                "output_tokens": 50,
                                "output_tokens_details": {
                                    "reasoning_tokens": 0
                                },
                                "total_tokens": 150
                            }
                        }
                    ],
                    "properties": {
                        "created_at": {
                            "title": "Created At",
                            "type": "integer"
                        },
                        "completed_at": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "title": "Completed At"
                        },
                        "error": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseError"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "id": {
                            "title": "Id",
                            "type": "string"
                        },
                        "model": {
                            "title": "Model",
                            "type": "string"
                        },
                        "object": {
                            "const": "response",
                            "default": "response",
                            "title": "Object",
                            "type": "string"
                        },
                        "output": {
                            "items": {
                                "discriminator": {
                                    "mapping": {
                                        "file_search_call": "`#/components/schemas/`OpenAIResponseOutputMessageFileSearchToolCall",
                                        "function_call": "`#/components/schemas/`OpenAIResponseOutputMessageFunctionToolCall",
                                        "mcp_approval_request": "`#/components/schemas/`OpenAIResponseMCPApprovalRequest",
                                        "mcp_call": "`#/components/schemas/`OpenAIResponseOutputMessageMCPCall",
                                        "mcp_list_tools": "`#/components/schemas/`OpenAIResponseOutputMessageMCPListTools",
                                        "message": "`#/components/schemas/`OpenAIResponseMessage",
                                        "web_search_call": "`#/components/schemas/`OpenAIResponseOutputMessageWebSearchToolCall"
                                    },
                                    "propertyName": "type"
                                },
                                "oneOf": [
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseMessage"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageWebSearchToolCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageFileSearchToolCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageFunctionToolCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageMCPCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageMCPListTools"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseMCPApprovalRequest"
                                    }
                                ]
                            },
                            "title": "Output",
                            "type": "array"
                        },
                        "parallel_tool_calls": {
                            "default": true,
                            "title": "Parallel Tool Calls",
                            "type": "boolean"
                        },
                        "previous_response_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Previous Response Id"
                        },
                        "prompt": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponsePrompt"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "status": {
                            "title": "Status",
                            "type": "string"
                        },
                        "temperature": {
                            "type": "number",
                            "nullable": true,
                            "default": null,
                            "title": "Temperature"
                        },
                        "text": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseText"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "top_p": {
                            "type": "number",
                            "nullable": true,
                            "default": null,
                            "title": "Top P"
                        },
                        "tools": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Tools"
                        },
                        "tool_choice": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceMode"
                                },
                                {
                                    "discriminator": {
                                        "mapping": {
                                            "allowed_tools": "`#/components/schemas/`OpenAIResponseInputToolChoiceAllowedTools",
                                            "custom": "`#/components/schemas/`OpenAIResponseInputToolChoiceCustomTool",
                                            "file_search": "`#/components/schemas/`OpenAIResponseInputToolChoiceFileSearch",
                                            "function": "`#/components/schemas/`OpenAIResponseInputToolChoiceFunctionTool",
                                            "mcp": "`#/components/schemas/`OpenAIResponseInputToolChoiceMCPTool",
                                            "web_search": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_2025_08_26": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_preview": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch",
                                            "web_search_preview_2025_03_11": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch"
                                        },
                                        "propertyName": "type"
                                    },
                                    "oneOf": [
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceAllowedTools"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceFileSearch"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceWebSearch"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceFunctionTool"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceMCPTool"
                                        },
                                        {
                                            "$ref": "`#/components/schemas/`OpenAIResponseInputToolChoiceCustomTool"
                                        }
                                    ]
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null,
                            "title": "Tool Choice"
                        },
                        "truncation": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Truncation"
                        },
                        "usage": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseUsage"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "instructions": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Instructions"
                        },
                        "max_tool_calls": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "title": "Max Tool Calls"
                        },
                        "reasoning": {
                            "anyOf": [
                                {
                                    "$ref": "`#/components/schemas/`OpenAIResponseReasoning"
                                },
                                {
                                    "type": "null"
                                }
                            ],
                            "default": null
                        },
                        "max_output_tokens": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "title": "Max Output Tokens"
                        },
                        "safety_identifier": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Safety Identifier"
                        },
                        "metadata": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "title": "Metadata"
                        },
                        "store": {
                            "type": "boolean",
                            "nullable": true,
                            "default": null,
                            "title": "Store"
                        },
                        "conversation": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Conversation"
                        },
                        "available_quotas": {
                            "additionalProperties": {
                                "type": "integer"
                            },
                            "title": "Available Quotas",
                            "type": "object"
                        },
                        "output_text": {
                            "title": "Output Text",
                            "type": "string"
                        }
                    },
                    "required": [
                        "created_at",
                        "id",
                        "model",
                        "output",
                        "status",
                        "available_quotas",
                        "output_text"
                    ],
                    "sse_example": "event: response.created\ndata: {\"type\":\"response.created\",\"sequence_number\":0,\"response\":{\"id\":\"resp_abc\",\"object\":\"response\",\"created_at\":1704067200,\"status\":\"in_progress\",\"model\":\"openai/gpt-4o-mini\",\"output\":[],\"store\":true,\"text\":{\"format\":{\"type\":\"text\"}},\"conversation\":\"0d21ba731f21f798dc9680125d5d6f49\",\"available_quotas\":{},\"output_text\":\"\"}}\n\nevent: response.output_item.added\ndata: {\"type\":\"response.output_item.added\",\"sequence_number\":1,\"response_id\":\"resp_abc\",\"output_index\":0,\"item\":{\"id\":\"msg_abc\",\"type\":\"message\",\"status\":\"in_progress\",\"role\":\"assistant\",\"content\":[]}}\n\n...\n\nevent: response.completed\ndata: {\"type\":\"response.completed\",\"sequence_number\":30,\"response\":{\"id\":\"resp_abc\",\"object\":\"response\",\"created_at\":1704067200,\"status\":\"completed\",\"model\":\"openai/gpt-4o-mini\",\"output\":[{\"id\":\"msg_abc\",\"type\":\"message\",\"status\":\"completed\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"Hello! How can I help?\",\"annotations\":[]}]}],\"store\":true,\"text\":{\"format\":{\"type\":\"text\"}},\"usage\":{\"input_tokens\":10,\"output_tokens\":6,\"total_tokens\":16,\"input_tokens_details\":{\"cached_tokens\":0},\"output_tokens_details\":{\"reasoning_tokens\":0}},\"conversation\":\"0d21ba731f21f798dc9680125d5d6f49\",\"available_quotas\":{\"daily\":1000,\"monthly\":50000},\"output_text\":\"Hello! How can I help?\"}}\n\ndata: [DONE]\n\n",
                    "title": "ResponsesResponse",
                    "type": "object"
                },
                "RlsapiV1Attachment": {
                    "additionalProperties": false,
                    "description": "Attachment data from rlsapi v1 context.\n\nAttributes:\n    contents: The textual contents of the file read on the client machine.\n    mimetype: The MIME type of the file.",
                    "properties": {
                        "contents": {
                            "default": "",
                            "description": "File contents read on client",
                            "examples": [
                                "# Configuration file\nkey=value"
                            ],
                            "maxLength": 65536,
                            "title": "Contents",
                            "type": "string"
                        },
                        "mimetype": {
                            "default": "",
                            "description": "MIME type of the file",
                            "examples": [
                                "text/plain",
                                "application/json"
                            ],
                            "title": "Mimetype",
                            "type": "string"
                        }
                    },
                    "title": "RlsapiV1Attachment",
                    "type": "object"
                },
                "RlsapiV1CLA": {
                    "additionalProperties": false,
                    "description": "Command Line Assistant information from rlsapi v1 context.\n\nAttributes:\n    nevra: The NEVRA (Name-Epoch-Version-Release-Architecture) of the CLA.\n    version: The version of the command line assistant.",
                    "properties": {
                        "nevra": {
                            "default": "",
                            "description": "CLA NEVRA identifier",
                            "examples": [
                                "command-line-assistant-0:0.2.0-1.el9.noarch"
                            ],
                            "pattern": "^[a-zA-Z0-9._:+~\\-]*$",
                            "title": "Nevra",
                            "type": "string"
                        },
                        "version": {
                            "default": "",
                            "description": "Command line assistant version",
                            "examples": [
                                "0.2.0"
                            ],
                            "pattern": "^[a-zA-Z0-9._\\-]*$",
                            "title": "Version",
                            "type": "string"
                        }
                    },
                    "title": "RlsapiV1CLA",
                    "type": "object"
                },
                "RlsapiV1Configuration": {
                    "additionalProperties": false,
                    "description": "Configuration for the rlsapi v1 /infer endpoint.\n\nSettings specific to the RHEL Lightspeed Command Line Assistant (CLA)\nstateless inference endpoint. Kept separate from shared configuration\nsections so that CLA-specific options do not affect other endpoints.",
                    "properties": {
                        "allow_verbose_infer": {
                            "default": false,
                            "description": "Allow /v1/infer to return extended metadata (tool_calls, rag_chunks, token_usage) when the client sends \"include_metadata\": true. Should NOT be enabled in production. If production use is needed, consider RBAC-based access control via an Action.RLSAPI_V1_INFER authorization rule.",
                            "title": "Allow verbose infer",
                            "type": "boolean"
                        },
                        "quota_subject": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Identity field used as the quota subject for /v1/infer. When set, token quota enforcement is enabled for this endpoint. Requires quota_handlers to be configured. \"org_id\" and \"system_id\" require rh-identity authentication; falls back to user_id when rh-identity data is unavailable.",
                            "title": "Quota subject"
                        }
                    },
                    "title": "RlsapiV1Configuration",
                    "type": "object"
                },
                "RlsapiV1Context": {
                    "additionalProperties": false,
                    "description": "Context data for rlsapi v1 /infer request.\n\nAttributes:\n    stdin: Redirect input read by command-line-assistant.\n    attachments: Attachment object received by the client.\n    terminal: Terminal object received by the client.\n    systeminfo: System information object received by the client.\n    cla: Command Line Assistant information.",
                    "properties": {
                        "stdin": {
                            "default": "",
                            "description": "Redirect input from stdin",
                            "examples": [
                                "piped input from previous command"
                            ],
                            "maxLength": 65536,
                            "title": "Stdin",
                            "type": "string"
                        },
                        "attachments": {
                            "$ref": "`#/components/schemas/`RlsapiV1Attachment",
                            "description": "File attachment data"
                        },
                        "terminal": {
                            "$ref": "`#/components/schemas/`RlsapiV1Terminal",
                            "description": "Terminal output context"
                        },
                        "systeminfo": {
                            "$ref": "`#/components/schemas/`RlsapiV1SystemInfo",
                            "description": "Client system information"
                        },
                        "cla": {
                            "$ref": "`#/components/schemas/`RlsapiV1CLA",
                            "description": "Command line assistant metadata"
                        }
                    },
                    "title": "RlsapiV1Context",
                    "type": "object"
                },
                "RlsapiV1InferData": {
                    "additionalProperties": false,
                    "description": "Response data for rlsapi v1 /infer endpoint.\n\nAttributes:\n    text: The generated response text.\n    request_id: Unique identifier for the request.\n    tool_calls: MCP tool calls made during inference (verbose mode only).\n    tool_results: Results from MCP tool calls (verbose mode only).\n    rag_chunks: RAG chunks retrieved from documentation (verbose mode only).\n    referenced_documents: Source documents referenced (verbose mode only).\n    input_tokens: Number of input tokens consumed (verbose mode only).\n    output_tokens: Number of output tokens generated (verbose mode only).",
                    "properties": {
                        "text": {
                            "description": "Generated response text",
                            "examples": [
                                "To list files in Linux, use the `ls` command."
                            ],
                            "title": "Text",
                            "type": "string"
                        },
                        "request_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Unique request identifier",
                            "examples": [
                                "01JDKR8N7QW9ZMXVGK3PB5TQWZ"
                            ],
                            "title": "Request Id"
                        },
                        "tool_calls": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Tool calls made during inference (requires include_metadata=true)",
                            "title": "Tool Calls"
                        },
                        "tool_results": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Results from tool calls (requires include_metadata=true)",
                            "title": "Tool Results"
                        },
                        "rag_chunks": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Retrieved RAG documentation chunks (requires include_metadata=true)",
                            "title": "Rag Chunks"
                        },
                        "referenced_documents": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Source documents referenced in answer (requires include_metadata=true)",
                            "title": "Referenced Documents"
                        },
                        "input_tokens": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Number of input tokens consumed (requires include_metadata=true)",
                            "title": "Input Tokens"
                        },
                        "output_tokens": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Number of output tokens generated (requires include_metadata=true)",
                            "title": "Output Tokens"
                        }
                    },
                    "required": [
                        "text"
                    ],
                    "title": "RlsapiV1InferData",
                    "type": "object"
                },
                "RlsapiV1InferRequest": {
                    "additionalProperties": false,
                    "description": "RHEL Lightspeed rlsapi v1 /infer request.\n\nAttributes:\n    question: User question string.\n    context: Context with system info, terminal output, etc. (defaults provided).\n    skip_rag: Reserved for future use. RAG retrieval is not yet implemented.\n    include_metadata: Request extended response with debugging metadata (dev/testing only).\n\nExample:\n    ```python\n    request = RlsapiV1InferRequest(\n        question=\"How do I list files?\",\n        context=RlsapiV1Context(\n            systeminfo=RlsapiV1SystemInfo(os=\"RHEL\", version=\"9.3\"),\n            terminal=RlsapiV1Terminal(output=\"bash: command not found\"),\n        ),\n    )\n    ```",
                    "properties": {
                        "question": {
                            "description": "User question",
                            "examples": [
                                "How do I list files?",
                                "How do I configure SELinux?"
                            ],
                            "maxLength": 32768,
                            "minLength": 1,
                            "title": "Question",
                            "type": "string"
                        },
                        "context": {
                            "$ref": "`#/components/schemas/`RlsapiV1Context",
                            "description": "Optional context (system info, terminal output, stdin, attachments)"
                        },
                        "skip_rag": {
                            "default": false,
                            "description": "Reserved for future use. RAG retrieval is not yet implemented.",
                            "examples": [
                                false,
                                true
                            ],
                            "title": "Skip Rag",
                            "type": "boolean"
                        },
                        "include_metadata": {
                            "default": false,
                            "description": "[Development/Testing Only] Return extended response with debugging metadata (tool_calls, rag_chunks, tokens). Only honored when allow_verbose_infer is enabled. Not available in production.",
                            "examples": [
                                false,
                                true
                            ],
                            "title": "Include Metadata",
                            "type": "boolean"
                        }
                    },
                    "required": [
                        "question"
                    ],
                    "title": "RlsapiV1InferRequest",
                    "type": "object"
                },
                "RlsapiV1InferResponse": {
                    "additionalProperties": false,
                    "description": "RHEL Lightspeed rlsapi v1 /infer response.\n\nAttributes:\n    data: Response data containing text and request_id.",
                    "examples": [
                        {
                            "data": {
                                "request_id": "01JDKR8N7QW9ZMXVGK3PB5TQWZ",
                                "text": "To list files in Linux, use the `ls` command."
                            }
                        }
                    ],
                    "properties": {
                        "data": {
                            "$ref": "`#/components/schemas/`RlsapiV1InferData",
                            "description": "Response data containing text and request_id"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "RlsapiV1InferResponse",
                    "type": "object"
                },
                "RlsapiV1SystemInfo": {
                    "additionalProperties": false,
                    "description": "System information from rlsapi v1 context.\n\nAttributes:\n    os: The operating system of the client machine.\n    version: The version of the operating system.\n    arch: The architecture of the client machine.\n    system_id: The id of the client machine.",
                    "properties": {
                        "os": {
                            "default": "",
                            "description": "Operating system name",
                            "examples": [
                                "RHEL"
                            ],
                            "pattern": "^[a-zA-Z0-9._ \\-]*$",
                            "title": "Os",
                            "type": "string"
                        },
                        "version": {
                            "default": "",
                            "description": "Operating system version",
                            "examples": [
                                "9.3",
                                "8.10"
                            ],
                            "pattern": "^[a-zA-Z0-9._ \\-]*$",
                            "title": "Version",
                            "type": "string"
                        },
                        "arch": {
                            "default": "",
                            "description": "System architecture",
                            "examples": [
                                "x86_64",
                                "aarch64"
                            ],
                            "pattern": "^[a-zA-Z0-9._ \\-]*$",
                            "title": "Arch",
                            "type": "string"
                        },
                        "id": {
                            "default": "",
                            "description": "Client machine ID",
                            "examples": [
                                "01JDKR8N7QW9ZMXVGK3PB5TQWZ"
                            ],
                            "pattern": "^[a-zA-Z0-9._\\-]*$",
                            "title": "Id",
                            "type": "string"
                        }
                    },
                    "title": "RlsapiV1SystemInfo",
                    "type": "object"
                },
                "RlsapiV1Terminal": {
                    "additionalProperties": false,
                    "description": "Terminal output from rlsapi v1 context.\n\nAttributes:\n    output: The textual contents of the terminal read on the client machine.",
                    "properties": {
                        "output": {
                            "default": "",
                            "description": "Terminal output from client",
                            "examples": [
                                "bash: command not found",
                                "Permission denied"
                            ],
                            "maxLength": 65536,
                            "title": "Output",
                            "type": "string"
                        }
                    },
                    "title": "RlsapiV1Terminal",
                    "type": "object"
                },
                "SQLiteDatabaseConfiguration": {
                    "additionalProperties": false,
                    "description": "SQLite database configuration.",
                    "properties": {
                        "db_path": {
                            "description": "Path to file where SQLite database is stored",
                            "title": "DB path",
                            "type": "string"
                        }
                    },
                    "required": [
                        "db_path"
                    ],
                    "title": "SQLiteDatabaseConfiguration",
                    "type": "object"
                },
                "SavedPromptsConfiguration": {
                    "additionalProperties": false,
                    "description": "Configuration for saved prompts feature limits.\n\nControls the maximum number of prompts a user can save, the maximum\ndisplay name (title) length, and the maximum prompt content length.\nAll fields are optional and default to values defined in constants.\n\nAttributes:\n    max_prompts_per_user: Maximum number of saved prompts allowed per user.\n    max_display_name_length: Maximum character length for the prompt display name.\n    max_content_length: Maximum character length for the prompt content body.",
                    "properties": {
                        "max_prompts_per_user": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Maximum number of saved prompts a user can create. Defaults to 50. Cannot exceed 200.",
                            "title": "Max prompts per user"
                        },
                        "max_display_name_length": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Maximum character length for prompt display name (title). Defaults to 255. Cannot exceed 255.",
                            "title": "Max display name length"
                        },
                        "max_content_length": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Maximum character length for the prompt content body. Defaults to 10000. Cannot exceed 30000.",
                            "title": "Max content length"
                        }
                    },
                    "title": "SavedPromptsConfiguration",
                    "type": "object"
                },
                "SearchRankingOptions": {
                    "description": "Options for ranking and filtering search results.\n\nThis class configures how search results are ranked and filtered. You can use algorithm-based\nrerankers (weighted, RRF) or neural rerankers. Defaults from VectorStoresConfig are\nused when parameters are not provided.\n\nExamples:\n    # Weighted ranker with custom alpha\n    SearchRankingOptions(ranker=\"weighted\", alpha=0.7)\n\n    # RRF ranker with custom impact factor\n    SearchRankingOptions(ranker=\"rrf\", impact_factor=50.0)\n\n    # Use config defaults (just specify ranker type)\n    SearchRankingOptions(ranker=\"weighted\")  # Uses alpha from VectorStoresConfig\n\n    # Score threshold filtering\n    SearchRankingOptions(ranker=\"weighted\", score_threshold=0.5)\n\n:param ranker: (Optional) Name of the ranking algorithm to use. Supported values:\n    - \"weighted\": Weighted combination of vector and keyword scores\n    - \"rrf\": Reciprocal Rank Fusion algorithm\n    - \"neural\": Neural reranking model (requires model parameter, Part II)\n    Note: For OpenAI API compatibility, any string value is accepted, but only the above values are supported.\n:param score_threshold: (Optional) Minimum relevance score threshold for results. Default: 0.0\n:param alpha: (Optional) Weight factor for weighted ranker (0-1).\n    - 0.0 = keyword only\n    - 0.5 = equal weight (default)\n    - 1.0 = vector only\n    Only used when ranker=\"weighted\" and weights is not provided.\n    Falls back to VectorStoresConfig.chunk_retrieval_params.weighted_search_alpha if not provided.\n:param impact_factor: (Optional) Impact factor (k) for RRF algorithm.\n    Lower values emphasize higher-ranked results. Default: 60.0 (optimal from research).\n    Only used when ranker=\"rrf\".\n    Falls back to VectorStoresConfig.chunk_retrieval_params.rrf_impact_factor if not provided.\n:param weights: (Optional) Dictionary of weights for combining different signal types.\n    Keys can be \"vector\", \"keyword\", \"neural\". Values should sum to 1.0.\n    Used when combining algorithm-based reranking with neural reranking (Part II).\n    Example: {\"vector\": 0.3, \"keyword\": 0.3, \"neural\": 0.4}\n:param model: (Optional) Model identifier for neural reranker (e.g., \"vllm/Qwen3-Reranker-0.6B\").\n    Required when ranker=\"neural\" or when weights contains \"neural\" (Part II).",
                    "properties": {
                        "ranker": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Ranker"
                        },
                        "score_threshold": {
                            "type": "number",
                            "nullable": true,
                            "default": 0.0,
                            "title": "Score Threshold"
                        },
                        "alpha": {
                            "type": "number",
                            "nullable": true,
                            "default": null,
                            "description": "Weight factor for weighted ranker",
                            "title": "Alpha"
                        },
                        "impact_factor": {
                            "type": "number",
                            "nullable": true,
                            "default": null,
                            "description": "Impact factor for RRF algorithm",
                            "title": "Impact Factor"
                        },
                        "weights": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Weights for combining vector, keyword, and neural scores. Keys: 'vector', 'keyword', 'neural'",
                            "title": "Weights"
                        },
                        "model": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Model identifier for neural reranker",
                            "title": "Model"
                        }
                    },
                    "title": "SearchRankingOptions",
                    "type": "object"
                },
                "ServiceConfiguration": {
                    "additionalProperties": false,
                    "description": "Service configuration.\n\nLightspeed Core Stack is a REST API service that accepts requests on a\nspecified hostname and port. It is also possible to enable authentication\nand specify the number of Uvicorn workers. When more workers are specified,\nthe service can handle requests concurrently.",
                    "properties": {
                        "host": {
                            "default": "localhost",
                            "description": "Service hostname",
                            "title": "Host",
                            "type": "string"
                        },
                        "port": {
                            "default": 8080,
                            "description": "Service port",
                            "minimum": 0,
                            "title": "Port",
                            "type": "integer"
                        },
                        "base_url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Externally reachable base URL for the service; needed for A2A support.",
                            "title": "Base URL"
                        },
                        "auth_enabled": {
                            "default": false,
                            "description": "Enables the authentication subsystem",
                            "title": "Authentication enabled",
                            "type": "boolean"
                        },
                        "workers": {
                            "default": 1,
                            "description": "Number of Uvicorn worker processes to start",
                            "minimum": 0,
                            "title": "Number of workers",
                            "type": "integer"
                        },
                        "color_log": {
                            "default": true,
                            "description": "Enables colorized logging",
                            "title": "Color log",
                            "type": "boolean"
                        },
                        "access_log": {
                            "default": true,
                            "description": "Enables logging of all access information",
                            "title": "Access log",
                            "type": "boolean"
                        },
                        "tls_config": {
                            "$ref": "`#/components/schemas/`TLSConfiguration",
                            "description": "Transport Layer Security configuration for HTTPS support",
                            "title": "TLS configuration"
                        },
                        "root_path": {
                            "default": "",
                            "description": "ASGI root path for serving behind a reverse proxy on a subpath",
                            "title": "Root path",
                            "type": "string"
                        },
                        "cors": {
                            "$ref": "`#/components/schemas/`CORSConfiguration",
                            "description": "Cross-Origin Resource Sharing configuration for cross-domain requests",
                            "title": "CORS configuration"
                        }
                    },
                    "title": "ServiceConfiguration",
                    "type": "object"
                },
                "ServiceUnavailableResponse": {
                    "description": "503 Backend Unavailable.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "Connection error while trying to reach backend service.",
                                "response": "Unable to connect to OGX"
                            },
                            "label": "llama stack"
                        },
                        {
                            "detail": {
                                "cause": "Failed to connect to Kubernetes API: Service Unavailable (status 503)",
                                "response": "Unable to connect to Kubernetes API"
                            },
                            "label": "kubernetes api"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "ServiceUnavailableResponse",
                    "type": "object"
                },
                "ShieldModerationBlocked": {
                    "description": "Shield moderation blocked the content; refusal details are present.",
                    "properties": {
                        "decision": {
                            "const": "blocked",
                            "default": "blocked",
                            "title": "Decision",
                            "type": "string"
                        },
                        "message": {
                            "title": "Message",
                            "type": "string"
                        },
                        "moderation_id": {
                            "title": "Moderation Id",
                            "type": "string"
                        },
                        "refusal_response": {
                            "$ref": "`#/components/schemas/`OpenAIResponseMessage"
                        }
                    },
                    "required": [
                        "message",
                        "moderation_id",
                        "refusal_response"
                    ],
                    "title": "ShieldModerationBlocked",
                    "type": "object"
                },
                "ShieldModerationPassed": {
                    "description": "Shield moderation passed; no refusal.",
                    "properties": {
                        "decision": {
                            "const": "passed",
                            "default": "passed",
                            "title": "Decision",
                            "type": "string"
                        }
                    },
                    "title": "ShieldModerationPassed",
                    "type": "object"
                },
                "ShieldsResponse": {
                    "description": "Model representing a response to shields request.",
                    "examples": [
                        {
                            "shields": [
                                {
                                    "identifier": "lightspeed_question_validity-shield",
                                    "params": {},
                                    "provider_id": "lightspeed_question_validity",
                                    "provider_resource_id": "lightspeed_question_validity-shield",
                                    "type": "shield"
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "shields": {
                            "description": "List of shields available",
                            "items": {
                                "additionalProperties": true,
                                "type": "object"
                            },
                            "title": "Shields",
                            "type": "array"
                        }
                    },
                    "required": [
                        "shields"
                    ],
                    "title": "ShieldsResponse",
                    "type": "object"
                },
                "SkillsConfiguration": {
                    "additionalProperties": false,
                    "description": "Agent skills configuration.\n\nSpecifies paths to skill directories. Skill metadata (name, description)\nis read from SKILL.md frontmatter at startup.\n\nEach path can point to either:\n- A directory containing a SKILL.md file (single skill)\n- A directory containing subdirectories with SKILL.md files (multiple skills)\n\nPaths are validated at startup to ensure they exist and contain valid SKILL.md files.",
                    "properties": {
                        "paths": {
                            "description": "Paths to skill directories or directories containing skill subdirectories.",
                            "items": {
                                "format": "path",
                                "type": "string"
                            },
                            "title": "Skill paths",
                            "type": "array"
                        }
                    },
                    "title": "SkillsConfiguration",
                    "type": "object"
                },
                "SolrVectorSearchRequest": {
                    "additionalProperties": false,
                    "description": "LCORE Solr inline RAG options for vector_io.query (mode and provider filters).\n\nAttributes:\n    mode: Solr vector_io search mode. When omitted, the server default (hybrid) is used.\n    filters: Solr provider filter payload passed through as params['solr'].\n\nLegacy clients may send a plain JSON object with filter keys only;\nthat object is accepted as filters with mode unset (server default applies).",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Solr vector_io search mode. When omitted, the server default ('hybrid') is used.",
                            "examples": [
                                "hybrid",
                                "semantic",
                                "lexical"
                            ],
                            "title": "Mode"
                        },
                        "filters": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Solr provider filter payload passed through as params['solr']. Supports structured metadata filters (eq, ne, in, nin comparison operators). Legacy filter-only objects (e.g. fq) are still accepted.",
                            "examples": [
                                {
                                    "filters": {
                                        "key": "product",
                                        "type": "eq",
                                        "value": "openshift_container_platform"
                                    }
                                },
                                {
                                    "filters": {
                                        "filters": [
                                            {
                                                "key": "product",
                                                "type": "eq",
                                                "value": "openshift_container_platform"
                                            },
                                            {
                                                "key": "version",
                                                "type": "in",
                                                "value": [
                                                    "4.14",
                                                    "4.15",
                                                    "4.16"
                                                ]
                                            }
                                        ],
                                        "type": "and"
                                    }
                                },
                                {
                                    "fq": [
                                        "product:*openshift*"
                                    ]
                                }
                            ],
                            "title": "Filters"
                        }
                    },
                    "title": "SolrVectorSearchRequest",
                    "type": "object"
                },
                "SplunkConfiguration": {
                    "additionalProperties": false,
                    "description": "Splunk HEC (HTTP Event Collector) configuration.\n\nSplunk HEC allows sending events directly to Splunk over HTTP/HTTPS.\nThis configuration is used to send telemetry events for inference\nrequests to the corporate Splunk deployment.\n\nUseful resources:\n\n  - [Splunk HEC Docs](https://docs.splunk.com/Documentation/SplunkCloud)\n  - [About HEC](https://docs.splunk.com/Documentation/Splunk/latest/Data)",
                    "properties": {
                        "enabled": {
                            "default": false,
                            "description": "Enable or disable Splunk HEC integration.",
                            "title": "Enabled",
                            "type": "boolean"
                        },
                        "url": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Splunk HEC endpoint URL.",
                            "title": "HEC URL"
                        },
                        "token_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to file containing the Splunk HEC authentication token.",
                            "title": "Token path"
                        },
                        "index": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Target Splunk index for events.",
                            "title": "Index"
                        },
                        "source": {
                            "default": "lightspeed-stack",
                            "description": "Event source identifier.",
                            "title": "Source",
                            "type": "string"
                        },
                        "timeout": {
                            "default": 5,
                            "description": "HTTP timeout in seconds for HEC requests.",
                            "minimum": 0,
                            "title": "Timeout",
                            "type": "integer"
                        },
                        "verify_ssl": {
                            "default": true,
                            "description": "Whether to verify SSL certificates for HEC endpoint.",
                            "title": "Verify SSL",
                            "type": "boolean"
                        }
                    },
                    "title": "SplunkConfiguration",
                    "type": "object"
                },
                "StartEventData": {
                    "description": "Payload for event: \"start\".",
                    "properties": {
                        "conversation_id": {
                            "title": "Conversation Id",
                            "type": "string"
                        },
                        "request_id": {
                            "title": "Request Id",
                            "type": "string"
                        }
                    },
                    "required": [
                        "conversation_id",
                        "request_id"
                    ],
                    "title": "StartEventData",
                    "type": "object"
                },
                "StartStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE stream start body.",
                    "properties": {
                        "event": {
                            "const": "start",
                            "default": "start",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`StartEventData"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "StartStreamPayload",
                    "type": "object"
                },
                "StatusResponse": {
                    "description": "Model representing a response to a status request.\n\nAttributes:\n    functionality: The functionality of the service.\n    status: The status of the service.",
                    "examples": [
                        {
                            "functionality": "feedback",
                            "status": {
                                "enabled": true
                            }
                        }
                    ],
                    "properties": {
                        "functionality": {
                            "description": "The functionality of the service",
                            "examples": [
                                "feedback"
                            ],
                            "title": "Functionality",
                            "type": "string"
                        },
                        "status": {
                            "additionalProperties": true,
                            "description": "The status of the service",
                            "examples": [
                                {
                                    "enabled": true
                                }
                            ],
                            "title": "Status",
                            "type": "object"
                        }
                    },
                    "required": [
                        "functionality",
                        "status"
                    ],
                    "title": "StatusResponse",
                    "type": "object"
                },
                "StreamPayloadBase": {
                    "additionalProperties": false,
                    "description": "Base for streaming SSE JSON payloads.",
                    "properties": {},
                    "title": "StreamPayloadBase",
                    "type": "object"
                },
                "StreamingInterruptRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a request to interrupt an active streaming query.\n\nAttributes:\n    request_id: Unique ID of the active streaming request to interrupt.",
                    "examples": [
                        {
                            "request_id": "123e4567-e89b-12d3-a456-426614174000"
                        }
                    ],
                    "properties": {
                        "request_id": {
                            "description": "The active streaming request ID to interrupt",
                            "examples": [
                                "123e4567-e89b-12d3-a456-426614174000"
                            ],
                            "title": "Request Id",
                            "type": "string"
                        }
                    },
                    "required": [
                        "request_id"
                    ],
                    "title": "StreamingInterruptRequest",
                    "type": "object"
                },
                "StreamingInterruptResponse": {
                    "description": "Model representing a response to a streaming interrupt request.\n\nAttributes:\n    request_id: The streaming request ID targeted by the interrupt call.\n    interrupted: Whether an in-progress stream was interrupted.\n    message: Human-readable interruption status message.",
                    "examples": [
                        {
                            "interrupted": true,
                            "message": "Streaming request interrupted",
                            "request_id": "123e4567-e89b-12d3-a456-426614174000"
                        }
                    ],
                    "properties": {
                        "request_id": {
                            "description": "The streaming request ID targeted by the interrupt call",
                            "examples": [
                                "123e4567-e89b-12d3-a456-426614174000"
                            ],
                            "title": "Request Id",
                            "type": "string"
                        },
                        "interrupted": {
                            "description": "Whether an in-progress stream was interrupted",
                            "examples": [
                                true
                            ],
                            "title": "Interrupted",
                            "type": "boolean"
                        },
                        "message": {
                            "description": "Human-readable interruption status message",
                            "examples": [
                                "Streaming request interrupted"
                            ],
                            "title": "Message",
                            "type": "string"
                        }
                    },
                    "required": [
                        "request_id",
                        "interrupted",
                        "message"
                    ],
                    "title": "StreamingInterruptResponse",
                    "type": "object"
                },
                "StreamingQueryResponse": {
                    "description": "Documentation-only model for streaming query responses using Server-Sent Events (SSE).",
                    "examples": [
                        "data: {\"event\": \"start\", \"data\": {\"conversation_id\": \"123e4567-e89b-12d3-a456-426614174000\", \"request_id\": \"123e4567-e89b-12d3-a456-426614174001\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 0, \"token\": \"No Violation\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 1, \"token\": \"\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 2, \"token\": \"Hello\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 3, \"token\": \"!\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 4, \"token\": \" How\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 5, \"token\": \" can\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 6, \"token\": \" I\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 7, \"token\": \" assist\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 8, \"token\": \" you\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 9, \"token\": \" today\"}}\n\ndata: {\"event\": \"token\", \"data\": {\"id\": 10, \"token\": \"?\"}}\n\ndata: {\"event\": \"turn_complete\", \"data\": {\"token\": \"Hello! How can I assist you today?\"}}\n\ndata: {\"event\": \"end\", \"data\": {\"referenced_documents\": [], \"truncated\": null, \"input_tokens\": 11, \"output_tokens\": 19}, \"available_quotas\": {}}\n\n"
                    ],
                    "properties": {},
                    "title": "StreamingQueryResponse",
                    "type": "object"
                },
                "TLSConfiguration": {
                    "additionalProperties": false,
                    "description": "TLS configuration.\n\nTransport Layer Security (TLS) is a cryptographic protocol designed to\nprovide communications security over a computer network, such as the\nInternet. The protocol is widely used in applications such as email,\ninstant messaging, and voice over IP, but its use in securing HTTPS remains\nthe most publicly visible.\n\nUseful resources:\n\n  - [FastAPI HTTPS Deployment](https://fastapi.tiangolo.com/deployment/https/)\n  - [Transport Layer Security Overview](https://en.wikipedia.org/wiki/Transport_Layer_Security)\n  - [What is TLS](https://www.ssltrust.eu/learning/ssl/transport-layer-security-tls)",
                    "properties": {
                        "tls_certificate_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "SSL/TLS certificate file path for HTTPS support.",
                            "title": "TLS certificate path"
                        },
                        "tls_key_path": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "SSL/TLS private key file path for HTTPS support.",
                            "title": "TLS key path"
                        },
                        "tls_key_password": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to file containing the password to decrypt the SSL/TLS private key.",
                            "title": "SSL/TLS key password path"
                        }
                    },
                    "title": "TLSConfiguration",
                    "type": "object"
                },
                "TokenChunkData": {
                    "description": "Structured data for token and turn-complete stream lines.",
                    "properties": {
                        "id": {
                            "title": "Id",
                            "type": "integer"
                        },
                        "token": {
                            "title": "Token",
                            "type": "string"
                        }
                    },
                    "required": [
                        "id",
                        "token"
                    ],
                    "title": "TokenChunkData",
                    "type": "object"
                },
                "TokenCounter": {
                    "description": "Model representing token counter.\n\nAttributes:\n    input_tokens: number of tokens sent to LLM\n    output_tokens: number of tokens received from LLM\n    input_tokens_counted: number of input tokens counted by the handler\n    llm_calls: number of LLM calls",
                    "properties": {
                        "input_tokens": {
                            "default": 0,
                            "title": "Input Tokens",
                            "type": "integer"
                        },
                        "output_tokens": {
                            "default": 0,
                            "title": "Output Tokens",
                            "type": "integer"
                        },
                        "input_tokens_counted": {
                            "default": 0,
                            "title": "Input Tokens Counted",
                            "type": "integer"
                        },
                        "llm_calls": {
                            "default": 0,
                            "title": "Llm Calls",
                            "type": "integer"
                        }
                    },
                    "title": "TokenCounter",
                    "type": "object"
                },
                "TokenStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE token delta (event: \"token\").",
                    "properties": {
                        "event": {
                            "const": "token",
                            "default": "token",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`TokenChunkData"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "TokenStreamPayload",
                    "type": "object"
                },
                "ToolCallStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE tool call summary.",
                    "properties": {
                        "event": {
                            "const": "tool_call",
                            "default": "tool_call",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`ToolCallSummary"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "ToolCallStreamPayload",
                    "type": "object"
                },
                "ToolCallSummary": {
                    "description": "Model representing a tool call made during response generation (for tool_calls list).",
                    "properties": {
                        "id": {
                            "description": "ID of the tool call",
                            "title": "Id",
                            "type": "string"
                        },
                        "name": {
                            "description": "Name of the tool called",
                            "title": "Name",
                            "type": "string"
                        },
                        "args": {
                            "additionalProperties": true,
                            "description": "Arguments passed to the tool",
                            "title": "Args",
                            "type": "object"
                        },
                        "type": {
                            "default": "tool_call",
                            "description": "Type indicator for tool call",
                            "title": "Type",
                            "type": "string"
                        }
                    },
                    "required": [
                        "id",
                        "name"
                    ],
                    "title": "ToolCallSummary",
                    "type": "object"
                },
                "ToolInfoSummary": {
                    "description": "Model representing metadata for a single tool exposed by MCP list tools.",
                    "properties": {
                        "name": {
                            "description": "Tool name",
                            "title": "Name",
                            "type": "string"
                        },
                        "description": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Human-readable tool description",
                            "title": "Description"
                        },
                        "input_schema": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "JSON schema for the tool input",
                            "title": "Input Schema"
                        }
                    },
                    "required": [
                        "name"
                    ],
                    "title": "ToolInfoSummary",
                    "type": "object"
                },
                "ToolResultStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE tool result summary.",
                    "properties": {
                        "event": {
                            "const": "tool_result",
                            "default": "tool_result",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`ToolResultSummary"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "ToolResultStreamPayload",
                    "type": "object"
                },
                "ToolResultSummary": {
                    "description": "Model representing a result from a tool call (for tool_results list).",
                    "properties": {
                        "id": {
                            "description": "ID of the tool call/result, matches the corresponding tool call 'id'",
                            "title": "Id",
                            "type": "string"
                        },
                        "status": {
                            "description": "Status of the tool execution (e.g., 'success')",
                            "title": "Status",
                            "type": "string"
                        },
                        "content": {
                            "description": "Content/result returned from the tool",
                            "title": "Content",
                            "type": "string"
                        },
                        "type": {
                            "default": "tool_result",
                            "description": "Type indicator for tool result",
                            "title": "Type",
                            "type": "string"
                        },
                        "round": {
                            "description": "Round number or step of tool execution",
                            "title": "Round",
                            "type": "integer"
                        }
                    },
                    "required": [
                        "id",
                        "status",
                        "content",
                        "round"
                    ],
                    "title": "ToolResultSummary",
                    "type": "object"
                },
                "ToolsResponse": {
                    "description": "Model representing a response to tools request.",
                    "examples": [
                        {
                            "tools": [
                                {
                                    "description": "Read contents of a file from the filesystem",
                                    "identifier": "filesystem_read",
                                    "parameters": [
                                        {
                                            "default": null,
                                            "description": "Path to the file to read",
                                            "name": "path",
                                            "parameter_type": "string",
                                            "required": true
                                        }
                                    ],
                                    "provider_id": "model-context-protocol",
                                    "server_source": "http://localhost:3000",
                                    "toolgroup_id": "filesystem-tools",
                                    "type": "tool"
                                }
                            ]
                        }
                    ],
                    "properties": {
                        "tools": {
                            "description": "List of tools available from all configured MCP servers and built-in toolgroups",
                            "items": {
                                "additionalProperties": true,
                                "type": "object"
                            },
                            "title": "Tools",
                            "type": "array"
                        }
                    },
                    "required": [
                        "tools"
                    ],
                    "title": "ToolsResponse",
                    "type": "object"
                },
                "Transcript": {
                    "description": "Model representing a transcript entry to be stored.",
                    "properties": {
                        "metadata": {
                            "$ref": "`#/components/schemas/`TranscriptMetadata"
                        },
                        "redacted_query": {
                            "title": "Redacted Query",
                            "type": "string"
                        },
                        "query_is_valid": {
                            "title": "Query Is Valid",
                            "type": "boolean"
                        },
                        "llm_response": {
                            "title": "Llm Response",
                            "type": "string"
                        },
                        "rag_chunks": {
                            "items": {
                                "additionalProperties": true,
                                "type": "object"
                            },
                            "title": "Rag Chunks",
                            "type": "array"
                        },
                        "truncated": {
                            "title": "Truncated",
                            "type": "boolean"
                        },
                        "attachments": {
                            "items": {
                                "additionalProperties": true,
                                "type": "object"
                            },
                            "title": "Attachments",
                            "type": "array"
                        },
                        "tool_calls": {
                            "items": {
                                "additionalProperties": true,
                                "type": "object"
                            },
                            "title": "Tool Calls",
                            "type": "array"
                        },
                        "tool_results": {
                            "items": {
                                "additionalProperties": true,
                                "type": "object"
                            },
                            "title": "Tool Results",
                            "type": "array"
                        }
                    },
                    "required": [
                        "metadata",
                        "redacted_query",
                        "query_is_valid",
                        "llm_response",
                        "truncated"
                    ],
                    "title": "Transcript",
                    "type": "object"
                },
                "TranscriptMetadata": {
                    "description": "Metadata for a transcript entry.",
                    "properties": {
                        "provider": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Provider"
                        },
                        "model": {
                            "title": "Model",
                            "type": "string"
                        },
                        "query_provider": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Query Provider"
                        },
                        "query_model": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "title": "Query Model"
                        },
                        "user_id": {
                            "title": "User Id",
                            "type": "string"
                        },
                        "conversation_id": {
                            "title": "Conversation Id",
                            "type": "string"
                        },
                        "timestamp": {
                            "title": "Timestamp",
                            "type": "string"
                        }
                    },
                    "required": [
                        "model",
                        "user_id",
                        "conversation_id",
                        "timestamp"
                    ],
                    "title": "TranscriptMetadata",
                    "type": "object"
                },
                "TrustedProxyConfiguration": {
                    "additionalProperties": false,
                    "description": "Configuration for trusted-proxy auth module.",
                    "properties": {
                        "user_header": {
                            "default": "X-Forwarded-User",
                            "description": "HTTP header containing the forwarded user identity.",
                            "title": "User identity header",
                            "type": "string"
                        },
                        "allowed_service_accounts": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Optional allowlist of Kubernetes ServiceAccount identities permitted to act as trusted proxies. When set to null/omitted, any ServiceAccount with a valid token is accepted. When set to a non-empty list, only the listed ServiceAccounts are allowed. An empty list behaves the same as null (no restriction).",
                            "title": "Allowed service accounts"
                        }
                    },
                    "title": "TrustedProxyConfiguration",
                    "type": "object"
                },
                "TrustedProxyServiceAccount": {
                    "additionalProperties": false,
                    "description": "A Kubernetes ServiceAccount identity for trusted-proxy allowlist.",
                    "properties": {
                        "namespace": {
                            "description": "Kubernetes namespace of the ServiceAccount.",
                            "title": "Namespace",
                            "type": "string"
                        },
                        "name": {
                            "description": "Name of the Kubernetes ServiceAccount.",
                            "title": "Name",
                            "type": "string"
                        }
                    },
                    "required": [
                        "namespace",
                        "name"
                    ],
                    "title": "TrustedProxyServiceAccount",
                    "type": "object"
                },
                "TurnCompleteStreamPayload": {
                    "additionalProperties": false,
                    "description": "SSE turn completion (same data shape as token).",
                    "properties": {
                        "event": {
                            "const": "turn_complete",
                            "default": "turn_complete",
                            "title": "Event",
                            "type": "string"
                        },
                        "data": {
                            "$ref": "`#/components/schemas/`TokenChunkData"
                        }
                    },
                    "required": [
                        "data"
                    ],
                    "title": "TurnCompleteStreamPayload",
                    "type": "object"
                },
                "TurnSummary": {
                    "description": "Summary of a turn in llama stack.",
                    "properties": {
                        "id": {
                            "default": "",
                            "description": "ID of the response",
                            "title": "Id",
                            "type": "string"
                        },
                        "llm_response": {
                            "default": "",
                            "title": "Llm Response",
                            "type": "string"
                        },
                        "tool_calls": {
                            "items": {
                                "$ref": "`#/components/schemas/`ToolCallSummary"
                            },
                            "title": "Tool Calls",
                            "type": "array"
                        },
                        "tool_results": {
                            "items": {
                                "$ref": "`#/components/schemas/`ToolResultSummary"
                            },
                            "title": "Tool Results",
                            "type": "array"
                        },
                        "rag_chunks": {
                            "items": {
                                "$ref": "`#/components/schemas/`RAGChunk"
                            },
                            "title": "Rag Chunks",
                            "type": "array"
                        },
                        "referenced_documents": {
                            "items": {
                                "$ref": "`#/components/schemas/`ReferencedDocument"
                            },
                            "title": "Referenced Documents",
                            "type": "array"
                        },
                        "token_usage": {
                            "$ref": "`#/components/schemas/`TokenCounter"
                        },
                        "output_items": {
                            "description": "Structured response output items, captured for compacted-mode turn persistence (LCORE-1572). Empty on the non-compacted path.",
                            "items": {
                                "discriminator": {
                                    "mapping": {
                                        "file_search_call": "`#/components/schemas/`OpenAIResponseOutputMessageFileSearchToolCall",
                                        "function_call": "`#/components/schemas/`OpenAIResponseOutputMessageFunctionToolCall",
                                        "mcp_approval_request": "`#/components/schemas/`OpenAIResponseMCPApprovalRequest",
                                        "mcp_call": "`#/components/schemas/`OpenAIResponseOutputMessageMCPCall",
                                        "mcp_list_tools": "`#/components/schemas/`OpenAIResponseOutputMessageMCPListTools",
                                        "message": "`#/components/schemas/`OpenAIResponseMessage",
                                        "web_search_call": "`#/components/schemas/`OpenAIResponseOutputMessageWebSearchToolCall"
                                    },
                                    "propertyName": "type"
                                },
                                "oneOf": [
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseMessage"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageWebSearchToolCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageFileSearchToolCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageFunctionToolCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageMCPCall"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseOutputMessageMCPListTools"
                                    },
                                    {
                                        "$ref": "`#/components/schemas/`OpenAIResponseMCPApprovalRequest"
                                    }
                                ]
                            },
                            "title": "Output Items",
                            "type": "array"
                        },
                        "partial_tokens": {
                            "description": "Accumulated text deltas during streaming, used to reconstruct partial content on interruption.",
                            "items": {
                                "type": "string"
                            },
                            "title": "Partial Tokens",
                            "type": "array"
                        },
                        "next_chunk_id": {
                            "default": 0,
                            "description": "Next monotonic SSE chunk index, kept in sync with the inner generator so the interrupt handler can emit a sequentially valid id.",
                            "title": "Next Chunk Id",
                            "type": "integer"
                        }
                    },
                    "title": "TurnSummary",
                    "type": "object"
                },
                "UnauthorizedResponse": {
                    "description": "401 Unauthorized - Missing or invalid credentials.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "No Authorization header found",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "missing header"
                        },
                        {
                            "detail": {
                                "cause": "No token found in Authorization header",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "missing token"
                        },
                        {
                            "detail": {
                                "cause": "Token has expired",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "expired token"
                        },
                        {
                            "detail": {
                                "cause": "Invalid token signature",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "invalid signature"
                        },
                        {
                            "detail": {
                                "cause": "Token signed by unknown key",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "invalid key"
                        },
                        {
                            "detail": {
                                "cause": "Token missing claim: user_id",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "missing claim"
                        },
                        {
                            "detail": {
                                "cause": "Invalid or expired Kubernetes token",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "invalid k8s token"
                        },
                        {
                            "detail": {
                                "cause": "Authentication key server returned invalid data",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "invalid jwk token"
                        },
                        {
                            "detail": {
                                "cause": "MCP server at https://mcp.example.com/v1 requires OAuth",
                                "response": "Missing or invalid credentials provided by client"
                            },
                            "label": "mcp oauth"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "UnauthorizedResponse",
                    "type": "object"
                },
                "UnifiedInferenceProvider": {
                    "additionalProperties": false,
                    "description": "A high-level inference provider entry for unified-mode synthesis.\n\nOperators describe inference providers at this high level (backend-agnostic\nvocabulary) instead of authoring raw Llama Stack provider blocks. The\nsynthesizer (`apply_high_level_inference`) expands each entry into a Llama\nStack `providers.inference` entry, mapping `type` to a `provider_type` and\nemitting `${env.<VAR>}` references for secrets (never literal values).\n\nAttributes:\n    type: Canonical provider identifier. Vendor-neutral so it survives a\n        future backend change; each backend-specific synthesizer maps it to\n        its own provider vocabulary.\n    id: Optional identifier emitted as the Llama Stack provider_id. When\n        omitted, synthesized as type with underscores hyphenated. If set,\n        must be non-empty after stripping whitespace and may contain only\n        lowercase letters, digits, underscores, and hyphens.\n    api_key_env: Name of the environment variable holding the provider API\n        key. Emitted verbatim as `${env.<name>}` so the secret never lands\n        on disk resolved.\n    allowed_models: Optional allow-list of model identifiers passed through\n        to the synthesized provider config.\n    extra: Additional provider-config keys merged verbatim into the\n        synthesized provider's `config` block \u2014 an escape hatch for\n        provider-specific knobs not modeled here.",
                    "properties": {
                        "type": {
                            "description": "Canonical, backend-agnostic provider identifier mapped to a Llama Stack provider_type by the synthesizer.",
                            "enum": [
                                "openai",
                                "ollama",
                                "vllm",
                                "sentence_transformers",
                                "azure",
                                "vertexai",
                                "watsonx",
                                "vllm_rhaiis",
                                "vllm_rhel_ai"
                            ],
                            "title": "Provider type",
                            "type": "string"
                        },
                        "id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Optional identifier emitted as the Llama Stack provider_id. When omitted, synthesized as type with underscores hyphenated. If set, must be non-empty after stripping whitespace and may contain only lowercase letters, digits, underscores, and hyphens.",
                            "title": "Provider ID"
                        },
                        "api_key_env": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Name of the environment variable holding the provider API key. Emitted as a ${env.<name>} reference so the secret is never written to disk in resolved form.",
                            "title": "API key environment variable"
                        },
                        "allowed_models": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "description": "Optional allow-list of model identifiers for this provider.",
                            "title": "Allowed models"
                        },
                        "extra": {
                            "additionalProperties": true,
                            "description": "Additional provider-config keys merged verbatim into the synthesized provider's config block.",
                            "title": "Extra provider config",
                            "type": "object"
                        }
                    },
                    "required": [
                        "type"
                    ],
                    "title": "UnifiedInferenceProvider",
                    "type": "object"
                },
                "UnifiedLlamaStackConfig": {
                    "additionalProperties": false,
                    "description": "Backend-specific knobs for unified-mode Llama Stack synthesis.\n\nPer Decision S5 of the design spike, backend-agnostic high-level sections\n(inference, ...) live at the configuration root, not here. This block holds\nonly the Llama-Stack-specific synthesis controls: which baseline to start\nfrom, an optional profile file, and a raw native_override escape hatch.\n\nAttributes:\n    baseline: Synthesis starting point. \"default\" begins from LCORE's\n        built-in baseline (src/data/default_run.yaml); \"empty\" begins from\n        an empty dict (used by the migration tool for an exact round-trip).\n        Ignored when `profile` is set.\n    profile: Optional path to a user-authored run.yaml-shaped file used as\n        the synthesis baseline. Relative paths resolve against the directory\n        of the loaded lightspeed-stack.yaml.\n    native_override: Raw Llama Stack schema deep-merged last (maps merge\n        recursively, lists and scalars replace). The escape hatch for\n        anything the high-level sections do not express.",
                    "properties": {
                        "baseline": {
                            "default": "default",
                            "description": "Synthesis starting point: 'default' uses LCORE's built-in baseline, 'empty' starts from {}. Ignored when 'profile' is set.",
                            "enum": [
                                "default",
                                "empty"
                            ],
                            "title": "Baseline selector",
                            "type": "string"
                        },
                        "profile": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to a run.yaml-shaped baseline file. Relative paths resolve against the directory of the loaded lightspeed-stack.yaml.",
                            "title": "Profile path"
                        },
                        "native_override": {
                            "additionalProperties": true,
                            "description": "Raw Llama Stack schema deep-merged last (maps merge recursively; lists and scalars replace).",
                            "title": "Native override",
                            "type": "object"
                        }
                    },
                    "title": "UnifiedLlamaStackConfig",
                    "type": "object"
                },
                "UnprocessableEntityResponse": {
                    "description": "422 Unprocessable Entity - Request validation failed.",
                    "examples": [
                        {
                            "detail": {
                                "cause": "Invalid request format. The request body could not be parsed.",
                                "response": "Invalid request format"
                            },
                            "label": "invalid format"
                        },
                        {
                            "detail": {
                                "cause": "Missing required attributes: ['query', 'model', 'provider']",
                                "response": "Missing required attributes"
                            },
                            "label": "missing attributes"
                        },
                        {
                            "detail": {
                                "cause": "Invalid attachment type: must be one of ['text/plain', 'application/json', 'application/yaml', 'application/xml']",
                                "response": "Invalid attribute value"
                            },
                            "label": "invalid value"
                        }
                    ],
                    "properties": {
                        "status_code": {
                            "description": "HTTP status code for the errors response",
                            "title": "Status Code",
                            "type": "integer"
                        },
                        "detail": {
                            "$ref": "`#/components/schemas/`DetailModel",
                            "description": "The detail model containing error summary and cause"
                        }
                    },
                    "required": [
                        "status_code",
                        "detail"
                    ],
                    "title": "UnprocessableEntityResponse",
                    "type": "object"
                },
                "UserDataCollection": {
                    "additionalProperties": false,
                    "description": "User data collection configuration.",
                    "properties": {
                        "feedback_enabled": {
                            "default": false,
                            "description": "When set to true the user feedback is stored and later sent for analysis.",
                            "title": "Feedback enabled",
                            "type": "boolean"
                        },
                        "feedback_storage": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to directory where feedback will be saved for further processing.",
                            "title": "Feedback storage directory"
                        },
                        "transcripts_enabled": {
                            "default": false,
                            "description": "When set to true the conversation history is stored and later sent for analysis.",
                            "title": "Transcripts enabled",
                            "type": "boolean"
                        },
                        "transcripts_storage": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Path to directory where conversation history will be saved for further processing.",
                            "title": "Transcripts storage directory"
                        }
                    },
                    "title": "UserDataCollection",
                    "type": "object"
                },
                "VectorStoreCreateRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a request to create a vector store.\n\nAttributes:\n    name: Name of the vector store.\n    embedding_model: Optional embedding model to use.\n    embedding_dimension: Optional embedding dimension.\n    chunking_strategy: Optional chunking strategy configuration.\n    provider_id: Optional vector store provider identifier.\n    metadata: Optional metadata dictionary for storing session information.",
                    "examples": [
                        {
                            "embedding_dimension": 1536,
                            "embedding_model": "text-embedding-ada-002",
                            "metadata": {
                                "user_id": "user123"
                            },
                            "name": "my_vector_store",
                            "provider_id": "rhdh-docs"
                        }
                    ],
                    "properties": {
                        "name": {
                            "description": "Name of the vector store",
                            "examples": [
                                "my_vector_store"
                            ],
                            "maxLength": 256,
                            "minLength": 1,
                            "title": "Name",
                            "type": "string"
                        },
                        "embedding_model": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Embedding model to use for the vector store",
                            "examples": [
                                "text-embedding-ada-002"
                            ],
                            "title": "Embedding Model"
                        },
                        "embedding_dimension": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Dimension of the embedding vectors",
                            "examples": [
                                1536
                            ],
                            "title": "Embedding Dimension"
                        },
                        "chunking_strategy": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Chunking strategy configuration",
                            "examples": [
                                {
                                    "chunk_overlap": 50,
                                    "chunk_size": 512,
                                    "type": "fixed"
                                }
                            ],
                            "title": "Chunking Strategy"
                        },
                        "provider_id": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Vector store provider identifier",
                            "examples": [
                                "rhdh-docs"
                            ],
                            "title": "Provider Id"
                        },
                        "metadata": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Metadata dictionary for storing session information",
                            "examples": [
                                {
                                    "session_id": "sess456",
                                    "user_id": "user123"
                                }
                            ],
                            "title": "Metadata"
                        }
                    },
                    "required": [
                        "name"
                    ],
                    "title": "VectorStoreCreateRequest",
                    "type": "object"
                },
                "VectorStoreDeleteResponse": {
                    "description": "Result of deleting a vector store (always HTTP 200).",
                    "examples": [
                        {
                            "label": "deleted",
                            "value": {
                                "deleted": true,
                                "response": "Vector store deleted successfully",
                                "vector_store_id": "vs_abc123"
                            }
                        },
                        {
                            "label": "not found",
                            "value": {
                                "deleted": false,
                                "response": "Vector store not found",
                                "vector_store_id": "vs_abc123"
                            }
                        }
                    ],
                    "properties": {
                        "deleted": {
                            "description": "Whether the deletion was successful.",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Deleted",
                            "type": "boolean"
                        },
                        "vector_store_id": {
                            "description": "Vector store identifier that was passed to delete.",
                            "examples": [
                                "vs_abc123"
                            ],
                            "title": "Vector Store Id",
                            "type": "string"
                        }
                    },
                    "required": [
                        "deleted",
                        "vector_store_id"
                    ],
                    "title": "VectorStoreDeleteResponse",
                    "type": "object"
                },
                "VectorStoreFileCreateRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a request to add a file to a vector store.\n\nAttributes:\n    file_id: ID of the file to add to the vector store.\n    attributes: Optional metadata key-value pairs (max 16 pairs).\n    chunking_strategy: Optional chunking strategy configuration.",
                    "examples": [
                        {
                            "attributes": {
                                "created_at": "2026-04-04T15:20:00Z"
                            },
                            "chunking_strategy": {
                                "chunk_size": 512,
                                "type": "fixed"
                            },
                            "file_id": "file-abc123"
                        }
                    ],
                    "properties": {
                        "file_id": {
                            "description": "ID of the file to add to the vector store",
                            "examples": [
                                "file-abc123"
                            ],
                            "minLength": 1,
                            "title": "File Id",
                            "type": "string"
                        },
                        "attributes": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Set of up to 16 key-value pairs for storing additional information. Keys: strings (max 64 chars). Values: strings (max 512 chars), booleans, or numbers.",
                            "examples": [
                                {
                                    "created_at": "2026-04-04T15:20:00Z",
                                    "updated_at": "2026-04-04T15:20:00Z"
                                }
                            ],
                            "title": "Attributes"
                        },
                        "chunking_strategy": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Chunking strategy configuration for this file",
                            "examples": [
                                {
                                    "chunk_overlap": 50,
                                    "chunk_size": 512,
                                    "type": "fixed"
                                }
                            ],
                            "title": "Chunking Strategy"
                        }
                    },
                    "required": [
                        "file_id"
                    ],
                    "title": "VectorStoreFileCreateRequest",
                    "type": "object"
                },
                "VectorStoreFileDeleteResponse": {
                    "description": "Result of deleting a file from a vector store (always HTTP 200).",
                    "examples": [
                        {
                            "label": "deleted",
                            "value": {
                                "deleted": true,
                                "file_id": "file_abc123",
                                "response": "Vector store file deleted successfully"
                            }
                        },
                        {
                            "label": "not found",
                            "value": {
                                "deleted": false,
                                "file_id": "file_abc123",
                                "response": "Vector store file not found"
                            }
                        }
                    ],
                    "properties": {
                        "deleted": {
                            "description": "Whether the deletion was successful.",
                            "examples": [
                                true,
                                false
                            ],
                            "title": "Deleted",
                            "type": "boolean"
                        },
                        "file_id": {
                            "description": "File identifier that was passed to delete.",
                            "examples": [
                                "file_abc123"
                            ],
                            "title": "File Id",
                            "type": "string"
                        }
                    },
                    "required": [
                        "deleted",
                        "file_id"
                    ],
                    "title": "VectorStoreFileDeleteResponse",
                    "type": "object"
                },
                "VectorStoreFileResponse": {
                    "additionalProperties": false,
                    "description": "Response model containing a vector store file object.\n\nAttributes:\n    id: Vector store file ID.\n    vector_store_id: ID of the vector store.\n    status: File processing status.\n    attributes: Optional metadata key-value pairs.\n    last_error: Optional error message if processing failed.\n    object: Object type (always \"vector_store.file\").",
                    "examples": [
                        {
                            "attributes": {
                                "chunk_size": "512",
                                "indexed": true
                            },
                            "id": "file_abc123",
                            "last_error": null,
                            "object": "vector_store.file",
                            "status": "completed",
                            "vector_store_id": "vs_abc123"
                        }
                    ],
                    "properties": {
                        "id": {
                            "description": "Vector store file ID",
                            "title": "Id",
                            "type": "string"
                        },
                        "vector_store_id": {
                            "description": "ID of the vector store",
                            "title": "Vector Store Id",
                            "type": "string"
                        },
                        "status": {
                            "description": "File processing status",
                            "title": "Status",
                            "type": "string"
                        },
                        "attributes": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Set of up to 16 key-value pairs for storing additional information. Keys: strings (max 64 chars). Values: strings (max 512 chars), booleans, or numbers.",
                            "title": "Attributes"
                        },
                        "last_error": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "Error message if processing failed",
                            "title": "Last Error"
                        },
                        "object": {
                            "default": "vector_store.file",
                            "description": "Object type",
                            "title": "Object",
                            "type": "string"
                        }
                    },
                    "required": [
                        "id",
                        "vector_store_id",
                        "status"
                    ],
                    "title": "VectorStoreFileResponse",
                    "type": "object"
                },
                "VectorStoreFilesListResponse": {
                    "additionalProperties": false,
                    "description": "Response model containing a list of vector store files.\n\nAttributes:\n    data: List of vector store file objects.\n    object: Object type (always \"list\").",
                    "examples": [
                        {
                            "data": [
                                {
                                    "attributes": {
                                        "chunk_size": "512"
                                    },
                                    "id": "file_abc123",
                                    "last_error": null,
                                    "object": "vector_store.file",
                                    "status": "completed",
                                    "vector_store_id": "vs_abc123"
                                },
                                {
                                    "attributes": null,
                                    "id": "file_def456",
                                    "last_error": null,
                                    "object": "vector_store.file",
                                    "status": "processing",
                                    "vector_store_id": "vs_abc123"
                                }
                            ],
                            "object": "list"
                        }
                    ],
                    "properties": {
                        "data": {
                            "description": "List of vector store files",
                            "items": {
                                "$ref": "`#/components/schemas/`VectorStoreFileResponse"
                            },
                            "title": "Data",
                            "type": "array"
                        },
                        "object": {
                            "default": "list",
                            "description": "Object type",
                            "title": "Object",
                            "type": "string"
                        }
                    },
                    "title": "VectorStoreFilesListResponse",
                    "type": "object"
                },
                "VectorStoreResponse": {
                    "additionalProperties": false,
                    "description": "Response model containing a single vector store.\n\nAttributes:\n    id: Vector store ID.\n    name: Vector store name.\n    created_at: Unix timestamp when created.\n    last_active_at: Unix timestamp of last activity.\n    expires_at: Optional Unix timestamp when it expires.\n    status: Vector store status.\n    usage_bytes: Storage usage in bytes.\n    metadata: Optional metadata dictionary for storing session information.",
                    "examples": [
                        {
                            "created_at": 1704067200,
                            "expires_at": null,
                            "id": "vs_abc123",
                            "last_active_at": 1704153600,
                            "metadata": {
                                "conversation_id": "conv_123",
                                "document_ids": [
                                    "doc_456",
                                    "doc_789"
                                ]
                            },
                            "name": "customer_support_docs",
                            "status": "active",
                            "usage_bytes": 1048576
                        }
                    ],
                    "properties": {
                        "id": {
                            "description": "Vector store ID",
                            "title": "Id",
                            "type": "string"
                        },
                        "name": {
                            "description": "Vector store name",
                            "title": "Name",
                            "type": "string"
                        },
                        "created_at": {
                            "description": "Unix timestamp when created",
                            "title": "Created At",
                            "type": "integer"
                        },
                        "last_active_at": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Unix timestamp of last activity",
                            "title": "Last Active At"
                        },
                        "expires_at": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Unix timestamp when it expires",
                            "title": "Expires At"
                        },
                        "status": {
                            "description": "Vector store status",
                            "title": "Status",
                            "type": "string"
                        },
                        "usage_bytes": {
                            "default": 0,
                            "description": "Storage usage in bytes",
                            "title": "Usage Bytes",
                            "type": "integer"
                        },
                        "metadata": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Metadata dictionary for storing session information",
                            "examples": [
                                {
                                    "conversation_id": "conv_123",
                                    "document_ids": [
                                        "doc_456",
                                        "doc_789"
                                    ]
                                }
                            ],
                            "title": "Metadata"
                        }
                    },
                    "required": [
                        "id",
                        "name",
                        "created_at",
                        "status"
                    ],
                    "title": "VectorStoreResponse",
                    "type": "object"
                },
                "VectorStoreUpdateRequest": {
                    "additionalProperties": false,
                    "description": "Model representing a request to update a vector store.\n\nAttributes:\n    name: New name for the vector store.\n    expires_at: Optional expiration timestamp.\n    metadata: Optional metadata dictionary for storing session information.",
                    "examples": [
                        {
                            "expires_at": 1735689600,
                            "metadata": {
                                "user_id": "user123"
                            },
                            "name": "updated_vector_store"
                        }
                    ],
                    "properties": {
                        "name": {
                            "type": "string",
                            "nullable": true,
                            "default": null,
                            "description": "New name for the vector store",
                            "examples": [
                                "updated_vector_store"
                            ],
                            "title": "Name"
                        },
                        "expires_at": {
                            "type": "integer",
                            "nullable": true,
                            "default": null,
                            "description": "Unix timestamp when the vector store should expire",
                            "examples": [
                                1735689600
                            ],
                            "title": "Expires At"
                        },
                        "metadata": {
                            "type": "object",
                            "nullable": true,
                            "default": null,
                            "description": "Metadata dictionary for storing session information",
                            "examples": [
                                {
                                    "session_id": "sess456",
                                    "user_id": "user123"
                                }
                            ],
                            "title": "Metadata"
                        }
                    },
                    "title": "VectorStoreUpdateRequest",
                    "type": "object"
                },
                "VectorStoresListResponse": {
                    "additionalProperties": false,
                    "description": "Response model containing a list of vector stores.\n\nAttributes:\n    data: List of vector store objects.\n    object: Object type (always \"list\").",
                    "examples": [
                        {
                            "data": [
                                {
                                    "created_at": 1704067200,
                                    "expires_at": null,
                                    "id": "vs_abc123",
                                    "last_active_at": 1704153600,
                                    "metadata": {
                                        "conversation_id": "conv_123"
                                    },
                                    "name": "customer_support_docs",
                                    "status": "active",
                                    "usage_bytes": 1048576
                                },
                                {
                                    "created_at": 1704070800,
                                    "expires_at": null,
                                    "id": "vs_def456",
                                    "last_active_at": 1704157200,
                                    "metadata": null,
                                    "name": "product_documentation",
                                    "status": "active",
                                    "usage_bytes": 2097152
                                }
                            ],
                            "object": "list"
                        }
                    ],
                    "properties": {
                        "data": {
                            "description": "List of vector stores",
                            "items": {
                                "$ref": "`#/components/schemas/`VectorStoreResponse"
                            },
                            "title": "Data",
                            "type": "array"
                        },
                        "object": {
                            "default": "list",
                            "description": "Object type",
                            "title": "Object",
                            "type": "string"
                        }
                    },
                    "title": "VectorStoresListResponse",
                    "type": "object"
                },
                "ogx_api__openai_responses__ApprovalFilter": {
                    "description": "Filter configuration for MCP tool approval requirements.\n\n:param always: (Optional) List of tool names that always require approval\n:param never: (Optional) List of tool names that never require approval",
                    "properties": {
                        "always": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Always"
                        },
                        "never": {
                            "type": "array",
                            "nullable": true,
                            "default": null,
                            "title": "Never"
                        }
                    },
                    "title": "ApprovalFilter",
                    "type": "object"
                },
                "models__config__ApprovalFilter": {
                    "additionalProperties": false,
                    "description": "Granular approval control for specific MCP tools.\n\nAttributes:\n    always: Tool names that always require human approval before execution.\n    never: Tool names that never require approval (pre-approved).",
                    "properties": {
                        "always": {
                            "description": "List of tool names that always require human approval",
                            "items": {
                                "type": "string"
                            },
                            "title": "Always require approval",
                            "type": "array"
                        },
                        "never": {
                            "description": "List of tool names that never require approval",
                            "items": {
                                "type": "string"
                            },
                            "title": "Never require approval",
                            "type": "array"
                        }
                    },
                    "title": "ApprovalFilter",
                    "type": "object"
                }
            }
        },
        "paths": {}
    }
    """
    filename = tmpdir / "foo.json"
    dump_models(str(filename))

    with open(filename, "r", encoding="utf-8") as fin:
        # schema should be stored in JSON format
        content = load(fin)
        assert content is not None

        # top-level keys test
        keys = ("openapi", "info", "components", "paths")
        for key in keys:
            assert key in content

        # components should be top-level node
        components = content["components"]
        assert components is not None

        # schemas should be a node stored inside components node
        assert "schemas" in components
        schemas = components["schemas"]
        assert schemas is not None

        # list of schemas expected in a dump
        expected_schemas = (
            "A2AStateConfiguration",
            "APIKeyTokenConfiguration",
            "AbstractErrorResponse",
            "AccessRule",
            "Action",
            "AllowedToolsFilter",
            "ApprovalsConfiguration",
            "Attachment",
            "AuthenticationConfiguration",
            "AuthorizationConfiguration",
            "AuthorizedResponse",
            "AzureEntraIdConfiguration",
            "BadRequestResponse",
            "ByokRag",
            "CORSConfiguration",
            "CatalogShield",
            "CompactionConfiguration",
            "Configuration",
            "ConfigurationResponse",
            "ConflictResponse",
            "ConversationData",
            "ConversationDeleteResponse",
            "ConversationDetails",
            "ConversationHistoryConfiguration",
            "ConversationResponse",
            "ConversationSummary",
            "ConversationTurn",
            "ConversationUpdateRequest",
            "ConversationUpdateResponse",
            "ConversationsListResponse",
            "ConversationsListResponseV2",
            "CustomProfile",
            "Customization",
            "DatabaseConfiguration",
            "DetailModel",
            "EndEventData",
            "EndStreamPayload",
            "ErrorEventData",
            "ErrorStreamPayload",
            "FeedbackCategory",
            "FeedbackRequest",
            "FeedbackResponse",
            "FeedbackStatusUpdateRequest",
            "FeedbackStatusUpdateResponse",
            "FileResponse",
            "FileTooLargeResponse",
            "ForbiddenResponse",
            "HealthStatus",
            "InMemoryCacheConfig",
            "IncludeParameter",
            "InferenceConfiguration",
            "InfoResponse",
            "InputToolMCP",
            "InternalServerErrorResponse",
            "InterruptedEventData",
            "InterruptedStreamPayload",
            "JsonPathOperator",
            "JwkConfiguration",
            "JwtConfiguration",
            "JwtRoleRule",
            "LivenessResponse",
            "LlamaStackConfiguration",
            "MCPClientAuthOptionsResponse",
            "MCPListToolsSummary",
            "MCPListToolsTool",
            "MCPServerAuthInfo",
            "MCPServerDeleteResponse",
            "MCPServerInfo",
            "MCPServerListResponse",
            "MCPServerRegistrationRequest",
            "MCPServerRegistrationResponse",
            "Message",
            "ModelContextProtocolServer",
            "ModelFilter",
            "ModelsResponse",
            "NotFoundResponse",
            "OkpConfiguration",
            "OpenAIResponseAnnotationCitation",
            "OpenAIResponseAnnotationContainerFileCitation",
            "OpenAIResponseAnnotationFileCitation",
            "OpenAIResponseAnnotationFilePath",
            "OpenAIResponseContentPartRefusal",
            "OpenAIResponseError",
            "OpenAIResponseInputFunctionToolCallOutput",
            "OpenAIResponseInputMessageContentFile",
            "OpenAIResponseInputMessageContentImage",
            "OpenAIResponseInputMessageContentText",
            "OpenAIResponseInputToolChoiceAllowedTools",
            "OpenAIResponseInputToolChoiceCustomTool",
            "OpenAIResponseInputToolChoiceFileSearch",
            "OpenAIResponseInputToolChoiceFunctionTool",
            "OpenAIResponseInputToolChoiceMCPTool",
            "OpenAIResponseInputToolChoiceMode",
            "OpenAIResponseInputToolChoiceWebSearch",
            "OpenAIResponseInputToolFileSearch",
            "OpenAIResponseInputToolFunction",
            "OpenAIResponseInputToolWebSearch",
            "OpenAIResponseMCPApprovalRequest",
            "OpenAIResponseMCPApprovalResponse",
            "OpenAIResponseMessage",
            "OpenAIResponseOutputMessageContentOutputText",
            "OpenAIResponseOutputMessageFileSearchToolCall",
            "OpenAIResponseOutputMessageFileSearchToolCallResults",
            "OpenAIResponseOutputMessageFunctionToolCall",
            "OpenAIResponseOutputMessageMCPCall",
            "OpenAIResponseOutputMessageMCPListTools",
            "OpenAIResponseOutputMessageWebSearchToolCall",
            "OpenAIResponsePrompt",
            "OpenAIResponseReasoning",
            "OpenAIResponseText",
            "OpenAIResponseTextFormat",
            "OpenAIResponseToolMCP",
            "OpenAIResponseUsage",
            "OpenAIResponseUsageInputTokensDetails",
            "OpenAIResponseUsageOutputTokensDetails",
            "OpenAITokenLogProb",
            "OpenAITopLogProb",
            "PostgreSQLDatabaseConfiguration",
            "PromptCreateRequest",
            "PromptDeleteResponse",
            "PromptResourceResponse",
            "PromptTooLongResponse",
            "PromptUpdateRequest",
            "PromptsListResponse",
            "ProviderHealthStatus",
            "ProviderResponse",
            "ProvidersListResponse",
            "QueryRequest",
            "QueryResponse",
            "QuotaExceededResponse",
            "QuotaHandlersConfiguration",
            "QuotaLimiterConfiguration",
            "QuotaSchedulerConfiguration",
            "RAGChunk",
            "RAGContext",
            "RAGInfoResponse",
            "RAGListResponse",
            "RHIdentityConfiguration",
            "RagConfiguration",
            "ReadinessResponse",
            "ReferencedDocument",
            "RerankerConfiguration",
            "ResponseInput",
            "ResponseItem",
            "ResponsesApiParams",
            "ResponsesRequest",
            "ResponsesResponse",
            "RlsapiV1Attachment",
            "RlsapiV1CLA",
            "RlsapiV1Configuration",
            "RlsapiV1Context",
            "RlsapiV1InferData",
            "RlsapiV1InferRequest",
            "RlsapiV1InferResponse",
            "RlsapiV1SystemInfo",
            "RlsapiV1Terminal",
            "SQLiteDatabaseConfiguration",
            "SavedPromptsConfiguration",
            "SearchRankingOptions",
            "ServiceConfiguration",
            "ServiceUnavailableResponse",
            "ShieldModerationBlocked",
            "ShieldModerationPassed",
            "ShieldsResponse",
            "SkillsConfiguration",
            "SolrVectorSearchRequest",
            "SplunkConfiguration",
            "StartEventData",
            "StartStreamPayload",
            "StatusResponse",
            "StreamPayloadBase",
            "StreamingInterruptRequest",
            "StreamingInterruptResponse",
            "StreamingQueryResponse",
            "TLSConfiguration",
            "TokenChunkData",
            "TokenCounter",
            "TokenStreamPayload",
            "ToolCallStreamPayload",
            "ToolCallSummary",
            "ToolInfoSummary",
            "ToolResultStreamPayload",
            "ToolResultSummary",
            "ToolsResponse",
            "Transcript",
            "TranscriptMetadata",
            "TrustedProxyConfiguration",
            "TrustedProxyServiceAccount",
            "TurnCompleteStreamPayload",
            "TurnSummary",
            "UnauthorizedResponse",
            "UnifiedInferenceProvider",
            "UnifiedLlamaStackConfig",
            "UnprocessableEntityResponse",
            "UserDataCollection",
            "VectorStoreCreateRequest",
            "VectorStoreDeleteResponse",
            "VectorStoreFileCreateRequest",
            "VectorStoreFileDeleteResponse",
            "VectorStoreFileResponse",
            "VectorStoreFilesListResponse",
            "VectorStoreResponse",
            "VectorStoreUpdateRequest",
            "VectorStoresListResponse",
        )
        for expected_schema in expected_schemas:
            assert expected_schema in schemas
