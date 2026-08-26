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
from typing import Optional

import requests
from behave.contrib.scenario_autoretry import patch_scenario_with_autoretry
from behave.model import Feature, Scenario
from behave.runner import Context

from tests.e2e.features.steps.common import (
    get_llama_stack_hostname,
    get_llama_stack_port,
    reset_active_lightspeed_stack_config_basename,
)
from tests.e2e.features.steps.health import (
    get_llama_stack_was_running,
    reset_llama_stack_disrupt_once_tracking,
    reset_llama_stack_was_running,
)
from tests.e2e.features.steps.tls import (
    is_tls_feature_file,
    prepare_tls_feature_entry_on_prow,
    reset_tls_prow_state,
)
from tests.e2e.utils.llama_stack_utils import register_shield
from tests.e2e.utils.prow_utils import (
    restart_pod,
    restore_llama_stack_pod,
    run_e2e_ops,
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
        response = requests.get(url, params={"model_type": "llm"}, timeout=15)
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
    ``FALLBACK_MODEL`` / ``FALLBACK_PROVIDER`` (aligned with server-mode e2e YAML).

    Parameters:
    ----------
        context (Context): Behave context into which this function writes:
            - deployment_mode (str): "server" or "library".
            - is_library_mode (bool): True when deployment_mode is "library".
            - default_model (str): Detected model id or fallback model.
            - default_provider (str): Detected provider id or fallback provider.
    """
    # Set OTEL anonymization secret for E2E tests if not already configured
    if not os.environ.get("OTEL_ANONYMIZATION_SECRET"):
        os.environ["OTEL_ANONYMIZATION_SECRET"] = (
            "e2e-test-secret-do-not-use-in-production"
        )

    # Detect deployment mode from environment variable
    context.deployment_mode = os.getenv("E2E_DEPLOYMENT_MODE", "server").lower()
    context.is_library_mode = context.deployment_mode == "library"

    # Detect Docker mode once for proxy tests
    from tests.e2e.features.steps.proxy import _is_docker_mode

    context.is_docker_mode = _is_docker_mode()

    # Get first LLM model from running service
    print(f"Running tests in {context.deployment_mode} mode")

    # Check for environment variable overrides first
    model_override = os.getenv("E2E_DEFAULT_MODEL_OVERRIDE", "")
    provider_override = os.getenv("E2E_DEFAULT_PROVIDER_OVERRIDE", "")

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


def _ensure_prow_port_forward(context: Context) -> None:
    """Check that the lightspeed port-forward is alive; restart it if dead.

    Probes localhost:{E2E_LSC_PORT}/readiness — if it fails, calls e2e-ops
    restart-port-forward to re-establish the tunnel before the scenario runs.

    Treat HTTP 503 like 200/401 here: it means the tunnel reached Lightspeed and the
    app responded. ``llama_stack_disrupted`` leaves Llama stopped on purpose; readiness
    then returns 503. Previously we treated 503 as a dead tunnel and ran
    ``restart-lightspeed``, which restores Llama via e2e-ops and breaks later scenarios
    that skip disruption (once-per-feature) while expecting Llama to stay down.
    """
    host = os.getenv("E2E_LSC_HOSTNAME", "localhost")
    port = os.getenv("E2E_LSC_PORT", "8080")
    url = f"http://{host}:{port}/readiness"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code in (200, 401, 503):
            return
    except requests.RequestException:
        pass

    print("[before_scenario] Port-forward appears dead, restarting...")
    try:
        result = run_e2e_ops("restart-port-forward", timeout=60)
        print(result.stdout, end="")
        if result.returncode == 0:
            print("[before_scenario] Port-forward re-established")
            return
        print(result.stderr, end="")
    except subprocess.TimeoutExpired:
        pass

    # Port-forward alone failed — the pod itself may be dead (e.g. OGX
    # was never restored after a disruption feature). Attempt a full restart,
    # which also checks Llama health before recreating LCS.
    print("[before_scenario] Port-forward failed; attempting full pod restart...")
    try:
        result = run_e2e_ops("restart-lightspeed", timeout=200)
        print(result.stdout, end="")
        if result.returncode != 0:
            print(result.stderr, end="")
            print("[before_scenario] Warning: full pod restart failed")
        else:
            print("[before_scenario] Pod restart + port-forward re-established")
    except subprocess.TimeoutExpired:
        print("[before_scenario] Warning: full pod restart timed out")


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Run before each scenario is run.

    Prepare scenario execution by skipping scenarios based on tags and
    resetting per-scenario Lightspeed override tracking and skip-restart flags.

    Skips the scenario if it has the `skip` tag, if it has the `local` tag
    while the test run is not in local mode, if it has `skip-in-library-mode`
    when running in library mode, or if it has `skip-in-server-mode` when running
    in server mode. Scenario-specific Lightspeed YAML is applied in the feature
    files (``The service uses the ... configuration`` steps).
    """
    if "skip" in scenario.effective_tags:
        scenario.skip("Marked with @skip")
        return
    if "local" in scenario.effective_tags and not context.local:
        scenario.skip("Marked with @local")
        return

    # Skip scenarios that require separate OGX container in library mode
    if context.is_library_mode and "skip-in-library-mode" in scenario.effective_tags:
        scenario.skip("Skipped in library mode (no separate llama-stack container)")
        return

    # Skip scenarios that rely on a non-default BYOK store. Only library mode
    # re-enriches the (in-process) OGX with the active config's byok_rag
    # on restart; in server mode the external OGX keeps its startup
    # config, so a feature-specific store would not be loaded.
    if not context.is_library_mode and "skip-in-server-mode" in scenario.effective_tags:
        scenario.skip(
            "Skipped in server mode (feature-specific BYOK store is not loaded "
            "into the external llama-stack)"
        )
        return

    # Skip scenarios that depend on services not deployed in Prow/OpenShift
    # (e.g. mock-tls-inference, proxy sidecars only available in Docker Compose)
    if is_prow_environment() and "skip-in-prow" in scenario.effective_tags:
        scenario.skip("Skipped in Prow (requires Docker Compose services)")
        return

    # In Prow, verify the lightspeed port-forward is alive before each scenario.
    # Port-forwards can silently die between scenarios (e.g. pod restart, TCP reset).
    if is_prow_environment():
        _ensure_prow_port_forward(context)

    context.scenario_lightspeed_override_active = False
    context.lightspeed_stack_skip_restart = False
    # Reset force-restart from a prior disrupt/MCP reset scenario.
    context.force_lightspeed_restart_after_mcp_config_reset = False

    # Clear shield unregister state from previous scenarios (see ``shields_are_disabled_for_scenario``).
    for _attr in (
        "shields_disabled_for_scenario",
        "llama_guard_provider_id",
        "llama_guard_provider_shield_id",
    ):
        if hasattr(context, _attr):
            delattr(context, _attr)


def _dump_pod_logs_on_failure(
    context: Context, scenario: Scenario, namespace: str
) -> None:
    """Dump container logs when a scenario fails in Prow."""
    if scenario.status != "failed":
        return
    pods: tuple[str, ...] = ("llama-stack-service", "lightspeed-stack-service")
    feature = getattr(context, "feature", None)
    feat_file = getattr(feature, "filename", "") or "" if feature else ""
    if is_tls_feature_file(feat_file):
        pods = (*pods, "e2e-mock-tls-inference")
    print(f"--- scenario failed: {scenario.name!r} — pod logs ---", flush=True)
    for pod in pods:
        try:
            result = run_e2e_ops("dump-pod-logs", [pod, "150"], timeout=90)
            print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="")
        except subprocess.TimeoutExpired:
            print(f"(timed out fetching logs for {pod})")


