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
from behave.contrib.scenario_autoretry import patch_scenario_with_autoretry
from behave.model import Feature, Scenario
from behave.runner import Context

from tests.e2e.features.steps.common import (
    reset_active_lightspeed_stack_config_basename,
)
from tests.e2e.features.steps.health import reset_llama_stack_disrupt_once_tracking
from tests.e2e.utils.llama_stack_utils import register_shield
from tests.e2e.utils.prow_utils import (
    restart_pod,
    restore_llama_stack_pod,
)
from tests.e2e.utils.utils import (
    is_prow_environment,
    remove_config_backup,
    restart_container,
    switch_config,
)

FALLBACK_MODEL = "gpt-4o-mini"
FALLBACK_PROVIDER = "openai"

# Wall-clock start for each feature (on ``Feature``; survives Behave context resets).
_E2E_FEATURE_PERF_START_ATTR = "_lightspeed_e2e_feature_perf_start"

# Opt-in scenario retries for infrastructure flakiness (tag scenario with ``@flaky``).
_E2E_FLAKY_TAG = "flaky"
_E2E_FLAKY_MAX_ATTEMPTS = 5


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
    ----------
        context (Context): Behave context into which this function writes:
            - deployment_mode (str): "server" or "library".
            - is_library_mode (bool): True when deployment_mode is "library".
            - default_model (str): Detected model id or fallback model.
            - default_provider (str): Detected provider id or fallback provider.
    """
    # Detect deployment mode from environment variable
    context.deployment_mode = os.getenv("E2E_DEPLOYMENT_MODE", "server").lower()
    context.is_library_mode = context.deployment_mode == "library"

    # Detect Docker mode once for proxy tests
    from tests.e2e.features.steps.proxy import _is_docker_mode

    context.is_docker_mode = _is_docker_mode()

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
    resetting per-scenario Lightspeed override tracking and skip-restart flags.

    Skips the scenario if it has the `skip` tag, if it has the `local` tag
    while the test run is not in local mode, or if it has
    `skip-in-library-mode` when running in library mode. Scenario-specific
    Lightspeed YAML is applied in the feature files (``The service uses the
    ... configuration`` steps).
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

    context.scenario_lightspeed_override_active = False
    context.lightspeed_stack_skip_restart = False

    # Clear shield unregister state from previous scenarios (see ``shields_are_disabled_for_scenario``).
    for _attr in (
        "shields_disabled_for_scenario",
        "llama_guard_provider_id",
        "llama_guard_provider_shield_id",
    ):
        if hasattr(context, _attr):
            delattr(context, _attr)


def after_scenario(context: Context, scenario: Scenario) -> None:
    """Run after each scenario is run.

    Perform per-scenario teardown: restore scenario-specific configuration and,
    in server mode, attempt to restart and verify the Llama Stack container if
    it was previously running.

    If ``configure_service`` applied a non-baseline YAML during the scenario
    (``context.scenario_lightspeed_override_active``), copies
    ``context.feature_config`` back and restarts lightspeed-stack.

    When not running in library mode and the context indicates the Llama Stack
    was running before the scenario, this function attempts to start the
    llama-stack container and polls its health endpoint until it becomes
    healthy or a timeout is reached.

    Parameters:
    ----------
        context (Context): Behave test context. Expected attributes used here include:
            - feature_config: path to the feature-level configuration to restore.
            - scenario_lightspeed_override_active: set by ``configure_service``
              when a scenario switches YAML after Background.
            - is_library_mode (bool): whether tests run in library mode.
            - llama_stack_was_running (bool, optional): whether llama-stack was
              running before the scenario.
            - hostname_llama, port_llama (str/int, optional): host and port
              used for the llama-stack health check.
        scenario (Scenario): Behave scenario (unused; shield restore uses context flags).
    """
    if getattr(context, "scenario_lightspeed_override_active", False):
        context.scenario_lightspeed_override_active = False
        feature_cfg = getattr(context, "feature_config", None)
        if feature_cfg:
            switch_config(feature_cfg)
            restart_container("lightspeed-stack")

    # Re-register shield if ``Given shields are disabled for this scenario`` unregistered it.
    if getattr(context, "shields_disabled_for_scenario", False):
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
        # Recreate llama pod, then restart LCS so in-process clients reconnect (Llama IP/pod changed).
        try:
            restore_llama_stack_pod()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Warning: Could not restore Llama Stack pod on Prow: {e}")
            return
        last_lcs_err: (
            subprocess.CalledProcessError | subprocess.TimeoutExpired | None
        ) = None
        for attempt in range(1, 4):
            try:
                restart_pod("lightspeed-stack")
                print(
                    "✓ Prow: Llama Stack restored and lightspeed-stack restarted "
                    "for clean reconnect"
                )
                reset_llama_stack_disrupt_once_tracking()
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                last_lcs_err = e
                print(
                    f"Warning: lightspeed-stack restart after Llama restore "
                    f"attempt {attempt}/3 failed: {e}"
                )
                if attempt < 3:
                    time.sleep(5)
        print(
            "Warning: Could not restart lightspeed-stack after Llama restore "
            f"after 3 attempts: {last_lcs_err}"
        )
        return

    try:
        # Start the llama-stack container again
        subprocess.run(
            ["docker", "start", "llama-stack"], check=True, capture_output=True
        )

        # Wait for the service to be healthy
        print("Restoring Llama Stack connection...")
        max_attempts = 24
        for attempt in range(max_attempts):
            try:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "llama-stack",
                        "curl",
                        "-sf",
                        f"http://{context.hostname_llama}:{context.port_llama}/v1/health",
                    ],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    print("✓ Llama Stack connection restored successfully")
                    reset_llama_stack_disrupt_once_tracking()
                    break
            except subprocess.TimeoutExpired:
                print(
                    f"⏱ Health check timed out on attempt {attempt + 1}/{max_attempts}"
                )

            if attempt < max_attempts - 1:
                print(
                    f"Waiting for Llama Stack to be healthy... "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )
                time.sleep(2)
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

    Per-feature setup that is not expressed in Gherkin.
    Lightspeed YAML is applied in feature Backgrounds via ``configure_service``.

    Records monotonic start time on ``feature`` for duration logging in
    ``after_feature`` (includes scenarios and feature teardown).

    Scenarios tagged ``@flaky`` are patched to retry the full scenario up to
    ``max_attempts`` times before accepting failure. The cap defaults to
    ``_E2E_FLAKY_MAX_ATTEMPTS`` and can be overridden with the
    ``E2E_FLAKY_MAX_ATTEMPTS`` environment variable.
    """
    setattr(feature, _E2E_FEATURE_PERF_START_ATTR, time.perf_counter())
    reset_active_lightspeed_stack_config_basename()
    context.active_lightspeed_stack_config_basename = None
    # One real Llama disruption per feature (module-level flag; survives context resets)
    reset_llama_stack_disrupt_once_tracking()

    try:
        max_flaky = int(os.getenv("E2E_FLAKY_MAX_ATTEMPTS", _E2E_FLAKY_MAX_ATTEMPTS))
    except ValueError:
        max_flaky = _E2E_FLAKY_MAX_ATTEMPTS
    if max_flaky > 1:
        for scenario in feature.walk_scenarios():
            if _E2E_FLAKY_TAG in scenario.effective_tags:
                patch_scenario_with_autoretry(scenario, max_attempts=max_flaky)

    # Do not inherit feedback teardown state from a previous feature file.
    for _attr in ("feedback_e2e_conversation_cleanup", "feedback_conversations"):
        if hasattr(context, _attr):
            delattr(context, _attr)


