"""Tests for configuration snapshot with PII masking."""

# pylint: disable=too-many-lines,too-many-public-methods

import json
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml
from pydantic import SecretStr

import constants
from models.config import Action, JsonPathOperator
from telemetry.configuration_snapshot import (
    CONFIGURED,
    LIGHTSPEED_STACK_FIELDS,
    LLAMA_STACK_FIELDS,
    NOT_AVAILABLE,
    NOT_CONFIGURED,
    FieldSpec,
    ListFieldSpec,
    MaskingType,
    _extract_field,
    _extract_list_field,
    _extract_store_info,
    _serialize_passthrough,
    _set_nested_value,
    build_configuration_snapshot,
    build_lightspeed_stack_snapshot,
    build_llama_stack_snapshot,
    get_nested_value,
    mask_value,
)
from tests.unit.telemetry.conftest import (
    ALL_PII_VALUES,
    BYOK_PORT,
    LLAMA_STACK_PII_VALUES,
    OKP_CHUNK_FILTER,
    SAMPLE_LLAMA_STACK_CONFIG,
    build_fully_populated_config,
    build_minimal_config,
)

# =============================================================================
# Tests: get_nested_value
# =============================================================================


class TestGetNestedValue:
    """Tests for get_nested_value function."""

    def test_dict_simple_key(self) -> None:
        """Test simple key lookup in a dict."""
        assert get_nested_value({"a": 1}, "a") == 1

    def test_dict_nested_key(self) -> None:
        """Test nested key lookup in a dict."""
        assert get_nested_value({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_dict_missing_key(self) -> None:
        """Test missing key returns None."""
        assert get_nested_value({"a": 1}, "b") is None

    def test_dict_missing_intermediate(self) -> None:
        """Test missing intermediate key returns None."""
        assert get_nested_value({"a": 1}, "a.b.c") is None

    def test_dict_none_intermediate(self) -> None:
        """Test None intermediate returns None."""
        assert get_nested_value({"a": None}, "a.b") is None

    def test_none_root(self) -> None:
        """Test None root returns None."""
        assert get_nested_value(None, "a.b") is None

    def test_pydantic_model(self) -> None:
        """Test attribute access on a Pydantic model."""
        config = build_minimal_config()
        assert get_nested_value(config, "service.port") == 8080

    def test_pydantic_model_nested(self) -> None:
        """Test deeply nested attribute access on Pydantic models."""
        config = build_fully_populated_config()
        assert (
            get_nested_value(
                config,
                "authentication.jwk_config.jwt_configuration.user_id_claim",
            )
            == "sub"
        )

    def test_pydantic_model_none_intermediate(self) -> None:
        """Test None intermediate in Pydantic model returns None."""
        config = build_minimal_config()
        assert get_nested_value(config, "authentication.jwk_config.url") is None


# =============================================================================
# Tests: _serialize_passthrough
# =============================================================================


class TestSerializePassthrough:
    """Tests for _serialize_passthrough function."""

    def test_none(self) -> None:
        """Test None returns None."""
        assert _serialize_passthrough(None) is None

    def test_bool(self) -> None:
        """Test bool passes through."""
        assert _serialize_passthrough(True) is True
        assert _serialize_passthrough(False) is False

    def test_int(self) -> None:
        """Test int passes through."""
        assert _serialize_passthrough(42) == 42

    def test_float(self) -> None:
        """Test float passes through."""
        assert _serialize_passthrough(3.14) == 3.14

    def test_str(self) -> None:
        """Test str passes through."""
        assert _serialize_passthrough("hello") == "hello"

    def test_enum(self) -> None:
        """Test enum returns its value."""

        class TestColor(Enum):
            """Test enum for serialization."""

            RED = "red"

        assert _serialize_passthrough(TestColor.RED) == "red"

    def test_action_enum(self) -> None:
        """Test Action enum serialization."""
        assert _serialize_passthrough(Action.QUERY) == "query"

    def test_json_path_operator_enum(self) -> None:
        """Test JsonPathOperator enum serialization."""
        assert _serialize_passthrough(JsonPathOperator.EQUALS) == "equals"

    def test_list(self) -> None:
        """Test list with mixed types."""
        result = _serialize_passthrough([1, "a", True, Action.QUERY])
        assert result == [1, "a", True, "query"]

    def test_empty_list(self) -> None:
        """Test empty list."""
        assert _serialize_passthrough([]) == []

    def test_dict(self) -> None:
        """Test dict serialization."""
        assert _serialize_passthrough({"a": 1, "b": "x"}) == {"a": 1, "b": "x"}

    def test_secret_str_safety(self) -> None:
        """Test SecretStr is masked even in passthrough mode."""
        assert _serialize_passthrough(SecretStr("secret")) == CONFIGURED

    def test_path_safety(self) -> None:
        """Test Path is masked even in passthrough mode."""
        assert _serialize_passthrough(PurePosixPath("/etc/secret")) == CONFIGURED


# =============================================================================
# Tests: mask_value
# =============================================================================


class TestMaskValue:
    """Tests for mask_value function."""

    def test_sensitive_with_value(self) -> None:
        """Test sensitive masking with non-None value returns 'configured'."""
        assert mask_value("secret", MaskingType.SENSITIVE) == CONFIGURED

    def test_sensitive_with_none(self) -> None:
        """Test sensitive masking with None returns 'not_configured'."""
        assert mask_value(None, MaskingType.SENSITIVE) == NOT_CONFIGURED

    def test_sensitive_with_secret_str(self) -> None:
        """Test sensitive masking with SecretStr returns 'configured'."""
        assert mask_value(SecretStr("key"), MaskingType.SENSITIVE) == CONFIGURED

    def test_sensitive_with_path(self) -> None:
        """Test sensitive masking with Path returns 'configured'."""
        assert (
            mask_value(PurePosixPath("/etc/cert"), MaskingType.SENSITIVE) == CONFIGURED
        )

    def test_sensitive_with_empty_string(self) -> None:
        """Test sensitive masking with empty string returns 'not_configured'."""
        assert mask_value("", MaskingType.SENSITIVE) == NOT_CONFIGURED

    def test_passthrough_bool(self) -> None:
        """Test passthrough returns bool as-is."""
        assert mask_value(True, MaskingType.PASSTHROUGH) is True

    def test_passthrough_int(self) -> None:
        """Test passthrough returns int as-is."""
        assert mask_value(8080, MaskingType.PASSTHROUGH) == 8080

    def test_passthrough_string(self) -> None:
        """Test passthrough returns string as-is."""
        assert mask_value("noop", MaskingType.PASSTHROUGH) == "noop"

    def test_passthrough_none(self) -> None:
        """Test passthrough with None returns None."""
        assert mask_value(None, MaskingType.PASSTHROUGH) is None

    def test_passthrough_list(self) -> None:
        """Test passthrough with list returns list."""
        assert mask_value(["GET", "POST"], MaskingType.PASSTHROUGH) == ["GET", "POST"]

    def test_rag_sources_with_okp(self) -> None:
        """Test RAG_SOURCES summarizes ids as count + okp_enabled flag."""
        assert mask_value(
            [constants.OKP_RAG_ID, "my-rag"], MaskingType.RAG_SOURCES
        ) == {
            "count": 2,
            "okp_enabled": True,
        }

    def test_rag_sources_without_okp(self) -> None:
        """Test RAG_SOURCES reports okp_enabled False when sentinel absent."""
        assert mask_value(["a", "b", "c"], MaskingType.RAG_SOURCES) == {
            "count": 3,
            "okp_enabled": False,
        }

    def test_rag_sources_empty(self) -> None:
        """Test RAG_SOURCES with empty list reports zero count."""
        assert mask_value([], MaskingType.RAG_SOURCES) == {
            "count": 0,
            "okp_enabled": False,
        }

    def test_rag_sources_none(self) -> None:
        """Test RAG_SOURCES with None reports zero count."""
        assert mask_value(None, MaskingType.RAG_SOURCES) == {
            "count": 0,
            "okp_enabled": False,
        }

    def test_rag_sources_never_leaks_ids(self) -> None:
        """Test RAG_SOURCES never emits the raw (potentially PII) source ids."""
        sensitive_id = "sensitive-private-rag-id"
        result = mask_value(
            [sensitive_id, constants.OKP_RAG_ID], MaskingType.RAG_SOURCES
        )
        assert sensitive_id not in str(result)
        assert result == {"count": 2, "okp_enabled": True}


# =============================================================================
# Tests: _set_nested_value
# =============================================================================


class TestSetNestedValue:
    """Tests for _set_nested_value function."""

    def test_simple_key(self) -> None:
        """Test setting a top-level key."""
        target: dict[str, Any] = {}
        _set_nested_value(target, "name", "test")
        assert target == {"name": "test"}

    def test_nested_key(self) -> None:
        """Test setting a nested key creates intermediates."""
        target: dict[str, Any] = {}
        _set_nested_value(target, "service.workers", 4)
        assert target == {"service": {"workers": 4}}

    def test_deeply_nested(self) -> None:
        """Test deeply nested path."""
        target: dict[str, Any] = {}
        _set_nested_value(target, "a.b.c.d", "value")
        assert target == {"a": {"b": {"c": {"d": "value"}}}}

    def test_multiple_fields_same_parent(self) -> None:
        """Test multiple fields under the same parent."""
        target: dict[str, Any] = {}
        _set_nested_value(target, "service.workers", 4)
        _set_nested_value(target, "service.port", 8080)
        assert target == {"service": {"workers": 4, "port": 8080}}

    def test_path_prefix_collision(self) -> None:
        """Test that a scalar at a.b is replaced by a dict when a.b.c is set."""
        target: dict[str, Any] = {}
        _set_nested_value(target, "a.b", "scalar")
        _set_nested_value(target, "a.b.c", "nested")
        assert target == {"a": {"b": {"c": "nested"}}}


# =============================================================================
# Tests: _extract_field and _extract_list_field
# =============================================================================


class TestExtractField:
    """Tests for _extract_field function."""

    def test_passthrough_from_dict(self) -> None:
        """Test passthrough extraction from a dict."""
        source = {"a": {"b": 42}}
        assert _extract_field(source, FieldSpec("a.b", MaskingType.PASSTHROUGH)) == 42

    def test_sensitive_from_dict(self) -> None:
        """Test sensitive extraction from a dict."""
        source = {"secret": "password123"}
        result = _extract_field(source, FieldSpec("secret", MaskingType.SENSITIVE))
        assert result == CONFIGURED

    def test_missing_field(self) -> None:
        """Test missing field returns appropriate default."""
        source: dict[str, Any] = {}
        assert (
            _extract_field(source, FieldSpec("missing", MaskingType.SENSITIVE))
            == NOT_CONFIGURED
        )
        assert (
            _extract_field(source, FieldSpec("missing", MaskingType.PASSTHROUGH))
            is None
        )


class TestExtractListField:
    """Tests for _extract_list_field function."""

    def test_extract_items(self) -> None:
        """Test extracting list items with sub-fields."""
        source = {"items": [{"name": "a", "secret": "x"}, {"name": "b", "secret": "y"}]}
        spec = ListFieldSpec(
            "items",
            item_fields=(
                FieldSpec("name", MaskingType.PASSTHROUGH),
                FieldSpec("secret", MaskingType.SENSITIVE),
            ),
        )
        result = _extract_list_field(source, spec)
        assert result == [
            {"name": "a", "secret": CONFIGURED},
            {"name": "b", "secret": CONFIGURED},
        ]

    def test_empty_list(self) -> None:
        """Test empty list returns empty list."""
        source: dict[str, Any] = {"items": []}
        spec = ListFieldSpec(
            "items", item_fields=(FieldSpec("name", MaskingType.PASSTHROUGH),)
        )
        assert _extract_list_field(source, spec) == []

    def test_none_list(self) -> None:
        """Test None list returns NOT_CONFIGURED."""
        source = {"items": None}
        spec = ListFieldSpec(
            "items", item_fields=(FieldSpec("name", MaskingType.PASSTHROUGH),)
        )
        assert _extract_list_field(source, spec) == NOT_CONFIGURED

    def test_missing_list(self) -> None:
        """Test missing list path returns NOT_CONFIGURED."""
        source: dict[str, Any] = {}
        spec = ListFieldSpec(
            "items", item_fields=(FieldSpec("name", MaskingType.PASSTHROUGH),)
        )
        assert _extract_list_field(source, spec) == NOT_CONFIGURED


# =============================================================================
# Tests: _extract_store_info
# =============================================================================


class TestExtractStoreInfo:
    """Tests for _extract_store_info function."""

    def test_inference_store(self) -> None:
        """Test inference store extraction."""
        result = _extract_store_info(SAMPLE_LLAMA_STACK_CONFIG, "inference")
        assert result["type"] == "sql_sqlite"
        assert result["db_path"] == CONFIGURED

    def test_metadata_store_with_namespace(self) -> None:
        """Test metadata store extraction includes namespace."""
        result = _extract_store_info(SAMPLE_LLAMA_STACK_CONFIG, "metadata")
        assert result["type"] == "kv_sqlite"
        assert result["db_path"] == CONFIGURED
        assert result["namespace"] == "registry"

    def test_missing_store(self) -> None:
        """Test missing store returns not_configured."""
        result = _extract_store_info(SAMPLE_LLAMA_STACK_CONFIG, "nonexistent")
        assert result["type"] == NOT_CONFIGURED
        assert result["db_path"] == NOT_CONFIGURED

    def test_no_storage_section(self) -> None:
        """Test config without storage section."""
        result = _extract_store_info({}, "inference")
        assert result["type"] == NOT_CONFIGURED

    def test_db_path_is_masked(self) -> None:
        """Test that db_path never leaks the actual path."""
        result = _extract_store_info(SAMPLE_LLAMA_STACK_CONFIG, "inference")
        assert "/secret/path" not in str(result)


# =============================================================================
# Tests: build_lightspeed_stack_snapshot
# =============================================================================


class TestBuildLightspeedStackSnapshot:
    """Tests for build_lightspeed_stack_snapshot function."""

    def test_minimal_config_snapshot(self) -> None:
        """Test snapshot from minimal config has expected structure."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["name"] == "minimal"
        assert snapshot["service"]["workers"] == 1
        assert snapshot["service"]["port"] == 8080
        assert snapshot["service"]["auth_enabled"] is False
        assert snapshot["service"]["host"] == CONFIGURED

    def test_sensitive_fields_masked(self) -> None:
        """Test all sensitive fields are masked in fully-populated config."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["service"]["host"] == CONFIGURED
        assert snapshot["service"]["tls_config"]["tls_certificate_path"] == CONFIGURED
        assert snapshot["service"]["tls_config"]["tls_key_path"] == CONFIGURED
        assert snapshot["service"]["tls_config"]["tls_key_password"] == CONFIGURED
        assert snapshot["service"]["cors"]["allow_origins"] == CONFIGURED
        assert snapshot["llama_stack"]["url"] == CONFIGURED
        assert snapshot["llama_stack"]["api_key"] == CONFIGURED
        assert snapshot["llama_stack"]["library_client_config_path"] == CONFIGURED
        assert snapshot["authentication"]["k8s_cluster_api"] == CONFIGURED
        assert snapshot["authentication"]["k8s_ca_cert_path"] == CONFIGURED
        assert snapshot["authentication"]["jwk_config"]["url"] == CONFIGURED
        assert snapshot["user_data_collection"]["feedback_storage"] == CONFIGURED
        assert snapshot["user_data_collection"]["transcripts_storage"] == CONFIGURED
        assert snapshot["customization"]["system_prompt"] == CONFIGURED
        assert snapshot["customization"]["system_prompt_path"] == CONFIGURED
        assert snapshot["database"]["sqlite"]["db_path"] == CONFIGURED
        assert snapshot["database"]["postgres"]["host"] == CONFIGURED
        assert snapshot["database"]["postgres"]["db"] == CONFIGURED
        assert snapshot["database"]["postgres"]["user"] == CONFIGURED
        assert snapshot["database"]["postgres"]["password"] == CONFIGURED
        assert snapshot["database"]["postgres"]["namespace"] == CONFIGURED
        assert snapshot["database"]["postgres"]["ca_cert_path"] == CONFIGURED

    def test_passthrough_fields_preserved(self) -> None:
        """Test non-sensitive fields pass through correctly."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["service"]["workers"] == 4
        assert snapshot["service"]["port"] == 8080
        assert snapshot["service"]["auth_enabled"] is True
        assert snapshot["service"]["color_log"] is True
        assert snapshot["service"]["access_log"] is False
        assert snapshot["service"]["cors"]["allow_credentials"] is True
        assert snapshot["service"]["cors"]["allow_methods"] == ["GET", "POST"]
        assert snapshot["llama_stack"]["use_as_library_client"] is False
        assert snapshot["inference"]["default_model"] == "gpt-4o-mini"
        assert snapshot["inference"]["default_provider"] == "openai"
        assert snapshot["authentication"]["module"] == "jwk_token"
        assert snapshot["authentication"]["skip_tls_verification"] is False

    def test_optional_none_fields(self) -> None:
        """Test optional fields that are None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert (
            snapshot["service"]["tls_config"]["tls_certificate_path"] == NOT_CONFIGURED
        )
        assert snapshot["service"]["tls_config"]["tls_key_path"] == NOT_CONFIGURED
        assert snapshot["llama_stack"]["url"] == NOT_CONFIGURED
        assert snapshot["llama_stack"]["api_key"] == NOT_CONFIGURED
        assert snapshot["authentication"]["jwk_config"]["url"] == NOT_CONFIGURED
        assert snapshot["customization"]["system_prompt"] == NOT_CONFIGURED
        assert snapshot["database"]["postgres"]["host"] == NOT_CONFIGURED

    def test_list_field_mcp_servers(self) -> None:
        """Test MCP servers list extraction with masking."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        mcp = snapshot["mcp_servers"]
        assert isinstance(mcp, list)
        assert len(mcp) == 1
        assert mcp[0]["name"] == "my-mcp-server"
        assert mcp[0]["provider_id"] == "model-context-protocol"
        assert mcp[0]["url"] == CONFIGURED
        assert mcp[0]["authorization_headers"] == CONFIGURED
        assert mcp[0]["headers"] == CONFIGURED
        assert mcp[0]["require_approval"] == "always"
        assert mcp[0]["timeout"] == 60

    def test_empty_mcp_servers(self) -> None:
        """Test empty MCP servers list."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["mcp_servers"] == []

    def test_role_rules_extraction(self) -> None:
        """Test JWT role rules list extraction with value masking."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        rules = snapshot["authentication"]["jwk_config"]["jwt_configuration"][
            "role_rules"
        ]
        assert isinstance(rules, list)
        assert len(rules) == 1
        assert rules[0]["jsonpath"] == "$.org_id"
        assert rules[0]["operator"] == "equals"
        assert rules[0]["value"] == CONFIGURED
        assert rules[0]["roles"] == ["admin"]
        assert rules[0]["negate"] is False

    def test_access_rules_extraction(self) -> None:
        """Test authorization access rules extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        rules = snapshot["authorization"]["access_rules"]
        assert isinstance(rules, list)
        assert len(rules) == 2
        assert rules[0]["role"] == "admin"
        assert rules[0]["actions"] == ["admin"]
        assert rules[1]["role"] == "user"
        assert rules[1]["actions"] == ["query", "feedback"]

    def test_authorization_none(self) -> None:
        """Test authorization section when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["authorization"]["access_rules"] == NOT_CONFIGURED

    def test_database_ssl_mode_passthrough(self) -> None:
        """Test database ssl_mode and gss_encmode pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["database"]["postgres"]["ssl_mode"] == "verify-full"
        assert snapshot["database"]["postgres"]["gss_encmode"] == "prefer"

    def test_service_base_url_masked(self) -> None:
        """Test service base_url is masked as sensitive."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["service"]["base_url"] == CONFIGURED

    def test_service_base_url_none(self) -> None:
        """Test service base_url when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["service"]["base_url"] == NOT_CONFIGURED

    def test_service_root_path_masked(self) -> None:
        """Test service root_path is masked as sensitive."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["service"]["root_path"] == CONFIGURED

    def test_llama_stack_timeout_passthrough(self) -> None:
        """Test llama_stack timeout passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["timeout"] == 180

    def test_llama_stack_max_retries_passthrough(self) -> None:
        """Test llama_stack max_retries passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["max_retries"] == 5

    def test_llama_stack_retry_delay_passthrough(self) -> None:
        """Test llama_stack retry_delay passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["retry_delay"] == 2

    def test_llama_stack_allow_degraded_mode_passthrough(self) -> None:
        """Test llama_stack allow_degraded_mode passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["allow_degraded_mode"] is True

    def test_llama_stack_config_baseline_passthrough(self) -> None:
        """Test llama_stack config baseline passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["config"]["baseline"] == "default"

    def test_llama_stack_config_profile_masked(self) -> None:
        """Test llama_stack config profile is masked as sensitive."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["config"]["profile"] == CONFIGURED

    def test_llama_stack_config_native_override_masked(self) -> None:
        """Test llama_stack config native_override is masked as sensitive."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["config"]["native_override"] == CONFIGURED

    def test_llama_stack_config_none(self) -> None:
        """Test llama_stack config fields when config is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["llama_stack"]["config"]["baseline"] is None
        assert snapshot["llama_stack"]["config"]["profile"] == NOT_CONFIGURED
        assert snapshot["llama_stack"]["config"]["native_override"] == NOT_CONFIGURED

    def test_inference_context_windows_passthrough(self) -> None:
        """Test inference context_windows passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["inference"]["context_windows"] == {
            "openai/gpt-4o-mini": 128000
        }

    def test_inference_max_infer_iters_passthrough(self) -> None:
        """Test inference max_infer_iters passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["inference"]["max_infer_iters"] == 10

    def test_inference_max_tool_calls_passthrough(self) -> None:
        """Test inference max_tool_calls passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["inference"]["max_tool_calls"] == 30

    def test_inference_providers_extraction(self) -> None:
        """Test inference providers list extraction with masking."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        providers = snapshot["inference"]["providers"]
        assert isinstance(providers, list)
        assert len(providers) == 1
        assert providers[0]["type"] == "openai"
        assert providers[0]["id"] == "openai-provider"
        assert providers[0]["api_key_env"] == CONFIGURED
        assert providers[0]["allowed_models"] == ["gpt-4o-mini", "gpt-4o"]

    def test_inference_providers_empty(self) -> None:
        """Test inference providers when empty."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["inference"]["providers"] == []

    def test_authentication_skip_for_health_probes(self) -> None:
        """Test authentication skip_for_health_probes passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["authentication"]["skip_for_health_probes"] is True

    def test_authentication_skip_for_metrics(self) -> None:
        """Test authentication skip_for_metrics passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["authentication"]["skip_for_metrics"] is True

    def test_authentication_api_key_config_masked(self) -> None:
        """Test authentication api_key_config.api_key is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["authentication"]["api_key_config"]["api_key"] == CONFIGURED

    def test_authentication_api_key_config_none(self) -> None:
        """Test authentication api_key_config when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["authentication"]["api_key_config"]["api_key"] == NOT_CONFIGURED

    def test_authentication_rh_identity_config(self) -> None:
        """Test authentication rh_identity_config fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert (
            snapshot["authentication"]["rh_identity_config"]["required_entitlements"]
            == CONFIGURED
        )
        assert (
            snapshot["authentication"]["rh_identity_config"]["max_header_size"] == 16384
        )

    def test_authentication_rh_identity_config_none(self) -> None:
        """Test authentication rh_identity_config when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert (
            snapshot["authentication"]["rh_identity_config"]["required_entitlements"]
            == NOT_CONFIGURED
        )
        assert (
            snapshot["authentication"]["rh_identity_config"]["max_header_size"] is None
        )

    def test_authentication_trusted_proxy_config(self) -> None:
        """Test authentication trusted_proxy_config fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert (
            snapshot["authentication"]["trusted_proxy_config"]["user_header"]
            == "X-Forwarded-User"
        )
        accounts = snapshot["authentication"]["trusted_proxy_config"][
            "allowed_service_accounts"
        ]
        assert isinstance(accounts, list)
        assert len(accounts) == 1
        assert accounts[0]["namespace"] == CONFIGURED
        assert accounts[0]["name"] == CONFIGURED

    def test_authentication_trusted_proxy_config_none(self) -> None:
        """Test authentication trusted_proxy_config when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["authentication"]["trusted_proxy_config"]["user_header"] is None
        assert (
            snapshot["authentication"]["trusted_proxy_config"][
                "allowed_service_accounts"
            ]
            == NOT_CONFIGURED
        )

    def test_azure_entra_id_fields(self) -> None:
        """Test azure_entra_id fields are properly masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["azure_entra_id"]["tenant_id"] == CONFIGURED
        assert snapshot["azure_entra_id"]["client_id"] == CONFIGURED
        assert snapshot["azure_entra_id"]["client_secret"] == CONFIGURED
        assert (
            snapshot["azure_entra_id"]["scope"]
            == "https://cognitiveservices.azure.com/.default"
        )

    def test_azure_entra_id_none(self) -> None:
        """Test azure_entra_id when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["azure_entra_id"]["tenant_id"] == NOT_CONFIGURED
        assert snapshot["azure_entra_id"]["client_id"] == NOT_CONFIGURED
        assert snapshot["azure_entra_id"]["client_secret"] == NOT_CONFIGURED
        assert snapshot["azure_entra_id"]["scope"] is None

    def test_customization_profile_path_masked(self) -> None:
        """Test customization profile_path is masked as sensitive."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["customization"]["profile_path"] == CONFIGURED

    def test_customization_disable_shield_ids_override(self) -> None:
        """Test customization disable_shield_ids_override passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["customization"]["disable_shield_ids_override"] is True

    def test_customization_agent_card_path_masked(self) -> None:
        """Test customization agent_card_path is masked as sensitive."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["customization"]["agent_card_path"] == CONFIGURED

    def test_conversation_cache_fields(self) -> None:
        """Test conversation_cache fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        cache = snapshot["conversation_cache"]
        assert cache["type"] == "postgres"
        assert cache["memory"]["max_entries"] == 1000
        assert cache["sqlite"]["db_path"] == CONFIGURED
        assert cache["postgres"]["host"] == CONFIGURED
        assert cache["postgres"]["port"] == 5432
        assert cache["postgres"]["db"] == CONFIGURED
        assert cache["postgres"]["user"] == CONFIGURED
        assert cache["postgres"]["password"] == CONFIGURED
        assert cache["postgres"]["namespace"] == CONFIGURED
        assert cache["postgres"]["ssl_mode"] == "verify-full"
        assert cache["postgres"]["gss_encmode"] == "prefer"
        assert cache["postgres"]["ca_cert_path"] == CONFIGURED

    def test_conversation_cache_none(self) -> None:
        """Test conversation_cache when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["conversation_cache"]["type"] is None
        assert snapshot["conversation_cache"]["memory"]["max_entries"] is None
        assert snapshot["conversation_cache"]["sqlite"]["db_path"] == NOT_CONFIGURED
        assert snapshot["conversation_cache"]["postgres"]["host"] == NOT_CONFIGURED

    def test_compaction_fields(self) -> None:
        """Test compaction fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        compaction = snapshot["compaction"]
        assert compaction["enabled"] is True
        assert compaction["threshold_ratio"] == 0.8
        assert compaction["token_floor"] == 8192
        assert compaction["buffer_turns"] == 6
        assert compaction["buffer_max_ratio"] == 0.4

    def test_compaction_defaults(self) -> None:
        """Test compaction fields with default values."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        compaction = snapshot["compaction"]
        assert compaction["enabled"] is False
        assert compaction["threshold_ratio"] == 0.7
        assert compaction["token_floor"] == 4096
        assert compaction["buffer_turns"] == 4
        assert compaction["buffer_max_ratio"] == 0.3

    def test_quota_handlers_fields(self) -> None:
        """Test quota_handlers fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        qh = snapshot["quota_handlers"]
        assert qh["sqlite"]["db_path"] == CONFIGURED
        assert qh["postgres"]["host"] == CONFIGURED
        assert qh["postgres"]["port"] == 5432
        assert qh["postgres"]["db"] == CONFIGURED
        assert qh["postgres"]["user"] == CONFIGURED
        assert qh["postgres"]["password"] == CONFIGURED
        assert qh["postgres"]["namespace"] == CONFIGURED
        assert qh["postgres"]["ssl_mode"] == "verify-full"
        assert qh["postgres"]["gss_encmode"] == "prefer"
        assert qh["postgres"]["ca_cert_path"] == CONFIGURED
        assert qh["enable_token_history"] is True

    def test_quota_handlers_limiters(self) -> None:
        """Test quota_handlers limiters list extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        limiters = snapshot["quota_handlers"]["limiters"]
        assert isinstance(limiters, list)
        assert len(limiters) == 1
        assert limiters[0]["type"] == "user_limiter"
        assert limiters[0]["name"] == "daily-user-limit"
        assert limiters[0]["initial_quota"] == 10000
        assert limiters[0]["quota_increase"] == 0
        assert limiters[0]["period"] == "1 day"

    def test_quota_handlers_scheduler(self) -> None:
        """Test quota_handlers scheduler fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        scheduler = snapshot["quota_handlers"]["scheduler"]
        assert scheduler["period"] == 5
        assert scheduler["database_reconnection_count"] == 10
        assert scheduler["database_reconnection_delay"] == 2

    def test_quota_handlers_none(self) -> None:
        """Test quota_handlers when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["quota_handlers"]["sqlite"]["db_path"] == NOT_CONFIGURED
        assert snapshot["quota_handlers"]["postgres"]["host"] == NOT_CONFIGURED

    def test_byok_rag_extraction(self) -> None:
        """Test rag.byok.stores list extraction with masking."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        byok = snapshot["rag"]["byok"]["stores"]
        assert isinstance(byok, list)
        assert len(byok) == 1
        # rag_id / vector_db_id are user-chosen names -> masked as sensitive
        assert byok[0]["rag_id"] == CONFIGURED
        assert byok[0]["backend"] == "faiss"
        assert byok[0]["embedding_model"] == "all-MiniLM-L6-v2"
        assert byok[0]["embedding_dimension"] == 384
        assert byok[0]["vector_db_id"] == CONFIGURED
        assert byok[0]["db_path"] == CONFIGURED
        assert byok[0]["score_multiplier"] == 1.5
        assert byok[0]["relevance_cutoff_score"] == 0.42
        assert byok[0]["host"] == CONFIGURED
        assert byok[0]["port"] == BYOK_PORT
        assert byok[0]["db"] == CONFIGURED
        assert byok[0]["user"] == CONFIGURED
        assert byok[0]["password"] == CONFIGURED

    def test_byok_rag_empty(self) -> None:
        """Test rag.byok.stores when empty."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["rag"]["byok"]["stores"] == []

    def test_a2a_state_fields(self) -> None:
        """Test a2a_state fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        a2a = snapshot["a2a_state"]
        assert a2a["sqlite"]["db_path"] == CONFIGURED
        assert a2a["postgres"]["host"] == CONFIGURED
        assert a2a["postgres"]["port"] == 5432
        assert a2a["postgres"]["db"] == CONFIGURED
        assert a2a["postgres"]["user"] == CONFIGURED
        assert a2a["postgres"]["password"] == CONFIGURED
        assert a2a["postgres"]["namespace"] == CONFIGURED
        assert a2a["postgres"]["ssl_mode"] == "verify-full"
        assert a2a["postgres"]["gss_encmode"] == "prefer"
        assert a2a["postgres"]["ca_cert_path"] == CONFIGURED

    def test_a2a_state_none(self) -> None:
        """Test a2a_state when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["a2a_state"]["sqlite"]["db_path"] == NOT_CONFIGURED
        assert snapshot["a2a_state"]["postgres"]["host"] == NOT_CONFIGURED

    def test_splunk_fields(self) -> None:
        """Test splunk fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        splunk = snapshot["splunk"]
        assert splunk["enabled"] is True
        assert splunk["url"] == CONFIGURED
        assert splunk["token_path"] == CONFIGURED
        assert splunk["index"] == CONFIGURED
        assert splunk["source"] == "lightspeed-stack"
        assert splunk["timeout"] == 5
        assert splunk["verify_ssl"] is True

    def test_splunk_none(self) -> None:
        """Test splunk when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["splunk"]["enabled"] is None
        assert snapshot["splunk"]["url"] == NOT_CONFIGURED
        assert snapshot["splunk"]["token_path"] == NOT_CONFIGURED
        assert snapshot["splunk"]["index"] == NOT_CONFIGURED
        assert snapshot["splunk"]["source"] is None

    def test_rag_fields(self) -> None:
        """Test rag retrieval strategy fields extraction.

        sources are summarized as {count, okp_enabled}: the user-chosen rag_ids
        are not emitted, but the OKP sentinel is surfaced as a boolean.
        """
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        retrieval = snapshot["rag"]["retrieval"]
        # inline sources = ["okp", "my-rag"] -> 2 sources, OKP enabled
        assert retrieval["inline"]["sources"] == {"count": 2, "okp_enabled": True}
        # tool sources = ["my-rag"] -> 1 source, OKP not enabled
        assert retrieval["tool"]["sources"] == {"count": 1, "okp_enabled": False}

    def test_rag_defaults(self) -> None:
        """Test rag retrieval strategy fields with defaults."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        retrieval = snapshot["rag"]["retrieval"]
        assert retrieval["inline"]["sources"] == {"count": 0, "okp_enabled": False}
        assert retrieval["tool"]["sources"] == {"count": 0, "okp_enabled": False}

    def test_okp_fields(self) -> None:
        """Test okp fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        okp = snapshot["rag"]["okp"]
        assert okp["rhokp_url"] == CONFIGURED
        assert okp["offline"] is True
        # chunk_filter_query is passthrough (not treated as PII)
        assert okp["chunk_filter_query"] == OKP_CHUNK_FILTER
        assert okp["search_mode"] == "hybrid"
        assert okp["max_chunks"] == 5

    def test_okp_defaults(self) -> None:
        """Test okp fields with defaults."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        okp = snapshot["rag"]["okp"]
        assert okp["rhokp_url"] == NOT_CONFIGURED
        assert okp["offline"] is True
        assert okp["chunk_filter_query"] is None
        assert okp["search_mode"] is None

    def test_reranker_fields(self) -> None:
        """Test reranker fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        reranker = snapshot["rag"]["retrieval"]["inline"]["reranker"]
        assert reranker["enabled"] is True
        assert reranker["model"] == "cross-encoder/ms-marco-MiniLM-L6-v2"

    def test_reranker_defaults(self) -> None:
        """Test reranker fields with defaults."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        reranker = snapshot["rag"]["retrieval"]["inline"]["reranker"]
        assert reranker["enabled"] is False
        assert reranker["model"] == "cross-encoder/ms-marco-MiniLM-L6-v2"

    def test_approvals_fields(self) -> None:
        """Test approvals fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["approvals"]["approval_timeout_seconds"] == 600
        assert snapshot["approvals"]["approval_retention_days"] == 90

    def test_approvals_defaults(self) -> None:
        """Test approvals fields with defaults."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["approvals"]["approval_timeout_seconds"] == 300
        assert snapshot["approvals"]["approval_retention_days"] == 30

    def test_rlsapi_v1_fields(self) -> None:
        """Test rlsapi_v1 fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["rlsapi_v1"]["allow_verbose_infer"] is True
        assert snapshot["rlsapi_v1"]["quota_subject"] == "user_id"

    def test_rlsapi_v1_defaults(self) -> None:
        """Test rlsapi_v1 fields with defaults."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["rlsapi_v1"]["allow_verbose_infer"] is False
        assert snapshot["rlsapi_v1"]["quota_subject"] is None

    def test_saved_prompts_fields(self) -> None:
        """Test saved_prompts fields extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["saved_prompts"]["max_prompts_per_user"] == 100
        assert snapshot["saved_prompts"]["max_display_name_length"] == 200
        assert snapshot["saved_prompts"]["max_content_length"] == 5000

    def test_saved_prompts_defaults(self) -> None:
        """Test saved_prompts fields with defaults."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["saved_prompts"]["max_prompts_per_user"] == 50
        assert snapshot["saved_prompts"]["max_display_name_length"] == 255
        assert snapshot["saved_prompts"]["max_content_length"] == 10000

    def test_skills_paths_masked(self) -> None:
        """Test skills paths is masked as sensitive."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["skills"]["paths"] == CONFIGURED

    def test_skills_none(self) -> None:
        """Test skills when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["skills"]["paths"] == NOT_CONFIGURED

    def test_deployment_environment_passthrough(self) -> None:
        """Test deployment_environment passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["deployment_environment"] == "production"

    def test_deployment_environment_default(self) -> None:
        """Test deployment_environment with default value."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["deployment_environment"] == "development"

    def test_config_format_version_passthrough(self) -> None:
        """Test config_format_version passes through as its actual value."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["config_format_version"] == "unified"

    def test_config_format_version_none(self) -> None:
        """Test config_format_version passes through as None when unset."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["config_format_version"] is None

    def test_vector_store_fields(self) -> None:
        """Test vector_store.providers extraction with masking."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        # default_provider / provider ids are user-chosen names -> masked
        assert snapshot["vector_store"]["default_provider"] == CONFIGURED
        providers = snapshot["vector_store"]["providers"]
        assert isinstance(providers, list)
        assert len(providers) == 2
        # faiss provider: id masked, type passthrough, config.path masked
        # (dotted item paths nest into a "config" sub-object)
        assert providers[0]["id"] == CONFIGURED
        assert providers[0]["type"] == "faiss"
        assert providers[0]["embedding_model"] == "all-MiniLM-L6-v2"
        assert providers[0]["embedding_dimension"] == 384
        assert providers[0]["config"]["path"] == CONFIGURED
        # pgvector provider: connection fields masked
        assert providers[1]["id"] == CONFIGURED
        assert providers[1]["type"] == "pgvector"
        assert providers[1]["config"]["host"] == CONFIGURED
        assert providers[1]["config"]["port"] == 5432
        assert providers[1]["config"]["db"] == CONFIGURED
        assert providers[1]["config"]["user"] == CONFIGURED
        assert providers[1]["config"]["password"] == CONFIGURED

    def test_vector_store_empty(self) -> None:
        """Test vector_store with no providers configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["vector_store"]["default_provider"] == NOT_CONFIGURED
        assert snapshot["vector_store"]["providers"] == []

    def test_shields_extraction(self) -> None:
        """Test shields list extraction with masking."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        shields = snapshot["shields"]
        assert isinstance(shields, list)
        assert len(shields) == 2
        assert shields[0]["name"] == "question-validity"
        assert shields[0]["provider_id"] == "question_validity"
        assert shields[1]["name"] == "pii-redaction"
        assert shields[1]["provider_id"] == "redaction"

    def test_shields_empty(self) -> None:
        """Test shields when none configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["shields"] == []


# =============================================================================
# Tests: build_llama_stack_snapshot
# =============================================================================


class TestBuildLlamaStackSnapshot:
    """Tests for build_llama_stack_snapshot function."""

    @pytest.mark.asyncio
    async def test_service_mode_returns_not_available(self) -> None:
        """Test that service mode (no path) returns not_available status."""
        assert await build_llama_stack_snapshot(None) == {"status": NOT_AVAILABLE}

    @pytest.mark.asyncio
    async def test_nonexistent_file(self) -> None:
        """Test that missing file returns not_available status."""
        assert await build_llama_stack_snapshot("/nonexistent/path.yaml") == {
            "status": NOT_AVAILABLE
        }

    @pytest.mark.asyncio
    async def test_invalid_yaml(self, tmp_path: Path) -> None:
        """Test that invalid YAML returns not_available status."""
        path = tmp_path / "invalid.yaml"
        path.write_text(": invalid: yaml: [")
        result = await build_llama_stack_snapshot(str(path))
        assert result == {"status": NOT_AVAILABLE}

    @pytest.mark.asyncio
    async def test_valid_config(self, llama_stack_config_file: str) -> None:
        """Test snapshot from valid OGX config."""
        result = await build_llama_stack_snapshot(llama_stack_config_file)
        assert result["version"] == 2
        assert result["image_name"] == "starter"
        assert result["apis"] == ["agents", "inference", "safety", "vector_io"]
        assert result["external_providers_dir"] == CONFIGURED

    @pytest.mark.asyncio
    async def test_models_extraction(self, llama_stack_config_file: str) -> None:
        """Test models list extraction."""
        result = await build_llama_stack_snapshot(llama_stack_config_file)
        models = result["registered_resources"]["models"]
        assert len(models) == 2
        assert models[0]["model_id"] == "gpt-4o-mini"
        assert models[0]["model_type"] == "llm"

    @pytest.mark.asyncio
    async def test_providers_extraction(self, llama_stack_config_file: str) -> None:
        """Test provider lists extraction shows only id and type."""
        result = await build_llama_stack_snapshot(llama_stack_config_file)
        inference = result["providers"]["inference"]
        assert len(inference) == 1
        assert inference[0]["provider_id"] == "openai"
        assert inference[0]["provider_type"] == "remote::openai"
        assert "config" not in inference[0]

    @pytest.mark.asyncio
    async def test_storage_fields(self, llama_stack_config_file: str) -> None:
        """Test storage store extraction."""
        result = await build_llama_stack_snapshot(llama_stack_config_file)
        assert result["inference_store"]["type"] == "sql_sqlite"
        assert result["inference_store"]["db_path"] == CONFIGURED
        assert result["metadata_store"]["type"] == "kv_sqlite"
        assert result["metadata_store"]["namespace"] == "registry"

    @pytest.mark.asyncio
    async def test_missing_providers_section(self, tmp_path: Path) -> None:
        """Test config without providers section."""
        path = tmp_path / "no_providers.yaml"
        path.write_text(yaml.dump({"version": 1, "apis": []}))
        result = await build_llama_stack_snapshot(str(path))
        assert result["providers"]["inference"] == NOT_CONFIGURED

    @pytest.mark.asyncio
    async def test_server_fields_masked(self, tmp_path: Path) -> None:
        """Test server host and TLS fields are masked."""
        config = {
            "version": 1,
            "server": {
                "host": "0.0.0.0",
                "port": 8321,
                "tls_cafile": "/etc/ssl/ca.crt",
                "tls_certfile": "/etc/ssl/cert.crt",
                "tls_keyfile": "/etc/ssl/key.pem",
            },
        }
        path = tmp_path / "server.yaml"
        path.write_text(yaml.dump(config))
        result = await build_llama_stack_snapshot(str(path))
        assert result["server"]["host"] == CONFIGURED
        assert result["server"]["port"] == 8321
        assert result["server"]["tls_cafile"] == CONFIGURED


# =============================================================================
# Tests: build_configuration_snapshot
# =============================================================================


class TestBuildConfigurationSnapshot:
    """Tests for build_configuration_snapshot function."""

    @pytest.mark.asyncio
    async def test_combines_both_sources(self) -> None:
        """Test that snapshot contains both lightspeed_stack and llama_stack."""
        result = await build_configuration_snapshot(build_minimal_config(), None)
        assert "lightspeed_stack" in result
        assert "llama_stack" in result
        assert result["llama_stack"] == {"status": NOT_AVAILABLE}
        assert result["lightspeed_stack"]["name"] == "minimal"

    @pytest.mark.asyncio
    async def test_with_llama_stack_config(self, llama_stack_config_file: str) -> None:
        """Test snapshot with both config sources."""
        result = await build_configuration_snapshot(
            build_minimal_config(), llama_stack_config_file
        )
        assert result["lightspeed_stack"]["name"] == "minimal"
        assert result["llama_stack"]["version"] == 2


# =============================================================================
# Tests: PII Leak Prevention (Critical)
# =============================================================================


class TestPiiLeakPrevention:
    """Critical tests proving PII is not leaked in snapshots."""

    def test_no_pii_in_lightspeed_stack_snapshot(self) -> None:
        """Verify no PII leaks in lightspeed-stack snapshot JSON."""
        json_str = json.dumps(
            build_lightspeed_stack_snapshot(build_fully_populated_config())
        )
        for pii_value in ALL_PII_VALUES:
            assert (
                pii_value not in json_str
            ), f"PII leaked in lightspeed-stack snapshot: '{pii_value}'"

    @pytest.mark.asyncio
    async def test_no_pii_in_llama_stack_snapshot(
        self, llama_stack_config_file: str
    ) -> None:
        """Verify no PII leaks in OGX snapshot JSON."""
        json_str = json.dumps(await build_llama_stack_snapshot(llama_stack_config_file))
        for pii_value in LLAMA_STACK_PII_VALUES:
            assert (
                pii_value not in json_str
            ), f"PII leaked in llama-stack snapshot: '{pii_value}'"

    @pytest.mark.asyncio
    async def test_no_pii_in_combined_snapshot(
        self, llama_stack_config_file: str
    ) -> None:
        """Verify no PII leaks in the combined snapshot JSON."""
        snapshot = await build_configuration_snapshot(
            build_fully_populated_config(), llama_stack_config_file
        )
        json_str = json.dumps(snapshot)
        for pii_value in ALL_PII_VALUES + LLAMA_STACK_PII_VALUES:
            assert (
                pii_value not in json_str
            ), f"PII leaked in combined snapshot: '{pii_value}'"

    def test_snapshot_only_contains_allowlisted_fields(self) -> None:
        """Verify snapshot does not contain any fields outside the allowlist."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        allowed_top_keys = {spec.path.split(".")[0] for spec in LIGHTSPEED_STACK_FIELDS}
        unexpected = set(snapshot.keys()) - allowed_top_keys
        assert (
            not unexpected
        ), f"Snapshot contains unexpected top-level keys: {unexpected}"

    @pytest.mark.asyncio
    async def test_provider_config_not_leaked(
        self, llama_stack_config_file: str
    ) -> None:
        """Verify provider config sections (with secrets) are not included."""
        json_str = json.dumps(await build_llama_stack_snapshot(llama_stack_config_file))
        assert "api_key" not in json_str
        assert "sk-openai" not in json_str

    def test_secret_str_values_never_exposed(self) -> None:
        """Verify SecretStr values are never present in snapshot output."""
        json_str = json.dumps(
            build_lightspeed_stack_snapshot(build_fully_populated_config())
        )
        assert "sk-super-secret-api-key-12345" not in json_str
        assert "P@ssw0rd!SuperSecret" not in json_str
        assert "**********" not in json_str

    @pytest.mark.asyncio
    async def test_snapshot_is_json_serializable(self) -> None:
        """Verify the snapshot can be serialized to JSON without errors."""
        json_str = json.dumps(
            await build_configuration_snapshot(build_fully_populated_config(), None)
        )
        assert isinstance(json.loads(json_str), dict)


# =============================================================================
# Tests: Registry Validation
# =============================================================================


class TestRegistryValidation:
    """Tests validating the field registry itself."""

    def test_all_field_specs_have_valid_masking(self) -> None:
        """Verify all field specs have a valid MaskingType."""
        for spec in LIGHTSPEED_STACK_FIELDS + LLAMA_STACK_FIELDS:
            if isinstance(spec, FieldSpec):
                assert isinstance(
                    spec.masking, MaskingType
                ), f"Invalid masking for {spec.path}"
            elif isinstance(spec, ListFieldSpec):
                for sub in spec.item_fields:
                    assert isinstance(
                        sub.masking, MaskingType
                    ), f"Invalid masking for {spec.path}.{sub.path}"

    def test_no_duplicate_paths_in_lightspeed_registry(self) -> None:
        """Verify no duplicate paths in lightspeed-stack registry."""
        paths = [s.path for s in LIGHTSPEED_STACK_FIELDS]
        assert len(paths) == len(
            set(paths)
        ), f"Duplicate paths: {set(p for p in paths if paths.count(p) > 1)}"

    def test_no_duplicate_paths_in_llama_stack_registry(self) -> None:
        """Verify no duplicate paths in OGX registry."""
        paths = [s.path for s in LLAMA_STACK_FIELDS]
        assert len(paths) == len(
            set(paths)
        ), f"Duplicate paths: {set(p for p in paths if paths.count(p) > 1)}"
