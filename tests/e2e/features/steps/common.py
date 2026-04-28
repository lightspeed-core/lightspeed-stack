"""Implementation of common test steps."""

import os
from typing import Optional

from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.llama_stack_utils import unregister_mcp_toolgroups
from tests.e2e.utils.utils import (
    absolute_repo_path,
    clear_llama_stack_storage,
    create_config_backup,
    is_prow_environment,
    restart_container,
    switch_config,
)

# Behave may clear user attributes on ``context`` between scenarios; keep the
# last applied config basename here so Background can skip re-applying the same
# YAML across scenarios in one feature. Mutate the dict entry (no global).
_active_lightspeed_stack_config_basename: dict[str, Optional[str]] = {"basename": None}

# Behave clears user attributes on ``context`` between scenarios; store
# Llama Stack endpoint info at module level so ``after_feature`` can see it.
_llama_stack_endpoint: dict[str, str] = {"hostname": "localhost", "port": "8321"}


def reset_active_lightspeed_stack_config_basename() -> None:
    """Reset before each feature; see ``environment.before_feature``."""
    _active_lightspeed_stack_config_basename["basename"] = None


def get_llama_stack_hostname() -> str:
    """Return the Llama Stack hostname surviving per-scenario context clearing."""
    return _llama_stack_endpoint["hostname"]


def get_llama_stack_port() -> str:
    """Return the Llama Stack port surviving per-scenario context clearing."""
    return _llama_stack_endpoint["port"]


@given("The service is started locally")
def service_is_started_locally(context: Context) -> None:
    """Check the service status.

    Populate the Behave context with local service endpoint values read from
    environment variables.

    Parameters:
    ----------
        context (Context): Behave context object to receive the endpoint attributes.
    """
    assert context is not None
    context.hostname = os.getenv("E2E_LSC_HOSTNAME", "localhost")
    context.port = os.getenv("E2E_LSC_PORT", "8080")
    if is_prow_environment():
        context.hostname_llama = os.getenv("E2E_LLAMA_HOSTNAME", "localhost")
    else:
        context.hostname_llama = "localhost"
    context.port_llama = os.getenv("E2E_LLAMA_PORT", "8321")
    _llama_stack_endpoint["hostname"] = context.hostname_llama
    _llama_stack_endpoint["port"] = context.port_llama


@given('the Lightspeed stack configuration directory is "{directory}"')
def set_lightspeed_stack_config_directory(context: Context, directory: str) -> None:
    """Store the repo-relative config folder for ``The service uses the ... configuration``.

    ``configure_service`` joins this path with either
    ``<server-mode|library-mode>/<file>`` when those subdirs exist under ``directory``,
    or ``<file>`` alone for a flat directory (local Docker and Prow).

    Parameters:
        context: Behave context; sets ``lightspeed_stack_config_directory``.
        directory: Path relative to the repository root (e.g. ``tests/e2e/configuration``).
    """
    context.lightspeed_stack_config_directory = directory.strip().rstrip("/")


