"""Unsorted utility functions to be used from other sources and test step definitions."""

import os
import shutil
import subprocess
import time
import jsonschema
from typing import Any


def normalize_endpoint(endpoint: str) -> str:
    """Normalize endpoint to be added into the URL."""
    endpoint = endpoint.replace('"', "")
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return endpoint


def validate_json(message: Any, schema: Any) -> None:
    """Check the JSON message with the given schema."""
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
    """Wait for container to be healthy."""
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                [
                    os.getenv("CONTAINER_CMD", "docker"),
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


def validate_json_partially(actual: Any, expected: Any):
    """Recursively validate that `actual` JSON contains all keys and values specified in `expected`.

    Extra elements/keys are ignored. Raises AssertionError if validation fails.
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
    """Overwrite the config in `destination_path` by `source_path`."""
    try:
        shutil.copy(source_path, destination_path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"Failed to copy replacement file: {e}")
        raise


def create_config_backup(config_path: str) -> str:
    """Create a backup of `config_path` if it does not already exist."""
    backup_file = f"{config_path}.backup"
    if not os.path.exists(backup_file):
        try:
            shutil.copy(config_path, backup_file)
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Failed to create backup: {e}")
            raise
    return backup_file


def remove_config_backup(backup_path: str) -> None:
    """Delete the backup file at `backup_path` if it exists."""
    if os.path.exists(backup_path):
        try:
            os.remove(backup_path)
        except OSError as e:
            print(f"Warning: Could not remove backup file {backup_path}: {e}")


def restart_container(container_name: str) -> None:
    """Restart a Docker container by name and wait until it is healthy."""
    try:
        subprocess.run(
            [os.getenv("CONTAINER_CMD", "docker"), "restart", container_name],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Failed to restart container {container_name}: {e.stderr}")
        raise

    # Wait for container to be healthy
    wait_for_container_health(container_name)
