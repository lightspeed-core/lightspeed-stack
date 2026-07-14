"""Prow/OpenShift-specific utility functions for E2E tests.

This module contains all functions that interact with OpenShift via the `oc` CLI
and are only used when running tests in the Prow CI environment.
"""

import http.client
import os
import subprocess
import tempfile
import urllib.request
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


def _is_llama_stack_healthy() -> bool:
    """Check whether llama-stack pod is Ready and reachable on localhost:8321.

    Returns True when both the pod is Running/Ready *and* the local port-forward
    serves /v1/health.  Used to skip the expensive ``restore_llama_stack_pod()``
    when the pod never went away.
    """
    namespace = get_namespace()
    try:
        result = subprocess.run(
            [
                "oc",
                "get",
                "pod",
                "llama-stack-service",
                "-n",
                namespace,
                "-o",
                "jsonpath={.status.containerStatuses[0].ready}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.stdout.strip() != "true":
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8321/v1/health", timeout=5
        ) as resp:
            return resp.status == 200
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def restart_pod(container_name: str) -> None:
    """Restart lightspeed-stack pod in OpenShift/Prow environment.

    Only restores Llama Stack when it is not already healthy, avoiding the
    ~30 s overhead on every restart.  LSC needs Llama Stack at startup, so
    the check is still performed.
    """
    if not _is_llama_stack_healthy():
        print("[restart_pod] Llama Stack not healthy — restoring first")
        restore_llama_stack_pod()
    else:
        print("[restart_pod] Llama Stack already healthy — skipping restore")
    try:
        result = run_e2e_ops("restart-lightspeed", timeout=200)
        print(result.stdout, end="")
        if result.returncode != 0:
            print(result.stderr, end="")
            raise subprocess.CalledProcessError(result.returncode, "restart-lightspeed")
    except subprocess.TimeoutExpired as e:
        print(f"Failed to restart pod {container_name}: {e}")
        raise


def restore_llama_stack_pod() -> None:
    """Restore Llama Stack pod in Prow/OpenShift environment.

    Raises:
        subprocess.CalledProcessError: If oc/e2e-ops restore fails.
        subprocess.TimeoutExpired: If the operation times out.
    """
    # wait_for_pod (up to ~180s) + in-pod /v1/health polling (~105s) — allow headroom.
    result = run_e2e_ops("restart-llama-stack", timeout=420)
    print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="")
        raise subprocess.CalledProcessError(
            result.returncode, "restart-llama-stack", result.stderr
        )
    print("✓ Llama Stack pod restored successfully")


def ensure_port_forwards_healthy() -> None:
    """Verify both LSC and Llama Stack port-forwards are alive; restart dead ones.

    Intended to be called from ``before_scenario`` so that a stale forward left
    by a previous restart/cleanup does not cascade-fail unrelated scenarios.
    """
    # --- Llama Stack (8321) ---
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8321/v1/health", timeout=5
        ) as resp:
            if resp.status != 200:
                raise ConnectionError("non-200")
    except Exception:  # pylint: disable=broad-exception-caught
        print("[self-heal] Llama port-forward dead — re-establishing")
        try:
            result = run_e2e_ops("restart-llama-port-forward", timeout=120)
            print(result.stdout, end="")
            if result.returncode != 0:
                print(result.stderr, end="")
                print("[self-heal] WARNING: could not restore Llama port-forward")
        except subprocess.TimeoutExpired:
            print("[self-heal] WARNING: Llama port-forward restore timed out")

    # --- Lightspeed Stack (8080) ---
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=5)
        conn.request("GET", "/readiness")
        resp = conn.getresponse()
        if resp.status not in (200, 401):
            raise ConnectionError(f"HTTP {resp.status}")
        conn.close()
    except Exception:  # pylint: disable=broad-exception-caught
        print("[self-heal] LSC port-forward dead — re-establishing")
        try:
            result = run_e2e_ops("restart-port-forward", timeout=120)
            print(result.stdout, end="")
            if result.returncode != 0:
                print(result.stderr, end="")
                print("[self-heal] WARNING: could not restore LSC port-forward")
        except subprocess.TimeoutExpired:
            print("[self-heal] WARNING: LSC port-forward restore timed out")


def restart_lightspeed_stack_only() -> None:
    """Restart lightspeed-stack pod and port-forward on Prow without restoring Llama first.

    Use after Llama Stack was already restored (e.g. after disruption scenarios) so LCS
    picks up a fresh connection to the new llama pod; ``restart_pod`` is not suitable
    because it would redundantly run ``restart-llama-stack`` first.
    """
    try:
        result = run_e2e_ops("restart-lightspeed", timeout=200)
        print(result.stdout, end="")
        if result.returncode != 0:
            print(result.stderr, end="")
            raise subprocess.CalledProcessError(
                result.returncode, "restart-lightspeed", result.stderr
            )
    except subprocess.TimeoutExpired:
        print("Timeout while restarting lightspeed-stack after Llama restore")
        raise


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


def backup_configmap_to_memory() -> str:
    """Backup the current ConfigMap content to memory."""
    namespace = get_namespace()
    configmap_name = "lightspeed-stack-config"
    backup_key = f"{namespace}/{configmap_name}"

    if backup_key in _configmap_backups:
        print(f"ConfigMap backup already exists for {backup_key}")
        return backup_key

    print(f"Backing up ConfigMap {configmap_name} to memory...")

    try:
        result = run_e2e_ops("get-configmap-content", [configmap_name], timeout=30)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, "get-configmap-content", result.stderr
            )

        _configmap_backups[backup_key] = result.stdout
        print(f"ConfigMap backed up to memory ({len(result.stdout)} bytes)")
        return backup_key

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Failed to backup ConfigMap: {e}")
        raise


def remove_configmap_backup(backup_key: str) -> None:
    """Remove a ConfigMap backup from memory."""
    if backup_key in _configmap_backups:
        del _configmap_backups[backup_key]
        print(f"ConfigMap backup {backup_key} removed from memory")


def _recreate_configmap(configmap_name: str, source_file: str) -> None:
    """Delete and recreate a ConfigMap from a file.

    Args:
        configmap_name: Name of the ConfigMap.
        source_file: Path to the file to create the ConfigMap from.
    """
    result = run_e2e_ops("update-configmap", [configmap_name, source_file], timeout=60)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, "update-configmap", result.stderr
        )


def update_config_configmap(source: str) -> None:
    """Update the lightspeed-stack-config ConfigMap with new config in Prow environment.

    Args:
        source: Either a file path or a backup key from _configmap_backups.
    """
    configmap_name = "lightspeed-stack-config"

    # Check if source is a backup key (restore from memory)
    if source in _configmap_backups:
        config_content = _configmap_backups[source]
        print(f"Restoring ConfigMap {configmap_name} from memory backup...")

        # Write content to temp file (oc create configmap requires a file)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            temp_path = f.name

        try:
            _recreate_configmap(configmap_name, temp_path)
            print(f"✓ ConfigMap {configmap_name} restored successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to restore ConfigMap: {e}")
            raise
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return

    # Otherwise, source is a file path
    print(f"Updating ConfigMap {configmap_name} with config from {source}...")

    try:
        _recreate_configmap(configmap_name, source)
        print(f"ConfigMap {configmap_name} updated successfully")
    except subprocess.CalledProcessError as e:
        print(f"Failed to update ConfigMap: {e}")
        raise
