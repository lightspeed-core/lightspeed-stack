"""Code to be called before and after certain events during testing.

Currently four events have been registered:
1. before_all
2. before_feature
3. before_scenario
4. after_scenario
"""

import os
import requests
import subprocess
import time
import json
from behave.model import Scenario, Feature
from behave.runner import Context

from tests.e2e.utils.utils import (
    switch_config,
    restart_container,
    remove_config_backup,
    create_config_backup,
)

try:
    import os  # noqa: F401
except ImportError as e:
    print("Warning: unable to import module:", e)

from tests.unit.authentication.test_jwk_token import create_jwks_keys, make_key


def before_all(context: Context) -> None:
    """Run before and after the whole shooting match."""


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Run before each scenario is run."""
    if "skip" in scenario.effective_tags:
        scenario.skip("Marked with @skip")
        return
    if "local" in scenario.effective_tags and not context.local:
        scenario.skip("Marked with @local")
        return
    if "InvalidFeedbackStorageConfig" in scenario.effective_tags:
        context.scenario_config = (
            "tests/e2e/configuration/lightspeed-stack-invalid-feedback-storage.yaml"
        )


def after_scenario(context: Context, scenario: Scenario) -> None:
    """Run after each scenario is run."""
    if "InvalidFeedbackStorageConfig" in scenario.effective_tags:
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    # Restore Llama Stack connection if it was disrupted
    if hasattr(context, "llama_stack_was_running") and context.llama_stack_was_running:
        try:
            # Start the llama-stack container again
            subprocess.run(
                [os.getenv("CONTAINER_CMD", "docker"), "start", "llama-stack"],
            )

            # Wait for the service to be healthy
            print("Restoring Llama Stack connection...")
            time.sleep(5)

            # Check if it's healthy
            for attempt in range(6):  # Try for 30 seconds
                try:
                    result = subprocess.run(
                        [
                            os.getenv("CONTAINER_CMD", "docker"),
                            "exec",
                            "llama-stack",
                            "curl",
                            "-f",
                            "http://localhost:8321/v1/health",
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
        context.feature_config = (
            "tests/e2e/configuration/lightspeed-stack-auth-noop-token.yaml"
        )
        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config(context.feature_config)
        restart_container("lightspeed-stack")

    elif "JWKAuth" in feature.tags:
        context.feature_config = (
            "tests/e2e/configuration/lightspeed-stack-auth-jwk.yaml"
        )
        with open("tests/e2e/configuration/test_jwk/jwk.json", "w") as f:
            context.test_key = make_key()
            keys = create_jwks_keys([context.test_key], ["RS256"])
            f.write(json.dumps(keys))

        context.default_config_backup = create_config_backup("lightspeed-stack.yaml")
        switch_config("tests/e2e/configuration/lightspeed-stack-auth-jwk.yaml")
        restart_container("lightspeed-stack")

    if "Feedback" in feature.tags:
        context.feedback_conversations = []


def after_feature(context: Context, feature: Feature) -> None:
    """Run after each feature file is exercised."""
    if "Authorized" in feature.tags or "JWKAuth" in feature.tags:
        switch_config(context.default_config_backup)
        restart_container("lightspeed-stack")
        remove_config_backup(context.default_config_backup)

    if "Feedback" in feature.tags:
        print(context.feedback_conversations)
        for conversation_id in context.feedback_conversations:
            url = f"http://localhost:8080/v1/conversations/{conversation_id}"
            headers = context.auth_headers if hasattr(context, "auth_headers") else {}
            response = requests.delete(url, headers=headers)
            assert response.status_code == 200, url
