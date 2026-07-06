"""Unit tests for functions defined in authentication/__init__.py"""

from authentication import (
    get_auth_dependency,
    k8s,
    noop,
    noop_with_token,
    trusted_proxy,
)
from configuration import configuration
from constants import (
    AUTH_MOD_K8S,
    AUTH_MOD_NOOP,
    AUTH_MOD_NOOP_WITH_TOKEN,
    AUTH_MOD_TRUSTED_PROXY,
)
from models.config import TrustedProxyConfiguration


def test_get_auth_dependency_noop() -> None:
    """Test getting Noop authentication dependency."""
    assert configuration.authentication_configuration is not None
    configuration.authentication_configuration.module = AUTH_MOD_NOOP
    auth_dependency = get_auth_dependency()
    assert isinstance(auth_dependency, noop.NoopAuthDependency)


def test_get_auth_dependency_noop_with_token() -> None:
    """Test getting Noop with token authentication dependency."""
    assert configuration.authentication_configuration is not None
    configuration.authentication_configuration.module = AUTH_MOD_NOOP_WITH_TOKEN
    auth_dependency = get_auth_dependency()
    assert isinstance(auth_dependency, noop_with_token.NoopWithTokenAuthDependency)


def test_get_auth_dependency_k8s() -> None:
    """Test getting K8s authentication dependency."""
    assert configuration.authentication_configuration is not None
    configuration.authentication_configuration.module = AUTH_MOD_K8S
    auth_dependency = get_auth_dependency()
    assert isinstance(auth_dependency, k8s.K8SAuthDependency)


def test_get_auth_dependency_trusted_proxy() -> None:
    """Test getting trusted-proxy authentication dependency."""
    assert configuration.authentication_configuration is not None
    configuration.authentication_configuration.module = AUTH_MOD_TRUSTED_PROXY
    configuration.authentication_configuration.trusted_proxy_config = (
        TrustedProxyConfiguration()
    )
    auth_dependency = get_auth_dependency()
    assert isinstance(auth_dependency, trusted_proxy.TrustedProxyAuthDependency)