@given("The service uses the {config_name} configuration")  # type: ignore
def configure_service(context: Context, config_name: str) -> None:
    """Switch to the given configuration when the basename differs from the last apply.

    If ``config_name`` matches the last applied basename (tracked in module
    state, not only ``context``, so it survives per-scenario context resets),
    returns immediately: no backup, no copy, and sets
    ``context.lightspeed_stack_skip_restart`` so the next ``The service is
    restarted`` step can no-op—except after ``MCP toolgroups are reset for a new
    MCP configuration`` (library ``~/.llama`` clear or server-mode unregister),
    in which case the restart is not skipped so Lightspeed reloads config and
    Llama MCP state stays consistent. When the basename differs from the last apply, creates the
    backup on first use,
    copies the YAML, updates ``context.feature_config`` / override flags, and
    stores the basename for the next check. Cleared in ``before_feature`` so a
    new feature file always applies at least once.

    Build path from ``lightspeed_stack_config_directory`` (directory step),
    defaulting base to ``tests/e2e/configuration`` if that step was omitted; then
    ``server-mode`` / ``library-mode`` subdir when present, else flat. On Prow the
    resolved path is made absolute from the repo root so ``switch_config`` works
    regardless of cwd.

    Parameters:
    ----------
        context (Context): Behave context.
        config_name (str): Config filename (e.g. lightspeed-stack-inline-rag.yaml).
    """
    config_name = config_name.strip()
    if _active_lightspeed_stack_config_basename["basename"] == config_name:
        # ``MCP toolgroups are reset for a new MCP configuration`` may have run
        # (library: clear ``~/.llama``; server: unregister toolgroups). The next
        # restart must not be skipped or SQLite handles / MCP registration state
        # diverges from the running process.
        if getattr(
            context, "force_lightspeed_restart_after_mcp_toolgroup_reset", False
        ):
            context.lightspeed_stack_skip_restart = False
            context.force_lightspeed_restart_after_mcp_toolgroup_reset = False
        else:
            context.lightspeed_stack_skip_restart = True
        return

    had_backup_before = os.path.exists("lightspeed-stack.yaml.backup")

    mode_dir = "library-mode" if context.is_library_mode else "server-mode"
    raw_base = getattr(context, "lightspeed_stack_config_directory", None)
    if raw_base and str(raw_base).strip():
        base = str(raw_base).strip().rstrip("/")
    else:
        base = "tests/e2e/configuration"
    mode_base = os.path.join(base, mode_dir)
    if is_prow_environment():
        mode_base = absolute_repo_path(mode_base)
        base = absolute_repo_path(base)
    if os.path.isdir(mode_base):
        config_path = os.path.join(mode_base, config_name)
    else:
        config_path = os.path.join(base, config_name)

    normalized = (
        os.path.normpath(config_path)
        if is_prow_environment()
        else os.path.normpath(os.path.abspath(config_path))
    )

    create_config_backup("lightspeed-stack.yaml")
    switch_config(config_path)

    if not had_backup_before:
        context.feature_config = normalized
    else:
        baseline = getattr(context, "feature_config", None)
        baseline_norm = os.path.normpath(baseline) if baseline is not None else None
        if baseline_norm != normalized:
            context.scenario_lightspeed_override_active = True

    _active_lightspeed_stack_config_basename["basename"] = config_name
    context.active_lightspeed_stack_config_basename = config_name
    context.lightspeed_stack_skip_restart = False
    context.force_lightspeed_restart_after_mcp_toolgroup_reset = False


@given("MCP toolgroups are reset for a new MCP configuration")
def reset_mcp_toolgroups_for_new_configuration(context: Context) -> None:
    """Clear MCP toolgroups on Llama Stack (server) or ~/.llama storage (library).

    Run before applying a different MCP-related ``lightspeed-stack-*.yaml`` in a
    scenario so tool registration matches the new config. Sets
    ``force_lightspeed_restart_after_mcp_toolgroup_reset`` so the next
    ``The service uses ...`` step cannot skip ``The service is restarted`` when
    the YAML basename is unchanged—library mode needs a real restart after
    clearing ``~/.llama`` (SQLite); server mode needs it after unregister so
    Lightspeed re-registers MCP toolgroups on startup.
    """
    context.force_lightspeed_restart_after_mcp_toolgroup_reset = True
    context.lightspeed_stack_skip_restart = False
    if context.is_library_mode:
        clear_llama_stack_storage()
    else:
        unregister_mcp_toolgroups()


@given("The service is restarted")
def restart_service(context: Context) -> None:
    """Restart the lightspeed-stack container and wait for it to be healthy.

    If ``context.lightspeed_stack_skip_restart`` is True (set when the previous
    ``The service uses the ... configuration`` step did not change the active
    YAML), skips the restart and clears the flag.

    Parameters:
    ----------
        context (Context): Behave context.
    """
    if getattr(context, "lightspeed_stack_skip_restart", False):
        context.lightspeed_stack_skip_restart = False
        return
    restart_container("lightspeed-stack")


@given("The system is in default state")
def system_in_default_state(context: Context) -> None:
    """Check the default system state.

    Ensure the Behave test context is present for steps that assume the system
    is in its default state.

    Parameters:
    ----------
        context (Context): Behave Context instance used to store and share test state.

    Raises:
    ------
        AssertionError: If `context` is None.
    """
    assert context is not None
