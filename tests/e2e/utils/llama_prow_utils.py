"""Thin Prow/OpenShift wrappers for Llama Stack run.yaml ConfigMap operations."""

from tests.e2e.utils.prow_utils import (
    backup_configmap_to_memory,
    get_configmap_content,
    remove_configmap_backup,
    update_config_configmap,
)

_LLAMA_CONFIGMAP_NAME = "llama-stack-config"
_LLAMA_CONFIGMAP_KEY = "run.yaml"


def get_llama_run_config_content() -> str:
    """Return llama-stack-config run.yaml content in Prow/OpenShift."""
    return get_configmap_content(
        configmap_name=_LLAMA_CONFIGMAP_NAME,
        configmap_key=_LLAMA_CONFIGMAP_KEY,
    )


def backup_llama_run_config_to_memory() -> str:
    """Backup llama-stack-config run.yaml into in-memory backup storage."""
    return backup_configmap_to_memory(
        configmap_name=_LLAMA_CONFIGMAP_NAME,
        configmap_key=_LLAMA_CONFIGMAP_KEY,
    )


def update_llama_run_configmap(source: str) -> None:
    """Update or restore llama-stack-config run.yaml from file or backup key."""
    update_config_configmap(
        source,
        configmap_name=_LLAMA_CONFIGMAP_NAME,
        configmap_key=_LLAMA_CONFIGMAP_KEY,
    )


def remove_llama_run_config_backup(backup_key: str) -> None:
    """Remove a llama-stack-config run.yaml backup from in-memory storage."""
    remove_configmap_backup(backup_key)
