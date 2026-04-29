"""Unsorted utility functions to be used from other sources and test step definitions."""

import json
import os
import shutil
import subprocess
import time
from typing import Any, Optional

import jsonschema
import requests
from behave.runner import Context

from tests.e2e.utils.prow_utils import (
    backup_configmap_to_memory,
    remove_configmap_backup,
    restart_pod,
    update_config_configmap,
    wait_for_pod_health,
)

_DEFAULT_CLUSTER_LIGHTSPEED_CONFIG_DIR = "tests/e2e/configuration/server-mode"


def _e2e_repo_root() -> str:
    """Absolute path to repository root (for Prow/Konflux runners and local behave).

    Set ``E2E_REPO_ROOT`` when the process cwd is not the repo or checkout layout
    differs. Otherwise derived from this file: ``tests/e2e/utils/utils.py`` → root.
    """
    env = os.getenv("E2E_REPO_ROOT", "").strip()
    if env:
        return os.path.abspath(env)
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
    )


def absolute_repo_path(repo_relative: str) -> str:
    """Return an absolute path for a location given relative to the repository root.

    Used on Prow so ``oc`` and file reads do not depend on the process working
    directory. If ``repo_relative`` is already absolute, it is normalized and
    returned unchanged.

    Parameters:
        repo_relative: Path relative to the repo root, or an absolute path.

    Returns:
        Normalized absolute filesystem path.
    """
    rel = repo_relative.strip()
    if os.path.isabs(rel):
        return os.path.normpath(rel)
    return os.path.normpath(os.path.join(_e2e_repo_root(), rel))


def is_prow_environment() -> bool:
    """Check if running in Prow/OpenShift environment."""
    return os.getenv("RUNNING_PROW") is not None


# Transient connection resets (e.g. errno 104) after container restarts in CI/Docker.
E2E_HTTP_TRANSIENT_MAX_ATTEMPTS: int = 3
E2E_HTTP_TRANSIENT_DELAY_S: float = 0.5


def request_with_transient_retry(
    **kwargs: Any,
) -> requests.Response:
    """Call :func:`requests.request`, retrying on transient :exc:`~requests.exceptions.ConnectionError`.

    Parameters:
        **kwargs: Forwarded to :func:`requests.request` (``method``, ``url``, ``json``,
            ``headers``, ``timeout``, ``stream``, etc.).

    Returns:
        Successful :class:`requests.Response`.

    Raises:
        The last :exc:`requests.exceptions.ConnectionError` if all attempts fail.
    """
    last_err: BaseException | None = None
    for attempt in range(E2E_HTTP_TRANSIENT_MAX_ATTEMPTS):
        try:
            return requests.request(**kwargs)
        except requests.exceptions.ConnectionError as exc:
            last_err = exc
            if attempt < E2E_HTTP_TRANSIENT_MAX_ATTEMPTS - 1:
                time.sleep(E2E_HTTP_TRANSIENT_DELAY_S)
    assert last_err is not None
    raise last_err


def cluster_lightspeed_config_dir() -> str:
    """Directory of Lightspeed YAML files used for Prow/Konflux (ConfigMap sources).

    Paths are relative to the repository root. Pipelines set
    ``E2E_LIGHTSPEED_CONFIG_DIR`` explicitly so local and CI agree on one variable;
    when unset, defaults to ``tests/e2e/configuration/server-mode``.

    Returns:
        Non-empty repo-relative directory path.
    """
    raw = os.getenv("E2E_LIGHTSPEED_CONFIG_DIR", _DEFAULT_CLUSTER_LIGHTSPEED_CONFIG_DIR)
    stripped = raw.strip()
    return stripped if stripped else _DEFAULT_CLUSTER_LIGHTSPEED_CONFIG_DIR


