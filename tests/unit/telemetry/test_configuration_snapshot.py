"""Tests for configuration snapshot with PII masking."""

# pylint: disable=too-many-lines

import json
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
import yaml
from pydantic import SecretStr

from models.config import (
    Action,
    AzureEntraIdConfiguration,
    Configuration,
    JsonPathOperator,
    ServiceConfiguration,
)
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
    LLAMA_STACK_PII_VALUES,
    PII_AZURE_CLIENT_ID,
    PII_AZURE_CLIENT_SECRET,
    PII_AZURE_TENANT_ID,
    PII_SPLUNK_INDEX,
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
        """Test sensitive masking with empty string returns 'configured'."""
        assert mask_value("", MaskingType.SENSITIVE) == CONFIGURED

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
        assert snapshot["service"]["base_url"] == CONFIGURED
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
        """Test snapshot from valid llama-stack config."""
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
        """Verify no PII leaks in llama-stack snapshot JSON."""
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
        """Verify no duplicate paths in llama-stack registry."""
        paths = [s.path for s in LLAMA_STACK_FIELDS]
        assert len(paths) == len(
            set(paths)
        ), f"Duplicate paths: {set(p for p in paths if paths.count(p) > 1)}"


# =============================================================================
# Tests: New sections — Compaction
# =============================================================================


class TestCompactionSnapshot:
    """Tests for compaction section in the snapshot."""

    def test_compaction_passthrough_fields(self) -> None:
        """Test compaction fields pass through correctly."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["compaction"]["enabled"] is True
        assert snapshot["compaction"]["threshold_ratio"] == 0.8
        assert snapshot["compaction"]["token_floor"] == 2048
        assert snapshot["compaction"]["buffer_turns"] == 6
        assert snapshot["compaction"]["buffer_max_ratio"] == 0.4

    def test_compaction_none_when_not_configured(self) -> None:
        """Test compaction fields are None when compaction is not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["compaction"]["enabled"] is None
        assert snapshot["compaction"]["threshold_ratio"] is None
        assert snapshot["compaction"]["token_floor"] is None
        assert snapshot["compaction"]["buffer_turns"] is None
        assert snapshot["compaction"]["buffer_max_ratio"] is None


# =============================================================================
# Tests: New sections — Conversation Cache
# =============================================================================


class TestConversationCacheSnapshot:
    """Tests for conversation_cache section in the snapshot."""

    def test_cache_type_passthrough(self) -> None:
        """Test cache type passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["conversation_cache"]["type"] == "postgres"

    def test_cache_postgres_sensitive_fields_masked(self) -> None:
        """Test conversation cache postgres sensitive fields are masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        pg = snapshot["conversation_cache"]["postgres"]
        assert pg["host"] == CONFIGURED
        assert pg["db"] == CONFIGURED
        assert pg["user"] == CONFIGURED
        assert pg["password"] == CONFIGURED
        assert pg["namespace"] == CONFIGURED
        assert pg["ca_cert_path"] == CONFIGURED

    def test_cache_postgres_passthrough_fields(self) -> None:
        """Test conversation cache postgres passthrough fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        pg = snapshot["conversation_cache"]["postgres"]
        assert pg["port"] == 5432
        assert pg["ssl_mode"] == "require"
        assert pg["gss_encmode"] == "disable"

    def test_cache_sqlite_sensitive(self) -> None:
        """Test conversation cache sqlite db_path is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["conversation_cache"]["sqlite"]["db_path"] == CONFIGURED

    def test_cache_memory_passthrough(self) -> None:
        """Test conversation cache memory max_entries passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["conversation_cache"]["memory"]["max_entries"] is None

    def test_cache_none_when_not_configured(self) -> None:
        """Test conversation cache fields are None/not_configured when not set."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["conversation_cache"]["type"] is None


# =============================================================================
# Tests: New sections — Quota Handlers
# =============================================================================


