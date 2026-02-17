"""Shared fixtures for telemetry unit tests."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import SecretStr

from models.config import (
    AccessRule,
    Action,
    AuthenticationConfiguration,
    AuthorizationConfiguration,
    Configuration,
    CORSConfiguration,
    Customization,
    DatabaseConfiguration,
    InferenceConfiguration,
    JwkConfiguration,
    JsonPathOperator,
    JwtConfiguration,
    JwtRoleRule,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    PostgreSQLDatabaseConfiguration,
    ServiceConfiguration,
    SQLiteDatabaseConfiguration,
    TLSConfiguration,
    UserDataCollection,
)

# =============================================================================
# Known PII values used across tests
# =============================================================================

PII_HOST = "192.168.1.100"
PII_TLS_CERT = "/etc/ssl/certs/server.crt"
PII_TLS_KEY = "/etc/ssl/private/server.key"
PII_TLS_PASS = "/etc/ssl/private/key_password.txt"
PII_CORS_ORIGIN = "https://internal.corp.com"
PII_LLAMA_URL = "https://llama.internal.corp.com:8321"
PII_API_KEY = "sk-super-secret-api-key-12345"
PII_LIB_CONFIG = "/opt/llama-stack/run.yaml"
PII_K8S_API = "https://k8s.internal.corp.com:6443"
PII_K8S_CERT = "/var/run/secrets/ca.crt"
PII_JWK_URL = "https://auth.internal.corp.com/.well-known/jwks.json"
PII_ROLE_VALUE = "secret-org-id-99999"
PII_FEEDBACK_STORAGE = "/data/feedback"
PII_TRANSCRIPTS_STORAGE = "/data/transcripts"
PII_SYSTEM_PROMPT = "You are a secret internal assistant for ACME Corp project X."
PII_PROMPT_PATH = "/etc/lightspeed/system_prompt.txt"
PII_SQLITE_PATH = "/var/lib/lightspeed/db.sqlite"
PII_PG_HOST = "db.internal.corp.com"
PII_PG_DB = "lightspeed_prod"
PII_PG_USER = "admin_jsmith"
PII_PG_PASS = "P@ssw0rd!SuperSecret"
PII_PG_NAMESPACE = "production_ns"
PII_PG_CA_CERT = "/etc/ssl/postgres/ca.crt"
PII_MCP_URL = "https://mcp.internal.corp.com:9090"

ALL_PII_VALUES = [
    PII_HOST,
    PII_TLS_CERT,
    PII_TLS_KEY,
    PII_TLS_PASS,
    PII_CORS_ORIGIN,
    PII_LLAMA_URL,
    PII_API_KEY,
    PII_LIB_CONFIG,
    PII_K8S_API,
    PII_K8S_CERT,
    PII_JWK_URL,
    PII_ROLE_VALUE,
    PII_FEEDBACK_STORAGE,
    PII_TRANSCRIPTS_STORAGE,
    PII_SYSTEM_PROMPT,
    PII_PROMPT_PATH,
    PII_SQLITE_PATH,
    PII_PG_HOST,
    PII_PG_DB,
    PII_PG_USER,
    PII_PG_PASS,
    PII_PG_NAMESPACE,
    PII_PG_CA_CERT,
    PII_MCP_URL,
]

SAMPLE_LLAMA_STACK_CONFIG: dict[str, Any] = {
    "version": 2,
    "image_name": "starter",
    "container_image": None,
    "external_providers_dir": "/opt/providers",
    "apis": ["agents", "inference", "safety", "vector_io"],
    "server": {"port": 8321},
    "providers": {
        "inference": [
            {
                "provider_id": "openai",
                "provider_type": "remote::openai",
                "config": {"api_key": "sk-openai-secret-key"},
            },
        ],
        "safety": [
            {
                "provider_id": "llama-guard",
                "provider_type": "inline::llama-guard",
                "config": {},
            },
        ],
        "vector_io": [],
    },
    "registered_resources": {
        "models": [
            {
                "model_id": "gpt-4o-mini",
                "provider_id": "openai",
                "provider_model_id": "gpt-4o-mini",
                "model_type": "llm",
            },
            {
                "model_id": "granite-embedding-30m",
                "provider_id": "sentence-transformers",
                "provider_model_id": "all-MiniLM-L6-v2",
                "model_type": "embedding",
            },
        ],
        "shields": [
            {"shield_id": "llama-guard", "provider_id": "llama-guard"},
        ],
        "vector_stores": [],
    },
    "storage": {
        "backends": {
            "kv_default": {
                "type": "kv_sqlite",
                "db_path": "/secret/path/kv_store.db",
            },
            "sql_default": {
                "type": "sql_sqlite",
                "db_path": "/secret/path/sql_store.db",
            },
        },
        "stores": {
            "metadata": {
                "namespace": "registry",
                "backend": "kv_default",
            },
            "inference": {
                "table_name": "inference_store",
                "backend": "sql_default",
            },
        },
    },
    "benchmarks": [],
    "scoring_fns": [],
    "datasets": [],
}


LLAMA_STACK_PII_VALUES = [
    "sk-openai-secret-key",
    "/secret/path/kv_store.db",
    "/secret/path/sql_store.db",
    "/opt/providers",
]


def build_fully_populated_config() -> Configuration:
    """Build a Configuration with all fields populated using known PII values.

    Uses model_construct() to bypass file-existence validators.

    Returns:
        A fully-populated Configuration for testing PII masking.
    """
    return Configuration.model_construct(
        name="test-service",
        service=ServiceConfiguration.model_construct(
            host=PII_HOST,
            port=8080,
            base_url=None,
            workers=4,
            auth_enabled=True,
            color_log=True,
            access_log=False,
            root_path="",
            tls_config=TLSConfiguration.model_construct(
                tls_certificate_path=Path(PII_TLS_CERT),
                tls_key_path=Path(PII_TLS_KEY),
                tls_key_password=Path(PII_TLS_PASS),
            ),
            cors=CORSConfiguration.model_construct(
                allow_origins=[PII_CORS_ORIGIN, "https://admin.corp.com"],
                allow_credentials=True,
                allow_methods=["GET", "POST"],
                allow_headers=["Authorization", "Content-Type"],
            ),
        ),
        llama_stack=LlamaStackConfiguration.model_construct(
            url=PII_LLAMA_URL,
            api_key=SecretStr(PII_API_KEY),
            use_as_library_client=False,
            library_client_config_path=PII_LIB_CONFIG,
            timeout=180,
        ),
        inference=InferenceConfiguration.model_construct(
            default_model="gpt-4o-mini",
            default_provider="openai",
        ),
        authentication=AuthenticationConfiguration.model_construct(
            module="jwk_token",
            skip_tls_verification=False,
            skip_for_health_probes=False,
            k8s_cluster_api=PII_K8S_API,
            k8s_ca_cert_path=Path(PII_K8S_CERT),
            jwk_config=JwkConfiguration.model_construct(
                url=PII_JWK_URL,
                jwt_configuration=JwtConfiguration.model_construct(
                    user_id_claim="sub",
                    username_claim="preferred_username",
                    role_rules=[
                        JwtRoleRule.model_construct(
                            jsonpath="$.org_id",
                            operator=JsonPathOperator.EQUALS,
                            value=PII_ROLE_VALUE,
                            roles=["admin"],
                            negate=False,
                            compiled_regex=None,
                        ),
                    ],
                ),
            ),
            api_key_config=None,
            rh_identity_config=None,
        ),
        authorization=AuthorizationConfiguration.model_construct(
            access_rules=[
                AccessRule.model_construct(
                    role="admin",
                    actions=[Action.ADMIN],
                ),
                AccessRule.model_construct(
                    role="user",
                    actions=[Action.QUERY, Action.FEEDBACK],
                ),
            ],
        ),
        user_data_collection=UserDataCollection.model_construct(
            feedback_enabled=True,
            feedback_storage=PII_FEEDBACK_STORAGE,
            transcripts_enabled=True,
            transcripts_storage=PII_TRANSCRIPTS_STORAGE,
        ),
        customization=Customization.model_construct(
            system_prompt=PII_SYSTEM_PROMPT,
            system_prompt_path=Path(PII_PROMPT_PATH),
            disable_query_system_prompt=False,
            profile_path=None,
            custom_profile=None,
            agent_card_path=None,
            agent_card_config=None,
        ),
        database=DatabaseConfiguration.model_construct(
            sqlite=SQLiteDatabaseConfiguration.model_construct(
                db_path=PII_SQLITE_PATH,
            ),
            postgres=PostgreSQLDatabaseConfiguration.model_construct(
                host=PII_PG_HOST,
                port=5432,
                db=PII_PG_DB,
                user=PII_PG_USER,
                password=SecretStr(PII_PG_PASS),
                namespace=PII_PG_NAMESPACE,
                ssl_mode="verify-full",
                gss_encmode="prefer",
                ca_cert_path=Path(PII_PG_CA_CERT),
            ),
        ),
        mcp_servers=[
            ModelContextProtocolServer.model_construct(
                name="my-mcp-server",
                provider_id="model-context-protocol",
                url=PII_MCP_URL,
                authorization_headers={},
                timeout=None,
            ),
        ],
        conversation_cache=None,
        byok_rag=[],
        a2a_state=None,
        quota_handlers=None,
        azure_entra_id=None,
        splunk=None,
        deployment_environment="production",
        solr=None,
    )


def build_minimal_config() -> Configuration:
    """Build a minimal Configuration with mostly None/default optional fields.

    Returns:
        A minimal Configuration for testing snapshot behavior with defaults.
    """
    return Configuration.model_construct(
        name="minimal",
        service=ServiceConfiguration.model_construct(
            host="localhost",
            port=8080,
            base_url=None,
            workers=1,
            auth_enabled=False,
            color_log=True,
            access_log=True,
            root_path="",
            tls_config=TLSConfiguration.model_construct(
                tls_certificate_path=None,
                tls_key_path=None,
                tls_key_password=None,
            ),
            cors=CORSConfiguration.model_construct(
                allow_origins=["*"],
                allow_credentials=False,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ),
        llama_stack=LlamaStackConfiguration.model_construct(
            url=None,
            api_key=None,
            use_as_library_client=True,
            library_client_config_path=None,
            timeout=180,
        ),
        inference=InferenceConfiguration.model_construct(
            default_model=None,
            default_provider=None,
        ),
        authentication=AuthenticationConfiguration.model_construct(
            module="noop",
            skip_tls_verification=False,
            skip_for_health_probes=False,
            k8s_cluster_api=None,
            k8s_ca_cert_path=None,
            jwk_config=None,
            api_key_config=None,
            rh_identity_config=None,
        ),
        authorization=None,
        user_data_collection=UserDataCollection.model_construct(
            feedback_enabled=False,
            feedback_storage=None,
            transcripts_enabled=False,
            transcripts_storage=None,
        ),
        customization=None,
        database=DatabaseConfiguration.model_construct(
            sqlite=SQLiteDatabaseConfiguration.model_construct(
                db_path="/tmp/lightspeed-stack.db",
            ),
            postgres=None,
        ),
        mcp_servers=[],
        conversation_cache=None,
        byok_rag=[],
        a2a_state=None,
        quota_handlers=None,
        azure_entra_id=None,
        splunk=None,
        deployment_environment="development",
        solr=None,
    )


@pytest.fixture(name="llama_stack_config_file")
def llama_stack_config_file_fixture(tmp_path: Path) -> str:
    """Write SAMPLE_LLAMA_STACK_CONFIG to a temp YAML file and return its path.

    Parameters:
        tmp_path: Pytest-managed temporary directory (auto-cleaned).

    Returns:
        str: Path to the temporary YAML file.
    """
    path = tmp_path / "llama_stack_config.yaml"
    path.write_text(yaml.dump(SAMPLE_LLAMA_STACK_CONFIG))
    return str(path)
