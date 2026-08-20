"""Integration tests for Llama Stack container lifecycle management.

Tests verify build, startup, health monitoring, configuration, and teardown.
"""

import os
import time
from subprocess import CalledProcessError, CompletedProcess, run
from typing import Any

import pytest
import requests

LLAMA_STACK_IMAGE_NAME = "lightspeed-llama-stack:local"
LLAMA_STACK_CONTAINER_NAME = "lightspeed-llama-stack"
HEALTH_ENDPOINT = "http://localhost:8321/v1/health"
LLAMA_STACK_CONTAINER_LOG = "/tmp/llama-stack-last-run.log"
MUST_HAVE_FILES = [
    "/opt/app-root/run.yaml",
    "/opt/app-root/lightspeed-stack.yaml",
    "/opt/app-root/enrich-entrypoint.sh",
    "/opt/app-root/llama_stack_configuration.py",
]
DEFAULT_TIMEOUT = 60
NETWORK_BINDING_MAX_ATTEMPTS = 5


@pytest.fixture(scope="session")
def container_runtime() -> str:
    """Detect available container runtime (podman or docker).

    Returns
    -------
        str: Container runtime command ("podman" or "docker").

    Raises
    ------
        pytest.skip: If no container runtime is available.
    """
    for runtime in ["podman", "docker"]:
        try:
            _run_container_command(
                [runtime, "--version"],
                check=True,
            )

            return runtime
        except (CalledProcessError, FileNotFoundError):
            continue
    pytest.skip("No container runtime available")


def _run_container_command(
    cmd: list[str],
    *,
    capture_output=True,
    text=True,
    timeout=DEFAULT_TIMEOUT,
    check=False,
) -> CompletedProcess[Any]:
    """Run a container command as a subprocess.

    Parameters
    ----------
        cmd: Command and arguments to execute.
        capture_output: Whether to capture stdout and stderr.
        text: Whether to decode output as text.
        timeout: Maximum seconds to wait before killing the process.
        check: Whether to raise CalledProcessError on non-zero exit.

    Returns
    -------
        CompletedProcess: Result of the subprocess execution.
    """
    return run(
        cmd, capture_output=capture_output, text=text, timeout=timeout, check=check
    )


class TestContainerLifecycle:
    """Integration tests for Llama Stack container lifecycle management."""

    def test_container_lifecycle(self, container_runtime):
        """Verify the full container lifecycle: build, start, health, files, and cleanup."""
        # Make sure we start clean
        _run_container_command(
            [container_runtime, "rmi", "-f", LLAMA_STACK_IMAGE_NAME],
        )

        # Test image build
        build_image_result = _run_container_command(
            ["make", "build-llama-stack-image"], timeout=300
        )
        assert (
            build_image_result.returncode == 0
        ), f"Build failed: {build_image_result.stderr}"

        # Verify image is listed with correct tag
        query_image_result = _run_container_command(
            [container_runtime, "images", LLAMA_STACK_IMAGE_NAME]
        )

        assert query_image_result.returncode == 0, "Failed to list images"
        assert (
            "lightspeed-llama-stack" in query_image_result.stdout
        ), "Image not found in image list"

        # Spawn container
        build_container_result = _run_container_command(
            [
                "make",
                "start-llama-stack-container",
            ],
            timeout=300,
        )
        assert (
            build_container_result.returncode == 0
        ), f"Container start failed: {build_container_result.stderr}"

        # Verify the container is healthy
        attempts_left = NETWORK_BINDING_MAX_ATTEMPTS
        passed = False
        while attempts_left != 0:
            attempts_left -= 1
            try:
                response = requests.get(HEALTH_ENDPOINT, timeout=30)
                assert (
                    response.status_code == 200
                ), f"Health endpoint returned status {response.status_code}"
                body = response.json()
                assert (
                    body.get("status") == "OK"
                ), 'Health response missing "status" field or its value is not "OK"'

                passed = True
                break

            except Exception:
                time.sleep(1)

        if not passed:
            pytest.fail(
                f"Could not reach /v1/health from host machine after "
                f"{NETWORK_BINDING_MAX_ATTEMPTS} attempts"
            )

        # Verify we have these essential files mounted
        for file in MUST_HAVE_FILES:
            search_result = _run_container_command(
                [
                    container_runtime,
                    "exec",
                    LLAMA_STACK_CONTAINER_NAME,
                    "test",
                    "-f",
                    file,
                ]
            )
            assert (
                search_result.returncode == 0
            ), f"Required mount missing or not a file: {file}"

        remove_container_result = _run_container_command(
            [
                "make",
                "remove-llama-stack-container",
            ],
        )
        assert (
            remove_container_result.returncode == 0
        ), "Failed to remove the Llama Stack container"

        # Verify log file was created and is not empty
        assert os.path.exists(
            LLAMA_STACK_CONTAINER_LOG
        ), f"Container logs were not written to {LLAMA_STACK_CONTAINER_LOG}"
        assert (
            os.path.getsize(LLAMA_STACK_CONTAINER_LOG) > 0
        ), "Log file was created but is empty"

        # Remove the Llama Stack image
        clean_result = _run_container_command(
            [
                "make",
                "clean-llama-stack",
            ],
        )
        assert (
            clean_result.returncode == 0
        ), f"Clean target failed: {clean_result.stderr}"
