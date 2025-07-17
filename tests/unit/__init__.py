"""Unit tests."""

from configuration import configuration  # noqa: F401

config_dict = {
    "name": "test",
    "service": {
        "host": "localhost",
        "port": 8080,
        "auth_enabled": False,
        "workers": 1,
        "color_log": True,
        "access_log": True,
    },
    "llama_stack": {
        "api_key": "test-key",
        "url": "http://test.com:1234",
        "use_as_library_client": False,
    },
    "user_data_collection": {
        "transcripts_disabled": True,
    },
    "mcp_servers": [],
    "authentication": {
        "module": "noop",
        "skip_tls_verification": False,
        "k8s_ca_cert_path": None,
        "k8s_cluster_api": None,
    },
    "customization": {
        "disable_query_system_prompt": False,
        "system_prompt_path": None,
        "system_prompt": None,
    },
}

# NOTE(lucasagomes): Configuration must be initialized before importing
# endpoints, since get_auth_dependency() uses it during import time
configuration.init_from_dict(config_dict)