class TestQuotaHandlersSnapshot:
    """Tests for quota_handlers section in the snapshot."""

    def test_quota_sqlite_sensitive(self) -> None:
        """Test quota handlers sqlite db_path is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["quota_handlers"]["sqlite"]["db_path"] == CONFIGURED

    def test_quota_postgres_sensitive_fields_masked(self) -> None:
        """Test quota handlers postgres sensitive fields are masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        pg = snapshot["quota_handlers"]["postgres"]
        assert pg["host"] == CONFIGURED
        assert pg["db"] == CONFIGURED
        assert pg["user"] == CONFIGURED
        assert pg["password"] == CONFIGURED
        assert pg["namespace"] == CONFIGURED
        assert pg["ca_cert_path"] == CONFIGURED

    def test_quota_postgres_passthrough_fields(self) -> None:
        """Test quota handlers postgres passthrough fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        pg = snapshot["quota_handlers"]["postgres"]
        assert pg["port"] == 5432
        assert pg["ssl_mode"] == "prefer"
        assert pg["gss_encmode"] == "require"

    def test_quota_limiters_extraction(self) -> None:
        """Test quota limiters list extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        limiters = snapshot["quota_handlers"]["limiters"]
        assert isinstance(limiters, list)
        assert len(limiters) == 1
        assert limiters[0]["type"] == "user_limiter"
        assert limiters[0]["name"] == "daily-user-quota"
        assert limiters[0]["initial_quota"] == 10000
        assert limiters[0]["quota_increase"] == 0
        assert limiters[0]["period"] == "1 day"

    def test_quota_scheduler_passthrough(self) -> None:
        """Test quota scheduler fields pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        sched = snapshot["quota_handlers"]["scheduler"]
        assert sched["period"] == 5
        assert sched["database_reconnection_count"] == 20
        assert sched["database_reconnection_delay"] == 2

    def test_quota_enable_token_history_passthrough(self) -> None:
        """Test enable_token_history passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["quota_handlers"]["enable_token_history"] is True

    def test_quota_none_when_not_configured(self) -> None:
        """Test quota handlers fields are not_configured/None when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        # sqlite.db_path is SENSITIVE — returns NOT_CONFIGURED when quota_handlers is None
        assert snapshot["quota_handlers"]["sqlite"]["db_path"] == NOT_CONFIGURED
        assert snapshot["quota_handlers"]["enable_token_history"] is None


# =============================================================================
# Tests: New sections — BYOK RAG
# =============================================================================


class TestByokRagSnapshot:
    """Tests for byok_rag section in the snapshot."""

    def test_byok_rag_passthrough_fields(self) -> None:
        """Test BYOK RAG passthrough fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        byok = snapshot["byok_rag"]
        assert isinstance(byok, list)
        assert len(byok) == 1
        assert byok[0]["rag_id"] == "my-rag"
        assert byok[0]["rag_type"] == "inline::faiss"
        assert byok[0]["embedding_model"] == "all-MiniLM-L6-v2"
        assert byok[0]["embedding_dimension"] == 384
        assert byok[0]["vector_db_id"] == "my-vector-db"
        assert byok[0]["score_multiplier"] == 1.5

    def test_byok_rag_sensitive_fields_masked(self) -> None:
        """Test BYOK RAG sensitive fields are masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        byok = snapshot["byok_rag"]
        assert byok[0]["db_path"] == CONFIGURED
        assert byok[0]["host"] == CONFIGURED
        assert byok[0]["port"] == CONFIGURED
        assert byok[0]["db"] == CONFIGURED
        assert byok[0]["user"] == CONFIGURED
        assert byok[0]["password"] == CONFIGURED

    def test_byok_rag_empty_list(self) -> None:
        """Test empty BYOK RAG list."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["byok_rag"] == []


# =============================================================================
# Tests: New sections — A2A State
# =============================================================================


class TestA2AStateSnapshot:
    """Tests for a2a_state section in the snapshot."""

    def test_a2a_sqlite_sensitive(self) -> None:
        """Test A2A state sqlite db_path is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["a2a_state"]["sqlite"]["db_path"] == CONFIGURED

    def test_a2a_postgres_sensitive_fields_masked(self) -> None:
        """Test A2A state postgres sensitive fields are masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        pg = snapshot["a2a_state"]["postgres"]
        assert pg["host"] == CONFIGURED
        assert pg["db"] == CONFIGURED
        assert pg["user"] == CONFIGURED
        assert pg["password"] == CONFIGURED
        assert pg["namespace"] == CONFIGURED
        assert pg["ca_cert_path"] == CONFIGURED

    def test_a2a_postgres_passthrough_fields(self) -> None:
        """Test A2A state postgres passthrough fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        pg = snapshot["a2a_state"]["postgres"]
        assert pg["port"] == 5432
        assert pg["ssl_mode"] == "verify-ca"
        assert pg["gss_encmode"] == "prefer"

    def test_a2a_state_none_when_not_configured(self) -> None:
        """Test A2A state fields are not_configured when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        # sqlite.db_path is SENSITIVE — returns NOT_CONFIGURED when a2a_state is None
        assert snapshot["a2a_state"]["sqlite"]["db_path"] == NOT_CONFIGURED
        assert snapshot["a2a_state"]["postgres"]["host"] == NOT_CONFIGURED


