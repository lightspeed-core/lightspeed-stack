"""Shared fixtures for telemetry unit tests."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import SecretStr

from models.config import (
    A2AAgentEndpointConfiguration,
    A2AAgentsConfiguration,
    A2AStateConfiguration,
    AccessRule,
    Action,
    APIKeyTokenConfiguration,
    ApprovalsConfiguration,
    AuthenticationConfiguration,
    AuthorizationConfiguration,
    AzureEntraIdConfiguration,
    ByokRag,
    CompactionConfiguration,
    Configuration,
    ConversationHistoryConfiguration,
    CORSConfiguration,
    Customization,
    DatabaseConfiguration,
    InferenceConfiguration,
    InMemoryCacheConfig,
    JsonPathOperator,
    JwkConfiguration,
    JwtConfiguration,
    JwtRoleRule,
    LlamaStackConfiguration,
    ModelContextProtocolServer,
    OkpConfiguration,
    PostgreSQLDatabaseConfiguration,
    QuotaHandlersConfiguration,
    QuotaLimiterConfiguration,
    QuotaSchedulerConfiguration,
    RagConfiguration,
    RerankerConfiguration,
    RHIdentityConfiguration,
    RlsapiV1Configuration,
    SavedPromptsConfiguration,
    ServiceConfiguration,
    SkillsConfiguration,
    SplunkConfiguration,
    SQLiteDatabaseConfiguration,
    TLSConfiguration,
    TrustedProxyConfiguration,
    TrustedProxyServiceAccount,
    UnifiedInferenceProvider,
    UnifiedLlamaStackConfig,
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
PII_MCP_AUTH_HEADER_VALUE = "/etc/secrets/mcp-token.txt"
PII_BASE_URL = "https://lightspeed.internal.corp.com"
PII_ROOT_PATH = "/api/v1/lightspeed"
PII_PROFILE_PATH = "/opt/lightspeed/custom_profile.py"
PII_AGENT_CARD_PATH = "/opt/lightspeed/agent_card.yaml"
PII_CACHE_SQLITE_PATH = "/var/lib/lightspeed/cache.sqlite"
PII_CACHE_PG_HOST = "cache-db.internal.corp.com"
PII_CACHE_PG_DB = "lightspeed_cache"
PII_CACHE_PG_USER = "cache_admin"
PII_CACHE_PG_PASS = "CacheP@ss!Secret"
PII_CACHE_PG_NAMESPACE = "cache_ns"
PII_CACHE_PG_CA_CERT = "/etc/ssl/cache/ca.crt"
PII_QUOTA_SQLITE_PATH = "/var/lib/lightspeed/quota.sqlite"
PII_QUOTA_PG_HOST = "quota-db.internal.corp.com"
PII_QUOTA_PG_DB = "lightspeed_quota"
PII_QUOTA_PG_USER = "quota_admin"
PII_QUOTA_PG_PASS = "QuotaP@ss!Secret"
PII_QUOTA_PG_NAMESPACE = "quota_ns"
PII_QUOTA_PG_CA_CERT = "/etc/ssl/quota/ca.crt"
PII_BYOK_DB_PATH = "/var/lib/lightspeed/byok_rag.db"
PII_BYOK_HOST = "byok-db.internal.corp.com"
PII_BYOK_PORT = "5433"
PII_BYOK_DB = "byok_vectors"
PII_BYOK_USER = "byok_admin"
PII_BYOK_PASS = "ByokP@ss!Secret"
PII_A2A_SQLITE_PATH = "/var/lib/lightspeed/a2a.sqlite"
PII_A2A_PG_HOST = "a2a-db.internal.corp.com"
PII_A2A_PG_DB = "lightspeed_a2a"
PII_A2A_PG_USER = "a2a_admin"
PII_A2A_PG_PASS = "A2aP@ss!Secret"
PII_A2A_PG_NAMESPACE = "a2a_ns"
PII_A2A_PG_CA_CERT = "/etc/ssl/a2a/ca.crt"
PII_A2A_AGENT_URL = "https://a2a-agent.internal.corp.com:8443"
PII_A2A_AGENT_TOKEN = "a2a-secret-bearer-token-xyz"
PII_SPLUNK_URL = "https://splunk-hec.internal.corp.com:8088"
PII_SPLUNK_TOKEN_PATH = "/etc/secrets/splunk-token.txt"
PII_SPLUNK_INDEX = "lightspeed_prod_index"
PII_OKP_URL = "https://okp.internal.corp.com:9443"
PII_OKP_CHUNK_FILTER = "product:ansible AND product:*openshift*"
PII_AZURE_TENANT_ID = "azure-tenant-id-secret-12345"
PII_AZURE_CLIENT_ID = "azure-client-id-secret-67890"
PII_AZURE_CLIENT_SECRET = "azure-client-secret-abcdef"
PII_RH_IDENTITY_ENTITLEMENTS = "insights,openshift"
PII_TRUSTED_PROXY_SA_NS = "proxy-namespace-secret"
PII_TRUSTED_PROXY_SA_NAME = "proxy-sa-secret-name"
PII_SKILLS_PATH = "/opt/lightspeed/skills"
PII_LS_PROFILE = "/opt/llama-stack/custom-profile.yaml"
PII_LS_NATIVE_OVERRIDE = "override-secret-value"
PII_PROVIDER_API_KEY_ENV = "OPENAI_API_KEY"

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
    PII_MCP_AUTH_HEADER_VALUE,
    PII_BASE_URL,
    PII_ROOT_PATH,
    PII_PROFILE_PATH,
    PII_AGENT_CARD_PATH,
    PII_CACHE_SQLITE_PATH,
    PII_CACHE_PG_HOST,
    PII_CACHE_PG_DB,
    PII_CACHE_PG_USER,
    PII_CACHE_PG_PASS,
    PII_CACHE_PG_NAMESPACE,
    PII_CACHE_PG_CA_CERT,
    PII_QUOTA_SQLITE_PATH,
    PII_QUOTA_PG_HOST,
    PII_QUOTA_PG_DB,
    PII_QUOTA_PG_USER,
    PII_QUOTA_PG_PASS,
    PII_QUOTA_PG_NAMESPACE,
    PII_QUOTA_PG_CA_CERT,
    PII_BYOK_DB_PATH,
    PII_BYOK_HOST,
    PII_BYOK_PORT,
    PII_BYOK_DB,
    PII_BYOK_USER,
    PII_BYOK_PASS,
    PII_A2A_SQLITE_PATH,
    PII_A2A_PG_HOST,
    PII_A2A_PG_DB,
    PII_A2A_PG_USER,
    PII_A2A_PG_PASS,
    PII_A2A_PG_NAMESPACE,
    PII_A2A_PG_CA_CERT,
    PII_A2A_AGENT_URL,
    PII_A2A_AGENT_TOKEN,
    PII_SPLUNK_URL,
    PII_SPLUNK_TOKEN_PATH,
    PII_SPLUNK_INDEX,
    PII_OKP_URL,
    PII_OKP_CHUNK_FILTER,
    PII_AZURE_TENANT_ID,
    PII_AZURE_CLIENT_ID,
    PII_AZURE_CLIENT_SECRET,
    PII_RH_IDENTITY_ENTITLEMENTS,
    PII_TRUSTED_PROXY_SA_NS,
    PII_TRUSTED_PROXY_SA_NAME,
    PII_SKILLS_PATH,
    PII_LS_PROFILE,
    PII_LS_NATIVE_OVERRIDE,
    PII_PROVIDER_API_KEY_ENV,
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
            base_url=PII_BASE_URL,
            workers=4,
            auth_enabled=True,
            color_log=True,
            access_log=False,
            root_path=PII_ROOT_PATH,
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
            max_retries=5,
            retry_delay=2,
            allow_degraded_mode=True,
            config=UnifiedLlamaStackConfig.model_construct(
                baseline="default",
                profile=PII_LS_PROFILE,
                native_override={"key": PII_LS_NATIVE_OVERRIDE},
            ),
        ),
        inference=InferenceConfiguration.model_construct(
            default_model="gpt-4o-mini",
            default_provider="openai",
            context_windows={"openai/gpt-4o-mini": 128000},
            max_infer_iters=10,
            max_tool_calls=30,
            providers=[
                UnifiedInferenceProvider.model_construct(
                    type="openai",
                    id="openai-provider",
                    api_key_env=PII_PROVIDER_API_KEY_ENV,
                    allowed_models=["gpt-4o-mini", "gpt-4o"],
                    extra={},
                ),
            ],
        ),
        authentication=AuthenticationConfiguration.model_construct(
            module="jwk_token",
            skip_tls_verification=False,
            skip_for_health_probes=True,
            skip_for_metrics=True,
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
            api_key_config=APIKeyTokenConfiguration.model_construct(
                api_key=SecretStr(PII_API_KEY),
            ),
            rh_identity_config=RHIdentityConfiguration.model_construct(
                required_entitlements=[PII_RH_IDENTITY_ENTITLEMENTS],
                max_header_size=16384,
            ),
            trusted_proxy_config=TrustedProxyConfiguration.model_construct(
                user_header="X-Forwarded-User",
                allowed_service_accounts=[
                    TrustedProxyServiceAccount.model_construct(
                        namespace=PII_TRUSTED_PROXY_SA_NS,
                        name=PII_TRUSTED_PROXY_SA_NAME,
                    ),
                ],
            ),
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
            profile_path=PII_PROFILE_PATH,
            disable_query_system_prompt=False,
            disable_shield_ids_override=True,
            custom_profile=None,
            agent_card_path=Path(PII_AGENT_CARD_PATH),
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
        conversation_cache=ConversationHistoryConfiguration.model_construct(
            type="postgres",
            memory=InMemoryCacheConfig.model_construct(max_entries=1000),
            sqlite=SQLiteDatabaseConfiguration.model_construct(
                db_path=PII_CACHE_SQLITE_PATH,
            ),
            postgres=PostgreSQLDatabaseConfiguration.model_construct(
                host=PII_CACHE_PG_HOST,
                port=5432,
                db=PII_CACHE_PG_DB,
                user=PII_CACHE_PG_USER,
                password=SecretStr(PII_CACHE_PG_PASS),
                namespace=PII_CACHE_PG_NAMESPACE,
                ssl_mode="verify-full",
                gss_encmode="prefer",
                ca_cert_path=Path(PII_CACHE_PG_CA_CERT),
            ),
        ),
        compaction=CompactionConfiguration.model_construct(
            enabled=True,
            threshold_ratio=0.8,
            token_floor=8192,
            buffer_turns=6,
            buffer_max_ratio=0.4,
        ),
        quota_handlers=QuotaHandlersConfiguration.model_construct(
            sqlite=SQLiteDatabaseConfiguration.model_construct(
                db_path=PII_QUOTA_SQLITE_PATH,
            ),
            postgres=PostgreSQLDatabaseConfiguration.model_construct(
                host=PII_QUOTA_PG_HOST,
                port=5432,
                db=PII_QUOTA_PG_DB,
                user=PII_QUOTA_PG_USER,
                password=SecretStr(PII_QUOTA_PG_PASS),
                namespace=PII_QUOTA_PG_NAMESPACE,
                ssl_mode="verify-full",
                gss_encmode="prefer",
                ca_cert_path=Path(PII_QUOTA_PG_CA_CERT),
            ),
            limiters=[
                QuotaLimiterConfiguration.model_construct(
                    type="user_limiter",
                    name="daily-user-limit",
                    initial_quota=10000,
                    quota_increase=0,
                    period="1 day",
                ),
            ],
            scheduler=QuotaSchedulerConfiguration.model_construct(
                period=5,
                database_reconnection_count=10,
                database_reconnection_delay=2,
            ),
            enable_token_history=True,
        ),
        byok_rag=[
            ByokRag.model_construct(
                rag_id="my-rag",
                rag_type="inline::faiss",
                embedding_model="all-MiniLM-L6-v2",
                embedding_dimension=384,
                vector_db_id="my-vector-db",
                db_path=PII_BYOK_DB_PATH,
                score_multiplier=1.5,
                host=PII_BYOK_HOST,
                port=PII_BYOK_PORT,
                db=PII_BYOK_DB,
                user=PII_BYOK_USER,
                password=SecretStr(PII_BYOK_PASS),
            ),
        ],
        a2a_state=A2AStateConfiguration.model_construct(
            sqlite=SQLiteDatabaseConfiguration.model_construct(
                db_path=PII_A2A_SQLITE_PATH,
            ),
            postgres=PostgreSQLDatabaseConfiguration.model_construct(
                host=PII_A2A_PG_HOST,
                port=5432,
                db=PII_A2A_PG_DB,
                user=PII_A2A_PG_USER,
                password=SecretStr(PII_A2A_PG_PASS),
                namespace=PII_A2A_PG_NAMESPACE,
                ssl_mode="verify-full",
                gss_encmode="prefer",
                ca_cert_path=Path(PII_A2A_PG_CA_CERT),
            ),
        ),
        a2a_agents=A2AAgentsConfiguration.model_construct(
            agents=[
                A2AAgentEndpointConfiguration.model_construct(
                    name="external-agent",
                    url=PII_A2A_AGENT_URL,
                    auth_token=SecretStr(PII_A2A_AGENT_TOKEN),
                    timeout=30,
                    max_retries=3,
                ),
            ],
        ),
        mcp_servers=[
            ModelContextProtocolServer.model_construct(
                name="my-mcp-server",
                provider_id="model-context-protocol",
                url=PII_MCP_URL,
                authorization_headers={"Authorization": PII_MCP_AUTH_HEADER_VALUE},
                headers=["x-rh-identity"],
                require_approval="always",
                timeout=60,
            ),
        ],
        azure_entra_id=AzureEntraIdConfiguration.model_construct(
            tenant_id=SecretStr(PII_AZURE_TENANT_ID),
            client_id=SecretStr(PII_AZURE_CLIENT_ID),
            client_secret=SecretStr(PII_AZURE_CLIENT_SECRET),
            scope="https://cognitiveservices.azure.com/.default",
        ),
        splunk=SplunkConfiguration.model_construct(
            enabled=True,
            url=PII_SPLUNK_URL,
            token_path=Path(PII_SPLUNK_TOKEN_PATH),
            index=PII_SPLUNK_INDEX,
            source="lightspeed-stack",
            timeout=5,
            verify_ssl=True,
        ),
        rag=RagConfiguration.model_construct(
            inline=["okp", "my-rag"],
            tool=["my-rag"],
        ),
        okp=OkpConfiguration.model_construct(
            rhokp_url=PII_OKP_URL,
            offline=True,
            chunk_filter_query=PII_OKP_CHUNK_FILTER,
        ),
        reranker=RerankerConfiguration.model_construct(
            enabled=True,
            model="cross-encoder/ms-marco-MiniLM-L6-v2",
        ),
        approvals=ApprovalsConfiguration.model_construct(
            approval_timeout_seconds=600,
            approval_retention_days=90,
        ),
        rlsapi_v1=RlsapiV1Configuration.model_construct(
            allow_verbose_infer=True,
            quota_subject="user_id",
        ),
        saved_prompts=SavedPromptsConfiguration.model_construct(
            max_prompts_per_user=100,
            max_display_name_length=200,
            max_content_length=5000,
        ),
        skills=SkillsConfiguration.model_construct(
            paths=[Path(PII_SKILLS_PATH)],
        ),
        deployment_environment="production",
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
            max_retries=5,
            retry_delay=2,
            allow_degraded_mode=False,
            config=None,
        ),
        inference=InferenceConfiguration.model_construct(
            default_model=None,
            default_provider=None,
            context_windows={},
            max_infer_iters=10,
            max_tool_calls=30,
            providers=[],
        ),
        authentication=AuthenticationConfiguration.model_construct(
            module="noop",
            skip_tls_verification=False,
            skip_for_health_probes=False,
            skip_for_metrics=False,
            k8s_cluster_api=None,
            k8s_ca_cert_path=None,
            jwk_config=None,
            api_key_config=None,
            rh_identity_config=None,
            trusted_proxy_config=None,
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
        compaction=CompactionConfiguration.model_construct(
            enabled=False,
            threshold_ratio=0.7,
            token_floor=4096,
            buffer_turns=4,
            buffer_max_ratio=0.3,
        ),
        byok_rag=[],
        a2a_state=None,
        a2a_agents=None,
        quota_handlers=None,
        azure_entra_id=None,
        splunk=None,
        rag=RagConfiguration.model_construct(
            inline=[],
            tool=[],
        ),
        okp=OkpConfiguration.model_construct(
            rhokp_url=None,
            offline=True,
            chunk_filter_query=None,
        ),
        reranker=RerankerConfiguration.model_construct(
            enabled=False,
            model="cross-encoder/ms-marco-MiniLM-L6-v2",
        ),
        approvals=ApprovalsConfiguration.model_construct(
            approval_timeout_seconds=300,
            approval_retention_days=30,
        ),
        rlsapi_v1=RlsapiV1Configuration.model_construct(
            allow_verbose_infer=False,
            quota_subject=None,
        ),
        saved_prompts=SavedPromptsConfiguration.model_construct(
            max_prompts_per_user=50,
            max_display_name_length=255,
            max_content_length=10000,
        ),
        skills=None,
        deployment_environment="development",
    )


@pytest.fixture(name="llama_stack_config_file")
def llama_stack_config_file_fixture(tmp_path: Path) -> str:
    """Write SAMPLE_LLAMA_STACK_CONFIG to a temp YAML file and return its path.

    Parameters:
    ----------
        tmp_path: Pytest-managed temporary directory (auto-cleaned).

    Returns:
    -------
        str: Path to the temporary YAML file.
    """
    path = tmp_path / "llama_stack_config.yaml"
    path.write_text(yaml.dump(SAMPLE_LLAMA_STACK_CONFIG))
    return str(path)
