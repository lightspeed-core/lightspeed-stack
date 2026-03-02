"""Unsorted utility functions to be used from other sources and test step definitions."""

import os
import shutil
import subprocess
import time
from typing import Any

import jsonschema
from behave.runner import Context

from tests.e2e.utils.prow_utils import (
    backup_configmap_to_memory,
    remove_configmap_backup,
    restart_pod,
    update_config_configmap,
    wait_for_pod_health,
)


def is_prow_environment() -> bool:
    """Check if running in Prow/OpenShift environment."""
    return os.getenv("RUNNING_PROW") is not None


def normalize_endpoint(endpoint: str) -> str:
    """Normalize endpoint to be added into the URL.

    Ensure an endpoint string is suitable for inclusion in a URL.

    Removes any double-quote characters and prepends a leading slash if one is
    not already present.

    Parameters:
        endpoint (str): The endpoint string to normalize.

    Returns:
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
        message (Any): The JSON-like instance to validate (typically a dict or list).
        schema (Any): A jsonschema-compatible schema describing the expected structure.

    Returns:
        None

    Raises:
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


def wait_for_container_health(container_name: str, max_attempts: int = 3) -> None:
    """Wait for container to be healthy.

    Polls a Docker container until its health status becomes `healthy` or the
    attempt limit is reached.

    Checks the container's `Health.Status` using `docker inspect` up to
    `max_attempts`, printing progress and final status messages. Transient
    inspect errors or timeouts are ignored and retried; the function returns
    after the container is observed healthy or after all attempts complete.

    Returns:
        None

    Parameters:
        container_name (str): Docker container name or ID to check.
        max_attempts (int): Maximum number of health check attempts (default 3).
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
                timeout=10,
            )
            if result.stdout.strip() == "healthy":
                break
            else:
                if attempt < max_attempts - 1:
                    time.sleep(5)
                else:
                    print(
                        f"{container_name} not healthy after {max_attempts * 5} seconds"
                    )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        if attempt < max_attempts - 1:
            print(f"⏱ Attempt {attempt + 1}/{max_attempts} - waiting...")
            time.sleep(5)
        else:
            print(f"Could not check health status for {container_name}")


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


def switch_config(
    source_path: str, destination_path: str = "lightspeed-stack.yaml"
) -> None:
    """Overwrite the config in `destination_path` by `source_path`.

    Replace the destination configuration file with the file at source_path.

    Parameters:
        source_path (str): Path to the replacement configuration file.
        destination_path (str): Path to the configuration file to be
        overwritten (defaults to "lightspeed-stack.yaml").

    Returns:
        None

    Raises:
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
        None

    Parameters:
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
        return

    try:
        subprocess.run(
            ["docker", "restart", container_name],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Failed to restart container {container_name}: {str(e.stderr)}")
        raise

    # Wait for container to be healthy
    wait_for_container_health(container_name)


def replace_placeholders(context: Context, text: str) -> str:
    """Replace {MODEL} and {PROVIDER} placeholders with actual values from context.

    Parameters:
        context (Context): Behave context containing default_model and default_provider
        text (str): String that may contain {MODEL} and {PROVIDER} placeholders

    Returns:
        String with placeholders replaced by actual values
    """
    result = text.replace("{MODEL}", context.default_model)
    result = result.replace("{PROVIDER}", context.default_provider)
    result = result.replace("{VECTOR_STORE_ID}", context.faiss_vector_store_id)
    return result
