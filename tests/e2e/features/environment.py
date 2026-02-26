"""Code to be called before and after certain events during testing.

Currently four events have been registered:
1. before_all
2. before_feature
3. before_scenario
4. after_scenario
"""

import os
import subprocess
import time

import requests
from behave.model import Feature, Scenario
from tests.e2e.utils.prow_utils import restore_llama_stack_pod
from behave.runner import Context

from tests.e2e.utils.llama_stack_shields import (
    register_shield,
    unregister_shield,
)
from tests.e2e.utils.utils import (
    create_config_backup,
    is_prow_environment,
    remove_config_backup,
    restart_container,
    switch_config,
)

FALLBACK_MODEL = "gpt-4o-mini"
FALLBACK_PROVIDER = "openai"

# Config file mappings: config_name -> (docker_path, prow_path)
_CONFIG_PATHS = {
    "no-cache": (
        "tests/e2e/configuration/{mode_dir}/lightspeed-stack-no-cache.yaml",
        "tests/e2e-prow/rhoai/configs/lightspeed-stack-no-cache.yaml",
    ),
    "auth-noop-token": (
        "tests/e2e/configuration/{mode_dir}/lightspeed-stack-auth-noop-token.yaml",
        "tests/e2e-prow/rhoai/configs/lightspeed-stack-auth-noop-token.yaml",
    ),
    "rbac": (
        "tests/e2e/configuration/{mode_dir}/lightspeed-stack-rbac.yaml",
        "tests/e2e-prow/rhoai/configs/lightspeed-stack-rbac.yaml",
    ),
    "invalid-feedback-storage": (
        "tests/e2e/configuration/{mode_dir}/lightspeed-stack-invalid-feedback-storage.yaml",
        "tests/e2e-prow/rhoai/configs/lightspeed-stack-invalid-feedback-storage.yaml",
    ),
    "rh-identity": (
        "tests/e2e/configuration/{mode_dir}/lightspeed-stack-auth-rh-identity.yaml",
        "tests/e2e-prow/rhoai/configs/lightspeed-stack-auth-rh-identity.yaml",
    ),
}


def _get_config_path(config_name: str, mode_dir: str) -> str:
    """Get the appropriate config path based on environment."""
    docker_path_template, prow_path = _CONFIG_PATHS[config_name]
    if is_prow_environment():
        return prow_path
    return docker_path_template.format(mode_dir=mode_dir)


def _fetch_models_from_service() -> dict:
    """Query /v1/models endpoint and return first LLM model.

    Returns:
        Dict with model_id and provider_id, or empty dict if unavailable
    """
    try:
        host_env = os.getenv("E2E_LSC_HOSTNAME", "localhost")
        port_env = os.getenv("E2E_LSC_PORT", "8080")
        url = f"http://{host_env}:{port_env}/v1/models"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        # Find first LLM model
        for model in data.get("models", []):
            if model.get("api_model_type") == "llm":
                provider_id = model.get("provider_id")
                model_id = model.get("provider_resource_id")
                if provider_id and model_id:
                    return {"model_id": model_id, "provider_id": provider_id}
        return {}
    except (requests.RequestException, ValueError, KeyError):
        return {}


