"""Configuration snapshot with PII masking for telemetry.

This module creates snapshots of configuration at startup, masking all PII
and using logical feature collection. It collects a specific allowlisted set
of configuration entries from both lightspeed-stack and llama-stack
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
    """

    PASSTHROUGH = "passthrough"
    SENSITIVE = "sensitive"


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
    # Core Service Configuration
    FieldSpec("service.workers", MaskingType.PASSTHROUGH),
    FieldSpec("service.host", MaskingType.SENSITIVE),
    FieldSpec("service.port", MaskingType.PASSTHROUGH),
    FieldSpec("service.auth_enabled", MaskingType.PASSTHROUGH),
    FieldSpec("service.color_log", MaskingType.PASSTHROUGH),
    FieldSpec("service.access_log", MaskingType.PASSTHROUGH),
    FieldSpec("service.tls_config.tls_certificate_path", MaskingType.SENSITIVE),
    FieldSpec("service.tls_config.tls_key_path", MaskingType.SENSITIVE),
    FieldSpec("service.tls_config.tls_key_password", MaskingType.SENSITIVE),
    FieldSpec("service.cors.allow_origins", MaskingType.SENSITIVE),
    FieldSpec("service.cors.allow_credentials", MaskingType.PASSTHROUGH),
    FieldSpec("service.cors.allow_methods", MaskingType.PASSTHROUGH),
    FieldSpec("service.cors.allow_headers", MaskingType.PASSTHROUGH),
    # LLM Integration Architecture
    FieldSpec("llama_stack.use_as_library_client", MaskingType.PASSTHROUGH),
    FieldSpec("llama_stack.url", MaskingType.SENSITIVE),
    FieldSpec("llama_stack.api_key", MaskingType.SENSITIVE),
    FieldSpec("llama_stack.library_client_config_path", MaskingType.SENSITIVE),
    FieldSpec("inference.default_model", MaskingType.PASSTHROUGH),
    FieldSpec("inference.default_provider", MaskingType.PASSTHROUGH),
    # Authentication & Authorization
    FieldSpec("authentication.module", MaskingType.PASSTHROUGH),
    FieldSpec("authentication.skip_tls_verification", MaskingType.PASSTHROUGH),
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
    ListFieldSpec(
        "authorization.access_rules",
        item_fields=(
            FieldSpec("role", MaskingType.PASSTHROUGH),
            FieldSpec("actions", MaskingType.PASSTHROUGH),
        ),
    ),
    # User Data Collection Features
    FieldSpec("user_data_collection.feedback_enabled", MaskingType.PASSTHROUGH),
    FieldSpec("user_data_collection.feedback_storage", MaskingType.SENSITIVE),
    FieldSpec("user_data_collection.transcripts_enabled", MaskingType.PASSTHROUGH),
    FieldSpec("user_data_collection.transcripts_storage", MaskingType.SENSITIVE),
    # AI/ML Capabilities Configuration
    FieldSpec("customization.system_prompt", MaskingType.SENSITIVE),
    FieldSpec("customization.system_prompt_path", MaskingType.SENSITIVE),
    FieldSpec("customization.disable_query_system_prompt", MaskingType.PASSTHROUGH),
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
    # Integration & Connectivity
    ListFieldSpec(
        "mcp_servers",
        item_fields=(
            FieldSpec("name", MaskingType.PASSTHROUGH),
            FieldSpec("provider_id", MaskingType.PASSTHROUGH),
            FieldSpec("url", MaskingType.SENSITIVE),
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
    # NOTE: Update this list when llama-stack adds new provider categories.
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
        obj: The root object to traverse (Pydantic model or dict).
        path: Dotted path to the target field (e.g., "service.tls_config.tls_key_path").

    Returns:
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
        value: The value to serialize.

    Returns:
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


def mask_value(value: Any, masking: MaskingType) -> Any:
    """Apply masking to a configuration value.

    Parameters:
        value: The raw configuration value.
        masking: The masking type to apply.

    Returns:
        The masked or serialized value.
    """
    if masking == MaskingType.SENSITIVE:
        if value is None:
            return NOT_CONFIGURED
        return CONFIGURED
    return _serialize_passthrough(value)


def _set_nested_value(target: dict[str, Any], path: str, value: Any) -> None:
    """Set a value in a nested dict by dotted path, creating intermediates.

    Parameters:
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
        source: The source object (Pydantic model or dict).
        spec: The field specification.

    Returns:
        The masked value of the field.
    """
    value = get_nested_value(source, spec.path)
    return mask_value(value, spec.masking)


def _extract_list_field(
    source: Any, spec: ListFieldSpec
) -> list[dict[str, Any]] | Literal["not_configured"]:
    """Extract and mask a list field with per-item sub-fields.

    Parameters:
        source: The source object (Pydantic model or dict).
        spec: The list field specification.

    Returns:
        A list of dicts with masked sub-fields, or NOT_CONFIGURED if the
        list is None.
    """
    items = get_nested_value(source, spec.path)
    if items is None:
        return NOT_CONFIGURED
    if not isinstance(items, (list, tuple)):
        return NOT_CONFIGURED
    return [
        {
            field_spec.path: mask_value(
                get_nested_value(item, field_spec.path),
                field_spec.masking,
            )
            for field_spec in spec.item_fields
        }
        for item in items
    ]


def _extract_snapshot_fields(
    source: Any,
    field_registry: tuple[FieldSpec | ListFieldSpec, ...],
) -> dict[str, Any]:
    """Extract and mask fields from a source according to the field registry.

    Parameters:
        source: The source object (Pydantic model or dict).
        field_registry: Tuple of field specifications defining what to extract.

    Returns:
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
# Llama Stack Storage Field Extraction
# =============================================================================


def _extract_store_info(ls_config: dict[str, Any], store_name: str) -> dict[str, Any]:
    """Extract store type and db_path from llama-stack storage configuration.

    Resolves the store → backend → type/db_path chain in the llama-stack
    storage config structure.

    Parameters:
        ls_config: The parsed llama-stack configuration dict.
        store_name: Name of the store to look up (e.g., "inference", "metadata").

    Returns:
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
        config: The lightspeed-stack Configuration object.

    Returns:
        A nested dict containing the masked configuration snapshot.
    """
    return _extract_snapshot_fields(config, LIGHTSPEED_STACK_FIELDS)


def _read_yaml_file(config_path: str) -> Any:
    """Read and parse a YAML config file synchronously.

    Parameters:
        config_path: Path to the YAML file.

    Returns:
        The parsed YAML content, or None on failure.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Failed to read llama-stack config for snapshot: %s", e)
        return None


async def build_llama_stack_snapshot(
    config_path: Optional[str] = None,
) -> dict[str, Any]:
    """Build snapshot of llama-stack configuration with PII masking.

    In library mode, parses the llama-stack YAML config file and extracts
    allowlisted fields with masking. In service mode (config_path is None),
    returns a status indicating the config is not available locally.

    Parameters:
        config_path: Path to the llama-stack YAML config file. If None
            (service mode), llama-stack fields are marked as not available.

    Returns:
        A nested dict containing the masked llama-stack configuration snapshot,
        or a status dict if the config is not available.
    """
    if config_path is None:
        return {"status": NOT_AVAILABLE}

    ls_config = await asyncio.to_thread(_read_yaml_file, config_path)

    if not isinstance(ls_config, dict):
        logger.warning("Llama-stack config is not a dict, skipping snapshot")
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

    Creates a snapshot containing both lightspeed-stack and llama-stack
    configuration data with appropriate PII masking applied. Only collects
    fields from an explicit allowlist — does not automatically grab the
    whole configuration.

    Parameters:
        config: The lightspeed-stack Configuration object.
        llama_stack_config_path: Path to the llama-stack YAML config file.
            If None (service mode), llama-stack section is marked not available.

    Returns:
        A dict with 'lightspeed_stack' and 'llama_stack' keys containing
        the respective masked snapshots, ready for JSON serialization.
    """
    return {
        "lightspeed_stack": build_lightspeed_stack_snapshot(config),
        "llama_stack": await build_llama_stack_snapshot(llama_stack_config_path),
    }
