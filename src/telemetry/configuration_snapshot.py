"""Configuration snapshot with PII masking for telemetry.

This module creates snapshots of configuration at startup, masking all PII
and using logical feature collection. It collects a specific allowlisted set
of configuration entries from both lightspeed-stack and OGX
configurations rather than automatically grabbing the whole configuration.

The snapshot is built as a JSON-serializable dict ready for telemetry emission.
No integration with ingress is provided here — only methods to build the JSON.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath
from typing import Any, Literal, Optional

import yaml
from pydantic import SecretStr

import constants
from log import get_logger
from models.config import Configuration

logger = get_logger(__name__)

# Masking output constants
CONFIGURED: Literal["configured"] = "configured"
NOT_CONFIGURED: Literal["not_configured"] = "not_configured"
NOT_AVAILABLE: Literal["not_available"] = "not_available"


class MaskingType(Enum):
    """Type of masking to apply to a configuration field.

    Attributes:
        PASSTHROUGH: Value is returned as-is (booleans, numbers, identifiers).
        SENSITIVE: Value is replaced with 'configured' or 'not_configured'
            (credentials, URLs, file paths, hostnames).
        RAG_SOURCES: A list of RAG source ids is summarized as
            {'count': int, 'okp_enabled': bool}. The individual ids are
            user-chosen rag_ids (potential PII), so only the count is emitted;
            the fixed OKP sentinel is surfaced as a boolean so telemetry can
            tell whether the OKP knowledge source is in use.
    """

    PASSTHROUGH = "passthrough"
    SENSITIVE = "sensitive"
    RAG_SOURCES = "rag_sources"


@dataclass(frozen=True)
class FieldSpec:
    """Specification for a single configuration field to collect.

    Attributes:
        path: Dotted path to the field in the configuration object.
        masking: Type of masking to apply to the field value.
    """

    path: str
    masking: MaskingType


@dataclass(frozen=True)
class ListFieldSpec:
    """Specification for a list field with per-item sub-fields to collect.

    Attributes:
        path: Dotted path to the list field in the configuration object.
        item_fields: Sub-field specifications to extract from each list item.
    """

    path: str
    item_fields: tuple[FieldSpec, ...]


# =============================================================================
# Field Registries
# =============================================================================

LIGHTSPEED_STACK_FIELDS: tuple[FieldSpec | ListFieldSpec, ...] = (
    # Operational
    FieldSpec("name", MaskingType.PASSTHROUGH),
    FieldSpec("config_format_version", MaskingType.PASSTHROUGH),
    # Core Service Configuration
    FieldSpec("service.workers", MaskingType.PASSTHROUGH),
    FieldSpec("service.host", MaskingType.SENSITIVE),
    FieldSpec("service.port", MaskingType.PASSTHROUGH),
    FieldSpec("service.base_url", MaskingType.SENSITIVE),
    FieldSpec("service.auth_enabled", MaskingType.PASSTHROUGH),
    FieldSpec("service.color_log", MaskingType.PASSTHROUGH),
    FieldSpec("service.access_log", MaskingType.PASSTHROUGH),
    FieldSpec("service.root_path", MaskingType.SENSITIVE),
    FieldSpec("service.tls_config.tls_certificate_path", MaskingType.SENSITIVE),
    FieldSpec("service.tls_config.tls_key_path", MaskingType.SENSITIVE),
    FieldSpec("service.tls_config.tls_key_password", MaskingType.SENSITIVE),
    FieldSpec("service.cors.allow_origins", MaskingType.SENSITIVE),
    FieldSpec("service.cors.allow_credentials", MaskingType.PASSTHROUGH),
    FieldSpec("service.cors.allow_methods", MaskingType.PASSTHROUGH),
    FieldSpec("service.cors.allow_headers", MaskingType.PASSTHROUGH),
    # LLM Integration Architecture
    FieldSpec("ogx.use_as_library_client", MaskingType.PASSTHROUGH),
    FieldSpec("ogx.url", MaskingType.SENSITIVE),
    FieldSpec("ogx.api_key", MaskingType.SENSITIVE),
    FieldSpec("ogx.library_client_config_path", MaskingType.SENSITIVE),
    FieldSpec("ogx.timeout", MaskingType.PASSTHROUGH),
    FieldSpec("ogx.max_retries", MaskingType.PASSTHROUGH),
    FieldSpec("ogx.retry_delay", MaskingType.PASSTHROUGH),
    FieldSpec("ogx.allow_degraded_mode", MaskingType.PASSTHROUGH),
    FieldSpec("ogx.config.baseline", MaskingType.PASSTHROUGH),
    FieldSpec("ogx.config.profile", MaskingType.SENSITIVE),
    FieldSpec("ogx.config.native_override", MaskingType.SENSITIVE),
    FieldSpec("inference.default_model", MaskingType.PASSTHROUGH),
    FieldSpec("inference.default_provider", MaskingType.PASSTHROUGH),
    FieldSpec("inference.context_windows", MaskingType.PASSTHROUGH),
    FieldSpec("inference.max_infer_iters", MaskingType.PASSTHROUGH),
    FieldSpec("inference.max_tool_calls", MaskingType.PASSTHROUGH),
    ListFieldSpec(
        "inference.providers",
        item_fields=(
            FieldSpec("type", MaskingType.PASSTHROUGH),
            FieldSpec("id", MaskingType.PASSTHROUGH),
            FieldSpec("api_key_env", MaskingType.SENSITIVE),
            FieldSpec("allowed_models", MaskingType.PASSTHROUGH),
        ),
    ),
    # Authentication & Authorization
    FieldSpec("authentication.module", MaskingType.PASSTHROUGH),
    FieldSpec("authentication.skip_tls_verification", MaskingType.PASSTHROUGH),
    FieldSpec("authentication.skip_for_health_probes", MaskingType.PASSTHROUGH),
    FieldSpec("authentication.skip_for_metrics", MaskingType.PASSTHROUGH),
    FieldSpec("authentication.k8s_cluster_api", MaskingType.SENSITIVE),
    FieldSpec("authentication.k8s_ca_cert_path", MaskingType.SENSITIVE),
    FieldSpec("authentication.jwk_config.url", MaskingType.SENSITIVE),
    FieldSpec(
        "authentication.jwk_config.jwt_configuration.user_id_claim",
        MaskingType.PASSTHROUGH,
    ),
    FieldSpec(
        "authentication.jwk_config.jwt_configuration.username_claim",
        MaskingType.PASSTHROUGH,
    ),
    ListFieldSpec(
        "authentication.jwk_config.jwt_configuration.role_rules",
        item_fields=(
            FieldSpec("jsonpath", MaskingType.PASSTHROUGH),
            FieldSpec("operator", MaskingType.PASSTHROUGH),
            FieldSpec("value", MaskingType.SENSITIVE),
            FieldSpec("roles", MaskingType.PASSTHROUGH),
            FieldSpec("negate", MaskingType.PASSTHROUGH),
        ),
    ),
    FieldSpec("authentication.api_key_config.api_key", MaskingType.SENSITIVE),
    FieldSpec(
        "authentication.rh_identity_config.required_entitlements",
        MaskingType.SENSITIVE,
    ),
    FieldSpec(
        "authentication.rh_identity_config.max_header_size",
        MaskingType.PASSTHROUGH,
    ),
    FieldSpec(
        "authentication.trusted_proxy_config.user_header",
        MaskingType.PASSTHROUGH,
    ),
    ListFieldSpec(
        "authentication.trusted_proxy_config.allowed_service_accounts",
        item_fields=(
            FieldSpec("namespace", MaskingType.SENSITIVE),
            FieldSpec("name", MaskingType.SENSITIVE),
        ),
    ),
    ListFieldSpec(
        "authorization.access_rules",
        item_fields=(
            FieldSpec("role", MaskingType.PASSTHROUGH),
            FieldSpec("actions", MaskingType.PASSTHROUGH),
        ),
    ),
    # Azure Entra ID
    FieldSpec("azure_entra_id.tenant_id", MaskingType.SENSITIVE),
    FieldSpec("azure_entra_id.client_id", MaskingType.SENSITIVE),
    FieldSpec("azure_entra_id.client_secret", MaskingType.SENSITIVE),
    FieldSpec("azure_entra_id.scope", MaskingType.PASSTHROUGH),
    # User Data Collection Features
    FieldSpec("user_data_collection.feedback_enabled", MaskingType.PASSTHROUGH),
    FieldSpec("user_data_collection.feedback_storage", MaskingType.SENSITIVE),
    FieldSpec("user_data_collection.transcripts_enabled", MaskingType.PASSTHROUGH),
    FieldSpec("user_data_collection.transcripts_storage", MaskingType.SENSITIVE),
    # AI/ML Capabilities Configuration
    FieldSpec("customization.system_prompt", MaskingType.SENSITIVE),
    FieldSpec("customization.system_prompt_path", MaskingType.SENSITIVE),
    FieldSpec("customization.profile_path", MaskingType.SENSITIVE),
    FieldSpec("customization.disable_query_system_prompt", MaskingType.PASSTHROUGH),
    FieldSpec("customization.disable_shield_ids_override", MaskingType.PASSTHROUGH),
    FieldSpec("customization.agent_card_path", MaskingType.SENSITIVE),
    # Database & Storage Configuration
    FieldSpec("database.sqlite.db_path", MaskingType.SENSITIVE),
    FieldSpec("database.postgres.host", MaskingType.SENSITIVE),
    FieldSpec("database.postgres.port", MaskingType.PASSTHROUGH),
    FieldSpec("database.postgres.db", MaskingType.SENSITIVE),
    FieldSpec("database.postgres.user", MaskingType.SENSITIVE),
    FieldSpec("database.postgres.password", MaskingType.SENSITIVE),
    FieldSpec("database.postgres.namespace", MaskingType.SENSITIVE),
    FieldSpec("database.postgres.ssl_mode", MaskingType.PASSTHROUGH),
    FieldSpec("database.postgres.gss_encmode", MaskingType.PASSTHROUGH),
    FieldSpec("database.postgres.ca_cert_path", MaskingType.SENSITIVE),
    # Conversation Cache
    FieldSpec("conversation_cache.type", MaskingType.PASSTHROUGH),
    FieldSpec("conversation_cache.memory.max_entries", MaskingType.PASSTHROUGH),
    FieldSpec("conversation_cache.sqlite.db_path", MaskingType.SENSITIVE),
    FieldSpec("conversation_cache.postgres.host", MaskingType.SENSITIVE),
    FieldSpec("conversation_cache.postgres.port", MaskingType.PASSTHROUGH),
    FieldSpec("conversation_cache.postgres.db", MaskingType.SENSITIVE),
    FieldSpec("conversation_cache.postgres.user", MaskingType.SENSITIVE),
    FieldSpec("conversation_cache.postgres.password", MaskingType.SENSITIVE),
    FieldSpec("conversation_cache.postgres.namespace", MaskingType.SENSITIVE),
    FieldSpec("conversation_cache.postgres.ssl_mode", MaskingType.PASSTHROUGH),
    FieldSpec("conversation_cache.postgres.gss_encmode", MaskingType.PASSTHROUGH),
    FieldSpec("conversation_cache.postgres.ca_cert_path", MaskingType.SENSITIVE),
    # Conversation Compaction
    FieldSpec("compaction.enabled", MaskingType.PASSTHROUGH),
    FieldSpec("compaction.threshold_ratio", MaskingType.PASSTHROUGH),
    FieldSpec("compaction.token_floor", MaskingType.PASSTHROUGH),
    FieldSpec("compaction.buffer_turns", MaskingType.PASSTHROUGH),
    FieldSpec("compaction.buffer_max_ratio", MaskingType.PASSTHROUGH),
    # Quota Handlers
    FieldSpec("quota_handlers.sqlite.db_path", MaskingType.SENSITIVE),
    FieldSpec("quota_handlers.postgres.host", MaskingType.SENSITIVE),
    FieldSpec("quota_handlers.postgres.port", MaskingType.PASSTHROUGH),
    FieldSpec("quota_handlers.postgres.db", MaskingType.SENSITIVE),
    FieldSpec("quota_handlers.postgres.user", MaskingType.SENSITIVE),
    FieldSpec("quota_handlers.postgres.password", MaskingType.SENSITIVE),
    FieldSpec("quota_handlers.postgres.namespace", MaskingType.SENSITIVE),
    FieldSpec("quota_handlers.postgres.ssl_mode", MaskingType.PASSTHROUGH),
    FieldSpec("quota_handlers.postgres.gss_encmode", MaskingType.PASSTHROUGH),
    FieldSpec("quota_handlers.postgres.ca_cert_path", MaskingType.SENSITIVE),
    ListFieldSpec(
        "quota_handlers.limiters",
        item_fields=(
            FieldSpec("type", MaskingType.PASSTHROUGH),
            FieldSpec("name", MaskingType.PASSTHROUGH),
            FieldSpec("initial_quota", MaskingType.PASSTHROUGH),
            FieldSpec("quota_increase", MaskingType.PASSTHROUGH),
            FieldSpec("period", MaskingType.PASSTHROUGH),
        ),
    ),
    FieldSpec("quota_handlers.scheduler.period", MaskingType.PASSTHROUGH),
    FieldSpec(
        "quota_handlers.scheduler.database_reconnection_count",
        MaskingType.PASSTHROUGH,
    ),
    FieldSpec(
        "quota_handlers.scheduler.database_reconnection_delay",
        MaskingType.PASSTHROUGH,
    ),
    FieldSpec("quota_handlers.enable_token_history", MaskingType.PASSTHROUGH),
    # BYOK RAG
    FieldSpec("rag.byok.max_chunks", MaskingType.PASSTHROUGH),
    ListFieldSpec(
        "rag.byok.stores",
        item_fields=(
            # rag_id / vector_db_id are user-chosen names (potential PII)
            FieldSpec("rag_id", MaskingType.SENSITIVE),
            FieldSpec("backend", MaskingType.PASSTHROUGH),
            FieldSpec("embedding_model", MaskingType.PASSTHROUGH),
            FieldSpec("embedding_dimension", MaskingType.PASSTHROUGH),
            FieldSpec("vector_db_id", MaskingType.SENSITIVE),
            FieldSpec("db_path", MaskingType.SENSITIVE),
            FieldSpec("score_multiplier", MaskingType.PASSTHROUGH),
            FieldSpec("relevance_cutoff_score", MaskingType.PASSTHROUGH),
            FieldSpec("host", MaskingType.SENSITIVE),
            FieldSpec("port", MaskingType.PASSTHROUGH),
            FieldSpec("db", MaskingType.SENSITIVE),
            FieldSpec("user", MaskingType.SENSITIVE),
            FieldSpec("password", MaskingType.SENSITIVE),
        ),
    ),
    # A2A State
    FieldSpec("a2a_state.sqlite.db_path", MaskingType.SENSITIVE),
    FieldSpec("a2a_state.postgres.host", MaskingType.SENSITIVE),
    FieldSpec("a2a_state.postgres.port", MaskingType.PASSTHROUGH),
    FieldSpec("a2a_state.postgres.db", MaskingType.SENSITIVE),
    FieldSpec("a2a_state.postgres.user", MaskingType.SENSITIVE),
    FieldSpec("a2a_state.postgres.password", MaskingType.SENSITIVE),
    FieldSpec("a2a_state.postgres.namespace", MaskingType.SENSITIVE),
    FieldSpec("a2a_state.postgres.ssl_mode", MaskingType.PASSTHROUGH),
    FieldSpec("a2a_state.postgres.gss_encmode", MaskingType.PASSTHROUGH),
    FieldSpec("a2a_state.postgres.ca_cert_path", MaskingType.SENSITIVE),
    # Splunk
    FieldSpec("splunk.enabled", MaskingType.PASSTHROUGH),
    FieldSpec("splunk.url", MaskingType.SENSITIVE),
    FieldSpec("splunk.token_path", MaskingType.SENSITIVE),
    FieldSpec("splunk.index", MaskingType.SENSITIVE),
    FieldSpec("splunk.source", MaskingType.PASSTHROUGH),
    FieldSpec("splunk.timeout", MaskingType.PASSTHROUGH),
    FieldSpec("splunk.verify_ssl", MaskingType.PASSTHROUGH),
    # RAG Retrieval Strategy
    # sources are user-chosen rag_ids (potential PII) -> summarized as
    # {count, okp_enabled} rather than emitted verbatim.
    FieldSpec("rag.retrieval.inline.sources", MaskingType.RAG_SOURCES),
    FieldSpec("rag.retrieval.inline.max_chunks", MaskingType.PASSTHROUGH),
    FieldSpec("rag.retrieval.tool.sources", MaskingType.RAG_SOURCES),
    FieldSpec("rag.retrieval.tool.max_chunks", MaskingType.PASSTHROUGH),
    # OKP
    FieldSpec("rag.okp.rhokp_url", MaskingType.SENSITIVE),
    FieldSpec("rag.okp.offline", MaskingType.PASSTHROUGH),
    FieldSpec("rag.okp.chunk_filter_query", MaskingType.PASSTHROUGH),
    FieldSpec("rag.okp.search_mode", MaskingType.PASSTHROUGH),
    FieldSpec("rag.okp.max_chunks", MaskingType.PASSTHROUGH),
    # Reranker (inline retrieval)
    FieldSpec("rag.retrieval.inline.reranker.enabled", MaskingType.PASSTHROUGH),
    FieldSpec("rag.retrieval.inline.reranker.model", MaskingType.PASSTHROUGH),
    # Vector Store (dynamic provider capacity)
    # default_provider / providers[].id are user-chosen names (potential PII)
    FieldSpec("vector_store.default_provider", MaskingType.SENSITIVE),
    ListFieldSpec(
        "vector_store.providers",
        item_fields=(
            FieldSpec("id", MaskingType.SENSITIVE),
            FieldSpec("type", MaskingType.PASSTHROUGH),
            FieldSpec("embedding_model", MaskingType.PASSTHROUGH),
            FieldSpec("embedding_dimension", MaskingType.PASSTHROUGH),
            FieldSpec("config.path", MaskingType.SENSITIVE),
            FieldSpec("config.host", MaskingType.SENSITIVE),
            FieldSpec("config.port", MaskingType.PASSTHROUGH),
            FieldSpec("config.db", MaskingType.SENSITIVE),
            FieldSpec("config.user", MaskingType.SENSITIVE),
            FieldSpec("config.password", MaskingType.SENSITIVE),
        ),
    ),
    # Shields (pydantic-ai agent guardrails)
    ListFieldSpec(
        "shields",
        item_fields=(
            FieldSpec("name", MaskingType.PASSTHROUGH),
            FieldSpec("provider_id", MaskingType.PASSTHROUGH),
        ),
    ),
    # Approvals
    FieldSpec("approvals.approval_timeout_seconds", MaskingType.PASSTHROUGH),
    FieldSpec("approvals.approval_retention_days", MaskingType.PASSTHROUGH),
    # rlsapi v1
    FieldSpec("rlsapi_v1.allow_verbose_infer", MaskingType.PASSTHROUGH),
    FieldSpec("rlsapi_v1.quota_subject", MaskingType.PASSTHROUGH),
    # Saved Prompts
    FieldSpec("saved_prompts.max_prompts_per_user", MaskingType.PASSTHROUGH),
    FieldSpec("saved_prompts.max_display_name_length", MaskingType.PASSTHROUGH),
    FieldSpec("saved_prompts.max_content_length", MaskingType.PASSTHROUGH),
    # Skills
    FieldSpec("skills.paths", MaskingType.SENSITIVE),
    # Deployment Environment
    FieldSpec("deployment_environment", MaskingType.PASSTHROUGH),
    # Integration & Connectivity
    ListFieldSpec(
        "mcp_servers",
        item_fields=(
            FieldSpec("name", MaskingType.PASSTHROUGH),
            FieldSpec("provider_id", MaskingType.PASSTHROUGH),
            FieldSpec("url", MaskingType.SENSITIVE),
            FieldSpec("authorization_headers", MaskingType.SENSITIVE),
            FieldSpec("headers", MaskingType.SENSITIVE),
            FieldSpec("require_approval", MaskingType.PASSTHROUGH),
            FieldSpec("timeout", MaskingType.PASSTHROUGH),
        ),
    ),
)

LLAMA_STACK_FIELDS: tuple[FieldSpec | ListFieldSpec, ...] = (
    # Operational Configuration
    FieldSpec("version", MaskingType.PASSTHROUGH),
    FieldSpec("image_name", MaskingType.PASSTHROUGH),
    FieldSpec("container_image", MaskingType.PASSTHROUGH),
    FieldSpec("external_providers_dir", MaskingType.SENSITIVE),
    FieldSpec("server.host", MaskingType.SENSITIVE),
    FieldSpec("server.port", MaskingType.PASSTHROUGH),
    FieldSpec("server.auth", MaskingType.SENSITIVE),
    FieldSpec("server.quota", MaskingType.SENSITIVE),
    FieldSpec("server.tls_cafile", MaskingType.SENSITIVE),
    FieldSpec("server.tls_certfile", MaskingType.SENSITIVE),
    FieldSpec("server.tls_keyfile", MaskingType.SENSITIVE),
    FieldSpec("logging", MaskingType.PASSTHROUGH),
    # APIs
    FieldSpec("apis", MaskingType.PASSTHROUGH),
    # Models
    ListFieldSpec(
        "registered_resources.models",
        item_fields=(
            FieldSpec("model_id", MaskingType.PASSTHROUGH),
            FieldSpec("provider_id", MaskingType.PASSTHROUGH),
            FieldSpec("provider_model_id", MaskingType.PASSTHROUGH),
            FieldSpec("model_type", MaskingType.PASSTHROUGH),
        ),
    ),
    # Shields
    ListFieldSpec(
        "registered_resources.shields",
        item_fields=(
            FieldSpec("shield_id", MaskingType.PASSTHROUGH),
            FieldSpec("provider_id", MaskingType.PASSTHROUGH),
        ),
    ),
    # Vector stores
    ListFieldSpec(
        "registered_resources.vector_stores",
        item_fields=(
            FieldSpec("vector_store_id", MaskingType.PASSTHROUGH),
            FieldSpec("provider_id", MaskingType.PASSTHROUGH),
        ),
    ),
    # Providers — extract only provider_id and provider_type per entry.
    # NOTE: Update this list when OGX adds new provider categories.
    *(
        ListFieldSpec(
            f"providers.{provider_name}",
            item_fields=(
                FieldSpec("provider_id", MaskingType.PASSTHROUGH),
                FieldSpec("provider_type", MaskingType.PASSTHROUGH),
            ),
        )
        for provider_name in (
            "inference",
            "safety",
            "vector_io",
            "agents",
            "tool_runtime",
            "datasetio",
            "post_training",
            "eval",
            "telemetry",
            "scoring",
        )
    ),
    # Simple list fields — pass through as-is (typically enums/identifiers)
    FieldSpec("benchmarks", MaskingType.PASSTHROUGH),
    FieldSpec("scoring_fns", MaskingType.PASSTHROUGH),
    FieldSpec("datasets", MaskingType.PASSTHROUGH),
)


# =============================================================================
# Value Extraction and Masking
# =============================================================================


def get_nested_value(obj: Any, path: str) -> Any:
    """Navigate a nested object by dotted path.

    Supports both Pydantic models (via getattr) and dicts (via get).
    Returns None if any intermediate value is None or missing.

    Parameters:
    ----------
        obj: The root object to traverse (Pydantic model or dict).
        path: Dotted path to the target field (e.g., "service.tls_config.tls_key_path").

    Returns:
    -------
        The value at the specified path, or None if not found.
    """
    current = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return current


def _serialize_passthrough(value: Any) -> Any:
    """Convert a passthrough value to JSON-serializable form.

    Parameters:
    ----------
        value: The value to serialize.

    Returns:
    -------
        A JSON-serializable representation of the value.
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_serialize_passthrough(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_passthrough(v) for k, v in value.items()}
    # Safety: mask SecretStr, file paths, and any unrecognised types
    if not isinstance(value, (SecretStr, PurePath)):
        logger.warning(
            "Passthrough masking unexpected type %s as configured", type(value).__name__
        )
    return CONFIGURED