# =============================================================================
# Tests: New sections — Splunk
# =============================================================================


class TestSplunkSnapshot:
    """Tests for splunk section in the snapshot."""

    def test_splunk_passthrough_fields(self) -> None:
        """Test Splunk passthrough fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["splunk"]["enabled"] is True
        assert snapshot["splunk"]["source"] == "lightspeed-stack"
        assert snapshot["splunk"]["timeout"] == 10
        assert snapshot["splunk"]["verify_ssl"] is False

    def test_splunk_sensitive_fields_masked(self) -> None:
        """Test Splunk sensitive fields are masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["splunk"]["url"] == CONFIGURED
        assert snapshot["splunk"]["token_path"] == CONFIGURED

    def test_splunk_index_passthrough(self) -> None:
        """Test Splunk index passes through (non-secret identifier)."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["splunk"]["index"] == PII_SPLUNK_INDEX

    def test_splunk_none_when_not_configured(self) -> None:
        """Test Splunk fields are not_configured when splunk is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["splunk"]["enabled"] is None
        assert snapshot["splunk"]["url"] == NOT_CONFIGURED
        assert snapshot["splunk"]["token_path"] == NOT_CONFIGURED
        assert snapshot["splunk"]["index"] is None


# =============================================================================
# Tests: New sections — Inference additional subfields
# =============================================================================


class TestInferenceAdditionalSnapshot:
    """Tests for additional inference subfields in the snapshot."""

    def test_inference_context_windows_passthrough(self) -> None:
        """Test inference context_windows passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["inference"]["context_windows"] == {
            "openai/gpt-4o-mini": 128000
        }

    def test_inference_max_iters_passthrough(self) -> None:
        """Test inference max_infer_iters and max_tool_calls pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["inference"]["max_infer_iters"] == 10
        assert snapshot["inference"]["max_tool_calls"] == 30

    def test_inference_providers_passthrough(self) -> None:
        """Test inference providers list extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        providers = snapshot["inference"]["providers"]
        assert isinstance(providers, list)
        assert len(providers) == 1
        assert providers[0]["type"] == "openai"
        assert providers[0]["api_key_env"] == "OPENAI_API_KEY"
        assert providers[0]["allowed_models"] == ["gpt-4o-mini"]

    def test_inference_providers_empty(self) -> None:
        """Test inference providers empty list."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["inference"]["providers"] == []


# =============================================================================
# Tests: New sections — Llama Stack additional subfields
# =============================================================================


class TestLlamaStackAdditionalSnapshot:
    """Tests for additional llama_stack subfields in the snapshot."""

    def test_llama_stack_timeout_passthrough(self) -> None:
        """Test llama_stack timeout passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["timeout"] == 180

    def test_llama_stack_retries_passthrough(self) -> None:
        """Test llama_stack max_retries and retry_delay pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["max_retries"] == 5
        assert snapshot["llama_stack"]["retry_delay"] == 3

    def test_llama_stack_degraded_mode_passthrough(self) -> None:
        """Test llama_stack allow_degraded_mode passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["allow_degraded_mode"] is True

    def test_llama_stack_config_baseline_passthrough(self) -> None:
        """Test llama_stack.config.baseline passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["config"]["baseline"] == "default"

    def test_llama_stack_config_profile_sensitive(self) -> None:
        """Test llama_stack.config.profile is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["llama_stack"]["config"]["profile"] == CONFIGURED

    def test_llama_stack_config_none_when_not_set(self) -> None:
        """Test llama_stack.config fields are None when config is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["llama_stack"]["config"]["baseline"] is None
        assert snapshot["llama_stack"]["config"]["profile"] == NOT_CONFIGURED


