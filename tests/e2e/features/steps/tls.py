"""Step definitions for TLS configuration e2e tests.

These tests configure Llama Stack's run.yaml with NetworkConfig TLS settings
and verify the full pipeline works through the Lightspeed Stack.

Config switching uses the same pattern as other e2e tests: overwrite the
host-mounted run.yaml and restart Docker containers. Cleanup is handled
by a Background step that restores the backup before each scenario.
"""

import copy
import os
from typing import Any, Optional

from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.llama_config_utils import (
    backup_llama_config,
    clear_llama_config_backup,
    load_llama_config,
    reset_llama_run_config_to_pipeline_default,
    write_llama_config,
)
from tests.e2e.utils.prow_utils import get_namespace, restart_pod, run_e2e_ops
from tests.e2e.utils.utils import is_prow_environment

_MOCK_TLS_PORT_TLS = 8443
_MOCK_TLS_PORT_MTLS = 8444
_MOCK_TLS_PORT_HOSTNAME_MISMATCH = 8445

_TLS_MODEL_RESOURCE: dict[str, str] = {
    "model_id": "mock-tls-model",
    "provider_id": "tls-openai",
    "provider_model_id": "mock-tls-model",
}


def reset_tls_prow_state() -> None:
    """Reset per-feature TLS test state (call from ``before_feature``)."""
    os.environ.pop("E2E_COPY_MOCK_TLS_CERTS_TO_LLAMA", None)
    os.environ.pop("E2E_SYNC_MOCK_TLS_CERTS", None)
    os.environ.pop("E2E_MOCK_TLS_INFERENCE_HOST", None)
    clear_llama_config_backup()


def is_tls_feature_file(feature_filename: Optional[str]) -> bool:
    """Return True for split TLS feature files (``tls-ca.feature``, etc.)."""
    if not feature_filename:
        return False
    basename = os.path.basename(feature_filename)
    return basename.startswith("tls-") and basename.endswith(".feature")


def prepare_tls_feature_entry_on_prow(feature_filename: Optional[str] = None) -> None:
    """Baseline cluster state at the start of each tls-*.feature file.

    Mock TLS stays up for the whole tls suite (tls-ca → tls-mtls → tls-tlsv13).
    Certs are synced to the Secret only when the mock pod is first deployed
    (``deploy-e2e-mock-tls-inference``). Per-scenario TLS cases change which
    ``/certs/*`` path Llama uses via run.yaml, not the Secret contents.
    """
    if not is_prow_environment():
        return
    label = os.path.basename(feature_filename or "tls.feature")
    print(
        f"[{label}] Prow/Konflux entry: ensure mock TLS, reset run.yaml, warm Llama..."
    )
    reset_llama_run_config_to_pipeline_default()
    _ensure_cluster_mock_tls_inference()
    _prepare_tls_prow_llama_restart_env()
    os.environ.pop("E2E_SYNC_MOCK_TLS_CERTS", None)
    restart_pod("llama-stack")
    print(f"[{label}] Prow/Konflux entry baseline complete", flush=True)


def is_tls_configuration_feature(context: Context) -> bool:
    """Return True when the active Behave feature is a tls-*.feature file."""
    feature = getattr(context, "feature", None)
    if feature is None:
        return False
    filename = getattr(feature, "filename", None)
    if is_tls_feature_file(filename):
        return True
    name = getattr(feature, "name", "") or ""
    return "TLS configuration" in name


def _prepare_tls_prow_llama_restart_env() -> None:
    """Set env for full llama pod recreate with mock TLS certs mounted."""
    os.environ["E2E_COPY_MOCK_TLS_CERTS_TO_LLAMA"] = "1"


def _restart_lightspeed_after_llama_tls(context: Context) -> None:
    """Restart LCS after Llama recreate so the in-process Llama client reconnects.

    TLS scenarios only change Llama run.yaml; LCS yaml is unchanged. Without this,
    queries through LCS often fail with 503/connection errors after Llama pod
    recreate on Prow (stale HTTP connections).
    """
    from tests.e2e.utils.utils import (
        restart_container,
        wait_for_lightspeed_stack_http_ready,
    )

    scenario = getattr(getattr(context, "scenario", None), "name", "") or "?"
    feature_file = os.path.basename(
        getattr(getattr(context, "feature", None), "filename", "") or "tls.feature"
    )
    print(
        f"[{feature_file}] Lightspeed Stack refresh after Llama recreate "
        f"scenario={scenario!r}",
        flush=True,
    )
    restart_container("lightspeed-stack")
    wait_for_lightspeed_stack_http_ready()