def cluster_lightspeed_config_path(filename: str) -> str:
    """Absolute path to a Lightspeed stack YAML used for Prow/OpenShift ConfigMap updates.

    The cluster loads config from the ConfigMap; Behave/e2e-ops must read the same
    YAML from the **runner filesystem**. Using an absolute path anchored at the repo
    root avoids failures when behave's cwd is not the repository root.

    Parameters:
        filename: Basename of the Lightspeed stack YAML.

    Returns:
        Absolute path suitable for ``switch_config`` and ``oc --from-file`` on CI.
    """
    base = cluster_lightspeed_config_dir()
    if os.path.isabs(base):
        return os.path.normpath(os.path.join(base, filename))
    return os.path.normpath(os.path.join(_e2e_repo_root(), base, filename))


def normalize_endpoint(endpoint: str) -> str:
    """Normalize endpoint to be added into the URL.

    Ensure an endpoint string is suitable for inclusion in a URL.

    Removes any double-quote characters and prepends a leading slash if one is
    not already present.

    Parameters:
    ----------
        endpoint (str): The endpoint string to normalize.

    Returns:
    -------
        str: The normalized endpoint starting with '/' and containing no double-quote characters.
    """
    endpoint = endpoint.replace('"', "")
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return endpoint


def validate_json(message: Any, schema: Any) -> None:
    """Check the JSON message with the given schema.

    Validate a JSON-like object against a jsonschema-compatible schema.

    Parameters:
    ----------
        message (Any): The JSON-like instance to validate (typically a dict or list).
        schema (Any): A jsonschema-compatible schema describing the expected structure.

    Returns:
    -------
        None

    Raises:
    ------
        AssertionError: If the instance does not conform to the schema or if
        the schema itself is invalid; the assertion message contains the
        underlying jsonschema error.
    """
    try:
        jsonschema.validate(
            instance=message,
            schema=schema,
        )

    except jsonschema.ValidationError as e:
        assert False, "The message doesn't fit the expected schema:" + str(e)

    except jsonschema.SchemaError as e:
        assert False, "The provided schema is faulty:" + str(e)


