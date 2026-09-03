"""Thin Prow/OpenShift wrappers for OGX run.yaml ConfigMap operations."""

from tests.e2e.utils.prow_utils import (
    backup_configmap_to_memory,
    get_configmap_content,
    remove_configmap_backup,
    update_config_configmap,
)

# OpenShift ConfigMap name (legacy K8s resource id in Prow manifests).
_OGX_CONFIGMAP_NAME = "llama-stack-config"
_OGX_CONFIGMAP_KEY = "run.yaml"


def get_ogx_run_config_content() -> str:
    """Return OGX run.yaml ConfigMap content in Prow/OpenShift."""
    return get_configmap_content(
        configmap_name=_OGX_CONFIGMAP_NAME,
        configmap_key=_OGX_CONFIGMAP_KEY,
    )


def backup_ogx_run_config_to_memory() -> str:
    """Backup OGX run.yaml ConfigMap into in-memory backup storage."""
    return backup_configmap_to_memory(
        configmap_name=_OGX_CONFIGMAP_NAME,
        configmap_key=_OGX_CONFIGMAP_KEY,
    )


def update_ogx_run_configmap(source: str) -> None:
    """Update or restore OGX run.yaml ConfigMap from file or backup key."""
    update_config_configmap(
        source,
        configmap_name=_OGX_CONFIGMAP_NAME,
        configmap_key=_OGX_CONFIGMAP_KEY,
    )


def remove_ogx_run_config_backup(backup_key: str) -> None:
    """Remove an OGX run.yaml ConfigMap backup from in-memory storage."""
    remove_configmap_backup(backup_key)
