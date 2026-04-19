"""Behave steps for temporarily disabling Llama Stack shields in e2e (server mode)."""

from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.llama_stack_utils import unregister_shield


@given("shields are disabled for this scenario")
def shields_are_disabled_for_scenario(context: Context) -> None:
    """Unregister ``llama-guard`` for this scenario; ``after_scenario`` restores it when possible.

    Sets ``context.shields_disabled_for_scenario`` so ``environment.after_scenario``
    re-registers the shield. **Server mode only**; in library mode the scenario is skipped
    (no separate Llama Stack to call).

    Parameters:
    ----------
        context: Behave context; must expose ``is_library_mode`` and ``scenario``.
    """
    if context.is_library_mode:
        context.scenario.skip(
            "Shield unregister/register only applies in server mode (Llama Stack as a "
            "separate service). In library mode the app's shields cannot be disabled from e2e."
        )
        return

    try:
        saved = unregister_shield("llama-guard")
        context.llama_guard_provider_id = saved[0] if saved else None
        context.llama_guard_provider_shield_id = saved[1] if saved else None
        context.shields_disabled_for_scenario = True
        print("Unregistered shield llama-guard for this scenario")
    except Exception as e:  # pylint: disable=broad-exception-caught
        context.scenario.skip(
            f"Could not unregister shield (is Llama Stack reachable?): {e}"
        )
