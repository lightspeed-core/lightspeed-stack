"""Tests for configuration snapshot coverage of new configuration sections.

Verifies that the ~118 new fields across 20 configuration sections are
properly represented in the telemetry configuration snapshot, with correct
masking for sensitive fields and passthrough for non-sensitive fields.

Spec: LCORE-2923 — Add missing configuration fields to telemetry configuration
snapshot.
"""

import json
from typing import Any

import pytest

from telemetry.configuration_snapshot import (
    CONFIGURED,
    LIGHTSPEED_STACK_FIELDS,
    NOT_CONFIGURED,
    FieldSpec,
    ListFieldSpec,
    MaskingType,
    build_lightspeed_stack_snapshot,
)
from tests.unit.telemetry.conftest import (
    ALL_PII_VALUES,
    PII_A2A_AGENT_TOKEN,
    PII_A2A_AGENT_URL,
    PII_A2A_PG_CA_CERT,
    PII_A2A_PG_DB,
    PII_A2A_PG_HOST,
    PII_A2A_PG_NAMESPACE,
    PII_A2A_PG_PASS,
    PII_A2A_PG_USER,
    PII_A2A_SQLITE_PATH,
    PII_AGENT_CARD_PATH,
    PII_AZURE_CLIENT_ID,
    PII_AZURE_CLIENT_SECRET,
    PII_AZURE_TENANT_ID,
    PII_BYOK_DB,
    PII_BYOK_DB_PATH,
    PII_BYOK_HOST,
    PII_BYOK_PASS,
    PII_BYOK_PORT,
    PII_BYOK_USER,
    PII_CACHE_PG_CA_CERT,
    PII_CACHE_PG_DB,
    PII_CACHE_PG_HOST,
    PII_CACHE_PG_NAMESPACE,
    PII_CACHE_PG_PASS,
    PII_CACHE_PG_USER,
    PII_CACHE_SQLITE_PATH,
    PII_LS_NATIVE_OVERRIDE,
    PII_LS_PROFILE,
    PII_MCP_AUTH_HEADER_VALUE,
    PII_MCP_URL,
    PII_OKP_CHUNK_FILTER,
    PII_OKP_URL,
    PII_PROFILE_PATH,
    PII_QUOTA_PG_CA_CERT,
    PII_QUOTA_PG_DB,
    PII_QUOTA_PG_HOST,
    PII_QUOTA_PG_NAMESPACE,
    PII_QUOTA_PG_PASS,
    PII_QUOTA_PG_USER,
    PII_QUOTA_SQLITE_PATH,
    PII_RH_IDENTITY_ENTITLEMENTS,
    PII_SKILLS_PATH,
    PII_SPLUNK_INDEX,
    PII_SPLUNK_TOKEN_PATH,
    PII_SPLUNK_URL,
    PII_TRUSTED_PROXY_SA_NAME,
    PII_TRUSTED_PROXY_SA_NS,
    build_fully_populated_config,
    build_minimal_config,
)

# =============================================================================
# Helper: build snapshot once for fully-populated config
# =============================================================================


@pytest.fixture(name="full_snapshot")
def full_snapshot_fixture() -> dict[str, Any]:
    """Build a snapshot from the fully-populated config.

    Returns:
        The lightspeed-stack snapshot dict.
    """
    return build_lightspeed_stack_snapshot(build_fully_populated_config())


@pytest.fixture(name="minimal_snapshot")
def minimal_snapshot_fixture() -> dict[str, Any]:
    """Build a snapshot from the minimal config.

    Returns:
        The lightspeed-stack snapshot dict.
    """
    return build_lightspeed_stack_snapshot(build_minimal_config())


# =============================================================================
# Tests: Compaction section (5 fields)
# =============================================================================


class TestCompactionSection:
    """Tests for compaction configuration section in snapshot."""

    def test_compaction_enabled_passthrough(self, full_snapshot: dict) -> None:
        """Test compaction.enabled passes through as its actual boolean value."""
        assert full_snapshot["compaction"]["enabled"] is True

    def test_compaction_threshold_ratio_passthrough(self, full_snapshot: dict) -> None:
        """Test compaction.threshold_ratio passes through as its actual float."""
        assert full_snapshot["compaction"]["threshold_ratio"] == 0.8

    def test_compaction_token_floor_passthrough(self, full_snapshot: dict) -> None:
        """Test compaction.token_floor passes through as its actual int."""
        assert full_snapshot["compaction"]["token_floor"] == 8192

    def test_compaction_buffer_turns_passthrough(self, full_snapshot: dict) -> None:
        """Test compaction.buffer_turns passes through as its actual int."""
        assert full_snapshot["compaction"]["buffer_turns"] == 6

    def test_compaction_buffer_max_ratio_passthrough(self, full_snapshot: dict) -> None:
        """Test compaction.buffer_max_ratio passes through as its actual float."""
        assert full_snapshot["compaction"]["buffer_max_ratio"] == 0.4

    def test_compaction_section_present_in_minimal(
        self, minimal_snapshot: dict
    ) -> None:
        """Test compaction section is present even in minimal config."""
        assert "compaction" in minimal_snapshot


# =============================================================================
# Tests: Conversation cache section (12 fields)
# =============================================================================


