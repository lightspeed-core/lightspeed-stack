"""Unit tests for AuthenticationConfiguration model."""

from pathlib import Path

import pytest

from pydantic import ValidationError, SecretStr

from models.config import (
    AuthenticationConfiguration,
    Configuration,
    JwkConfiguration,
    RHIdentityConfiguration,
    LlamaStackConfiguration,
    ServiceConfiguration,
    UserDataCollection,
    APIKeyTokenConfiguration,
)

from constants import (
    AUTH_MOD_NOOP,
    AUTH_MOD_K8S,
    AUTH_MOD_JWK_TOKEN,
    AUTH_MOD_RH_IDENTITY,
    AUTH_MOD_APIKEY_TOKEN,
)


def test_authentication_configuration() -> None:
    """Test the AuthenticationConfiguration constructor."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_NOOP,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_NOOP
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None
    assert auth_config.rh_identity_config is None

    # try to retrieve JWK configuration
    with pytest.raises(
        ValueError,
        match="JWK configuration is only available for JWK token authentication module",
    ):
        _ = auth_config.jwk_configuration


def test_authentication_configuration_rh_identity() -> None:
    """Test the AuthenticationConfiguration with RH identity token."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_RH_IDENTITY,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
        rh_identity_config=RHIdentityConfiguration(required_entitlements=[]),
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_RH_IDENTITY
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None
    assert auth_config.rh_identity_config is not None
    assert auth_config.rh_identity_configuration is auth_config.rh_identity_config
    assert auth_config.rh_identity_configuration.required_entitlements == []


def test_authentication_configuration_rh_identity_default_value() -> None:
    """Test the AuthenticationConfiguration with RH identity token."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_RH_IDENTITY,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
        rh_identity_config=RHIdentityConfiguration(),
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_RH_IDENTITY
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None
    assert auth_config.rh_identity_config is not None
    assert auth_config.rh_identity_configuration is auth_config.rh_identity_config
    assert auth_config.rh_identity_configuration.required_entitlements is None


def test_authentication_configuration_rh_identity_one_entitlement() -> None:
    """Test the AuthenticationConfiguration with RH identity token."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_RH_IDENTITY,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
        rh_identity_config=RHIdentityConfiguration(required_entitlements=["foo"]),
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_RH_IDENTITY
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None
    assert auth_config.rh_identity_config is not None
    assert auth_config.rh_identity_configuration is auth_config.rh_identity_config
    assert auth_config.rh_identity_configuration.required_entitlements == ["foo"]


def test_authentication_configuration_rh_identity_more_entitlements() -> None:
    """Test the AuthenticationConfiguration with RH identity token."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_RH_IDENTITY,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
        rh_identity_config=RHIdentityConfiguration(
            required_entitlements=["foo", "bar", "baz"]
        ),
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_RH_IDENTITY
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None
    assert auth_config.rh_identity_config is not None
    assert auth_config.rh_identity_configuration is auth_config.rh_identity_config
    assert auth_config.rh_identity_configuration.required_entitlements == [
        "foo",
        "bar",
        "baz",
    ]


def test_authentication_configuration_rh_identity_but_insufficient_config() -> None:
    """Test the AuthenticationConfiguration with RH identity token."""

    with pytest.raises(
        ValidationError, match="RH Identity configuration must be specified"
    ):
        AuthenticationConfiguration(
            module=AUTH_MOD_RH_IDENTITY,
            skip_tls_verification=False,
            k8s_ca_cert_path=None,
            k8s_cluster_api=None,
        )


def test_authentication_configuration_jwk_token() -> None:
    """Test the AuthenticationConfiguration with JWK token."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_JWK_TOKEN,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
        jwk_config=JwkConfiguration(url="http://foo.bar.baz"),
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_JWK_TOKEN
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None

    # try to retrieve JWK configuration
    assert auth_config.jwk_configuration is not None


def test_authentication_configuration_jwk_token_but_insufficient_config() -> None:
    """Test the AuthenticationConfiguration with JWK token."""

    with pytest.raises(ValidationError, match="JwkConfiguration"):
        AuthenticationConfiguration(
            module=AUTH_MOD_JWK_TOKEN,
            skip_tls_verification=False,
            k8s_ca_cert_path=None,
            k8s_cluster_api=None,
            jwk_config=JwkConfiguration(),
        )


def test_authentication_configuration_jwk_token_but_not_config() -> None:
    """Test the AuthenticationConfiguration with JWK token."""

    with pytest.raises(
        ValidationError,
        match="Value error, JWK configuration must be specified when using JWK token",
    ):
        AuthenticationConfiguration(
            module=AUTH_MOD_JWK_TOKEN,
            skip_tls_verification=False,
            k8s_ca_cert_path=None,
            k8s_cluster_api=None,
            # no JwkConfiguration
        )


