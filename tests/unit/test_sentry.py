"""Unit tests for functions defined in src/sentry.py."""

import pytest
from pytest_mock import MockerFixture

from constants import (
    SENTRY_CA_CERTS_ENV_VAR,
    SENTRY_DEFAULT_ENVIRONMENT,
    SENTRY_DEFAULT_TRACES_SAMPLE_RATE,
    SENTRY_DSN_ENV_VAR,
    SENTRY_ENVIRONMENT_ENV_VAR,
    SENTRY_EXCLUDED_ROUTES,
)
from sentry import initialize_sentry, sentry_traces_sampler


class TestInitializeSentry:
    """Tests for the initialize_sentry function."""

    def test_dsn_not_set(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that Sentry is not initialized when DSN env var is unset."""
        monkeypatch.delenv(SENTRY_DSN_ENV_VAR, raising=False)
        mock_init = mocker.patch("sentry.sentry_sdk.init")

        initialize_sentry()

        mock_init.assert_not_called()

    def test_dsn_empty_string(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that Sentry is not initialized when DSN is an empty string."""
        monkeypatch.setenv(SENTRY_DSN_ENV_VAR, "")
        mock_init = mocker.patch("sentry.sentry_sdk.init")

        initialize_sentry()

        mock_init.assert_not_called()

    def test_dsn_set_no_ca_certs(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test Sentry init without CA certs env var uses ca_certs=None."""
        dsn = "https://key@sentry.io/123"
        monkeypatch.setenv(SENTRY_DSN_ENV_VAR, dsn)
        monkeypatch.delenv(SENTRY_ENVIRONMENT_ENV_VAR, raising=False)
        monkeypatch.delenv(SENTRY_CA_CERTS_ENV_VAR, raising=False)
        mock_init = mocker.patch("sentry.sentry_sdk.init")

        initialize_sentry()

        mock_init.assert_called_once()
        call_kwargs = mock_init.call_args.kwargs
        assert call_kwargs["dsn"] == dsn
        assert call_kwargs["ca_certs"] is None
        assert call_kwargs["send_default_pii"] is False
        assert call_kwargs["environment"] == SENTRY_DEFAULT_ENVIRONMENT
        assert call_kwargs["release"].startswith("lightspeed-stack@")

    def test_ca_certs_file_exists(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that ca_certs is set when SENTRY_CA_CERTS points to an existing file."""
        ca_path = "/etc/pki/tls/certs/ca-bundle.crt"
        monkeypatch.setenv(SENTRY_DSN_ENV_VAR, "https://key@sentry.io/123")
        monkeypatch.setenv(SENTRY_CA_CERTS_ENV_VAR, ca_path)
        monkeypatch.delenv(SENTRY_ENVIRONMENT_ENV_VAR, raising=False)
        mock_init = mocker.patch("sentry.sentry_sdk.init")
        mocker.patch("sentry.os.path.exists", return_value=True)

        initialize_sentry()

        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["ca_certs"] == ca_path

    def test_ca_certs_file_missing(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that ca_certs is None and a warning is logged when the cert file is missing."""
        ca_path = "/nonexistent/ca-bundle.crt"
        monkeypatch.setenv(SENTRY_DSN_ENV_VAR, "https://key@sentry.io/123")
        monkeypatch.setenv(SENTRY_CA_CERTS_ENV_VAR, ca_path)
        monkeypatch.delenv(SENTRY_ENVIRONMENT_ENV_VAR, raising=False)
        mock_init = mocker.patch("sentry.sentry_sdk.init")
        mocker.patch("sentry.os.path.exists", return_value=False)
        mock_logger = mocker.patch("sentry.logger")

        initialize_sentry()

        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["ca_certs"] is None
        mock_logger.warning.assert_called_once_with(
            "CA cert file specified by %s not found at %s; "
            "proceeding without custom CA certs",
            SENTRY_CA_CERTS_ENV_VAR,
            ca_path,
        )

    def test_custom_environment(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that a custom SENTRY_ENVIRONMENT value is passed to init."""
        monkeypatch.setenv(SENTRY_DSN_ENV_VAR, "https://key@sentry.io/123")
        monkeypatch.setenv(SENTRY_ENVIRONMENT_ENV_VAR, "staging")
        mock_init = mocker.patch("sentry.sentry_sdk.init")

        initialize_sentry()

        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["environment"] == "staging"

    def test_default_environment(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that default environment is used when env var is unset."""
        monkeypatch.setenv(SENTRY_DSN_ENV_VAR, "https://key@sentry.io/123")
        monkeypatch.delenv(SENTRY_ENVIRONMENT_ENV_VAR, raising=False)
        mock_init = mocker.patch("sentry.sentry_sdk.init")

        initialize_sentry()

        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["environment"] == SENTRY_DEFAULT_ENVIRONMENT

    def test_init_failure_does_not_raise(
        self, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
    ) -> None:
        """Test that a failure during sentry_sdk.init does not propagate."""
        monkeypatch.setenv(SENTRY_DSN_ENV_VAR, "https://key@sentry.io/123")
        monkeypatch.delenv(SENTRY_ENVIRONMENT_ENV_VAR, raising=False)
        monkeypatch.delenv(SENTRY_CA_CERTS_ENV_VAR, raising=False)
        mocker.patch(
            "sentry.sentry_sdk.init", side_effect=RuntimeError("connection failed")
        )
        mock_logger = mocker.patch("sentry.logger")

        initialize_sentry()

        mock_logger.exception.assert_called_once_with(
            "Failed to initialize Sentry, continuing without error tracking"
        )


class TestSentryTracesSampler:
    """Tests for the sentry_traces_sampler function."""

    @pytest.mark.parametrize(
        "path",
        list(SENTRY_EXCLUDED_ROUTES),
        ids=[r.lstrip("/") or "root" for r in SENTRY_EXCLUDED_ROUTES],
    )
    def test_excluded_routes_return_zero(self, path: str) -> None:
        """Test that excluded routes produce a sample rate of 0.0."""
        context: dict = {"asgi_scope": {"path": path}}
        assert sentry_traces_sampler(context) == 0.0

    def test_excluded_route_suffix_match(self) -> None:
        """Test that suffix matching works for excluded routes (e.g. /prometheus/metrics)."""
        context: dict = {"asgi_scope": {"path": "/prometheus/metrics"}}
        assert sentry_traces_sampler(context) == 0.0

    @pytest.mark.parametrize(
        "path",
        ["/v1/query", "/v1/feedback", "/v1/query/"],
        ids=["query", "feedback", "query_trailing_slash"],
    )
    def test_normal_routes_return_default_rate(self, path: str) -> None:
        """Test that non-excluded routes use the default sample rate."""
        context: dict = {"asgi_scope": {"path": path}}
        assert sentry_traces_sampler(context) == SENTRY_DEFAULT_TRACES_SAMPLE_RATE

    def test_empty_context(self) -> None:
        """Test that an empty tracing context returns the default sample rate."""
        assert sentry_traces_sampler({}) == SENTRY_DEFAULT_TRACES_SAMPLE_RATE

    def test_missing_path_in_asgi_scope(self) -> None:
        """Test that missing path key in asgi_scope returns the default rate."""
        context: dict = {"asgi_scope": {}}
        assert sentry_traces_sampler(context) == SENTRY_DEFAULT_TRACES_SAMPLE_RATE

    def test_none_path_value(self) -> None:
        """Test that a None path value returns the default sample rate."""
        context: dict = {"asgi_scope": {"path": None}}
        assert sentry_traces_sampler(context) == SENTRY_DEFAULT_TRACES_SAMPLE_RATE
