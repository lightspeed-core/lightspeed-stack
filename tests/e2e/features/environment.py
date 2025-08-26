"""Code to be called before and after certain events during testing.

Currently four events have been registered:
1. before_all
2. before_feature
3. before_scenario
4. after_scenario
"""

import subprocess
import time
from behave.model import Scenario
from behave.runner import Context

try:
    import os  # noqa: F401
except ImportError as e:
    print("Warning: unable to import module:", e)


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


def after_scenario(context: Context, scenario: Scenario) -> None:
    """Run after each scenario is run."""
    # Restore Llama Stack connection if it was disrupted
    if hasattr(context, "llama_stack_was_running") and context.llama_stack_was_running:
        try:
            # Start the llama-stack container again
            subprocess.run(
                ["docker", "start", "llama-stack"], check=True, capture_output=True
            )

            # Wait for the service to be healthy
            print("Restoring Llama Stack connection...")
            time.sleep(5)

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


def before_feature(context: Context, feature: Scenario) -> None:
    """Run before each feature file is exercised."""