def after_scenario(context: Context, scenario: Scenario) -> None:
    """Run after each scenario is run.

    Perform per-scenario teardown: failure logs (Prow) and shield re-register.

    If ``configure_service`` applied a non-baseline YAML during the scenario
    (``context.scenario_lightspeed_override_active``), clears that flag only;
    the next ``The service uses ...`` step re-applies config as needed.

    Parameters:
    ----------
        context (Context): Behave test context. Expected attributes used here include:
            - feature_config: path to the feature-level configuration to restore.
            - scenario_lightspeed_override_active: set by ``configure_service``
              when a scenario switches YAML after Background.
            - is_library_mode (bool): whether tests run in library mode.
            - llama_stack_was_running (bool, optional): whether OGX was
              running before the scenario.
            - hostname_llama, port_llama (str/int, optional): host and port
              used for the OGX health check.
        scenario (Scenario): Behave scenario (unused; shield restore uses context flags).
    """
    if is_prow_environment():
        _dump_pod_logs_on_failure(
            context, scenario, os.environ.get("NAMESPACE", "e2e-rhoai-dsc")
        )

    if getattr(context, "scenario_lightspeed_override_active", False):
        context.scenario_lightspeed_override_active = False

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
            except (TypeError, ValueError, RuntimeError, KeyboardInterrupt) as e:
                print(f"Warning: Could not re-register shield: {e}")

    # Restart OKP server if it was stopped during the scenario
    # (only in local/Docker mode - OpenShift manages containers differently)
    if getattr(context, "okp_was_running", False) and not is_prow_environment():
        from tests.e2e.features.steps.okp_rag import (
            OKP_DEFAULT_URL,
            OKP_IMAGE_NAME,
        )

        container_name = getattr(context, "okp_container_name", None)
        if container_name:
            # Check if container still exists (may be auto-removed if started with --rm)
            check_result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True,
                check=False,
            )

            if check_result.returncode != 0:
                # Container was removed (likely started with --rm flag) - recreate it
                print(
                    f"OKP container '{container_name}' was removed, recreating from {OKP_IMAGE_NAME}..."
                )
                try:
                    subprocess.run(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "-d",
                            "-p",
                            "8081:8080",
                            OKP_IMAGE_NAME,
                        ],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    print(f"Warning: Could not recreate OKP container: {e}")
                    if e.stderr:
                        print(f"  Error: {e.stderr}")
            else:
                # Container exists - just start it
                try:
                    subprocess.run(
                        ["docker", "start", container_name],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as e:
                    print(
                        f"Warning: Could not start OKP container '{container_name}': {e}"
                    )
                    if e.stderr:
                        print(f"  Error: {e.stderr}")

            # Wait for the server to be ready
            max_attempts = 30
            for attempt in range(max_attempts):
                try:
                    resp = requests.get(OKP_DEFAULT_URL, timeout=5)
                    if resp.status_code < 500:
                        print("✓ OKP server restarted successfully")
                        break
                except requests.ConnectionError:
                    if attempt < max_attempts - 1:
                        time.sleep(1)
                    else:
                        print(
                            "Warning: OKP server may not be fully ready after restart"
                        )


def _print_llama_stack_diagnostics() -> None:
    """Print container state, health, and recent logs to diagnose why OGX did not recover."""
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


def _restore_llama_stack() -> None:
    """Restore OGX connection after disruption."""
    if is_prow_environment():
        # Recreate llama pod, then restart LCS so in-process clients reconnect (Llama IP/pod changed).
        try:
            restore_llama_stack_pod()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Warning: Could not restore OGX pod on Prow: {e}")
            return
        last_lcs_err: Optional[
            subprocess.CalledProcessError | subprocess.TimeoutExpired
        ] = None
        for attempt in range(1, 4):
            try:
                restart_pod("lightspeed-stack")
                print(
                    "✓ Prow: OGX restored and lightspeed-stack restarted "
                    "for clean reconnect"
                )
                reset_llama_stack_disrupt_once_tracking()
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                last_lcs_err = e
                print(
                    f"Warning: lightspeed-stack restart after OGX restore "
                    f"attempt {attempt}/3 failed: {e}"
                )
                if attempt < 3:
                    time.sleep(5)
        print(
            "Warning: Could not restart lightspeed-stack after OGX restore "
            f"after 3 attempts: {last_lcs_err}"
        )
        return

    try:
        # Start the OGX container again
        subprocess.run(
            ["docker", "start", "llama-stack"], check=True, capture_output=True
        )

        # Wait for the service to be healthy
        print("Restoring OGX connection...")
        max_attempts = 60
        for attempt in range(max_attempts):
            try:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "llama-stack",
                        "curl",
                        "-sf",
                        f"http://{get_llama_stack_hostname()}:{get_llama_stack_port()}/v1/health",
                    ],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    print("✓ OGX connection restored successfully")
                    reset_llama_stack_disrupt_once_tracking()
                    break
            except subprocess.TimeoutExpired:
                print(
                    f"⏱ Health check timed out on attempt {attempt + 1}/{max_attempts}"
                )

            if attempt < max_attempts - 1:
                print(
                    f"Waiting for OGX to be healthy... "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )
                time.sleep(2)
            else:
                print("Warning: OGX may not be fully healthy after restoration")
                _print_llama_stack_diagnostics()

    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not restore OGX connection: {e}")
        if e.stderr:
            print(f"  docker start stderr: {e.stderr}")
        if e.stdout:
            print(f"  docker start stdout: {e.stdout}")
        _print_llama_stack_diagnostics()