def after_feature(context: Context, feature: Feature) -> None:
    """Run after each feature file is exercised.

    Perform feature-level teardown: restore any modified configuration and,
    when ``context.feedback_e2e_conversation_cleanup`` is set by feedback steps,
    delete tracked feedback test conversations.
    """
    # Restore Llama Stack FIRST (before any lightspeed-stack restart)
    llama_was_running = getattr(context, "llama_stack_was_running", False)
    if llama_was_running:
        _restore_llama_stack(context)
        context.llama_stack_was_running = False

    if getattr(context, "feedback_e2e_conversation_cleanup", False):
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva"
        for conversation_id in getattr(context, "feedback_conversations", []):
            url = f"http://{context.hostname}:{context.port}/v1/conversations/{conversation_id}"
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.delete(url, headers=headers, timeout=10)
            assert response.status_code == 200, f"{url} returned {response.status_code}"

    # Restore Lightspeed Stack config if the generic configure_service step switched it.
    # This cleanup intentionally runs for any feature (not tag-gated) - any feature that
    # leaves a backup file will trigger config restoration and container restarts.
    backup_path = "lightspeed-stack.yaml.backup"
    if os.path.exists(backup_path):
        switch_config(backup_path)
        remove_config_backup(backup_path)
        if not context.is_library_mode:
            restart_container("llama-stack")
        restart_container("lightspeed-stack")

    # Clean up any proxy servers left from the last scenario
    if hasattr(context, "tunnel_proxy") or hasattr(context, "interception_proxy"):
        from tests.e2e.features.steps.proxy import _stop_proxy

        _stop_proxy(context, "tunnel_proxy", "proxy_loop")
        _stop_proxy(context, "interception_proxy", "interception_proxy_loop")

    start = getattr(feature, _E2E_FEATURE_PERF_START_ATTR, None)
    if start is not None:
        elapsed_s = time.perf_counter() - start
        try:
            delattr(feature, _E2E_FEATURE_PERF_START_ATTR)
        except AttributeError:
            pass
        feat_path = getattr(feature, "filename", "") or ""
        label = os.path.basename(feat_path) if feat_path else feature.name
        print(f"[e2e feature timing] {elapsed_s:.2f}s  {label}", flush=True)


# Behave captures hook stdout by default; output is only shown in some failure paths.
# Disable capture so feature timing lines always appear on the real console/CI log.
after_feature.capture = False  # type: ignore[attr-defined]
