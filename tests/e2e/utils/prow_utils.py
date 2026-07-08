"""Prow/OpenShift-specific utility functions for E2E tests.

This module contains all functions that interact with OpenShift via the `oc` CLI
and are only used when running tests in the Prow CI environment.
"""

import os
import re
import subprocess
import tempfile
from typing import Optional


def get_namespace() -> str:
    """Get the Kubernetes namespace for Prow environment."""
    return os.getenv("NAMESPACE", "e2e-rhoai-dsc")


# Mapping from container names (used in tests) to pod names (used in OpenShift)
_POD_NAME_MAP = {
    "lightspeed-stack": "lightspeed-stack-service",
    "llama-stack": "llama-stack-service",
}


def get_pod_name(container_name: str) -> str:
    """Map container name to OpenShift pod name."""
    return _POD_NAME_MAP.get(container_name, container_name)


def _get_e2e_ops_script() -> str:
    """Get the path to the consolidated e2e-ops.sh script."""
    tests_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(tests_dir, "e2e-prow/rhoai/scripts/e2e-ops.sh")


def run_e2e_ops(
    command: str, args: Optional[list[str]] = None, timeout: int = 180
) -> subprocess.CompletedProcess:
    """Run a command via the consolidated e2e-ops.sh script.

    Most script output is written to stdout (including errors); stderr is often empty.

    Args:
        command: The command to run (e.g., "restart-lightspeed", "wait-for-pod").
        args: Optional list of arguments to pass to the command.
        timeout: Timeout in seconds.

    Returns:
        CompletedProcess object with stdout/stderr.
    """
    script_path = _get_e2e_ops_script()
    cmd = ["bash", script_path, command] + (args or [])
    return subprocess.run(
        cmd,
        env={**os.environ, "NAMESPACE": get_namespace()},
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def wait_for_pod_health(pod_name: str, max_attempts: int = 12) -> None:
    """Wait for pod to be ready in OpenShift/Prow environment."""
    actual_pod_name = get_pod_name(pod_name)
    try:
        result = run_e2e_ops("wait-for-pod", [actual_pod_name, str(max_attempts)])
        print(result.stdout, end="")
        if result.returncode != 0:
            print(result.stderr, end="")
            raise subprocess.CalledProcessError(+result.returncode, "wait-for-pod")
    except subprocess.TimeoutExpired:
        print(f"Timeout waiting for pod {actual_pod_name}")
        raise


_LLAMA_RESTART_NAMES = frozenset({"llama-stack", "llama-stack-service"})
_LIGHTSPEED_RESTART_NAMES = frozenset({"lightspeed-stack", "lightspeed-stack-service"})


def restart_pod(container_name: str) -> None:
    """Restart Llama Stack or Lightspeed pod in OpenShift/Prow (not Docker).

    Maps ``container_name`` to the correct e2e-ops command: ``restart-llama-stack``
    vs ``restart-lightspeed``. Unknown names default to Lightspeed with a warning.

    For Lightspeed restarts, e2e-ops ensures Llama is running first. Llama pod logs
    may look unchanged after apply (no-op when healthy); that is expected.

    CI failures with healthy pod logs are often **localhost port-forward** contention
    (pipeline forward vs hook restart), not application crashes—see e2e-ops.sh header.
    """
    if container_name in _LLAMA_RESTART_NAMES:
        op = "restart-llama-stack"
        # Subprocess cap must exceed e2e-ops internal waits (pod + in-pod health + port-forward).
        # Konflux TLS full recreate: ~6–12 min typical, 15+ min under load (user-reported 400s+).
        if os.environ.get("E2E_COPY_MOCK_TLS_CERTS_TO_LLAMA") == "1":
            timeout = 1200
        elif os.environ.get("E2E_KONFLUX_E2E") == "1":
            timeout = 720
        else:
            timeout = 420
    elif container_name in _LIGHTSPEED_RESTART_NAMES:
        op = "restart-lightspeed"
        # Konflux LCS: TCP readiness + Llama handshake; full recreate can exceed 10 min under load.
        timeout = 1200 if os.environ.get("E2E_KONFLUX_E2E") == "1" else 320
    else:
        print(
            f"Warning: restart_pod({container_name!r}) unknown; "
            "using restart-lightspeed"
        )
        op = "restart-lightspeed"
        timeout = 200
    try:
        result = run_e2e_ops(op, timeout=timeout)
        print(result.stdout, end="")
        if result.returncode != 0:
            print(result.stderr, end="")
            combined = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
            # Prefer full e2e-ops output when diagnostics were printed (TLS/Llama failures).
            if "========== failure logs:" in combined:
                detail = combined
            else:
                detail = "\n".join(combined.splitlines()[-40:]) if combined else ""
            detail = detail or f"exit {result.returncode}"
            raise subprocess.CalledProcessError(
                result.returncode,
                op,
                detail,
            )
    except subprocess.TimeoutExpired as e:
        print(f"Failed to restart pod {container_name}: {e}")
        raise


def restore_llama_stack_pod() -> None:
    """Restore Llama Stack pod in Prow/OpenShift environment.

    Raises:
        subprocess.CalledProcessError: If oc/e2e-ops restore fails.
        subprocess.TimeoutExpired: If the operation times out.
    """
    if os.environ.get("E2E_KONFLUX_E2E") == "1":
        # Konflux: PVC fast-path init ~60-90s + Llama startup ~120-180s + health +
        # port-forward. 600s gives ample headroom without masking runaway installs.
        timeout = 600
    else:
        timeout = 420
    result = run_e2e_ops("restart-llama-stack", timeout=timeout)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="")
        raise subprocess.CalledProcessError(
            result.returncode, "restart-llama-stack", result.stderr
        )
    print("✓ Llama Stack pod restored successfully")