def wait_for_container_health(container_name: str, max_attempts: int = 6) -> None:
    """Wait for container to be healthy.

    Polls a Docker container until its health status becomes `healthy` or the
    attempt limit is reached.

    Checks the container's `Health.Status` using `docker inspect` up to
    `max_attempts`, printing progress and final status messages. Transient
    inspect errors or timeouts are ignored and retried; the function returns
    after the container is observed healthy or after all attempts complete.

    Returns:
    -------
        None

    Parameters:
    ----------
        container_name (str): Docker container name or ID to check.
        max_attempts (int): Maximum number of health check attempts (default 6).
    """
    if is_prow_environment():
        wait_for_pod_health(container_name, max_attempts)
        return

    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format={{.State.Health.Status}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            if result.stdout.strip() == "healthy":
                return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        if attempt < max_attempts - 1:
            print(
                f"⏱ Attempt {attempt + 1}/{max_attempts} - waiting for {container_name}..."
            )
            time.sleep(2)

    print(
        f"Could not confirm Docker health=healthy for {container_name} "
        f"after {max_attempts} attempts"
    )


def validate_json_partially(actual: Any, expected: Any) -> None:
    """Recursively validate that `actual` JSON contains all keys and values specified in `expected`.

    Extra elements/keys are ignored. Raises AssertionError if validation fails.

    Returns:
        None

    Raises:
        AssertionError: If a required key is missing, no list element matches
        an expected item, or a value does not equal the expected value.
    """
    if isinstance(expected, dict):
        for key, expected_value in expected.items():
            assert key in actual, f"Missing key in JSON: {key}"
            validate_json_partially(actual[key], expected_value)

    elif isinstance(expected, list):
        for schema_item in expected:
            matched = False
            for item in actual:
                try:
                    validate_json_partially(item, schema_item)
                    matched = True
                    break
                except AssertionError:
                    continue
            assert (
                matched
            ), f"No matching element found in list for schema item {schema_item}"

    else:
        assert actual == expected, f"Value mismatch: expected {expected}, got {actual}"


RESPONSES_SSE_TERMINAL_EVENT_TYPES = frozenset(
    {"response.completed", "response.incomplete", "response.failed"}
)


def parse_responses_sse_final_response_object(text: str) -> dict[str, Any]:
    """Return the ``response`` object from the last terminal LCORE ``/responses`` SSE event."""
    last: Optional[dict[str, Any]] = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if obj.get("type") in RESPONSES_SSE_TERMINAL_EVENT_TYPES and isinstance(
            obj.get("response"), dict
        ):
            last = obj["response"]
    if last is None:
        raise AssertionError(
            "No terminal responses SSE event (completed/incomplete/failed) found in body"
        )
    return last


def http_response_json_or_responses_sse_terminal(response: Any) -> Any:
    """Decode JSON body or, for streaming ``/responses`` SSE, the terminal ``response`` object.

    Non-SST responses use ``response.json()`` unchanged.
    """
    text = response.text
    content_type = (response.headers.get("content-type") or "").lower()
    if "text/event-stream" in content_type or (
        "event:" in text and "data:" in text and "[DONE]" in text
    ):
        return parse_responses_sse_final_response_object(text)
    return response.json()


def switch_config(
    source_path: str, destination_path: str = "lightspeed-stack.yaml"
) -> None:
    """Overwrite the config in `destination_path` by `source_path`.

    Replace the destination configuration file with the file at source_path.

    Parameters:
    ----------
        source_path (str): Path to the replacement configuration file.
        destination_path (str): Path to the configuration file to be
        overwritten (defaults to "lightspeed-stack.yaml").

    Returns:
    -------
        None

    Raises:
    ------
        FileNotFoundError: If source_path does not exist.
        PermissionError: If the file cannot be read or destination cannot be
                         written due to permissions.
        OSError: For other OS-related failures during the copy operation.
    """
    if is_prow_environment():
        update_config_configmap(source_path)
        return

    try:
        shutil.copy(source_path, destination_path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"Failed to copy replacement file: {e}")
        raise


def create_config_backup(config_path: str) -> str:
    """Create a backup of `config_path` if it does not already exist.

    Ensure a backup of the given configuration file exists by creating a
    `.backup` copy if it is missing.

    Returns:
        str: Path to the backup file (original path with `.backup` appended).

    Raises:
        FileNotFoundError: If the source config file does not exist.
        PermissionError: If the process lacks permission to read or write the files.
        OSError: For other OS-level errors encountered while copying.
    """
    if is_prow_environment():
        return backup_configmap_to_memory()

    backup_file = f"{config_path}.backup"
    if not os.path.exists(backup_file):
        try:
            shutil.copy(config_path, backup_file)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Failed to create backup: {e}")
            raise
    return backup_file


def remove_config_backup(backup_path: str) -> None:
    """Delete the backup file at `backup_path` if it exists.

    Remove the backup file at the given path if it exists.

    If the file is present, attempts to delete it; on failure prints a warning with the error.

    Returns:
    -------
        None

    Parameters:
    ----------
        backup_path (str): Filesystem path to the backup file to remove.
    """
    if is_prow_environment():
        remove_configmap_backup(backup_path)
        return

    if os.path.exists(backup_path):
        try:
            os.remove(backup_path)
        except OSError as e:
            print(f"Warning: Could not remove backup file {backup_path}: {e}")


def clear_llama_stack_storage(container_name: str = "lightspeed-stack") -> None:
    """Clear Llama Stack storage in library mode (embedded Llama Stack).

    Removes the ~/.llama directory so that toolgroups and other persisted
    state are reset. Used before MCP config scenarios when not running in
    server mode (no separate Llama Stack to unregister toolgroups from).
    Only runs when using Docker (skipped in Prow).

    Parameters:
    ----------
        container_name (str): Docker container name (default "lightspeed-stack").

    Returns:
    -------
        None
    """
    if is_prow_environment():
        return

    try:
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", "rm -rf ~/.llama"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        print(f"Failed to clear Llama Stack storage: {e}")
        raise


def restart_container(container_name: str) -> None:
    """Restart a Docker container by name and wait until it is healthy.

    Returns:
        None

    Raises:
        subprocess.CalledProcessError: if the `docker restart` command fails.
        subprocess.TimeoutExpired: if the `docker restart` command times out.
    """
    if is_prow_environment():
        restart_pod(container_name)
        if container_name in ("llama-stack", "lightspeed-stack"):
            from tests.e2e.features.steps.health import (
                reset_llama_stack_disrupt_once_tracking,
            )

            reset_llama_stack_disrupt_once_tracking()
        return

    try:
        subprocess.run(
            ["docker", "restart", container_name],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Failed to restart container {container_name}: {e}")
        raise

    # Wait for container to be healthy.
    # Library mode embeds llama-stack, so the container takes longer to start
    # (~45-60s vs ~10s in server mode).  Use a generous attempt count so
    # MCP-auth scenarios that restart the container don't time out.
    wait_for_container_health(container_name, max_attempts=12)

    if container_name == "llama-stack":
        from tests.e2e.features.steps.health import (
            reset_llama_stack_disrupt_once_tracking,
        )

        reset_llama_stack_disrupt_once_tracking()


def wait_for_lightspeed_stack_http_ready(
    max_attempts: int = 40,
    delay_s: float = 1.5,
) -> None:
    """Block until Lightspeed Stack accepts HTTP on the host-mapped port.

    Used from proxy e2e steps only: ``docker inspect`` health can report
    ``healthy`` before the published port accepts connections (Podman/Docker
    timing). Polls ``/liveness`` using the same host/port as Behave
    (``E2E_LSC_*``).

    Parameters:
    ----------
        max_attempts: Maximum GET attempts.
        delay_s: Sleep between attempts.
    Raises:
    ------
        AssertionError: If ``/liveness`` does not return HTTP 200 in time.
    """
    if is_prow_environment():
        return
    host = os.getenv("E2E_LSC_HOSTNAME", "localhost")
    port = os.getenv("E2E_LSC_PORT", "8080")
    url = f"http://{host}:{port}/liveness"
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
        if attempt < max_attempts - 1:
            print(f"⏱ HTTP wait LSC {attempt + 1}/{max_attempts} ({url})...")
            time.sleep(delay_s)
    raise AssertionError(
        f"Lightspeed Stack did not become reachable at {url!r} "
        f"after {max_attempts} attempts (~{max_attempts * delay_s:.0f}s)"
    )


def replace_placeholders(context: Context, text: str) -> str:
    """Replace {MODEL}, {PROVIDER}, and {VECTOR_STORE_ID} placeholders from context.

    Parameters:
    ----------
        context (Context): Behave context (default_model, default_provider,
            optional faiss_vector_store_id from ``FAISS_VECTOR_STORE_ID``).
        text (str): String that may contain placeholders to replace.

    Returns:
    -------
        String with placeholders replaced by actual values
    """
    result = text.replace("{MODEL}", context.default_model)
    result = result.replace("{PROVIDER}", context.default_provider)
    vector_store_id = getattr(context, "faiss_vector_store_id", None) or ""
    result = result.replace("{VECTOR_STORE_ID}", vector_store_id)
    if hasattr(context, "responses_first_response_id"):
        result = result.replace(
            "{RESPONSES_FIRST_RESPONSE_ID}", context.responses_first_response_id
        )
    if hasattr(context, "responses_conversation_id"):
        result = result.replace(
            "{RESPONSES_CONVERSATION_ID}", context.responses_conversation_id
        )
    if hasattr(context, "responses_second_response_id"):
        result = result.replace(
            "{RESPONSES_SECOND_RESPONSE_ID}", context.responses_second_response_id
        )
    return result