def restart_llama_for_tls_feature(context: Context) -> None:
    """Restart Llama for TLS tests (full pod recreate on Prow/Konflux)."""
    from tests.e2e.utils.utils import restart_container

    if is_prow_environment():
        _prepare_tls_prow_llama_restart_env()
        os.environ.pop("E2E_SYNC_MOCK_TLS_CERTS", None)
    scenario = getattr(getattr(context, "scenario", None), "name", "") or "?"
    feature_file = os.path.basename(
        getattr(getattr(context, "feature", None), "filename", "") or "tls.feature"
    )
    print(
        f"[{feature_file}] Llama Stack restart: full recreate scenario={scenario!r}",
        flush=True,
    )
    restart_container("llama-stack")


def _cluster_mock_tls_inference_host() -> str:
    """DNS name of the in-cluster mock TLS inference server (Konflux / Prow)."""
    explicit = os.getenv("E2E_MOCK_TLS_INFERENCE_HOST", "").strip()
    if explicit:
        return explicit
    return f"e2e-mock-tls-inference.{get_namespace()}.svc.cluster.local"


def _mock_tls_base_url(port: int) -> str:
    """OpenAI-compatible base URL for the mock TLS inference server."""
    if is_prow_environment():
        host = _cluster_mock_tls_inference_host()
    else:
        host = "mock-tls-inference"
    return f"https://{host}:{port}/v1"


def _tls_provider_base() -> dict[str, Any]:
    """Tls-openai provider dict with environment-appropriate base_url."""
    return {
        "provider_id": "tls-openai",
        "provider_type": "remote::openai",
        "config": {
            "api_key": "test-key",
            "base_url": _mock_tls_base_url(_MOCK_TLS_PORT_TLS),
            "allowed_models": ["mock-tls-model"],
            "refresh_models": False,
        },
    }


def _mock_tls_inference_pod_ready() -> bool:
    """Return True when the in-cluster mock TLS pod exists and is Ready."""
    result = run_e2e_ops("wait-for-pod", ["e2e-mock-tls-inference", "1"], timeout=45)
    return result.returncode == 0


def _ensure_cluster_mock_tls_inference() -> None:
    """Deploy mock TLS on Prow if missing; keep one pod for the whole tls suite.

    ``deploy-e2e-mock-tls-inference`` copies all PEMs into Secret ``e2e-mock-tls-certs``
    once. Scenarios only change which cert path Llama uses in run.yaml.
    """
    if _mock_tls_inference_pod_ready():
        print("Using existing e2e-mock-tls-inference deployment")
        os.environ.setdefault(
            "E2E_MOCK_TLS_INFERENCE_HOST",
            _cluster_mock_tls_inference_host(),
        )
        return

    result = run_e2e_ops("deploy-e2e-mock-tls-inference", timeout=300)
    print(result.stdout, end="")
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to deploy e2e-mock-tls-inference: "
            f"{result.stderr or result.stdout}"
        )
    os.environ.setdefault(
        "E2E_MOCK_TLS_INFERENCE_HOST",
        _cluster_mock_tls_inference_host(),
    )


def _ensure_tls_provider(config: dict[str, Any]) -> dict[str, Any]:
    """Find or create the tls-openai inference provider in the config.

    If the provider does not exist, it is added along with the
    mock-tls-model registered resource.

    Parameters:
    ----------
        config: The Llama Stack configuration dictionary.

    Returns:
    -------
        The tls-openai provider configuration dictionary.
    """
    providers = config.setdefault("providers", {})
    inference = providers.setdefault("inference", [])

    for provider in inference:
        if provider.get("provider_id") == "tls-openai":
            return provider

    # Provider not found — add it
    provider = copy.deepcopy(_tls_provider_base())
    inference.append(provider)

    # Also register the model resource
    resources = config.setdefault("registered_resources", {})
    models = resources.setdefault("models", [])
    if not any(m.get("model_id") == "mock-tls-model" for m in models):
        models.append(copy.deepcopy(_TLS_MODEL_RESOURCE))

    return provider


def _configure_tls(tls_config: dict[str, Any], base_url: Optional[str] = None) -> None:
    """Configure TLS settings for the tls-openai provider.

    Parameters:
    ----------
        tls_config: The TLS configuration dictionary.
        base_url: Optional base URL override for the provider.
    """
    backup_llama_config()
    config = load_llama_config()
    provider = _ensure_tls_provider(config)
    provider.setdefault("config", {}).setdefault("network", {})
    if base_url is not None:
        provider["config"]["base_url"] = base_url
    else:
        provider["config"]["base_url"] = _mock_tls_base_url(_MOCK_TLS_PORT_TLS)
    provider.setdefault("config", {})["refresh_models"] = False
    provider["config"]["network"]["tls"] = tls_config
    write_llama_config(config)
    if is_prow_environment():
        _prepare_tls_prow_llama_restart_env()


# --- Background Steps ---
# ``The original Llama Stack config is restored if modified`` only restores
# run.yaml (see proxy.py). Restart steps are listed in tls-*.feature / proxy.feature.