def test_authentication_configuration_jwk_broken_config() -> None:
    """Test the AuthenticationConfiguration with JWK set, but not configured."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_JWK_TOKEN,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
        jwk_config=JwkConfiguration(url="http://foo.bar.baz"),
    )
    assert auth_config is not None

    # emulate broken config
    auth_config.jwk_config = None
    # try to retrieve JWK configuration

    with pytest.raises(ValueError, match="JWK configuration should not be None"):
        _ = auth_config.jwk_configuration


def test_authentication_configuration_supported() -> None:
    """Test the AuthenticationConfiguration constructor."""
    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_K8S,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_K8S
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None


def test_authentication_configuration_module_unsupported() -> None:
    """Test the AuthenticationConfiguration constructor with module as None."""
    with pytest.raises(ValidationError, match="Unsupported authentication module"):
        AuthenticationConfiguration(
            module="non-existing-module",
            skip_tls_verification=False,
            k8s_ca_cert_path=None,
            k8s_cluster_api=None,
        )


def test_authentication_configuration_in_config_noop() -> None:
    """Test the authentication configuration in main config."""
    # pylint: disable=no-member
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=[],
    )
    assert cfg.authentication is not None
    assert cfg.authentication.module == AUTH_MOD_NOOP
    assert cfg.authentication.skip_tls_verification is False
    assert cfg.authentication.k8s_ca_cert_path is None
    assert cfg.authentication.k8s_cluster_api is None


def test_authentication_configuration_in_config_k8s() -> None:
    """Test the authentication configuration in main config."""
    # pylint: disable=no-member
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=[],
        authentication=AuthenticationConfiguration(
            module=AUTH_MOD_K8S,
            skip_tls_verification=True,
            k8s_ca_cert_path="tests/configuration/server.crt",
            k8s_cluster_api=None,
        ),
    )
    assert cfg.authentication is not None
    assert cfg.authentication.module == AUTH_MOD_K8S
    assert cfg.authentication.skip_tls_verification is True
    assert cfg.authentication.k8s_ca_cert_path == Path("tests/configuration/server.crt")
    assert cfg.authentication.k8s_cluster_api is None


def test_authentication_configuration_in_config_rh_identity() -> None:
    """Test the authentication configuration in main config."""
    # pylint: disable=no-member
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=[],
        authentication=AuthenticationConfiguration(
            module=AUTH_MOD_RH_IDENTITY,
            skip_tls_verification=True,
            k8s_ca_cert_path="tests/configuration/server.crt",
            k8s_cluster_api=None,
            rh_identity_config=RHIdentityConfiguration(required_entitlements=[]),
        ),
    )
    assert cfg.authentication is not None
    assert cfg.authentication.module == AUTH_MOD_RH_IDENTITY
    assert cfg.authentication.skip_tls_verification is True
    assert cfg.authentication.k8s_ca_cert_path == Path("tests/configuration/server.crt")
    assert cfg.authentication.k8s_cluster_api is None


def test_authentication_configuration_in_config_jwktoken() -> None:
    """Test the authentication configuration in main config."""
    # pylint: disable=no-member
    cfg = Configuration(
        name="test_name",
        service=ServiceConfiguration(),
        llama_stack=LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
        ),
        user_data_collection=UserDataCollection(
            feedback_enabled=False, feedback_storage=None
        ),
        mcp_servers=[],
        authentication=AuthenticationConfiguration(
            module=AUTH_MOD_JWK_TOKEN,
            skip_tls_verification=True,
            k8s_ca_cert_path="tests/configuration/server.crt",
            k8s_cluster_api=None,
            jwk_config=JwkConfiguration(url="http://foo.bar.baz"),
        ),
    )
    assert cfg.authentication is not None
    assert cfg.authentication.module == AUTH_MOD_JWK_TOKEN
    assert cfg.authentication.skip_tls_verification is True
    assert cfg.authentication.k8s_ca_cert_path == Path("tests/configuration/server.crt")
    assert cfg.authentication.k8s_cluster_api is None


def test_authentication_configuration_api_token() -> None:
    """Test the AuthenticationConfiguration with API Token."""

    auth_config = AuthenticationConfiguration(
        module=AUTH_MOD_APIKEY_TOKEN,
        skip_tls_verification=False,
        k8s_ca_cert_path=None,
        k8s_cluster_api=None,
        api_key_config=APIKeyTokenConfiguration(api_key=SecretStr("my-api-key")),
    )
    assert auth_config is not None
    assert auth_config.module == AUTH_MOD_APIKEY_TOKEN
    assert auth_config.skip_tls_verification is False
    assert auth_config.k8s_ca_cert_path is None
    assert auth_config.k8s_cluster_api is None

    assert auth_config.api_key_config is not None
    assert auth_config.api_key_configuration is auth_config.api_key_config
    assert auth_config.api_key_configuration.api_key is not None
    assert (
        auth_config.api_key_configuration.api_key is auth_config.api_key_config.api_key
    )


def test_authentication_configuration_api_key_but_insufficient_config() -> None:
    """Test the AuthenticationConfiguration with API Token."""

    with pytest.raises(
        ValidationError,
        match="API Key configuration section must be specified when using API Key token authentication",
    ):
        AuthenticationConfiguration(
            module=AUTH_MOD_APIKEY_TOKEN,
            skip_tls_verification=False,
            k8s_ca_cert_path=None,
            k8s_cluster_api=None,
        )