def _summarize_rag_sources(value: Any) -> dict[str, Any]:
    """Summarize a list of RAG source ids without leaking the ids themselves.

    RAG source ids are user-chosen rag_ids that may be identifying (PII), so
    only their count is reported. The fixed OKP sentinel (constants.OKP_RAG_ID)
    is a well-known, non-identifying value, so its presence is surfaced as a
    boolean to indicate whether the OKP knowledge source is enabled.

    Parameters:
    ----------
        value: The raw sources value (expected to be a list/tuple of str).

    Returns:
    -------
        A dict {'count': int, 'okp_enabled': bool}.
    """
    if not isinstance(value, (list, tuple)):
        return {"count": 0, "okp_enabled": False}
    return {
        "count": len(value),
        "okp_enabled": constants.OKP_RAG_ID in value,
    }


def mask_value(value: Any, masking: MaskingType) -> Any:
    """Apply masking to a configuration value.

    Parameters:
    ----------
        value: The raw configuration value.
        masking: The masking type to apply.

    Returns:
    -------
        The masked or serialized value.
    """
    if masking == MaskingType.SENSITIVE:
        if value is None or value == "":
            return NOT_CONFIGURED
        return CONFIGURED
    if masking == MaskingType.RAG_SOURCES:
        return _summarize_rag_sources(value)
    return _serialize_passthrough(value)