def before_feature(context: Context, feature: Feature) -> None:
    """Run before each feature file is exercised.

    Per-feature setup that is not expressed in Gherkin.
    Lightspeed YAML is applied in feature Backgrounds via ``configure_service``.

    Does not reset the applied-config basename tracker (skip-restart across features).

    Records monotonic start time on ``feature`` for duration logging in
    ``after_feature`` (includes scenarios and feature teardown).

    Scenarios tagged ``@flaky`` are patched to retry the full scenario up to
    ``max_attempts`` times before accepting failure. The cap defaults to
    ``_E2E_FLAKY_MAX_ATTEMPTS`` and can be overridden with the
    ``E2E_FLAKY_MAX_ATTEMPTS`` environment variable.
    """
    setattr(feature, _E2E_FEATURE_PERF_START_ATTR, time.perf_counter())
    context.feature_config = None
    context.scenario_lightspeed_override_active = False
    context.active_lightspeed_stack_config_basename = None
    # One real Llama disruption per feature (module-level flag; survives context resets)
    reset_llama_stack_disrupt_once_tracking()
    if feature.filename and is_tls_feature_file(feature.filename):
        reset_tls_prow_state()
        prepare_tls_feature_entry_on_prow(feature.filename)

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


def _restore_config_after_feature_enabled() -> bool:
    """Return True when legacy per-feature bootstrap restore/restart is requested."""
    return os.getenv("E2E_RESTORE_CONFIG_AFTER_FEATURE", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def after_feature(context: Context, feature: Feature) -> None:
    """Run after each feature file is exercised.

    Perform feature-level teardown: restore bootstrap configuration when
    ``E2E_RESTORE_CONFIG_AFTER_FEATURE=1``, otherwise keep the active config;
    when ``context.feedback_e2e_conversation_cleanup`` is set by feedback steps,
    delete tracked feedback test conversations.
    """
    # Restore OGX FIRST (before any lightspeed-stack restart).
    # Read from module-level state — Behave clears custom context attributes
    # between scenarios, so context.llama_stack_was_running is unreliable here.
    if get_llama_stack_was_running():
        _restore_llama_stack()
        reset_llama_stack_was_running()

    if getattr(context, "feedback_e2e_conversation_cleanup", False):
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6Ikpva"
        for conversation_id in getattr(context, "feedback_conversations", []):
            url = f"http://{context.hostname}:{context.port}/v1/conversations/{conversation_id}"
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.delete(url, headers=headers, timeout=10)
            assert response.status_code == 200, f"{url} returned {response.status_code}"

    # Restore Lightspeed Stack config if the generic configure_service step switched it.
    # This cleanup intentionally runs for any feature (not tag-gated) - any feature that
    # leaves a backup file will trigger config restoration and container restarts when
    # E2E_RESTORE_CONFIG_AFTER_FEATURE=1; otherwise the backup is dropped only.
    backup_path = "lightspeed-stack.yaml.backup"
    if os.path.exists(backup_path):
        if _restore_config_after_feature_enabled():
            switch_config(backup_path)
            remove_config_backup(backup_path)
            if not context.is_library_mode:
                restart_container("llama-stack")
            restart_container("lightspeed-stack")
            reset_active_lightspeed_stack_config_basename()
        else:
            remove_config_backup(backup_path)

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
# Disable capture so feature timing and failure diagnostics appear in the main CI log.
after_feature.capture = False  # type: ignore[attr-defined]
after_scenario.capture = False  # type: ignore[attr-defined]