# =============================================================================
# Tests: New sections — Authentication additional subfields
# =============================================================================


class TestAuthenticationAdditionalSnapshot:
    """Tests for additional authentication subfields in the snapshot."""

    def test_auth_skip_for_health_probes_passthrough(self) -> None:
        """Test skip_for_health_probes passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["authentication"]["skip_for_health_probes"] is True

    def test_auth_skip_for_metrics_passthrough(self) -> None:
        """Test skip_for_metrics passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["authentication"]["skip_for_metrics"] is True

    def test_auth_api_key_sensitive(self) -> None:
        """Test api_key_config.api_key is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["authentication"]["api_key_config"]["api_key"] == CONFIGURED

    def test_auth_rh_identity_passthrough(self) -> None:
        """Test rh_identity_config fields pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        rh = snapshot["authentication"]["rh_identity_config"]
        assert rh["required_entitlements"] == ["insights", "openshift"]
        assert rh["max_header_size"] == 65536

    def test_auth_trusted_proxy_passthrough(self) -> None:
        """Test trusted_proxy_config fields pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        tp = snapshot["authentication"]["trusted_proxy_config"]
        assert tp["user_header"] == "X-Forwarded-User"

    def test_auth_trusted_proxy_service_accounts(self) -> None:
        """Test trusted_proxy_config allowed_service_accounts extraction."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        accounts = snapshot["authentication"]["trusted_proxy_config"][
            "allowed_service_accounts"
        ]
        assert isinstance(accounts, list)
        assert len(accounts) == 1
        assert accounts[0]["namespace"] == "default"
        assert accounts[0]["name"] == "my-proxy"

    def test_auth_api_key_none_when_not_configured(self) -> None:
        """Test api_key_config.api_key is not_configured when api_key_config is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["authentication"]["api_key_config"]["api_key"] == NOT_CONFIGURED

    def test_auth_rh_identity_none_when_not_configured(self) -> None:
        """Test rh_identity_config fields are None when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        rh = snapshot["authentication"]["rh_identity_config"]
        assert rh["required_entitlements"] is None
        assert rh["max_header_size"] is None

    def test_auth_trusted_proxy_none_when_not_configured(self) -> None:
        """Test trusted_proxy_config fields are None when not configured."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        tp = snapshot["authentication"]["trusted_proxy_config"]
        assert tp["user_header"] is None
        assert tp["allowed_service_accounts"] == NOT_CONFIGURED


# =============================================================================
# Tests: New sections — Azure Entra ID
# =============================================================================


class TestAzureEntraIdSnapshot:
    """Tests for azure_entra_id section in the snapshot."""

    def test_azure_entra_id_none_when_not_configured(self) -> None:
        """Test azure_entra_id fields are not_configured when None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["azure_entra_id"]["tenant_id"] == NOT_CONFIGURED
        assert snapshot["azure_entra_id"]["client_id"] == NOT_CONFIGURED
        assert snapshot["azure_entra_id"]["client_secret"] == NOT_CONFIGURED
        assert snapshot["azure_entra_id"]["scope"] is None

    def test_azure_entra_id_sensitive_when_configured(self) -> None:
        """Test azure_entra_id sensitive fields are masked when configured."""
        config = build_fully_populated_config()
        config_with_azure = Configuration.model_construct(
            **{
                **config.__dict__,
                "azure_entra_id": AzureEntraIdConfiguration.model_construct(
                    tenant_id=SecretStr(PII_AZURE_TENANT_ID),
                    client_id=SecretStr(PII_AZURE_CLIENT_ID),
                    client_secret=SecretStr(PII_AZURE_CLIENT_SECRET),
                    scope="https://cognitiveservices.azure.com/.default",
                ),
            }
        )
        snapshot = build_lightspeed_stack_snapshot(config_with_azure)
        assert snapshot["azure_entra_id"]["tenant_id"] == CONFIGURED
        assert snapshot["azure_entra_id"]["client_id"] == CONFIGURED
        assert snapshot["azure_entra_id"]["client_secret"] == CONFIGURED
        assert (
            snapshot["azure_entra_id"]["scope"]
            == "https://cognitiveservices.azure.com/.default"
        )


# =============================================================================
# Tests: New sections — Customization additional subfields
# =============================================================================