def disrupt_llama_stack_pod() -> bool:
    """Disrupt llama-stack connection in Prow/OpenShift environment.

    Returns:
        True if the pod was running and has been disrupted, False otherwise.
    """
    try:
        result = run_e2e_ops("disrupt-llama-stack", timeout=90)
        print(result.stdout, end="")

        # Exit code 0 = disrupted (was running), exit code 2 = was not running
        if result.returncode == 0:
            return True
        elif result.returncode == 2:
            return False
        else:
            print(result.stderr, end="")
            return False

    except subprocess.TimeoutExpired:
        print("Warning: Timeout while disrupting Llama Stack connection")
        return False


# In-memory storage for ConfigMap backups in Prow environment
_configmap_backups: dict[str, str] = {}


def get_configmap_content(
    configmap_name: str = "lightspeed-stack-config",
    configmap_key: str = "lightspeed-stack.yaml",
) -> str:
    """Return a ConfigMap value by name/key."""
    result = run_e2e_ops(
        "get-configmap-content",
        [configmap_name, configmap_key],
        timeout=30,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, "get-configmap-content", result.stderr
        )
    return result.stdout


def backup_configmap_to_memory(
    configmap_name: str = "lightspeed-stack-config",
    configmap_key: str = "lightspeed-stack.yaml",
) -> str:
    """Backup a ConfigMap entry to memory."""
    namespace = get_namespace()
    backup_key = f"{namespace}/{configmap_name}:{configmap_key}"

    if backup_key in _configmap_backups:
        print(f"ConfigMap backup already exists for {backup_key}")
        return backup_key

    print(f"Backing up ConfigMap {configmap_name} to memory...")

    try:
        config_content = get_configmap_content(configmap_name, configmap_key)
        _configmap_backups[backup_key] = config_content
        print(f"ConfigMap backed up to memory ({len(config_content)} bytes)")
        return backup_key

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Failed to backup ConfigMap: {e}")
        raise


def remove_configmap_backup(backup_key: str) -> None:
    """Remove a ConfigMap backup from memory."""
    if backup_key in _configmap_backups:
        del _configmap_backups[backup_key]
        print(f"ConfigMap backup {backup_key} removed from memory")


def _apply_inference_overrides(content: str) -> str:
    """Override inference defaults from E2E env vars if set.

    When E2E_DEFAULT_MODEL_OVERRIDE or E2E_DEFAULT_PROVIDER_OVERRIDE are set,
    patch the YAML content so every config swap uses the correct model/provider
    for the current environment (e.g. vLLM instead of OpenAI in RHOAI Prow).
    """
    model = os.getenv("E2E_DEFAULT_MODEL_OVERRIDE")
    provider = os.getenv("E2E_DEFAULT_PROVIDER_OVERRIDE")
    if not model and not provider:
        return content
    if model:
        content = re.sub(r"(default_model:\s*).*", rf"\g<1>{model}", content)
    if provider:
        content = re.sub(r"(default_provider:\s*).*", rf"\g<1>{provider}", content)
    return content


def _recreate_configmap(
    configmap_name: str,
    source_file: str,
    configmap_key: str = "lightspeed-stack.yaml",
) -> None:
    """Update a ConfigMap from a file via oc apply.

    Args:
        configmap_name: Name of the ConfigMap.
        source_file: Path to the file to create the ConfigMap from.
    """
    result = run_e2e_ops(
        "update-configmap",
        [configmap_name, source_file, configmap_key],
        timeout=60,
    )
    if result.returncode != 0:
        print(f"update-configmap stdout: {result.stdout}")
        print(f"update-configmap stderr: {result.stderr}")
        raise subprocess.CalledProcessError(
            result.returncode, "update-configmap", result.stderr
        )


def update_config_configmap(
    source: str,
    configmap_name: str = "lightspeed-stack-config",
    configmap_key: str = "lightspeed-stack.yaml",
) -> None:
    """Update a ConfigMap entry with new config in Prow environment.

    Args:
        source: Either a file path or a backup key from _configmap_backups.
    """
    # Check if source is a backup key (restore from memory)
    if source in _configmap_backups:
        config_content = _apply_inference_overrides(_configmap_backups[source])
        print(f"Restoring ConfigMap {configmap_name} from memory backup...")

        # Write content to temp file (oc create configmap requires a file)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            _recreate_configmap(configmap_name, temp_path, configmap_key)
            print(f"✓ ConfigMap {configmap_name} restored successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to restore ConfigMap: {e}")
            raise
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return

    # Otherwise, source is a file path — apply inference overrides if needed
    print(f"Updating ConfigMap {configmap_name} with config from {source}...")

    source_to_apply = source
    temp_path = None
    try:
        with open(source) as f:
            patched = _apply_inference_overrides(f.read())
        with open(source) as f:
            original = f.read()
        if patched != original:
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
            tmp.write(patched)
            tmp.close()
            source_to_apply = tmp.name
            temp_path = tmp.name

        _recreate_configmap(configmap_name, source_to_apply, configmap_key)
        print(f"ConfigMap {configmap_name} updated successfully")
    except subprocess.CalledProcessError as e:
        print(f"Failed to update ConfigMap: {e}")
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