def _set_nested_value(target: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in a nested dict by dotted path, creating intermediates.

    Parameters:
    ----------
        target: The target dict to modify.
        path: Dotted path where the value should be set.
        value: The value to set.
    """
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _extract_field(source: Any, spec: FieldSpec) -> Any:
    """Extract and mask a single field from a source object.

    Parameters:
    ----------
        source: The source object (Pydantic model or dict).
        spec: The field specification.

    Returns:
    -------
        The masked value of the field.
    """
    value = get_nested_value(source, spec.path)
    return mask_value(value, spec.masking)


def _extract_list_field(
    source: Any, spec: ListFieldSpec
) -> list[dict[str, Any]] | Literal["not_configured"]:
    """Extract and mask a list field with per-item sub-fields.

    Parameters:
    ----------
        source: The source object (Pydantic model or dict).
        spec: The list field specification.

    Returns:
    -------
        A list of dicts with masked sub-fields, or NOT_CONFIGURED if the
        list is None.
    """
    items = get_nested_value(source, spec.path)
    if items is None:
        return NOT_CONFIGURED
    if not isinstance(items, (list, tuple)):
        return NOT_CONFIGURED
    result: list[dict[str, Any]] = []
    for item in items:
        item_dict: dict[str, Any] = {}
        for field_spec in spec.item_fields:
            # Use _set_nested_value so dotted item paths (e.g. "config.path")
            # nest into sub-objects instead of producing literal dotted keys,
            # matching the nesting used for top-level fields.
            _set_nested_value(
                item_dict,
                field_spec.path,
                mask_value(
                    get_nested_value(item, field_spec.path),
                    field_spec.masking,
                ),
            )
        result.append(item_dict)
    return result


def _extract_snapshot_fields(
    source: Any,
    field_registry: tuple[FieldSpec | ListFieldSpec, ...],
) -> dict[str, Any]:
    """Extract and mask fields from a source according to the field registry.

    Parameters:
    ----------
        source: The source object (Pydantic model or dict).
        field_registry: Tuple of field specifications defining what to extract.

    Returns:
    -------
        A nested dict containing the extracted and masked fields.
    """
    snapshot: dict[str, Any] = {}
    for spec in field_registry:
        if isinstance(spec, ListFieldSpec):
            value = _extract_list_field(source, spec)
        else:
            value = _extract_field(source, spec)
        _set_nested_value(snapshot, spec.path, value)
    return snapshot


# =============================================================================
# OGX Storage Field Extraction
# =============================================================================


def _extract_store_info(ls_config: dict[str, Any], store_name: str) -> dict[str, Any]:
    """Extract store type and db_path from OGX storage configuration.

    Resolves the store → backend → type/db_path chain in the OGX
    storage config structure.

    Parameters:
    ----------
        ls_config: The parsed OGX configuration dict.
        store_name: Name of the store to look up (e.g., "inference", "metadata").

    Returns:
    -------
        A dict with 'type' and 'db_path' keys, plus 'namespace' for metadata store.
    """
    store = get_nested_value(ls_config, f"storage.stores.{store_name}")
    if store is None or not isinstance(store, dict):
        return {"type": NOT_CONFIGURED, "db_path": NOT_CONFIGURED}

    backend_name = store.get("backend")
    if backend_name is None:
        return {"type": NOT_CONFIGURED, "db_path": NOT_CONFIGURED}

    backends = get_nested_value(ls_config, "storage.backends") or {}
    backend = backends.get(backend_name, {})

    result: dict[str, Any] = {
        "type": backend.get("type", NOT_CONFIGURED),
        "db_path": CONFIGURED if backend.get("db_path") is not None else NOT_CONFIGURED,
    }

    if store_name == "metadata":
        result["namespace"] = store.get("namespace", NOT_CONFIGURED)

    return result


# =============================================================================
# Public API
# =============================================================================


def build_lightspeed_stack_snapshot(
    config: Configuration,
) -> dict[str, Any]:
    """Build snapshot of lightspeed-stack configuration with PII masking.

    Extracts only the allowlisted fields from the Configuration object,
    applying binary masking to sensitive values (credentials, URLs, file paths)
    and passing through non-sensitive values (booleans, numbers, identifiers).

    Parameters:
    ----------
        config: The lightspeed-stack Configuration object.

    Returns:
    -------
        A nested dict containing the masked configuration snapshot.
    """
    return _extract_snapshot_fields(config, LIGHTSPEED_STACK_FIELDS)


def _read_yaml_file(config_path: str) -> Any:
    """Read and parse a YAML config file synchronously.

    Parameters:
    ----------
        config_path: Path to the YAML file.

    Returns:
    -------
        The parsed YAML content, or None on failure.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Failed to read OGX config for snapshot: %s", e)
        return None


async def build_llama_stack_snapshot(
    config_path: Optional[str] = None,
) -> dict[str, Any]:
    """Build snapshot of OGX configuration with PII masking.

    In library mode, parses the OGX YAML config file and extracts
    allowlisted fields with masking. In service mode (config_path is None),
    returns a status indicating the config is not available locally.

    Parameters:
    ----------
        config_path: Path to the OGX YAML config file. If None
            (service mode), OGX fields are marked as not available.

    Returns:
    -------
        A nested dict containing the masked OGX configuration snapshot,
        or a status dict if the config is not available.
    """
    if config_path is None:
        return {"status": NOT_AVAILABLE}

    ls_config = await asyncio.to_thread(_read_yaml_file, config_path)

    if not isinstance(ls_config, dict):
        logger.warning("OGX config is not a dict, skipping snapshot")
        return {"status": NOT_AVAILABLE}

    snapshot = _extract_snapshot_fields(ls_config, LLAMA_STACK_FIELDS)
    snapshot["inference_store"] = _extract_store_info(ls_config, "inference")
    snapshot["metadata_store"] = _extract_store_info(ls_config, "metadata")
    return snapshot


async def build_configuration_snapshot(
    config: Configuration,
    llama_stack_config_path: Optional[str] = None,
) -> dict[str, Any]:
    """Build a complete configuration snapshot with PII masking.

    Creates a snapshot containing both lightspeed-stack and OGX
    configuration data with appropriate PII masking applied. Only collects
    fields from an explicit allowlist — does not automatically grab the
    whole configuration.

    Parameters:
    ----------
        config: The lightspeed-stack Configuration object.
        llama_stack_config_path: Path to the OGX YAML config file.
            If None (service mode), OGX section is marked not available.

    Returns:
    -------
        A dict with 'lightspeed_stack' and 'ogx' keys containing
        the respective masked snapshots, ready for JSON serialization.
    """
    return {
        "lightspeed_stack": build_lightspeed_stack_snapshot(config),
        "ogx": await build_llama_stack_snapshot(llama_stack_config_path),
    }
