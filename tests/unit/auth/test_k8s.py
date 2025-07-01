"""Unit tests for auth/k8s module."""

import os

import pytest
from fastapi import HTTPException, Request
from kubernetes.client import AuthenticationV1Api, AuthorizationV1Api
from kubernetes.client.rest import ApiException

from auth.k8s import (
    K8sClientSingleton,
    K8SAuthDependency,
    ClusterIDUnavailableError,
    CLUSTER_ID_LOCAL,
)


class MockK8sResponseStatus:
    """Mock Kubernetes Response Status.

    Holds the status of a mocked Kubernetes API response,
    including authentication and authorization details,
    and user information if authenticated.
    """

    def __init__(self, authenticated, allowed, username=None, uid=None, groups=None):
        """Init function."""
        self.authenticated = authenticated
        self.allowed = allowed
        if authenticated:
            self.user = MockK8sUser(username, uid, groups)
        else:
            self.user = None


class MockK8sUser:
    """Mock Kubernetes User.

    Represents a user in the mocked Kubernetes environment.
    """

    def __init__(self, username=None, uid=None, groups=None):
        """Init function."""
        self.username = username
        self.uid = uid
        self.groups = groups


class MockK8sResponse:
    """Mock Kubernetes API Response.

    This class is designed to mock Kubernetes API responses for testing purposes.
    """

    def __init__(
        self, authenticated=None, allowed=None, username=None, uid=None, groups=None
    ):
        """Init function."""
        self.status = MockK8sResponseStatus(
            authenticated, allowed, username, uid, groups
        )


def test_singleton_pattern():
    """Test if K8sClientSingleton is really a singleton."""
    k1 = K8sClientSingleton()
    k2 = K8sClientSingleton()
    assert k1 is k2


async def test_auth_dependency_valid_token(mocker):
    """Tests the auth dependency with a mocked valid-token."""
    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("auth.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("auth.k8s.K8sClientSingleton.get_authz_api")

    # Mock a successful token review response
    mock_authn_api.return_value.create_token_review.return_value = MockK8sResponse(
        authenticated=True, username="valid-user", uid="valid-uid", groups=["ols-group"]
    )
    mock_authz_api.return_value.create_subject_access_review.return_value = (
        MockK8sResponse(allowed=True)
    )

    # Simulate a request with a valid token
    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer valid-token")],
        }
    )

    user_uid, username, token = await dependency(request)

    # Check if the correct user info has been returned
    assert user_uid == "valid-uid"
    assert username == "valid-user"
    assert token == "valid-token"


async def test_auth_dependency_invalid_token(mocker):
    """Test the auth dependency with a mocked invalid-token."""
    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("auth.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("auth.k8s.K8sClientSingleton.get_authz_api")

    # Setup mock responses for invalid token
    mock_authn_api.return_value.create_token_review.return_value = MockK8sResponse(
        authenticated=False
    )
    mock_authz_api.return_value.create_subject_access_review.return_value = (
        MockK8sResponse(allowed=False)
    )

    # Simulate a request with an invalid token
    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid-token")],
        }
    )

    # Expect an HTTPException for invalid tokens
    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    # Check if the correct status code is returned for unauthorized access
    assert exc_info.value.status_code == 403


async def test_cluster_id_is_used_for_kube_admin(mocker):
    """Test the cluster id is used as user_id when user is kube:admin."""
    dependency = K8SAuthDependency()
    mock_authz_api = mocker.patch("auth.k8s.K8sClientSingleton.get_authz_api")
    mock_authz_api.return_value.create_subject_access_review.return_value = (
        MockK8sResponse(allowed=True)
    )

    # simulate a request with a valid token
    request = Request(
        scope={
            "type": "http",
            "headers": [(b"authorization", b"Bearer valid-token")],
        }
    )

    mocker.patch(
        "auth.k8s.get_user_info",
        return_value=MockK8sResponseStatus(
            authenticated=True,
            allowed=True,
            username="kube:admin",
            uid="some-uuid",
            groups=["ols-group"],
        ),
    )
    mocker.patch(
        "auth.k8s.K8sClientSingleton.get_cluster_id",
        return_value="some-cluster-id",
    )

    user_uid, username, token = await dependency(request)

    # check if the correct user info has been returned
    assert user_uid == "some-cluster-id"
    assert username == "kube:admin"
    assert token == "valid-token"


def test_auth_dependency_config(mocker):
    """Test the auth dependency can load kubeconfig file."""
    mocker.patch.dict(os.environ, {"MY_ENV_VAR": "mocked"})

    authn_client = K8sClientSingleton.get_authn_api()
    authz_client = K8sClientSingleton.get_authz_api()
    assert isinstance(
        authn_client, AuthenticationV1Api
    ), "authn_client is not an instance of AuthenticationV1Api"
    assert isinstance(
        authz_client, AuthorizationV1Api
    ), "authz_client is not an instance of AuthorizationV1Api"


def test_get_cluster_id(mocker):
    """Test get_cluster_id function."""
    mock_get_custom_objects_api = mocker.patch(
        "auth.k8s.K8sClientSingleton.get_custom_objects_api"
    )

    cluster_id = {"spec": {"clusterID": "some-cluster-id"}}
    mocked_call = mocker.MagicMock()
    mocked_call.get_cluster_custom_object.return_value = cluster_id
    mock_get_custom_objects_api.return_value = mocked_call
    assert K8sClientSingleton._get_cluster_id() == "some-cluster-id"

    # keyerror
    cluster_id = {"spec": {}}
    mocked_call = mocker.MagicMock()
    mocked_call.get_cluster_custom_object.return_value = cluster_id
    mock_get_custom_objects_api.return_value = mocked_call
    with pytest.raises(ClusterIDUnavailableError, match="Failed to get cluster ID"):
        K8sClientSingleton._get_cluster_id()

    # typeerror
    cluster_id = None
    mocked_call = mocker.MagicMock()
    mocked_call.get_cluster_custom_object.return_value = cluster_id
    mock_get_custom_objects_api.return_value = mocked_call
    with pytest.raises(ClusterIDUnavailableError, match="Failed to get cluster ID"):
        K8sClientSingleton._get_cluster_id()

    # typeerror
    mock_get_custom_objects_api.side_effect = ApiException()
    with pytest.raises(ClusterIDUnavailableError, match="Failed to get cluster ID"):
        K8sClientSingleton._get_cluster_id()

    # exception
    mock_get_custom_objects_api.side_effect = Exception()
    with pytest.raises(ClusterIDUnavailableError, match="Failed to get cluster ID"):
        K8sClientSingleton._get_cluster_id()


def test_get_cluster_id_in_cluster(mocker):
    """Test get_cluster_id function when running inside of cluster."""
    mocker.patch("auth.k8s.RUNNING_IN_CLUSTER", True)
    mocker.patch("auth.k8s.K8sClientSingleton.__new__")
    mock_get_cluster_id = mocker.patch("auth.k8s.K8sClientSingleton._get_cluster_id")

    mock_get_cluster_id.return_value = "some-cluster-id"
    assert K8sClientSingleton.get_cluster_id() == "some-cluster-id"


def test_get_cluster_id_outside_of_cluster(mocker):
    """Test get_cluster_id function when running outside of cluster."""
    mocker.patch("auth.k8s.RUNNING_IN_CLUSTER", False)
    mocker.patch("auth.k8s.K8sClientSingleton.__new__")

    # ensure cluster_id is None to trigger the condition
    K8sClientSingleton._cluster_id = None
    assert K8sClientSingleton.get_cluster_id() == CLUSTER_ID_LOCAL