@given("The mock TLS inference server is deployed")
def deploy_mock_tls_inference_server(context: Context) -> None:
    """Ensure mock TLS inference is reachable (Compose locally, pod in Prow)."""
    if is_prow_environment():
        _ensure_cluster_mock_tls_inference()
        return
    print("Using docker-compose mock-tls-inference service")


# --- TLS Configuration Steps ---


@given("Llama Stack is configured with TLS verification disabled")
def configure_tls_verify_false(context: Context) -> None:
    """Configure run.yaml with TLS verify: false."""
    _configure_tls({"verify": False})


@given("Llama Stack is configured with CA certificate verification")
def configure_tls_verify_ca(context: Context) -> None:
    """Configure run.yaml with TLS verify: /certs/ca.crt."""
    _configure_tls({"verify": "/certs/ca.crt", "min_version": "TLSv1.2"})


@given("Llama Stack is configured with TLS verification enabled")
def configure_tls_verify_true(context: Context) -> None:
    """Configure run.yaml with TLS verify: true (fails with self-signed certs)."""
    _configure_tls({"verify": True})


@given("Llama Stack is configured with mutual TLS authentication")
def configure_tls_mtls(context: Context) -> None:
    """Configure run.yaml with mutual TLS (client cert and key)."""
    _configure_tls(
        {
            "verify": "/certs/ca.crt",
            "min_version": "TLSv1.2",
            "client_cert": "/certs/client.crt",
            "client_key": "/certs/client.key",
        },
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_MTLS),
    )


@given("Llama Stack is configured for mTLS without client certificate")
def configure_tls_mtls_no_client_cert(context: Context) -> None:
    """Configure run.yaml for mTLS port without client cert (should fail)."""
    _configure_tls(
        {"verify": "/certs/ca.crt"},
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_MTLS),
    )


@given("Llama Stack is configured for mTLS with wrong client certificate")
def configure_tls_mtls_wrong_client_cert(context: Context) -> None:
    """Configure run.yaml for mTLS with invalid client cert (CA cert as client cert)."""
    _configure_tls(
        {
            "verify": "/certs/ca.crt",
            "client_cert": "/certs/ca.crt",
            "client_key": "/certs/client.key",
        },
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_MTLS),
    )


@given("Llama Stack is configured for mTLS with untrusted client certificate")
def configure_tls_mtls_untrusted_client_cert(context: Context) -> None:
    """Configure run.yaml with untrusted client certificate."""
    _configure_tls(
        {
            "verify": "/certs/ca.crt",
            "min_version": "TLSv1.2",
            "client_cert": "/certs/untrusted-client.crt",
            "client_key": "/certs/untrusted-client.key",
        },
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_MTLS),
    )


@given("Llama Stack is configured for mTLS with expired client certificate")
def configure_tls_mtls_expired_client_cert(context: Context) -> None:
    """Configure run.yaml with expired client certificate."""
    _configure_tls(
        {
            "verify": "/certs/ca.crt",
            "min_version": "TLSv1.2",
            "client_cert": "/certs/expired-client.crt",
            "client_key": "/certs/client.key",
        },
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_MTLS),
    )


@given("Llama Stack is configured with CA certificate and hostname mismatch server")
def configure_tls_ca_hostname_mismatch(context: Context) -> None:
    """Configure run.yaml to connect to hostname-mismatch server (should fail)."""
    _configure_tls(
        {"verify": "/certs/ca.crt"},
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_HOSTNAME_MISMATCH),
    )


@given("Llama Stack is configured with mutual TLS and hostname mismatch server")
def configure_tls_mtls_hostname_mismatch(context: Context) -> None:
    """Configure run.yaml with mTLS against hostname-mismatch server."""
    _configure_tls(
        {
            "verify": "/certs/ca.crt",
            "min_version": "TLSv1.2",
            "client_cert": "/certs/client.crt",
            "client_key": "/certs/client.key",
        },
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_HOSTNAME_MISMATCH),
    )


@given('Llama Stack is configured with CA certificate path "{path}"')
def configure_tls_ca_path(context: Context, path: str) -> None:
    """Configure run.yaml with TLS verify pointing to a specific CA cert path."""
    _configure_tls({"verify": path})


@given(
    'Llama Stack is configured with TLS minimum version "{version}" and CA certificate path "{path}"'
)
def configure_tls_min_version_and_ca(context: Context, version: str, path: str) -> None:
    """Configure run.yaml with TLS minimum version and a specific CA cert path."""
    _configure_tls({"verify": path, "min_version": version})


@given(
    'Llama Stack is configured with TLS minimum version "{version}" and hostname mismatch server'
)
def configure_tls_min_version_hostname_mismatch(context: Context, version: str) -> None:
    """Configure run.yaml with TLS min version against hostname-mismatch server."""
    _configure_tls(
        {"verify": "/certs/ca.crt", "min_version": version},
        base_url=_mock_tls_base_url(_MOCK_TLS_PORT_HOSTNAME_MISMATCH),
    )
