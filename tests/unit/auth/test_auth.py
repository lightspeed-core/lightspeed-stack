"""Unit tests for functions defined in auth/__init__.py"""

from auth import get_auth_dependency
from auth import noop, noop_with_token, k8s
from constants import AUTH_MOD_NOOP, AUTH_MOD_NOOP_WITH_TOKEN, AUTH_MOD_K8S
from configuration import configuration


def test_get_auth_dependency_noop():
    """Test getting Noop authentication dependency."""
    configuration.authentication_configuration.module = AUTH_MOD_NOOP
    auth_dependency = get_auth_dependency()
    assert isinstance(auth_dependency, noop.NoopAuthDependency)


def test_get_auth_dependency_noop_with_token():
    """Test getting Noop with token authentication dependency."""
    configuration.authentication_configuration.module = AUTH_MOD_NOOP_WITH_TOKEN
    auth_dependency = get_auth_dependency()
    assert isinstance(auth_dependency, noop_with_token.NoopWithTokenAuthDependency)


def test_get_auth_dependency_k8s():
    """Test getting K8s authentication dependency."""
    configuration.authentication_configuration.module = AUTH_MOD_K8S
    auth_dependency = get_auth_dependency()
    assert isinstance(auth_dependency, k8s.K8SAuthDependency)