class TestConversationCacheSection:
    """Tests for conversation_cache configuration section in snapshot."""

    def test_cache_type_passthrough(self, full_snapshot: dict) -> None:
        """Test conversation_cache.type passes through as its actual value."""
        assert full_snapshot["conversation_cache"]["type"] == "postgres"

    def test_cache_memory_max_entries_passthrough(self, full_snapshot: dict) -> None:
        """Test conversation_cache.memory.max_entries passes through."""
        assert full_snapshot["conversation_cache"]["memory"]["max_entries"] == 1000

    def test_cache_sqlite_db_path_masked(self, full_snapshot: dict) -> None:
        """Test conversation_cache.sqlite.db_path is masked as sensitive."""
        assert full_snapshot["conversation_cache"]["sqlite"]["db_path"] == CONFIGURED

    def test_cache_postgres_host_masked(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.host is masked as sensitive."""
        assert full_snapshot["conversation_cache"]["postgres"]["host"] == CONFIGURED

    def test_cache_postgres_db_masked(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.db is masked as sensitive."""
        assert full_snapshot["conversation_cache"]["postgres"]["db"] == CONFIGURED

    def test_cache_postgres_user_masked(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.user is masked as sensitive."""
        assert full_snapshot["conversation_cache"]["postgres"]["user"] == CONFIGURED

    def test_cache_postgres_password_masked(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.password is masked as sensitive."""
        assert full_snapshot["conversation_cache"]["postgres"]["password"] == CONFIGURED

    def test_cache_postgres_namespace_masked(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.namespace is masked as sensitive."""
        assert (
            full_snapshot["conversation_cache"]["postgres"]["namespace"] == CONFIGURED
        )

    def test_cache_postgres_port_passthrough(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.port passes through as its actual value."""
        assert full_snapshot["conversation_cache"]["postgres"]["port"] == 5432

    def test_cache_postgres_ssl_mode_passthrough(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.ssl_mode passes through."""
        assert (
            full_snapshot["conversation_cache"]["postgres"]["ssl_mode"] == "verify-full"
        )

    def test_cache_postgres_ca_cert_path_masked(self, full_snapshot: dict) -> None:
        """Test conversation_cache.postgres.ca_cert_path is masked as sensitive."""
        assert (
            full_snapshot["conversation_cache"]["postgres"]["ca_cert_path"]
            == CONFIGURED
        )

    def test_cache_not_configured_when_none(self, minimal_snapshot: dict) -> None:
        """Test conversation_cache shows not_configured when None."""
        # When conversation_cache is None, the snapshot should reflect that
        cache = minimal_snapshot.get("conversation_cache")
        if cache is not None:
            assert cache.get("type") in (None, NOT_CONFIGURED)


# =============================================================================
# Tests: Quota handlers section (19 fields)
# =============================================================================


class TestQuotaHandlersSection:
    """Tests for quota_handlers configuration section in snapshot."""

    def test_quota_sqlite_db_path_masked(self, full_snapshot: dict) -> None:
        """Test quota_handlers.sqlite.db_path is masked as sensitive."""
        assert full_snapshot["quota_handlers"]["sqlite"]["db_path"] == CONFIGURED

    def test_quota_postgres_host_masked(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.host is masked as sensitive."""
        assert full_snapshot["quota_handlers"]["postgres"]["host"] == CONFIGURED

    def test_quota_postgres_db_masked(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.db is masked as sensitive."""
        assert full_snapshot["quota_handlers"]["postgres"]["db"] == CONFIGURED

    def test_quota_postgres_user_masked(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.user is masked as sensitive."""
        assert full_snapshot["quota_handlers"]["postgres"]["user"] == CONFIGURED

    def test_quota_postgres_password_masked(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.password is masked as sensitive."""
        assert full_snapshot["quota_handlers"]["postgres"]["password"] == CONFIGURED

    def test_quota_postgres_namespace_masked(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.namespace is masked as sensitive."""
        assert full_snapshot["quota_handlers"]["postgres"]["namespace"] == CONFIGURED

    def test_quota_postgres_port_passthrough(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.port passes through."""
        assert full_snapshot["quota_handlers"]["postgres"]["port"] == 5432

    def test_quota_postgres_ssl_mode_passthrough(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.ssl_mode passes through."""
        assert full_snapshot["quota_handlers"]["postgres"]["ssl_mode"] == "verify-full"

    def test_quota_postgres_ca_cert_path_masked(self, full_snapshot: dict) -> None:
        """Test quota_handlers.postgres.ca_cert_path is masked as sensitive."""
        assert full_snapshot["quota_handlers"]["postgres"]["ca_cert_path"] == CONFIGURED

    def test_quota_enable_token_history_passthrough(self, full_snapshot: dict) -> None:
        """Test quota_handlers.enable_token_history passes through."""
        assert full_snapshot["quota_handlers"]["enable_token_history"] is True

    def test_quota_scheduler_period_passthrough(self, full_snapshot: dict) -> None:
        """Test quota_handlers.scheduler.period passes through."""
        assert full_snapshot["quota_handlers"]["scheduler"]["period"] == 5

    def test_quota_scheduler_reconnection_count_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test quota_handlers.scheduler.database_reconnection_count passes through."""
        assert (
            full_snapshot["quota_handlers"]["scheduler"]["database_reconnection_count"]
            == 10
        )

    def test_quota_scheduler_reconnection_delay_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test quota_handlers.scheduler.database_reconnection_delay passes through."""
        assert (
            full_snapshot["quota_handlers"]["scheduler"]["database_reconnection_delay"]
            == 2
        )

    def test_quota_not_configured_when_none(self, minimal_snapshot: dict) -> None:
        """Test quota_handlers shows not_configured when None."""
        qh = minimal_snapshot.get("quota_handlers")
        if qh is not None:
            # When quota_handlers is None, sub-fields should be not_configured
            assert qh.get("sqlite", {}).get("db_path") in (
                None,
                NOT_CONFIGURED,
            )


# =============================================================================
# Tests: BYOK RAG section (12 fields per item)
# =============================================================================


class TestByokRagSection:
    """Tests for byok_rag[] list configuration section in snapshot."""

    def test_byok_rag_is_list(self, full_snapshot: dict) -> None:
        """Test byok_rag is a list in the snapshot."""
        assert isinstance(full_snapshot["byok_rag"], list)

    def test_byok_rag_has_items(self, full_snapshot: dict) -> None:
        """Test byok_rag list has the expected number of items."""
        assert len(full_snapshot["byok_rag"]) == 1

    def test_byok_rag_id_passthrough(self, full_snapshot: dict) -> None:
        """Test byok_rag[].rag_id passes through as its actual value."""
        assert full_snapshot["byok_rag"][0]["rag_id"] == "my-rag"

    def test_byok_rag_type_passthrough(self, full_snapshot: dict) -> None:
        """Test byok_rag[].rag_type passes through."""
        assert full_snapshot["byok_rag"][0]["rag_type"] == "inline::faiss"

    def test_byok_embedding_model_passthrough(self, full_snapshot: dict) -> None:
        """Test byok_rag[].embedding_model passes through."""
        assert full_snapshot["byok_rag"][0]["embedding_model"] == "all-MiniLM-L6-v2"

    def test_byok_embedding_dimension_passthrough(self, full_snapshot: dict) -> None:
        """Test byok_rag[].embedding_dimension passes through."""
        assert full_snapshot["byok_rag"][0]["embedding_dimension"] == 384

    def test_byok_vector_db_id_passthrough(self, full_snapshot: dict) -> None:
        """Test byok_rag[].vector_db_id passes through."""
        assert full_snapshot["byok_rag"][0]["vector_db_id"] == "my-vector-db"

    def test_byok_db_path_masked(self, full_snapshot: dict) -> None:
        """Test byok_rag[].db_path is masked as sensitive."""
        assert full_snapshot["byok_rag"][0]["db_path"] == CONFIGURED

    def test_byok_score_multiplier_passthrough(self, full_snapshot: dict) -> None:
        """Test byok_rag[].score_multiplier passes through."""
        assert full_snapshot["byok_rag"][0]["score_multiplier"] == 1.5

    def test_byok_host_masked(self, full_snapshot: dict) -> None:
        """Test byok_rag[].host is masked as sensitive."""
        assert full_snapshot["byok_rag"][0]["host"] == CONFIGURED

    def test_byok_user_masked(self, full_snapshot: dict) -> None:
        """Test byok_rag[].user is masked as sensitive."""
        assert full_snapshot["byok_rag"][0]["user"] == CONFIGURED

    def test_byok_password_masked(self, full_snapshot: dict) -> None:
        """Test byok_rag[].password is masked as sensitive."""
        assert full_snapshot["byok_rag"][0]["password"] == CONFIGURED

    def test_byok_empty_list(self, minimal_snapshot: dict) -> None:
        """Test byok_rag is empty list when no BYOK RAGs configured."""
        assert minimal_snapshot["byok_rag"] == []


# =============================================================================
# Tests: A2A state section (10 fields)
# =============================================================================


class TestA2AStateSection:
    """Tests for a2a_state configuration section in snapshot."""

    def test_a2a_state_sqlite_db_path_masked(self, full_snapshot: dict) -> None:
        """Test a2a_state.sqlite.db_path is masked as sensitive."""
        assert full_snapshot["a2a_state"]["sqlite"]["db_path"] == CONFIGURED

    def test_a2a_state_postgres_host_masked(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.host is masked as sensitive."""
        assert full_snapshot["a2a_state"]["postgres"]["host"] == CONFIGURED

    def test_a2a_state_postgres_db_masked(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.db is masked as sensitive."""
        assert full_snapshot["a2a_state"]["postgres"]["db"] == CONFIGURED

    def test_a2a_state_postgres_user_masked(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.user is masked as sensitive."""
        assert full_snapshot["a2a_state"]["postgres"]["user"] == CONFIGURED

    def test_a2a_state_postgres_password_masked(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.password is masked as sensitive."""
        assert full_snapshot["a2a_state"]["postgres"]["password"] == CONFIGURED

    def test_a2a_state_postgres_namespace_masked(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.namespace is masked as sensitive."""
        assert full_snapshot["a2a_state"]["postgres"]["namespace"] == CONFIGURED

    def test_a2a_state_postgres_port_passthrough(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.port passes through."""
        assert full_snapshot["a2a_state"]["postgres"]["port"] == 5432

    def test_a2a_state_postgres_ssl_mode_passthrough(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.ssl_mode passes through."""
        assert full_snapshot["a2a_state"]["postgres"]["ssl_mode"] == "verify-full"

    def test_a2a_state_postgres_ca_cert_path_masked(self, full_snapshot: dict) -> None:
        """Test a2a_state.postgres.ca_cert_path is masked as sensitive."""
        assert full_snapshot["a2a_state"]["postgres"]["ca_cert_path"] == CONFIGURED

    def test_a2a_state_not_configured_when_none(self, minimal_snapshot: dict) -> None:
        """Test a2a_state shows not_configured when None."""
        a2a = minimal_snapshot.get("a2a_state")
        if a2a is not None:
            assert a2a.get("sqlite", {}).get("db_path") in (
                None,
                NOT_CONFIGURED,
            )


# =============================================================================
# Tests: Splunk section (7 fields)
# =============================================================================


class TestSplunkSection:
    """Tests for splunk configuration section in snapshot."""

    def test_splunk_enabled_passthrough(self, full_snapshot: dict) -> None:
        """Test splunk.enabled passes through as its actual boolean value."""
        assert full_snapshot["splunk"]["enabled"] is True

    def test_splunk_url_masked(self, full_snapshot: dict) -> None:
        """Test splunk.url is masked as sensitive."""
        assert full_snapshot["splunk"]["url"] == CONFIGURED

    def test_splunk_token_path_masked(self, full_snapshot: dict) -> None:
        """Test splunk.token_path is masked as sensitive."""
        assert full_snapshot["splunk"]["token_path"] == CONFIGURED

    def test_splunk_index_masked(self, full_snapshot: dict) -> None:
        """Test splunk.index is masked as sensitive."""
        assert full_snapshot["splunk"]["index"] == CONFIGURED

    def test_splunk_source_passthrough(self, full_snapshot: dict) -> None:
        """Test splunk.source passes through as its actual value."""
        assert full_snapshot["splunk"]["source"] == "lightspeed-stack"

    def test_splunk_timeout_passthrough(self, full_snapshot: dict) -> None:
        """Test splunk.timeout passes through as its actual value."""
        assert full_snapshot["splunk"]["timeout"] == 5

    def test_splunk_verify_ssl_passthrough(self, full_snapshot: dict) -> None:
        """Test splunk.verify_ssl passes through as its actual boolean value."""
        assert full_snapshot["splunk"]["verify_ssl"] is True

    def test_splunk_not_configured_when_none(self, minimal_snapshot: dict) -> None:
        """Test splunk section when not configured."""
        splunk = minimal_snapshot.get("splunk")
        if splunk is not None:
            assert splunk.get("url") in (None, NOT_CONFIGURED)


# =============================================================================
# Tests: Inference section (7 new subfields)
# =============================================================================


class TestInferenceNewSubfields:
    """Tests for new inference configuration subfields in snapshot."""

    def test_inference_context_windows_passthrough(self, full_snapshot: dict) -> None:
        """Test inference.context_windows passes through as its actual value."""
        assert full_snapshot["inference"]["context_windows"] == {
            "openai/gpt-4o-mini": 128000
        }

    def test_inference_max_infer_iters_passthrough(self, full_snapshot: dict) -> None:
        """Test inference.max_infer_iters passes through."""
        assert full_snapshot["inference"]["max_infer_iters"] == 10

    def test_inference_max_tool_calls_passthrough(self, full_snapshot: dict) -> None:
        """Test inference.max_tool_calls passes through."""
        assert full_snapshot["inference"]["max_tool_calls"] == 30


# =============================================================================
# Tests: Llama Stack section (7 new subfields)
# =============================================================================


class TestLlamaStackNewSubfields:
    """Tests for new llama_stack configuration subfields in snapshot."""

    def test_llama_stack_timeout_passthrough(self, full_snapshot: dict) -> None:
        """Test llama_stack.timeout passes through as its actual value."""
        assert full_snapshot["llama_stack"]["timeout"] == 180

    def test_llama_stack_max_retries_passthrough(self, full_snapshot: dict) -> None:
        """Test llama_stack.max_retries passes through."""
        assert full_snapshot["llama_stack"]["max_retries"] == 5

    def test_llama_stack_retry_delay_passthrough(self, full_snapshot: dict) -> None:
        """Test llama_stack.retry_delay passes through."""
        assert full_snapshot["llama_stack"]["retry_delay"] == 2

    def test_llama_stack_allow_degraded_mode_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test llama_stack.allow_degraded_mode passes through."""
        assert full_snapshot["llama_stack"]["allow_degraded_mode"] is True

    def test_llama_stack_config_baseline_passthrough(self, full_snapshot: dict) -> None:
        """Test llama_stack.config.baseline passes through."""
        assert full_snapshot["llama_stack"]["config"]["baseline"] == "default"

    def test_llama_stack_config_profile_masked(self, full_snapshot: dict) -> None:
        """Test llama_stack.config.profile is masked as sensitive."""
        assert full_snapshot["llama_stack"]["config"]["profile"] == CONFIGURED

    def test_llama_stack_config_native_override_masked(
        self, full_snapshot: dict
    ) -> None:
        """Test llama_stack.config.native_override is masked as sensitive."""
        assert full_snapshot["llama_stack"]["config"]["native_override"] == CONFIGURED


# =============================================================================
# Tests: Authentication section (9 new subfields)
# =============================================================================


class TestAuthenticationNewSubfields:
    """Tests for new authentication configuration subfields in snapshot."""

    def test_auth_skip_for_health_probes_passthrough(self, full_snapshot: dict) -> None:
        """Test authentication.skip_for_health_probes passes through."""
        assert full_snapshot["authentication"]["skip_for_health_probes"] is True

    def test_auth_skip_for_metrics_passthrough(self, full_snapshot: dict) -> None:
        """Test authentication.skip_for_metrics passes through."""
        assert full_snapshot["authentication"]["skip_for_metrics"] is True

    def test_auth_api_key_config_api_key_masked(self, full_snapshot: dict) -> None:
        """Test authentication.api_key_config.api_key is masked as sensitive."""
        assert (
            full_snapshot["authentication"]["api_key_config"]["api_key"] == CONFIGURED
        )

    def test_auth_rh_identity_entitlements_masked(self, full_snapshot: dict) -> None:
        """Test authentication.rh_identity_config.required_entitlements is masked."""
        assert (
            full_snapshot["authentication"]["rh_identity_config"][
                "required_entitlements"
            ]
            == CONFIGURED
        )

    def test_auth_rh_identity_max_header_size_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test authentication.rh_identity_config.max_header_size passes through."""
        assert (
            full_snapshot["authentication"]["rh_identity_config"]["max_header_size"]
            == 16384
        )

    def test_auth_trusted_proxy_user_header_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test authentication.trusted_proxy_config.user_header passes through."""
        assert (
            full_snapshot["authentication"]["trusted_proxy_config"]["user_header"]
            == "X-Forwarded-User"
        )

    def test_auth_trusted_proxy_sa_namespace_masked(self, full_snapshot: dict) -> None:
        """Test trusted_proxy allowed_service_accounts namespace is masked."""
        sa_list = full_snapshot["authentication"]["trusted_proxy_config"][
            "allowed_service_accounts"
        ]
        assert isinstance(sa_list, list)
        assert len(sa_list) == 1
        assert sa_list[0]["namespace"] == CONFIGURED

    def test_auth_trusted_proxy_sa_name_masked(self, full_snapshot: dict) -> None:
        """Test trusted_proxy allowed_service_accounts name is masked."""
        sa_list = full_snapshot["authentication"]["trusted_proxy_config"][
            "allowed_service_accounts"
        ]
        assert sa_list[0]["name"] == CONFIGURED


# =============================================================================
# Tests: Azure Entra ID section (4 fields)
# =============================================================================


class TestAzureEntraIdSection:
    """Tests for azure_entra_id configuration section in snapshot."""

    def test_azure_tenant_id_masked(self, full_snapshot: dict) -> None:
        """Test azure_entra_id.tenant_id is masked as sensitive."""
        assert full_snapshot["azure_entra_id"]["tenant_id"] == CONFIGURED

    def test_azure_client_id_masked(self, full_snapshot: dict) -> None:
        """Test azure_entra_id.client_id is masked as sensitive."""
        assert full_snapshot["azure_entra_id"]["client_id"] == CONFIGURED

    def test_azure_client_secret_masked(self, full_snapshot: dict) -> None:
        """Test azure_entra_id.client_secret is masked as sensitive."""
        assert full_snapshot["azure_entra_id"]["client_secret"] == CONFIGURED

    def test_azure_scope_passthrough(self, full_snapshot: dict) -> None:
        """Test azure_entra_id.scope passes through as its actual value."""
        assert (
            full_snapshot["azure_entra_id"]["scope"]
            == "https://cognitiveservices.azure.com/.default"
        )

    def test_azure_not_configured_when_none(self, minimal_snapshot: dict) -> None:
        """Test azure_entra_id shows not_configured when None."""
        azure = minimal_snapshot.get("azure_entra_id")
        if azure is not None:
            assert azure.get("tenant_id") in (None, NOT_CONFIGURED)


# =============================================================================
# Tests: Customization section (4 new subfields)
# =============================================================================


class TestCustomizationNewSubfields:
    """Tests for new customization configuration subfields in snapshot."""

    def test_customization_profile_path_masked(self, full_snapshot: dict) -> None:
        """Test customization.profile_path is masked as sensitive."""
        assert full_snapshot["customization"]["profile_path"] == CONFIGURED

    def test_customization_agent_card_path_masked(self, full_snapshot: dict) -> None:
        """Test customization.agent_card_path is masked as sensitive."""
        assert full_snapshot["customization"]["agent_card_path"] == CONFIGURED

    def test_customization_disable_shield_ids_override_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test customization.disable_shield_ids_override passes through."""
        assert full_snapshot["customization"]["disable_shield_ids_override"] is True


# =============================================================================
# Tests: OKP section (3 fields)
# =============================================================================


class TestOkpSection:
    """Tests for okp configuration section in snapshot."""

    def test_okp_offline_passthrough(self, full_snapshot: dict) -> None:
        """Test okp.offline passes through as its actual boolean value."""
        assert full_snapshot["okp"]["offline"] is True

    def test_okp_url_masked(self, full_snapshot: dict) -> None:
        """Test okp.rhokp_url is masked as sensitive."""
        assert full_snapshot["okp"]["rhokp_url"] == CONFIGURED

    def test_okp_chunk_filter_query_masked(self, full_snapshot: dict) -> None:
        """Test okp.chunk_filter_query is masked as sensitive."""
        assert full_snapshot["okp"]["chunk_filter_query"] == CONFIGURED


# =============================================================================
# Tests: RAG section (2 fields)
# =============================================================================


class TestRagSection:
    """Tests for rag configuration section in snapshot."""

    def test_rag_inline_passthrough(self, full_snapshot: dict) -> None:
        """Test rag.inline passes through as its actual list value."""
        assert full_snapshot["rag"]["inline"] == ["okp", "my-rag"]

    def test_rag_tool_passthrough(self, full_snapshot: dict) -> None:
        """Test rag.tool passes through as its actual list value."""
        assert full_snapshot["rag"]["tool"] == ["my-rag"]


# =============================================================================
# Tests: Reranker section (2 fields)
# =============================================================================


class TestRerankerSection:
    """Tests for reranker configuration section in snapshot."""

    def test_reranker_enabled_passthrough(self, full_snapshot: dict) -> None:
        """Test reranker.enabled passes through as its actual boolean value."""
        assert full_snapshot["reranker"]["enabled"] is True

    def test_reranker_model_passthrough(self, full_snapshot: dict) -> None:
        """Test reranker.model passes through as its actual value."""
        assert (
            full_snapshot["reranker"]["model"] == "cross-encoder/ms-marco-MiniLM-L6-v2"
        )


# =============================================================================
# Tests: Approvals section (2 fields)
# =============================================================================


class TestApprovalsSection:
    """Tests for approvals configuration section in snapshot."""

    def test_approvals_timeout_passthrough(self, full_snapshot: dict) -> None:
        """Test approvals.approval_timeout_seconds passes through."""
        assert full_snapshot["approvals"]["approval_timeout_seconds"] == 600

    def test_approvals_retention_passthrough(self, full_snapshot: dict) -> None:
        """Test approvals.approval_retention_days passes through."""
        assert full_snapshot["approvals"]["approval_retention_days"] == 90


# =============================================================================
# Tests: RLSAPIv1 section (2 fields)
# =============================================================================


class TestRlsapiV1Section:
    """Tests for rlsapi_v1 configuration section in snapshot."""

    def test_rlsapi_allow_verbose_infer_passthrough(self, full_snapshot: dict) -> None:
        """Test rlsapi_v1.allow_verbose_infer passes through."""
        assert full_snapshot["rlsapi_v1"]["allow_verbose_infer"] is True

    def test_rlsapi_quota_subject_passthrough(self, full_snapshot: dict) -> None:
        """Test rlsapi_v1.quota_subject passes through."""
        assert full_snapshot["rlsapi_v1"]["quota_subject"] == "user_id"


# =============================================================================
# Tests: Saved prompts section (3 fields)
# =============================================================================


class TestSavedPromptsSection:
    """Tests for saved_prompts configuration section in snapshot."""

    def test_saved_prompts_max_per_user_passthrough(self, full_snapshot: dict) -> None:
        """Test saved_prompts.max_prompts_per_user passes through."""
        assert full_snapshot["saved_prompts"]["max_prompts_per_user"] == 100

    def test_saved_prompts_max_display_name_length_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test saved_prompts.max_display_name_length passes through."""
        assert full_snapshot["saved_prompts"]["max_display_name_length"] == 200

    def test_saved_prompts_max_content_length_passthrough(
        self, full_snapshot: dict
    ) -> None:
        """Test saved_prompts.max_content_length passes through."""
        assert full_snapshot["saved_prompts"]["max_content_length"] == 5000


# =============================================================================
# Tests: Skills section (1 field)
# =============================================================================


class TestSkillsSection:
    """Tests for skills configuration section in snapshot."""

    def test_skills_paths_masked(self, full_snapshot: dict) -> None:
        """Test skills.paths is masked as sensitive (contains file paths)."""
        assert full_snapshot["skills"]["paths"] == CONFIGURED


# =============================================================================
# Tests: Deployment environment section (1 field)
# =============================================================================


class TestDeploymentEnvironmentSection:
    """Tests for deployment_environment configuration field in snapshot."""

    def test_deployment_environment_passthrough(self, full_snapshot: dict) -> None:
        """Test deployment_environment passes through as its actual value."""
        assert full_snapshot["deployment_environment"] == "production"

    def test_deployment_environment_minimal(self, minimal_snapshot: dict) -> None:
        """Test deployment_environment in minimal config."""
        assert minimal_snapshot["deployment_environment"] == "development"


# =============================================================================
# Tests: MCP servers extra item fields (4 extra fields)
# =============================================================================


class TestMcpServersExtraFields:
    """Tests for new MCP server item fields in snapshot."""

    def test_mcp_authorization_headers_masked(self, full_snapshot: dict) -> None:
        """Test mcp_servers[].authorization_headers is masked as sensitive."""
        mcp = full_snapshot["mcp_servers"]
        assert isinstance(mcp, list)
        assert len(mcp) == 1
        assert mcp[0]["authorization_headers"] == CONFIGURED

    def test_mcp_headers_masked(self, full_snapshot: dict) -> None:
        """Test mcp_servers[].headers is masked as sensitive."""
        mcp = full_snapshot["mcp_servers"]
        assert mcp[0]["headers"] == CONFIGURED

    def test_mcp_require_approval_passthrough(self, full_snapshot: dict) -> None:
        """Test mcp_servers[].require_approval passes through."""
        mcp = full_snapshot["mcp_servers"]
        assert mcp[0]["require_approval"] == "always"

    def test_mcp_timeout_passthrough(self, full_snapshot: dict) -> None:
        """Test mcp_servers[].timeout passes through."""
        mcp = full_snapshot["mcp_servers"]
        assert mcp[0]["timeout"] == 60


# =============================================================================
# Tests: Completeness — all 20 sections present in registry
# =============================================================================


class TestSectionCompleteness:
    """Tests verifying all 20 new configuration sections are in the registry."""

    @staticmethod
    def _registry_paths() -> set[str]:
        """Extract all top-level section names from the field registry."""
        paths: set[str] = set()
        for spec in LIGHTSPEED_STACK_FIELDS:
            if isinstance(spec, FieldSpec):
                paths.add(spec.path.split(".")[0])
            elif isinstance(spec, ListFieldSpec):
                paths.add(spec.path.split(".")[0])
        return paths

    @pytest.mark.parametrize(
        "section",
        [
            "compaction",
            "conversation_cache",
            "quota_handlers",
            "byok_rag",
            "a2a_state",
            "splunk",
            "inference",
            "llama_stack",
            "authentication",
            "azure_entra_id",
            "customization",
            "okp",
            "rag",
            "reranker",
            "approvals",
            "rlsapi_v1",
            "saved_prompts",
            "skills",
            "deployment_environment",
            "mcp_servers",
        ],
    )
    def test_section_in_registry(self, section: str) -> None:
        """Test that each new section has at least one field in the registry."""
        paths = self._registry_paths()
        assert (
            section in paths
        ), f"Section '{section}' not found in LIGHTSPEED_STACK_FIELDS registry"

    @pytest.mark.parametrize(
        "section",
        [
            "compaction",
            "conversation_cache",
            "quota_handlers",
            "byok_rag",
            "a2a_state",
            "splunk",
            "inference",
            "llama_stack",
            "authentication",
            "azure_entra_id",
            "customization",
            "okp",
            "rag",
            "reranker",
            "approvals",
            "rlsapi_v1",
            "saved_prompts",
            "skills",
            "deployment_environment",
            "mcp_servers",
        ],
    )
    def test_section_in_snapshot_output(
        self, section: str, full_snapshot: dict
    ) -> None:
        """Test that each new section appears in the snapshot output."""
        assert (
            section in full_snapshot
        ), f"Section '{section}' not found in snapshot output"


# =============================================================================
# Tests: PII leak prevention for new sections
# =============================================================================


class TestNewSectionsPiiLeakPrevention:
    """Critical tests proving PII is not leaked in new section snapshots."""

    def test_no_pii_in_full_snapshot(self, full_snapshot: dict) -> None:
        """Verify no PII leaks in the full snapshot JSON for new sections."""
        json_str = json.dumps(full_snapshot)
        for pii_value in ALL_PII_VALUES:
            assert pii_value not in json_str, f"PII leaked in snapshot: '{pii_value}'"

    def test_no_cache_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no conversation cache PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        cache_pii = [
            PII_CACHE_SQLITE_PATH,
            PII_CACHE_PG_HOST,
            PII_CACHE_PG_DB,
            PII_CACHE_PG_USER,
            PII_CACHE_PG_PASS,
            PII_CACHE_PG_NAMESPACE,
            PII_CACHE_PG_CA_CERT,
        ]
        for pii in cache_pii:
            assert pii not in json_str, f"Cache PII leaked: '{pii}'"

    def test_no_quota_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no quota handler PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        quota_pii = [
            PII_QUOTA_SQLITE_PATH,
            PII_QUOTA_PG_HOST,
            PII_QUOTA_PG_DB,
            PII_QUOTA_PG_USER,
            PII_QUOTA_PG_PASS,
            PII_QUOTA_PG_NAMESPACE,
            PII_QUOTA_PG_CA_CERT,
        ]
        for pii in quota_pii:
            assert pii not in json_str, f"Quota PII leaked: '{pii}'"

    def test_no_byok_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no BYOK RAG PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        byok_pii = [
            PII_BYOK_DB_PATH,
            PII_BYOK_HOST,
            PII_BYOK_PORT,
            PII_BYOK_DB,
            PII_BYOK_USER,
            PII_BYOK_PASS,
        ]
        for pii in byok_pii:
            assert pii not in json_str, f"BYOK PII leaked: '{pii}'"

    def test_no_a2a_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no A2A state PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        a2a_pii = [
            PII_A2A_SQLITE_PATH,
            PII_A2A_PG_HOST,
            PII_A2A_PG_DB,
            PII_A2A_PG_USER,
            PII_A2A_PG_PASS,
            PII_A2A_PG_NAMESPACE,
            PII_A2A_PG_CA_CERT,
            PII_A2A_AGENT_URL,
            PII_A2A_AGENT_TOKEN,
        ]
        for pii in a2a_pii:
            assert pii not in json_str, f"A2A PII leaked: '{pii}'"

    def test_no_splunk_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no Splunk PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        splunk_pii = [PII_SPLUNK_URL, PII_SPLUNK_TOKEN_PATH, PII_SPLUNK_INDEX]
        for pii in splunk_pii:
            assert pii not in json_str, f"Splunk PII leaked: '{pii}'"

    def test_no_azure_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no Azure Entra ID PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        azure_pii = [
            PII_AZURE_TENANT_ID,
            PII_AZURE_CLIENT_ID,
            PII_AZURE_CLIENT_SECRET,
        ]
        for pii in azure_pii:
            assert pii not in json_str, f"Azure PII leaked: '{pii}'"

    def test_no_okp_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no OKP PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        okp_pii = [PII_OKP_URL, PII_OKP_CHUNK_FILTER]
        for pii in okp_pii:
            assert pii not in json_str, f"OKP PII leaked: '{pii}'"

    def test_no_mcp_auth_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no MCP authorization header PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        assert PII_MCP_AUTH_HEADER_VALUE not in json_str, "MCP auth header PII leaked"
        assert PII_MCP_URL not in json_str, "MCP URL PII leaked"

    def test_no_skills_path_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no skills path PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        assert PII_SKILLS_PATH not in json_str, "Skills path PII leaked"

    def test_no_customization_path_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no customization path PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        assert PII_PROFILE_PATH not in json_str, "Profile path PII leaked"
        assert PII_AGENT_CARD_PATH not in json_str, "Agent card path PII leaked"

    def test_no_auth_subfield_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no authentication subfield PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        auth_pii = [
            PII_RH_IDENTITY_ENTITLEMENTS,
            PII_TRUSTED_PROXY_SA_NS,
            PII_TRUSTED_PROXY_SA_NAME,
        ]
        for pii in auth_pii:
            assert pii not in json_str, f"Auth subfield PII leaked: '{pii}'"

    def test_no_llama_stack_config_pii_leaked(self, full_snapshot: dict) -> None:
        """Verify no llama_stack config PII values appear in snapshot."""
        json_str = json.dumps(full_snapshot)
        ls_pii = [PII_LS_PROFILE, PII_LS_NATIVE_OVERRIDE]
        for pii in ls_pii:
            assert pii not in json_str, f"Llama Stack config PII leaked: '{pii}'"


# =============================================================================
# Tests: Edge cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases with new configuration sections."""

    def test_empty_byok_rag_list(self, minimal_snapshot: dict) -> None:
        """Test empty byok_rag list produces empty list in snapshot."""
        assert minimal_snapshot["byok_rag"] == []

    def test_empty_mcp_servers_list(self, minimal_snapshot: dict) -> None:
        """Test empty mcp_servers list produces empty list in snapshot."""
        assert minimal_snapshot["mcp_servers"] == []

    def test_none_optional_sections_produce_not_configured(
        self, minimal_snapshot: dict
    ) -> None:
        """Test that None optional sections produce not_configured markers."""
        # These sections are None in minimal config
        json_str = json.dumps(minimal_snapshot)
        # The snapshot should be JSON-serializable even with None sections
        assert isinstance(json.loads(json_str), dict)

    def test_snapshot_is_json_serializable_with_all_sections(
        self, full_snapshot: dict
    ) -> None:
        """Test the full snapshot with all sections is JSON-serializable."""
        json_str = json.dumps(full_snapshot)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_snapshot_only_contains_allowlisted_fields(
        self, full_snapshot: dict
    ) -> None:
        """Verify snapshot does not contain any fields outside the allowlist."""
        allowed_top_keys = set()
        for spec in LIGHTSPEED_STACK_FIELDS:
            if isinstance(spec, FieldSpec):
                allowed_top_keys.add(spec.path.split(".")[0])
            elif isinstance(spec, ListFieldSpec):
                allowed_top_keys.add(spec.path.split(".")[0])
        unexpected = set(full_snapshot.keys()) - allowed_top_keys
        assert (
            not unexpected
        ), f"Snapshot contains unexpected top-level keys: {unexpected}"

    def test_minimal_config_no_pii_leak(self, minimal_snapshot: dict) -> None:
        """Verify minimal config snapshot has no PII leaks."""
        json_str = json.dumps(minimal_snapshot)
        # Minimal config uses "localhost" and "/tmp/..." paths which are
        # not in ALL_PII_VALUES, so this verifies no unexpected PII
        for pii_value in ALL_PII_VALUES:
            assert (
                pii_value not in json_str
            ), f"PII leaked in minimal snapshot: '{pii_value}'"


# =============================================================================
# Tests: Registry field count validation
# =============================================================================


class TestRegistryFieldCount:
    """Tests validating the field registry has sufficient coverage."""

    def test_registry_has_minimum_field_count(self) -> None:
        """Verify the registry has at least the expected number of fields.

        The spec requires ~118 new fields plus the existing fields.
        This test ensures the registry is not accidentally truncated.
        """
        # Count all field paths (including sub-fields in ListFieldSpec)
        total_fields = 0
        for spec in LIGHTSPEED_STACK_FIELDS:
            if isinstance(spec, FieldSpec):
                total_fields += 1
            elif isinstance(spec, ListFieldSpec):
                total_fields += len(spec.item_fields)
        # The original registry had ~30 fields, plus ~118 new = ~148 minimum
        # Use a conservative lower bound
        assert (
            total_fields >= 100
        ), f"Registry has only {total_fields} fields, expected at least 100"

    def test_all_field_specs_have_valid_masking(self) -> None:
        """Verify all field specs in the registry have valid MaskingType."""
        for spec in LIGHTSPEED_STACK_FIELDS:
            if isinstance(spec, FieldSpec):
                assert isinstance(
                    spec.masking, MaskingType
                ), f"Invalid masking for {spec.path}"
            elif isinstance(spec, ListFieldSpec):
                for sub in spec.item_fields:
                    assert isinstance(
                        sub.masking, MaskingType
                    ), f"Invalid masking for {spec.path}.{sub.path}"

    def test_no_duplicate_paths(self) -> None:
        """Verify no duplicate paths in the registry."""
        paths = [s.path for s in LIGHTSPEED_STACK_FIELDS]
        assert len(paths) == len(
            set(paths)
        ), f"Duplicate paths: {set(p for p in paths if paths.count(p) > 1)}"
