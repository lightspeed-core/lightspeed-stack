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
from behave.runner import Context

from tests.e2e.utils.utils import (
    create_config_backup,
    remove_config_backup,
    restart_container,
    switch_config,
)


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
    """Run before and after the whole shooting match."""
    # Detect deployment mode from environment variable
    context.deployment_mode = os.getenv("E2E_DEPLOYMENT_MODE", "server").lower()
    context.is_library_mode = context.deployment_mode == "library"

    # Get first LLM model from running service
    print(f"Running tests in {context.deployment_mode} mode")

    llm_model = _fetch_models_from_service()

    if llm_model:
        context.default_model = llm_model["model_id"]
        context.default_provider = llm_model["provider_id"]
        print(
            f"Detected LLM: {context.default_model} (provider: {context.default_provider})"
        )
    else:
        # Fallback for development
        context.default_model = "gpt-4o-mini"
        context.default_provider = "openai"
        print(
            f"⚠ Could not detect models, using fallback: {context.default_provider}/{context.default_model}"
        )


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Run before each scenario is run."""
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

    mode_dir = "library-mode" if context.is_library_mode else "server-mode"

    if "InvalidFeedbackStorageConfig" in scenario.effective_tags:
        context.scenario_config = f"tests/e2e/configuration/{mode_dir}/lightspeed-stack-invalid-feedback-storage.yaml"
    if "NoCacheConfig" in scenario.effective_tags:
        context.scenario_config = (
            f"tests/e2e/configuration/{mode_dir}/lightspeed-stack-no-cache.yaml"
        )


def after_scenario(context: Context, scenario: Scenario) -> None:
    """Run after each scenario is run."""
    if "InvalidFeedbackStorageConfig" in scenario.effective_tags:
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")
    if "NoCacheConfig" in scenario.effective_tags:
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    # Restore Llama Stack connection if it was disrupted (only in server mode)
    if (
        not context.is_library_mode
        and hasattr(context, "llama_stack_was_running")
        and context.llama_stack_was_running
    ):
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
                    print(f"⏱Health check timed out on attempt {attempt + 1}/6")

                if attempt < 5:
                    print(
                        f"Waiting for Llama Stack to be healthy... (attempt {attempt + 1}/6)"
                    )
                    time.sleep(5)
                else:
                    print(
                        "Warning: Llama Stack may not be fully healthy after restoration"
                    )

        except subprocess.CalledProcessError as e:
            print(f"Warning: Could not restore Llama Stack connection: {e}")


def before_feature(context: Context, feature: Feature) -> None:
    """Run before each feature file is exercised."""
    if "Authorized" in feature.tags:
        mode_dir = "library-mode" if context.is_library_mode else "server-mode"
        context.feature_config = (
            f"tests/e2e/configuration/{mode_dir}/lightspeed-stack-auth-noop-token.yaml"
        )
        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    if "RlsapiConfig" in feature.tags:
        mode_dir = "library-mode" if context.is_library_mode else "server-mode"
        context.feature_config = (
            f"tests/e2e/configuration/{mode_dir}/lightspeed-stack-rlsapi.yaml"
        )
        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    if "Feedback" in feature.tags:
        context.hostname = os.getenv("E2E_LSC_HOSTNAME", "localhost")
        context.port = os.getenv("E2E_LSC_PORT", "8080")
        context.feedback_conversations = []


def after_feature(context: Context, feature: Feature) -> None:
    """Run after each feature file is exercised."""
    if "Authorized" in feature.tags:
        switch_config(context.default_config_backup)
        restart_container("lightspeed-stack")
        remove_config_backup(context.default_config_backup)

    if "RlsapiConfig" in feature.tags:
        switch_config(context.default_config_backup)
        restart_container("lightspeed-stack")
        remove_config_backup(context.default_config_backup)

    if "Feedback" in feature.tags:
        for conversation_id in context.feedback_conversations:
            url = f"http://{context.hostname}:{context.port}/v1/conversations/{conversation_id}"
            headers = context.auth_headers if hasattr(context, "auth_headers") else {}
            response = requests.delete(url, headers=headers)
            assert response.status_code == 200, url
