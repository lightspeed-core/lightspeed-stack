"""Helpers for reading and updating Llama Stack run.yaml across environments."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml

from tests.e2e.utils.llama_prow_utils import (
    backup_llama_run_config_to_memory,
    get_llama_run_config_content,
    remove_llama_run_config_backup,
    update_llama_run_configmap,
)
from tests.e2e.utils.utils import is_prow_environment

_DEFAULT_LOCAL_LLAMA_CONFIG_PATH = "run.yaml"
_DEFAULT_LOCAL_LLAMA_CONFIG_BACKUP_PATH = "run.yaml.proxy-backup"
_llama_config_backup_key: dict[str, Optional[str]] = {"value": None}


def clear_llama_config_backup() -> None:
    """Drop in-memory run.yaml backup (e.g. at start of tls.feature)."""
    _llama_config_backup_key["value"] = None


def reset_llama_run_config_to_pipeline_default() -> None:
    """Reset llama-stack-config run.yaml to Konflux/Prow pipeline seed (run-ci.yaml)."""
    if not is_prow_environment():
        return
    run_ci = Path(__file__).resolve().parents[1] / "configs" / "run-ci.yaml"
    if not run_ci.is_file():
        print(f"WARN: pipeline run.yaml seed not found at {run_ci}", flush=True)
        return
    print(f"Resetting llama-stack-config from {run_ci.name}...", flush=True)
    update_llama_run_configmap(str(run_ci))


def _local_llama_config_path() -> str:
    """Return local run.yaml path for Docker/local e2e execution."""
    return os.getenv("E2E_LLAMA_CONFIG_PATH", _DEFAULT_LOCAL_LLAMA_CONFIG_PATH)


def _local_llama_config_backup_path() -> str:
    """Return backup path used for local run.yaml mutations."""
    return os.getenv(
        "E2E_LLAMA_CONFIG_BACKUP_PATH",
        _DEFAULT_LOCAL_LLAMA_CONFIG_BACKUP_PATH,
    )


def backup_llama_config() -> None:
    """Create a backup of the current Llama run config once per scenario."""
    if is_prow_environment():
        if _llama_config_backup_key["value"] is None:
            _llama_config_backup_key["value"] = backup_llama_run_config_to_memory()
        return

    backup_path = _local_llama_config_backup_path()
    if not os.path.exists(backup_path):
        shutil.copy(_local_llama_config_path(), backup_path)


def load_llama_config() -> dict[str, Any]:
    """Load run.yaml configuration as a dictionary."""
    if is_prow_environment():
        content = get_llama_run_config_content()
        loaded = yaml.safe_load(content) or {}
        assert isinstance(loaded, dict), "Expected run.yaml to deserialize to a mapping"
        return loaded

    with open(_local_llama_config_path(), encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    assert isinstance(loaded, dict), "Expected run.yaml to deserialize to a mapping"
    return loaded


def write_llama_config(config: dict[str, Any]) -> None:
    """Write run.yaml configuration in local or Prow environment."""
    if is_prow_environment():
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8",
        ) as file:
            yaml.dump(config, file, default_flow_style=False)
            temp_path = file.name
        try:
            update_llama_run_configmap(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return

    with open(_local_llama_config_path(), "w", encoding="utf-8") as file:
        yaml.dump(config, file, default_flow_style=False)


def restore_llama_config_if_modified() -> bool:
    """Restore run config when a backup exists.

    Returns:
        True when a restore happened, otherwise False.
    """
    if is_prow_environment():
        backup_key = _llama_config_backup_key["value"]
        if backup_key is None:
            return False
        update_llama_run_configmap(backup_key)
        remove_llama_run_config_backup(backup_key)
        _llama_config_backup_key["value"] = None
        return True

    backup_path = _local_llama_config_backup_path()
    if not os.path.exists(backup_path):
        return False
    shutil.move(backup_path, _local_llama_config_path())
    return True
