"""Successful response model for the configuration endpoint."""

from pydantic import ConfigDict

from models.api.responses.successful.bases import AbstractSuccessfulResponse
from models.config import Configuration


class ConfigurationResponse(AbstractSuccessfulResponse):
    """Success response model for the config endpoint.

    Attributes:
        configuration: Parsed application configuration returned to the client.
    """

    configuration: Configuration

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "configuration": {
                        "name": "lightspeed-stack",
                        "service": {
                            "host": "localhost",
                            "port": 8080,
                            "auth_enabled": False,
                            "workers": 1,
                            "color_log": True,
                            "access_log": True,
                            "tls_config": {
                                "tls_certificate_path": None,
                                "tls_key_path": None,
                                "tls_key_password": None,
                            },
                            "cors": {
                                "allow_origins": ["*"],
                                "allow_credentials": False,
                                "allow_methods": ["*"],
                                "allow_headers": ["*"],
                            },
                        },
                        "llama_stack": {
                            "url": "http://localhost:8321",
                            "api_key": "*****",
                            "use_as_library_client": False,
                            "library_client_config_path": None,
                        },
                        "user_data_collection": {
                            "feedback_enabled": True,
                            "feedback_storage": "/tmp/data/feedback",
                            "transcripts_enabled": False,
                            "transcripts_storage": "/tmp/data/transcripts",
                        },
                        "database": {
                            "sqlite": {"db_path": "/tmp/lightspeed-stack.db"},
                            "postgres": None,
                        },
                        "mcp_servers": [
                            {
                                "name": "server1",
                                "provider_id": "provider1",
                                "url": "http://url.com:1",
                            },
                        ],
                        "authentication": {
                            "module": "noop",
                            "skip_tls_verification": False,
                        },
                        "authorization": {"access_rules": []},
                        "customization": None,
                        "inference": {
                            "default_model": "gpt-4-turbo",
                            "default_provider": "openai",
                        },
                        "conversation_cache": {
                            "type": None,
                            "memory": None,
                            "sqlite": None,
                            "postgres": None,
                        },
                        "byok_rag": [],
                        "quota_handlers": {
                            "sqlite": None,
                            "postgres": None,
                            "limiters": [],
                            "scheduler": {"period": 1},
                            "enable_token_history": False,
                        },
                    }
                }
            ]
        }
    )
