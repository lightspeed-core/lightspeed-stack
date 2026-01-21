"""Unit tests for authentication/k8s module."""

# pylint: disable=too-many-arguments,too-many-positional-arguments,too-few-public-methods,protected-access

import os
from typing import Optional, cast

import pytest
from fastapi import HTTPException, Request
from kubernetes.client import AuthenticationV1Api, AuthorizationV1Api
from kubernetes.client.rest import ApiException
from pytest_mock import MockerFixture

from authentication.k8s import (
    CLUSTER_ID_LOCAL,
    ClusterIDUnavailableError,
    K8SAuthDependency,
    K8sClientSingleton,
)

from configuration import AppConfig


class MockK8sResponseStatus:
    """Mock Kubernetes Response Status.

    Holds the status of a mocked Kubernetes API response,
    including authentication and authorization details,
    and user information if authenticated.
    """

    def __init__(
        self,
        authenticated: Optional[bool],
        allowed: Optional[bool],
        username: Optional[str] = None,
        uid: Optional[str] = None,
        groups: Optional[list[str]] = None,
    ) -> None:
        """Init function.

        Initialize a mock Kubernetes response status representing
        authentication and authorization results.

        Parameters:
            authenticated (Optional[bool]): Whether the token was
            authenticated; when True, `user` is populated.
            allowed (Optional[bool]): Whether the action is authorized (subject
            access review result).
            username (Optional[str]): Username to set on the created
            `MockK8sUser` when `authenticated` is True.
            uid (Optional[str]): User UID to set on the created `MockK8sUser`
            when `authenticated` is True.
            groups (Optional[list[str]]): Group list to set on the created
            `MockK8sUser` when `authenticated` is True.
        """
        self.authenticated = authenticated
        self.allowed = allowed
        self.user: Optional[MockK8sUser]
        if authenticated:
            self.user = MockK8sUser(username, uid, groups)
        else:
            self.user = None


class MockK8sUser:
    """Mock Kubernetes User.

    Represents a user in the mocked Kubernetes environment.
    """

    def __init__(
        self,
        username: Optional[str] = None,
        uid: Optional[str] = None,
        groups: Optional[list[str]] = None,
    ) -> None:
        """Init function.

        Create a mock Kubernetes user holding identity attributes.

        Parameters:
                username (Optional[str]): The user's username, or None if not provided.
                uid (Optional[str]): The user's unique identifier, or None if not provided.
                groups (Optional[list[str]]): List of groups the user belongs
                to, or None if not provided.
        """
        self.username = username
        self.uid = uid
        self.groups = groups


class MockK8sResponse:
    """Mock Kubernetes API Response.

    This class is designed to mock Kubernetes API responses for testing purposes.
    """

    def __init__(
        self,
        authenticated: Optional[bool] = None,
        allowed: Optional[bool] = None,
        username: Optional[str] = None,
        uid: Optional[str] = None,
        groups: Optional[list[str]] = None,
    ) -> None:
        """Init function.

        Initialize a mock Kubernetes API response wrapper containing a status object.

        Parameters:
            authenticated (Optional[bool]): Whether the token was authenticated; use None to omit.
            allowed (Optional[bool]): Whether the action is authorized; use None to omit.
            username (Optional[str]): Username of the authenticated user, if any.
            uid (Optional[str]): User ID of the authenticated user, if any.
            groups (Optional[list[str]]): Groups the authenticated user belongs to, if any.
        """
        self.status = MockK8sResponseStatus(
            authenticated, allowed, username, uid, groups
        )


def test_singleton_pattern() -> None:
    """Test if K8sClientSingleton is really a singleton."""
    k1 = K8sClientSingleton()
    k2 = K8sClientSingleton()
    assert k1 is k2


async def test_auth_dependency_valid_token(mocker: MockerFixture) -> None:
    """Tests the auth dependency with a mocked valid-token."""
    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authz_api")

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

    user_uid, username, skip_userid_check, token = await dependency(request)

    # Check if the correct user info has been returned
    assert user_uid == "valid-uid"
    assert username == "valid-user"
    assert skip_userid_check is False
    assert token == "valid-token"


async def test_auth_dependency_invalid_token(mocker: MockerFixture) -> None:
    """Test the auth dependency with a mocked invalid-token."""
    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authz_api")

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
    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["response"] == ("Missing or invalid credentials provided by client")
    assert detail["cause"] == "Invalid or expired Kubernetes token"


async def test_auth_dependency_no_token(mocker: MockerFixture) -> None:
    """Test the auth dependency without a token."""
    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authz_api")

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
            "headers": [],
        }
    )

    # Expect an HTTPException for invalid tokens
    with pytest.raises(HTTPException) as exc_info:
        await dependency(request)

    # Check if the correct status code is returned for unauthorized access
    assert exc_info.value.status_code == 401
    detail = cast(dict[str, str], exc_info.value.detail)
    assert detail["response"] == ("Missing or invalid credentials provided by client")
    assert detail["cause"] == "No Authorization header found"


