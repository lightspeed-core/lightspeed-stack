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
                "ApprovalFilter": {
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
                "IncludeParameter": {
                    "enum": [
                        "web_search_call.action.sources",
                        "code_interpreter_call.outputs",
                        "computer_call_output.output.image_url",
                        "file_search_call.results",
                        "message.input_image.image_url",
                        "message.output_text.logprobs",
                        "reasoning.encrypted_content"
                    ],
                    "type": "string"
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
                                    "$ref": "`#/components/schemas/`ApprovalFilter"
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
            "AllowedToolsFilter",
            "ApprovalFilter",
            "Attachment",
            "ConversationSummary",
            "ConversationUpdateRequest",
            "FeedbackCategory",
            "FeedbackRequest",
            "FeedbackStatusUpdateRequest",
            "IncludeParameter",
            "InputToolMCP",
            "MCPListToolsTool",
            "MCPServerRegistrationRequest",
            "ModelFilter",
            "OpenAIResponseAnnotationCitation",
            "OpenAIResponseAnnotationContainerFileCitation",
            "OpenAIResponseAnnotationFileCitation",
            "OpenAIResponseAnnotationFilePath",
            "OpenAIResponseContentPartRefusal",
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
            "OpenAITokenLogProb",
            "OpenAITopLogProb",
            "PromptCreateRequest",
            "PromptUpdateRequest",
            "QueryRequest",
            "ResponseInput",
            "ResponseItem",
            "ResponsesRequest",
            "RlsapiV1Attachment",
            "RlsapiV1CLA",
            "RlsapiV1Context",
            "RlsapiV1InferRequest",
            "RlsapiV1SystemInfo",
            "RlsapiV1Terminal",
            "SearchRankingOptions",
            "SolrVectorSearchRequest",
            "StreamingInterruptRequest",
            "VectorStoreCreateRequest",
            "VectorStoreFileCreateRequest",
            "VectorStoreUpdateRequest",
        )
        for expected_schema in expected_schemas:
            assert expected_schema in schemas