class TestCustomizationAdditionalSnapshot:
    """Tests for additional customization subfields in the snapshot."""

    def test_customization_profile_path_sensitive(self) -> None:
        """Test customization profile_path is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["customization"]["profile_path"] == CONFIGURED

    def test_customization_disable_shield_ids_override_passthrough(self) -> None:
        """Test customization disable_shield_ids_override passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["customization"]["disable_shield_ids_override"] is True

    def test_customization_agent_card_path_sensitive(self) -> None:
        """Test customization agent_card_path is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["customization"]["agent_card_path"] == CONFIGURED

    def test_customization_none_when_not_configured(self) -> None:
        """Test customization fields are None/not_configured when customization is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["customization"]["profile_path"] == NOT_CONFIGURED
        assert snapshot["customization"]["disable_shield_ids_override"] is None
        assert snapshot["customization"]["agent_card_path"] == NOT_CONFIGURED


# =============================================================================
# Tests: New sections — OKP
# =============================================================================


class TestOkpSnapshot:
    """Tests for okp section in the snapshot."""

    def test_okp_sensitive_fields_masked(self) -> None:
        """Test OKP rhokp_url is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["okp"]["rhokp_url"] == CONFIGURED

    def test_okp_passthrough_fields(self) -> None:
        """Test OKP passthrough fields."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["okp"]["offline"] is True
        assert snapshot["okp"]["chunk_filter_query"] == "product:ansible"

    def test_okp_none_when_not_configured(self) -> None:
        """Test OKP fields are None when okp is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["okp"]["rhokp_url"] == NOT_CONFIGURED
        assert snapshot["okp"]["offline"] is None
        assert snapshot["okp"]["chunk_filter_query"] is None


# =============================================================================
# Tests: New sections — RAG
# =============================================================================


class TestRagSnapshot:
    """Tests for rag section in the snapshot."""

    def test_rag_passthrough_fields(self) -> None:
        """Test RAG inline and tool lists pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["rag"]["inline"] == ["okp"]
        assert snapshot["rag"]["tool"] == ["my-rag"]

    def test_rag_none_when_not_configured(self) -> None:
        """Test RAG fields are None when rag is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["rag"]["inline"] is None
        assert snapshot["rag"]["tool"] is None


# =============================================================================
# Tests: New sections — Reranker
# =============================================================================


class TestRerankerSnapshot:
    """Tests for reranker section in the snapshot."""

    def test_reranker_passthrough_fields(self) -> None:
        """Test reranker fields pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["reranker"]["enabled"] is True
        assert snapshot["reranker"]["model"] == "cross-encoder/ms-marco-MiniLM-L6-v2"

    def test_reranker_none_when_not_configured(self) -> None:
        """Test reranker fields are None when reranker is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["reranker"]["enabled"] is None
        assert snapshot["reranker"]["model"] is None


# =============================================================================
# Tests: New sections — Approvals
# =============================================================================


class TestApprovalsSnapshot:
    """Tests for approvals section in the snapshot."""

    def test_approvals_passthrough_fields(self) -> None:
        """Test approvals fields pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["approvals"]["approval_timeout_seconds"] == 600
        assert snapshot["approvals"]["approval_retention_days"] == 60

    def test_approvals_none_when_not_configured(self) -> None:
        """Test approvals fields are None when approvals is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["approvals"]["approval_timeout_seconds"] is None
        assert snapshot["approvals"]["approval_retention_days"] is None


# =============================================================================
# Tests: New sections — rlsapi_v1
# =============================================================================


class TestRlsapiV1Snapshot:
    """Tests for rlsapi_v1 section in the snapshot."""

    def test_rlsapi_v1_passthrough_fields(self) -> None:
        """Test rlsapi_v1 fields pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["rlsapi_v1"]["allow_verbose_infer"] is True
        assert snapshot["rlsapi_v1"]["quota_subject"] == "user_id"

    def test_rlsapi_v1_none_when_not_configured(self) -> None:
        """Test rlsapi_v1 fields are None when rlsapi_v1 is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["rlsapi_v1"]["allow_verbose_infer"] is None
        assert snapshot["rlsapi_v1"]["quota_subject"] is None


# =============================================================================
# Tests: New sections — Saved Prompts
# =============================================================================


class TestSavedPromptsSnapshot:
    """Tests for saved_prompts section in the snapshot."""

    def test_saved_prompts_passthrough_fields(self) -> None:
        """Test saved_prompts fields pass through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["saved_prompts"]["max_prompts_per_user"] == 50
        assert snapshot["saved_prompts"]["max_display_name_length"] == 200
        assert snapshot["saved_prompts"]["max_content_length"] == 5000

    def test_saved_prompts_none_when_not_configured(self) -> None:
        """Test saved_prompts fields are None when saved_prompts is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["saved_prompts"]["max_prompts_per_user"] is None
        assert snapshot["saved_prompts"]["max_display_name_length"] is None
        assert snapshot["saved_prompts"]["max_content_length"] is None


# =============================================================================
# Tests: New sections — Skills
# =============================================================================


class TestSkillsSnapshot:
    """Tests for skills section in the snapshot."""

    def test_skills_paths_sensitive(self) -> None:
        """Test skills paths are masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["skills"]["paths"] == CONFIGURED

    def test_skills_none_when_not_configured(self) -> None:
        """Test skills fields are not_configured when skills is None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["skills"]["paths"] == NOT_CONFIGURED


# =============================================================================
# Tests: New sections — Deployment Environment
# =============================================================================


class TestDeploymentEnvironmentSnapshot:
    """Tests for deployment_environment field in the snapshot."""

    def test_deployment_environment_passthrough(self) -> None:
        """Test deployment_environment passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["deployment_environment"] == "production"

    def test_deployment_environment_default(self) -> None:
        """Test deployment_environment default value."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["deployment_environment"] == "development"


# =============================================================================
# Tests: New sections — MCP Servers additional fields
# =============================================================================


class TestMcpServersAdditionalSnapshot:
    """Tests for additional MCP server fields in the snapshot."""

    def test_mcp_authorization_headers_sensitive(self) -> None:
        """Test MCP server authorization_headers is masked."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        mcp = snapshot["mcp_servers"]
        assert mcp[0]["authorization_headers"] == CONFIGURED

    def test_mcp_headers_passthrough(self) -> None:
        """Test MCP server headers list passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        mcp = snapshot["mcp_servers"]
        assert mcp[0]["headers"] == ["x-rh-identity"]

    def test_mcp_require_approval_sensitive(self) -> None:
        """Test MCP server require_approval is masked (may contain ApprovalFilter tool names)."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        mcp = snapshot["mcp_servers"]
        assert mcp[0]["require_approval"] == CONFIGURED

    def test_mcp_timeout_passthrough(self) -> None:
        """Test MCP server timeout passes through."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        mcp = snapshot["mcp_servers"]
        assert mcp[0]["timeout"] == 30


# =============================================================================
# Tests: New fields — service.base_url and service.root_path
# =============================================================================


class TestServiceAdditionalFieldsSnapshot:
    """Tests for service.base_url and service.root_path in the snapshot."""

    def test_service_base_url_sensitive_when_configured(self) -> None:
        """Test service.base_url is masked when set (it is a URL)."""
        snapshot = build_lightspeed_stack_snapshot(build_fully_populated_config())
        assert snapshot["service"]["base_url"] == CONFIGURED

    def test_service_base_url_not_configured_when_none(self) -> None:
        """Test service.base_url is not_configured when None."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["service"]["base_url"] == NOT_CONFIGURED

    def test_service_root_path_passthrough_when_set(self) -> None:
        """Test service.root_path passes through when set."""
        config = build_minimal_config()
        config_with_root_path = Configuration.model_construct(
            **{
                **config.__dict__,
                "service": ServiceConfiguration.model_construct(
                    **{
                        **config.service.__dict__,
                        "root_path": "/api/v1",
                    }
                ),
            }
        )
        snapshot = build_lightspeed_stack_snapshot(config_with_root_path)
        assert snapshot["service"]["root_path"] == "/api/v1"

    def test_service_root_path_passthrough_empty_string(self) -> None:
        """Test service.root_path passes through as empty string when not set."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert snapshot["service"]["root_path"] == ""

    def test_service_fields_present_in_snapshot_structure(self) -> None:
        """Test service.base_url and service.root_path keys are present in snapshot."""
        snapshot = build_lightspeed_stack_snapshot(build_minimal_config())
        assert "base_url" in snapshot["service"]
        assert "root_path" in snapshot["service"]