def before_all(context: Context) -> None:
    """Run before and after the whole shooting match.

    Initialize global test environment before the test suite runs.

    Sets context.deployment_mode from the E2E_DEPLOYMENT_MODE environment
    variable (default "server") and context.is_library_mode accordingly.

    Attempts to detect a default LLM model and provider via
    _fetch_models_from_service() and stores results in context.default_model
    and context.default_provider; if detection fails, falls back to
    "gpt-4-turbo" and "openai".

    Parameters:
        context (Context): Behave context into which this function writes:
            - deployment_mode (str): "server" or "library".
            - is_library_mode (bool): True when deployment_mode is "library".
            - default_model (str): Detected model id or fallback model.
            - default_provider (str): Detected provider id or fallback provider.
    """
    # Detect deployment mode from environment variable
    context.deployment_mode = os.getenv("E2E_DEPLOYMENT_MODE", "server").lower()
    context.is_library_mode = context.deployment_mode == "library"

    # Get first LLM model from running service
    print(f"Running tests in {context.deployment_mode} mode")

    # Check for environment variable overrides first
    model_override = os.getenv("E2E_DEFAULT_MODEL_OVERRIDE")
    provider_override = os.getenv("E2E_DEFAULT_PROVIDER_OVERRIDE")

    context.faiss_vector_store_id = os.getenv("FAISS_VECTOR_STORE_ID")

    # Only override if the variables contain actual values (skip if empty)
    if model_override and provider_override:
        context.default_model = model_override
        context.default_provider = provider_override
        print(
            f"Using override LLM: {context.default_model} (provider: {context.default_provider})"
        )
    else:
        llm_model = _fetch_models_from_service()

        if llm_model:
            context.default_model = llm_model["model_id"]
            context.default_provider = llm_model["provider_id"]
            print(
                f"Detected LLM: {context.default_model} (provider: {context.default_provider})"
            )
        else:
            # Fallback for development
            context.default_model = FALLBACK_MODEL
            context.default_provider = FALLBACK_PROVIDER
            print(
                f"⚠ Could not detect models, using fallback: {context.default_provider}/{context.default_model}"
            )


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Run before each scenario is run.

    Prepare scenario execution by skipping scenarios based on tags and
    selecting a scenario-specific configuration.

    Skips the scenario if it has the `skip` tag, if it has the `local` tag
    while the test run is not in local mode, or if it has
    `skip-in-library-mode` when running in library mode. When the scenario is
    tagged with `InvalidFeedbackStorageConfig` or `NoCacheConfig`, sets
    `context.scenario_config` to the appropriate configuration file path for
    the current deployment mode (library-mode or server-mode).
    """
    if "skip" in scenario.effective_tags:
        scenario.skip("Marked with @skip")
        return
    if "local" in scenario.effective_tags and not context.local:
        scenario.skip("Marked with @local")
        return

    # Skip scenarios that require separate llama-stack container in library mode
    if context.is_library_mode and "skip-in-library-mode" in scenario.effective_tags:
        scenario.skip("Skipped in library mode (no separate llama-stack container)")
        return

    # @disable-shields: unregister shield via client.shields.delete("llama-guard").
    # Only in server mode: in library mode there is no separate Llama Stack to call,
    # and unregistering in the test process would not affect the app's in-process instance.
    if "disable-shields" in scenario.effective_tags:
        if context.is_library_mode:
            scenario.skip(
                "Shield unregister/register only applies in server mode (Llama Stack as a "
                "separate service). In library mode the app's shields cannot be disabled from e2e."
            )
            return
        try:
            saved = unregister_shield("llama-guard")
            context.llama_guard_provider_id = saved[0] if saved else None
            context.llama_guard_provider_shield_id = saved[1] if saved else None
            print("Unregistered shield llama-guard for this scenario")
        except Exception as e:  # pylint: disable=broad-exception-caught
            scenario.skip(
                f"Could not unregister shield (is Llama Stack reachable?): {e}"
            )
            return

    mode_dir = "library-mode" if context.is_library_mode else "server-mode"

    if "InvalidFeedbackStorageConfig" in scenario.effective_tags:
        context.scenario_config = _get_config_path("invalid-feedback-storage", mode_dir)
    if "NoCacheConfig" in scenario.effective_tags:
        context.scenario_config = _get_config_path("no-cache", mode_dir)
        switch_config(context.scenario_config)
        restart_container("lightspeed-stack")


def after_scenario(context: Context, scenario: Scenario) -> None:
    """Run after each scenario is run.

    Perform per-scenario teardown: restore scenario-specific configuration and,
    in server mode, attempt to restart and verify the Llama Stack container if
    it was previously running.

    If the scenario used an alternate feedback storage or no-cache
    configuration, the original feature configuration is restored and the
    lightspeed-stack container is restarted. When not running in library mode
    and the context indicates the Llama Stack was running before the scenario,
    this function attempts to start the llama-stack container and polls its
    health endpoint until it becomes healthy or a timeout is reached.

    Parameters:
        context (Context): Behave test context. Expected attributes used here include:
            - feature_config: path to the feature-level configuration to restore.
            - is_library_mode (bool): whether tests run in library mode.
            - llama_stack_was_running (bool, optional): whether llama-stack was
              running before the scenario.
            - hostname_llama, port_llama (str/int, optional): host and port
              used for the llama-stack health check.
        scenario (Scenario): Behave scenario whose tags determine which
        scenario-specific teardown actions to run (e.g.,
        "InvalidFeedbackStorageConfig", "NoCacheConfig").
    """
    # Restore Llama Stack FIRST (before any lightspeed-stack restart)
    llama_was_running = getattr(context, "llama_stack_was_running", False)
    if llama_was_running:
        _restore_llama_stack(context)
        context.llama_stack_was_running = False

    # Tags that require config restoration after scenario
    config_restore_tags = {"InvalidFeedbackStorageConfig", "NoCacheConfig"}
    if config_restore_tags & set(scenario.effective_tags):
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    # @disable-shields: re-register shield only if we unregistered one (avoid creating a shield that did not exist)
    if "disable-shields" in scenario.effective_tags:
        provider_id = getattr(context, "llama_guard_provider_id", None)
        provider_shield_id = getattr(context, "llama_guard_provider_shield_id", None)
        if provider_id is not None and provider_shield_id is not None:
            try:
                register_shield(
                    "llama-guard",
                    provider_id=provider_id,
                    provider_shield_id=provider_shield_id,
                )
                print("Re-registered shield llama-guard")
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(f"Warning: Could not re-register shield: {e}")


def _print_llama_stack_diagnostics() -> None:
    """Print container state, health, and recent logs to diagnose why llama-stack did not recover."""
    print("--- llama-stack diagnostics ---")
    for label, cmd in [
        ("State", ["docker", "inspect", "--format={{.State}}", "llama-stack"]),
        ("Health", ["docker", "inspect", "--format={{.State.Health}}", "llama-stack"]),
    ]:
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5, check=False
            )
            print(f"  {label}: {r.stdout.strip() if r.stdout else r.stderr or 'N/A'}")
        except subprocess.TimeoutExpired:
            print(f"  {label}: (inspect timed out)")
    try:
        r = subprocess.run(
            ["docker", "logs", "--tail", "40", "llama-stack"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        out = (r.stdout or "") + (r.stderr or "")
        print("  Logs (last 40 lines):")
        for line in out.strip().splitlines():
            print(f"    {line}")
    except subprocess.TimeoutExpired:
        print("  Logs: (timed out)")
    print("--- end diagnostics ---")


def _restore_llama_stack(context: Context) -> None:
    """Restore Llama Stack connection after disruption."""
    if is_prow_environment():
        restore_llama_stack_pod()
        return

    try:
        # Start the llama-stack container again
        subprocess.run(
            ["docker", "start", "llama-stack"], check=True, capture_output=True
        )

        # Wait for the service to be healthy
        print("Restoring Llama Stack connection...")
        time.sleep(20)

        # Check if it's healthy
        for attempt in range(6):  # Try for 30 seconds
            try:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "llama-stack",
                        "curl",
                        "-f",
                        f"http://{context.hostname_llama}:{context.port_llama}/v1/health",
                    ],
                    capture_output=True,
                    timeout=5,
                    check=True,
                )
                if result.returncode == 0:
                    print("✓ Llama Stack connection restored successfully")
                    break
            except subprocess.TimeoutExpired:
                print(f"⏱ Health check timed out on attempt {attempt + 1}/6")

            if attempt < 5:
                print(
                    f"Waiting for Llama Stack to be healthy... (attempt {attempt + 1}/6)"
                )
                time.sleep(5)
            else:
                print("Warning: Llama Stack may not be fully healthy after restoration")
                _print_llama_stack_diagnostics()

    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not restore Llama Stack connection: {e}")
        if e.stderr:
            print(f"  docker start stderr: {e.stderr}")
        if e.stdout:
            print(f"  docker start stdout: {e.stdout}")
        _print_llama_stack_diagnostics()


def before_feature(context: Context, feature: Feature) -> None:
    """Run before each feature file is exercised.

    Prepare per-feature test environment and apply feature-specific configuration.
    """
    mode_dir = "library-mode" if context.is_library_mode else "server-mode"
    if "Authorized" in feature.tags:
        context.feature_config = _get_config_path("auth-noop-token", mode_dir)
        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    if "RBAC" in feature.tags:
        context.feature_config = _get_config_path("rbac", mode_dir)
        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    if "RHIdentity" in feature.tags:
        context.feature_config = _get_config_path("rh-identity", mode_dir)
        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    if "Feedback" in feature.tags:
        context.hostname = os.getenv("E2E_LSC_HOSTNAME", "localhost")
        context.port = os.getenv("E2E_LSC_PORT", "8080")
        context.feedback_conversations = []

    if "MCP" in feature.tags:
        mode_dir = "library-mode" if context.is_library_mode else "server-mode"
        context.feature_config = (
            f"tests/e2e/configuration/{mode_dir}/lightspeed-stack-mcp.yaml"
        )
        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")


def after_feature(context: Context, feature: Feature) -> None:
    """Run after each feature file is exercised.

    Perform feature-level teardown: restore any modified configuration and
    clean up feedback conversations.
    """
    if "Authorized" in feature.tags:
        switch_config(context.default_config_backup)
        restart_container("lightspeed-stack")
        remove_config_backup(context.default_config_backup)

    if "RBAC" in feature.tags:
        switch_config(context.default_config_backup)
        restart_container("lightspeed-stack")
        remove_config_backup(context.default_config_backup)

    if "RHIdentity" in feature.tags:
        switch_config(context.default_config_backup)
        restart_container("lightspeed-stack")
        remove_config_backup(context.default_config_backup)

    if "Feedback" in feature.tags:
        for conversation_id in context.feedback_conversations:
            url = f"http://{context.hostname}:{context.port}/v1/conversations/{conversation_id}"
            response = requests.delete(url, timeout=10)
            assert response.status_code == 200, f"{url} returned {response.status_code}"

    if "MCP" in feature.tags:
        switch_config(context.default_config_backup)
        restart_container("lightspeed-stack")
        remove_config_backup(context.default_config_backup)