async def test_auth_dependency_no_token_readiness_liveness_endpoints_1(
    mocker: MockerFixture,
) -> None:
    """Test the auth dependency without a token for readiness and liveness endpoints.

    For this test the skip_for_health_probes configuration parameter is set to
    True.
    """
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "authentication": {
            "module": "k8s",
            "skip_for_health_probes": True,
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": ".",
            "transcripts_enabled": False,
            "transcripts_storage": ".",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    # Update configuration for this test
    mocker.patch("authentication.k8s.configuration", cfg)

    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authz_api")

    # Setup mock responses for invalid token
    mock_authn_api.return_value.create_token_review.return_value = MockK8sResponse(
        authenticated=False
    )
    mock_authz_api.return_value.create_subject_access_review.return_value = (
        MockK8sResponse(allowed=False)
    )

    paths = ("/readiness", "/liveness")

    for path in paths:
        # Simulate a request with an invalid token
        request = Request(
            scope={
                "type": "http",
                "headers": [],
                "path": path,
            }
        )

        user_uid, username, skip_userid_check, token = await dependency(request)

        # Check if the correct user info has been returned
        assert user_uid == "00000000-0000-0000-0000-000"
        assert username == "lightspeed-user"
        assert skip_userid_check is True
        assert token == ""


async def test_auth_dependency_no_token_readiness_liveness_endpoints_2(
    mocker: MockerFixture,
) -> None:
    """Test the auth dependency without a token.

    For this test the skip_for_health_probes configuration parameter is set to
    False.
    """

    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "authentication": {
            "module": "k8s",
            "skip_for_health_probes": False,
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": ".",
            "transcripts_enabled": False,
            "transcripts_storage": ".",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    # Update configuration for this test
    mocker.patch("authentication.k8s.configuration", cfg)
    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authz_api")

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
            "headers": [],
        }
    )

    paths = ("/readiness", "/liveness")

    for path in paths:
        # Simulate a request with an invalid token
        request = Request(
            scope={
                "type": "http",
                "headers": [],
                "path": path,
            }
        )

        # Expect an HTTPException for invalid tokens
        with pytest.raises(HTTPException) as exc_info:
            await dependency(request)

        # Check if the correct status code is returned for unauthorized access
        assert exc_info.value.status_code == 401
        detail = cast(dict[str, str], exc_info.value.detail)
        assert detail["response"] == (
            "Missing or invalid credentials provided by client"
        )
        assert detail["cause"] == "No Authorization header found"


async def test_auth_dependency_no_token_normal_endpoints(
    mocker: MockerFixture,
) -> None:
    """Test the auth dependency without a token for endpoints different to readiness and liveness.

    For this test the skip_for_health_probes configuration parameter is set to
    True.
    """
    config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "authentication": {
            "module": "k8s",
            "skip_for_health_probes": True,
        },
        "user_data_collection": {
            "feedback_enabled": False,
            "feedback_storage": ".",
            "transcripts_enabled": False,
            "transcripts_storage": ".",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    # Update configuration for this test
    mocker.patch("authentication.k8s.configuration", cfg)

    dependency = K8SAuthDependency()

    # Mock the Kubernetes API calls
    mock_authn_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authn_api")
    mock_authz_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authz_api")

    # Setup mock responses for invalid token
    mock_authn_api.return_value.create_token_review.return_value = MockK8sResponse(
        authenticated=False
    )
    mock_authz_api.return_value.create_subject_access_review.return_value = (
        MockK8sResponse(allowed=False)
    )

    paths = ("/", "/v1/info")

    for path in paths:
        # Simulate a request with an invalid token
        request = Request(
            scope={
                "type": "http",
                "headers": [],
                "path": path,
            }
        )

        # Expect an HTTPException for invalid tokens
        with pytest.raises(HTTPException) as exc_info:
            await dependency(request)

        # Check if the correct status code is returned for unauthorized access
        assert exc_info.value.status_code == 401
        detail = cast(dict[str, str], exc_info.value.detail)
        assert detail["response"] == (
            "Missing or invalid credentials provided by client"
        )
        assert detail["cause"] == "No Authorization header found"


async def test_cluster_id_is_used_for_kube_admin(mocker: MockerFixture) -> None:
    """Test the cluster id is used as user_id when user is kube:admin."""
    dependency = K8SAuthDependency()
    mock_authz_api = mocker.patch("authentication.k8s.K8sClientSingleton.get_authz_api")
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
        "authentication.k8s.get_user_info",
        return_value=MockK8sResponseStatus(
            authenticated=True,
            allowed=True,
            username="kube:admin",
            uid="some-uuid",
            groups=["ols-group"],
        ),
    )
    mocker.patch(
        "authentication.k8s.K8sClientSingleton.get_cluster_id",
        return_value="some-cluster-id",
    )

    user_uid, username, skip_userid_check, token = await dependency(request)

    # check if the correct user info has been returned
    assert user_uid == "some-cluster-id"
    assert username == "kube:admin"
    assert skip_userid_check is False
    assert token == "valid-token"


def test_auth_dependency_config(mocker: MockerFixture) -> None:
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


def test_get_cluster_id(mocker: MockerFixture) -> None:
    """Test get_cluster_id function."""
    mock_get_custom_objects_api = mocker.patch(
        "authentication.k8s.K8sClientSingleton.get_custom_objects_api"
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
    cluster_id = None  # type: ignore
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


def test_get_cluster_id_in_cluster(mocker: MockerFixture) -> None:
    """Test get_cluster_id function when running inside of cluster."""
    mocker.patch("authentication.k8s.RUNNING_IN_CLUSTER", True)
    mocker.patch("authentication.k8s.K8sClientSingleton.__new__")
    mock_get_cluster_id = mocker.patch(
        "authentication.k8s.K8sClientSingleton._get_cluster_id"
    )

    mock_get_cluster_id.return_value = "some-cluster-id"
    assert K8sClientSingleton.get_cluster_id() == "some-cluster-id"


def test_get_cluster_id_outside_of_cluster(mocker: MockerFixture) -> None:
    """Test get_cluster_id function when running outside of cluster."""
    mocker.patch("authentication.k8s.RUNNING_IN_CLUSTER", False)
    mocker.patch("authentication.k8s.K8sClientSingleton.__new__")

    # ensure cluster_id is None to trigger the condition
    K8sClientSingleton._cluster_id = None
    assert K8sClientSingleton.get_cluster_id() == CLUSTER_ID_LOCAL
