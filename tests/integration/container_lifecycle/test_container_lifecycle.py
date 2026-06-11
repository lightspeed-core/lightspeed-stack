"""Integration tests for Llama Stack container lifecycle management.

Tests verify build, startup, health monitoring, configuration, and teardown.
"""

import os
import subprocess
import time
import urllib.error
import urllib.request

import pytest


@pytest.fixture(scope="session")
def container_runtime():
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
            subprocess.run(
                [runtime, "--version"], check=True, capture_output=True, timeout=5
            )
            return runtime
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    pytest.skip("No container runtime available")


@pytest.fixture(scope="session", autouse=True)
def build_container_image_once():
    """Build container image once at session start to avoid timeouts in tests.

    This fixture runs automatically before any tests and ensures the image
    is built once. Subsequent container starts can reuse the cached image,
    avoiding timeout issues in CI where builds can take >120 seconds.
    """
    subprocess.run(
        ["make", "build-llama-stack-image"],
        check=True,
        capture_output=True,
        timeout=300,  # 5 minutes for first build
    )


@pytest.fixture(scope="class")
def managed_container(container_runtime):
    """Start container once for entire test class with strict cleanup.

    Parameters
    ----------
        container_runtime (str): Container runtime to use.

    Yields
    ------
        str: Test container name.
    """
    container_name = "test-llama-stack-integration"

    # Pre-cleanup
    subprocess.run(
        [container_runtime, "rm", "-f", container_name],
        capture_output=True,
        timeout=10,
    )

    # Start container
    result = subprocess.run(
        [
            "make",
            "start-llama-stack-container",
            f"LLAMA_STACK_CONTAINER_NAME={container_name}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Container start failed: {result.stderr}"

    yield container_name

    # Post-cleanup
    subprocess.run(
        [container_runtime, "rm", "-f", container_name],
        capture_output=True,
        timeout=10,
    )


class TestContainerBuild:
    """Test container image building with idempotency checks."""

    def _get_image_id(self, runtime, image_name="lightspeed-llama-stack:local"):
        """Get the unique, immutable Image ID (SHA256).

        Parameters
        ----------
            runtime (str): Container runtime (podman or docker).
            image_name (str): Image name and tag to query.

        Returns
        -------
            str: The image ID (SHA256 hash).
        """
        result = subprocess.run(
            [runtime, "images", "-q", image_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()

    def test_build_llama_stack_image(self, container_runtime):
        """Test that llama-stack image builds successfully and exists.

        Parameters
        ----------
            container_runtime (str): Container runtime to use for verification.
        """
        result = subprocess.run(
            ["make", "build-llama-stack-image"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, f"Build failed: {result.stderr}"

        # Verify image exists via the runtime
        image_id = self._get_image_id(container_runtime)
        assert image_id, "Image ID not found after build"

        # Verify image is listed with correct tag
        result = subprocess.run(
            [container_runtime, "images", "lightspeed-llama-stack:local"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, "Failed to list images"
        assert (
            "lightspeed-llama-stack" in result.stdout
        ), "Image not found in image list"

    def test_build_is_idempotent_via_image_id(self, container_runtime):
        """Test that rebuilding without changes yields the exact same Image ID.

        Parameters
        ----------
            container_runtime (str): Container runtime to use for image inspection.
        """
        # Trigger the first build
        subprocess.run(["make", "build-llama-stack-image"], check=True, timeout=600)
        first_image_id = self._get_image_id(container_runtime)
        assert first_image_id, "Failed to retrieve Image ID after first build"

        # Trigger the second build (should be 100% cached)
        subprocess.run(["make", "build-llama-stack-image"], check=True, timeout=120)
        second_image_id = self._get_image_id(container_runtime)

        # Core Idempotency Assert: Image ID must be identical
        assert first_image_id == second_image_id, (
            f"Build was not idempotent! Image ID changed from {first_image_id} "
            f"to {second_image_id}. This means cache layers were invalidated."
        )


@pytest.mark.usefixtures("managed_container")
class TestLlamaStackDeployment:
    """Consolidated lifecycle, networking, and configuration verification."""

    def test_container_is_running(self, container_runtime, managed_container):
        """Verify container appears in the runtime's active process list.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
            managed_container (str): Test container name.
        """
        result = subprocess.run(
            [
                container_runtime,
                "ps",
                "--filter",
                f"name={managed_container}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert (
            managed_container in result.stdout
        ), f"Container {managed_container} not found in running containers"

    def test_container_becomes_healthy(self, container_runtime, managed_container):
        """Poll engine internal health state until status is healthy.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
            managed_container (str): Test container name.
        """
        for attempt in range(30):
            result = subprocess.run(
                [
                    container_runtime,
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    managed_container,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "healthy" in result.stdout:
                return
            time.sleep(2)
        pytest.fail(
            f"Container failed to transition to a 'healthy' state within 60s "
            f"(attempts: {attempt + 1})."
        )

    def test_health_endpoint_responds_on_host(self):
        """Verify HTTP API accessibility from host without container-side curl."""
        url = "http://localhost:8321/v1/health"

        # Retry loop for network binding stabilization
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    body = response.read().decode("utf-8").lower()
                    assert (
                        response.status == 200
                    ), f"Health endpoint returned status {response.status}"
                    assert (
                        "status" in body
                    ), f"Health response missing 'status' field: {body}"
                    return
            except (urllib.error.URLError, ConnectionError) as e:
                if attempt == 4:  # Last attempt
                    pytest.fail(
                        f"Could not reach /v1/health from host machine after "
                        f"{attempt + 1} attempts. Last error: {e}"
                    )
                time.sleep(1)

    def test_default_port_mapping(self, container_runtime, managed_container):
        """Verify internal port 8321 binds properly.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
            managed_container (str): Test container name.
        """
        result = subprocess.run(
            [container_runtime, "port", managed_container],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0, "Failed to query port mappings"
        assert (
            "8321" in result.stdout
        ), f"Port 8321 not found in port mappings: {result.stdout}"

    @pytest.mark.parametrize(
        "file_path",
        [
            "/opt/app-root/run.yaml",
            "/opt/app-root/lightspeed-stack.yaml",
            "/opt/app-root/enrich-entrypoint.sh",
            "/opt/app-root/llama_stack_configuration.py",
        ],
    )
    def test_required_volumes_mounted(
        self, container_runtime, managed_container, file_path
    ):
        """Parametrized verification of all critical configuration and script mounts.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
            managed_container (str): Test container name.
            file_path (str): Path to verify inside container.
        """
        result = subprocess.run(
            [container_runtime, "exec", managed_container, "test", "-f", file_path],
            capture_output=True,
            timeout=5,
        )
        assert (
            result.returncode == 0
        ), f"Required mount missing or not a file: {file_path}"


class TestContainerCustomConfiguration:
    """Isolates tests that require distinct runtime configurations."""

    def test_custom_port_mapping(self, container_runtime):
        """Verify alternative port bindings parameterize correctly.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
        """
        container_name = "test-llama-stack-custom-port"
        custom_port = "9321"

        try:
            subprocess.run(
                [
                    "make",
                    "start-llama-stack-container",
                    f"LLAMA_STACK_CONTAINER_NAME={container_name}",
                    f"LLAMA_STACK_PORT={custom_port}",
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
            result = subprocess.run(
                [container_runtime, "port", container_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, "Failed to query port mappings"
            assert (
                custom_port in result.stdout
            ), f"Custom port {custom_port} not found in port mappings: {result.stdout}"
        finally:
            subprocess.run(
                [container_runtime, "rm", "-f", container_name],
                capture_output=True,
                timeout=10,
            )


class TestContainerTeardown:
    """Test container cleanup and resource management."""

    def test_stop_container_gracefully(self, container_runtime):
        """Test that container stops gracefully within timeout.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
        """
        container_name = "test-llama-stack-teardown"

        try:
            # Start container
            subprocess.run(
                [
                    "make",
                    "start-llama-stack-container",
                    f"LLAMA_STACK_CONTAINER_NAME={container_name}",
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )

            # Stop container using Makefile target
            result = subprocess.run(
                [
                    "make",
                    "stop-llama-stack-container",
                    f"LLAMA_STACK_CONTAINER_NAME={container_name}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert result.returncode == 0, f"Container stop failed: {result.stderr}"

            # Verify container is no longer running
            result = subprocess.run(
                [
                    container_runtime,
                    "ps",
                    "--filter",
                    f"name={container_name}",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert (
                container_name not in result.stdout
            ), f"Container {container_name} still running after stop"

        finally:
            subprocess.run(
                [container_runtime, "rm", "-f", container_name],
                capture_output=True,
                timeout=10,
            )

    def test_remove_container_saves_logs(self, container_runtime):
        """Test that removing container saves logs to a clean, unique file path.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
        """
        container_name = "test-llama-stack-log-save"

        # Clear stale log file to prevent false positives
        target_log = "/tmp/llama-stack-last-run.log"
        if os.path.exists(target_log):
            os.remove(target_log)

        try:
            # Start container
            subprocess.run(
                [
                    "make",
                    "start-llama-stack-container",
                    f"LLAMA_STACK_CONTAINER_NAME={container_name}",
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )

            # Remove container (should save logs)
            subprocess.run(
                [
                    "make",
                    "remove-llama-stack-container",
                    f"LLAMA_STACK_CONTAINER_NAME={container_name}",
                ],
                check=True,
                capture_output=True,
                timeout=15,
            )

            # Verify log file was created and is not empty
            assert os.path.exists(
                target_log
            ), f"Container logs were not written to {target_log}"
            assert os.path.getsize(target_log) > 0, "Log file was created but is empty"

        finally:
            subprocess.run(
                [container_runtime, "rm", "-f", container_name],
                capture_output=True,
                timeout=10,
            )

    @pytest.mark.order("last")
    @pytest.mark.destructive
    def test_clean_removes_image_and_container(self, container_runtime):
        """Test that clean target removes assets. Runs last to avoid deleting dev images.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.

        Notes
        -----
            Marked as destructive and ordered last. Skip locally with:
            pytest -m "not destructive"
        """
        container_name = "test-llama-stack-clean"

        # Ensure image exists
        subprocess.run(
            ["make", "build-llama-stack-image"],
            check=True,
            capture_output=True,
            timeout=600,
        )

        # Start a container
        subprocess.run(
            [
                "make",
                "start-llama-stack-container",
                f"LLAMA_STACK_CONTAINER_NAME={container_name}",
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )

        # Run clean target
        result = subprocess.run(
            [
                "make",
                "clean-llama-stack",
                f"LLAMA_STACK_CONTAINER_NAME={container_name}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Clean target failed: {result.stderr}"

        # Verify container is removed
        result = subprocess.run(
            [container_runtime, "ps", "-a", "--filter", f"name={container_name}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert (
            container_name not in result.stdout
        ), f"Container {container_name} still exists after clean"

        # Verify image is removed
        result = subprocess.run(
            [container_runtime, "images", "-q", "lightspeed-llama-stack:local"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert not result.stdout.strip(), "Image still exists after clean"


class TestContainerErrorScenarios:
    """Test error handling and edge cases."""

    def test_double_start_replaces_container(self, container_runtime):
        """Test that starting container twice replaces the first instance.

        Parameters
        ----------
            container_runtime (str): Container runtime to use.
        """
        container_name = "test-llama-stack-double-start"

        try:
            # First start
            subprocess.run(
                [
                    "make",
                    "start-llama-stack-container",
                    f"LLAMA_STACK_CONTAINER_NAME={container_name}",
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )

            # Get first container ID
            result = subprocess.run(
                [
                    container_runtime,
                    "ps",
                    "-q",
                    "--filter",
                    f"name={container_name}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            first_id = result.stdout.strip()

            # Second start (should replace)
            subprocess.run(
                [
                    "make",
                    "start-llama-stack-container",
                    f"LLAMA_STACK_CONTAINER_NAME={container_name}",
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )

            # Get second container ID
            result = subprocess.run(
                [
                    container_runtime,
                    "ps",
                    "-q",
                    "--filter",
                    f"name={container_name}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            second_id = result.stdout.strip()

            # IDs should be different (new container created)
            assert (
                first_id != second_id
            ), f"Container was not replaced on second start (ID: {first_id})"

        finally:
            subprocess.run(
                [container_runtime, "rm", "-f", container_name],
                capture_output=True,
                timeout=10,
            )
