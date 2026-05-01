"""Manage authentication flow for FastAPI endpoints with K8S/OCP."""

import os
import time
from http import HTTPStatus
from typing import Optional, Self, cast

import kubernetes.client
from fastapi import HTTPException, Request
from kubernetes.client.rest import ApiException
from kubernetes.config import ConfigException

from authentication.interface import NO_AUTH_TUPLE, AuthInterface
from authentication.utils import extract_user_token, record_auth_metrics
from configuration import configuration
from constants import AUTH_MOD_K8S, DEFAULT_VIRTUAL_PATH
from log import get_logger
from models.api.responses import (
    ForbiddenResponse,
    InternalServerErrorResponse,
    ServiceUnavailableResponse,
    UnauthorizedResponse,
)

logger = get_logger(__name__)


CLUSTER_ID_LOCAL = "local"
RUNNING_IN_CLUSTER = (
    "KUBERNETES_SERVICE_HOST" in os.environ and "KUBERNETES_SERVICE_PORT" in os.environ
)


class K8sAuthenticationError(Exception):
    """Base exception for Kubernetes authentication errors."""


class K8sAPIConnectionError(K8sAuthenticationError):
    """Cannot connect to Kubernetes API server.

    Indicates transient failures that may be resolved by retrying.
    Maps to HTTP 503 Service Unavailable.
    """


class K8sConfigurationError(K8sAuthenticationError):
    """Kubernetes cluster configuration issue.

    Indicates persistent configuration problems requiring admin intervention.
    Maps to HTTP 500 Internal Server Error.
    """


class ClusterVersionNotFoundError(K8sConfigurationError):
    """ClusterVersion resource not found in OpenShift cluster.

    Raised when the ClusterVersion custom resource does not exist (HTTP 404).
    """


class ClusterVersionPermissionError(K8sConfigurationError):
    """No permission to access ClusterVersion resource.

    Raised when RBAC denies access to the ClusterVersion resource (HTTP 403).
    """


class InvalidClusterVersionError(K8sConfigurationError):
    """ClusterVersion resource has invalid structure or missing required fields.

    Raised when the ClusterVersion exists but is missing spec.clusterID or has wrong type.
    """


class K8sClientSingleton:
    """Return the Kubernetes client instances.

    Ensures we initialize the k8s client only once per application life cycle.
    manage the initialization and config loading.
    """

    _instance = None
    _api_client = None
    _authn_api: kubernetes.client.AuthenticationV1Api
    _authz_api: kubernetes.client.AuthorizationV1Api
    _cluster_id = None
    _custom_objects_api: kubernetes.client.CustomObjectsApi

    def __new__(cls: type[Self]) -> Self:
        """Create a new instance of the singleton, or returns the existing instance.

        This method initializes the Kubernetes API clients the first time it is called.
        and ensures that subsequent calls return the same instance.

        Returns:
            instance (K8sClientSingleton): The singleton instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            k8s_config = kubernetes.client.Configuration()

            try:
                try:
                    logger.info("loading in-cluster config")
                    kubernetes.config.load_incluster_config(
                        client_configuration=k8s_config
                    )
                except ConfigException as e:
                    logger.debug("unable to load in-cluster config: %s", e)
                    try:
                        logger.info("loading config from kube-config file")
                        kubernetes.config.load_kube_config(
                            client_configuration=k8s_config
                        )
                    except ConfigException as ce:
                        logger.error(
                            "failed to load kubeconfig, in-cluster config\
                                and no override token was provided: %s",
                            ce,
                        )

                k8s_api_url = configuration.authentication_configuration.k8s_cluster_api
                if k8s_api_url is not None:
                    k8s_config.host = str(k8s_api_url)
                k8s_config.verify_ssl = (
                    not configuration.authentication_configuration.skip_tls_verification
                )
                ca_cert_path = (
                    configuration.authentication_configuration.k8s_ca_cert_path
                )
                if ca_cert_path is not None:
                    # Kubernetes client library has incomplete type stubs for ssl_ca_cert
                    k8s_config.ssl_ca_cert = str(ca_cert_path)  # type: ignore[assignment]
                # else keep the default k8s_config.ssl_ca_cert
                api_client = kubernetes.client.ApiClient(k8s_config)
                cls._api_client = api_client
                cls._custom_objects_api = kubernetes.client.CustomObjectsApi(api_client)
                cls._authn_api = kubernetes.client.AuthenticationV1Api(api_client)
                cls._authz_api = kubernetes.client.AuthorizationV1Api(api_client)
            except Exception as e:
                logger.info("Failed to initialize Kubernetes client: %s", e)
                raise
        # At this point _instance is guaranteed to be initialized
        return cast(Self, cls._instance)

    @classmethod
    def get_authn_api(cls) -> kubernetes.client.AuthenticationV1Api:
        """Return the Authentication API client instance.

        Ensures the singleton is initialized before returning the Authentication API client.

        Returns:
            kubernetes.client.AuthenticationV1Api: The initialized AuthenticationV1Api instance.
        """
        if cls._instance is None or cls._authn_api is None:
            cls()
        return cls._authn_api

    @classmethod
    def get_authz_api(cls) -> kubernetes.client.AuthorizationV1Api:
        """Return the Authorization API client instance.

        Ensures the singleton is initialized before returning the Authorization API client.

        Returns:
            kubernetes.client.AuthorizationV1Api: The Kubernetes Authorization
                                                  API client instance.
        """
        if cls._instance is None or cls._authz_api is None:
            cls()
        return cls._authz_api

    @classmethod
    def get_custom_objects_api(cls) -> kubernetes.client.CustomObjectsApi:
        """Return the custom objects API instance.

        Ensures the singleton is initialized before returning the Authorization API client.

        Returns:
            kubernetes.client.CustomObjectsApi: The CustomObjectsApi client used by the singleton.
        """
        if cls._instance is None or cls._custom_objects_api is None:
            cls()
        return cls._custom_objects_api

    @classmethod
    def _get_cluster_id(cls) -> str:
        """
        Retrieve the OpenShift cluster ID from the ClusterVersion custom object and cache it.

        Fetches the "version" ClusterVersion from group
        `config.openshift.io/v1`, extracts `spec.clusterID`, assigns it to
        `cls._cluster_id`, and returns it.

        Returns:
            str: The cluster's `clusterID`.

        Raises:
            K8sAPIConnectionError: If the Kubernetes API is unreachable or returns 5xx errors.
            ClusterVersionNotFoundError: If the ClusterVersion resource does not exist (404).
            ClusterVersionPermissionError: If access to ClusterVersion is denied (403).
            InvalidClusterVersionError: If ClusterVersion has invalid structure or missing fields.
        """
        try:
            custom_objects_api = cls.get_custom_objects_api()
            # Kubernetes API always returns dict for custom objects
            version_data = cast(
                dict,
                custom_objects_api.get_cluster_custom_object(
                    "config.openshift.io", "v1", "clusterversions", "version"
                ),
            )
            spec = version_data.get("spec")
            if not isinstance(spec, dict):
                raise InvalidClusterVersionError(
                    "Missing or invalid 'spec' in ClusterVersion"
                )
            cluster_id = spec.get("clusterID")
            if not isinstance(cluster_id, str) or not cluster_id.strip():
                raise InvalidClusterVersionError(
                    "Missing or invalid 'clusterID' in ClusterVersion"
                )
            cls._cluster_id = cluster_id
            return cluster_id
        except ApiException as e:
            # Handle specific HTTP status codes from Kubernetes API
            if e.status is None:
                # No status code indicates a connection/network issue
                logger.error("Kubernetes API error with no status code: %s", e.reason)
                raise K8sAPIConnectionError(
                    f"Failed to connect to Kubernetes API: {e.reason}"
                ) from e

            if e.status == HTTPStatus.NOT_FOUND:
                logger.error(
                    "ClusterVersion resource 'version' not found in cluster: %s",
                    e.reason,
                )
                raise ClusterVersionNotFoundError(
                    "ClusterVersion 'version' resource not found in OpenShift cluster"
                ) from e
            if e.status == HTTPStatus.FORBIDDEN:
                logger.error(
                    "Permission denied to access ClusterVersion resource: %s", e.reason
                )
                raise ClusterVersionPermissionError(
                    "Insufficient permissions to read ClusterVersion resource"
                ) from e
            # Classify errors by status code range
            # 5xx errors and 429 (rate limit) are transient - map to 503
            if (
                e.status >= HTTPStatus.INTERNAL_SERVER_ERROR
                or e.status == HTTPStatus.TOO_MANY_REQUESTS
            ):
                logger.error(
                    "Kubernetes API unavailable while fetching ClusterVersion (status %s): %s",
                    e.status,
                    e.reason,
                )
                raise K8sAPIConnectionError(
                    f"Failed to connect to Kubernetes API: {e.reason} (status {e.status})"
                ) from e
            # All other errors (4xx client errors) are configuration issues - map to 500
            logger.error(
                "Kubernetes API returned client error while fetching "
                "ClusterVersion (status %s): %s",
                e.status,
                e.reason,
            )
            raise K8sConfigurationError(
                f"Kubernetes API request failed: {e.reason} (status {e.status})"
            ) from e

    @classmethod
    def get_cluster_id(cls) -> str:
        """Return the cluster ID.

        Get the cached Kubernetes cluster identifier, initializing the
        singleton and fetching the ID when necessary.

        If running outside a cluster, sets and returns the sentinel value
        "local". When running inside a cluster, attempts to fetch and cache the
        cluster ID via the private retrieval method.

        Returns:
            str: The cluster identifier.

        Raises:
            K8sAPIConnectionError: If the Kubernetes API is unreachable.
            ClusterVersionNotFoundError: If the ClusterVersion resource does not exist.
            ClusterVersionPermissionError: If access to ClusterVersion is denied.
            InvalidClusterVersionError: If ClusterVersion has invalid structure.
        """
        if cls._instance is None:
            cls()
        if cls._cluster_id is None:
            if RUNNING_IN_CLUSTER:
                cls._cluster_id = cls._get_cluster_id()
            else:
                logger.debug("Not running in cluster, setting cluster_id to 'local'")
                cls._cluster_id = CLUSTER_ID_LOCAL
        return cls._cluster_id


def get_user_info(token: str) -> Optional[kubernetes.client.V1TokenReviewStatus]:
    """Perform a Kubernetes TokenReview to validate a given token.

    Parameters:
    ----------
        token: The bearer token to be validated.

    Returns:
    -------
        The V1TokenReviewStatus if the token is valid, None otherwise.

    Raises:
    ------
        HTTPException:
            503 if Kubernetes API is unavailable (5xx errors, 429 rate limit).
            503 if unable to initialize Kubernetes client.
            500 if Kubernetes API configuration issue (4xx errors).
    """
    try:
        auth_api = K8sClientSingleton.get_authn_api()
    except Exception as e:
        logger.error("Failed to get Kubernetes authentication API: %s", e)
        response = ServiceUnavailableResponse(
            backend_name="Kubernetes API",
            cause="Unable to initialize Kubernetes client",
        )
        raise HTTPException(**response.model_dump()) from e

    token_review = kubernetes.client.V1TokenReview(
        spec=kubernetes.client.V1TokenReviewSpec(token=token)
    )
    try:
        response = cast(
            kubernetes.client.V1TokenReview,
            auth_api.create_token_review(token_review),
        )
        status = response.status
        if status is not None and status.authenticated:
            return status
        return None
    except ApiException as e:
        if e.status is None:
            logger.error(
                "Kubernetes API error during TokenReview with no status code: %s",
                e.reason,
            )
            response = ServiceUnavailableResponse(
                backend_name="Kubernetes API",
                cause=f"Failed to connect to Kubernetes API: {e.reason}",
            )
            raise HTTPException(**response.model_dump()) from e

        # 5xx errors and 429 (rate limit) are transient - map to 503
        if (
            e.status >= HTTPStatus.INTERNAL_SERVER_ERROR
            or e.status == HTTPStatus.TOO_MANY_REQUESTS
        ):
            logger.error(
                "Kubernetes API unavailable during TokenReview (status %s): %s",
                e.status,
                e.reason,
            )
            response = ServiceUnavailableResponse(
                backend_name="Kubernetes API",
                cause=f"Kubernetes API unavailable: {e.reason} (status {e.status})",
            )
            raise HTTPException(**response.model_dump()) from e

        # All other errors (4xx client errors) are configuration issues - map to 500
        logger.error(
            "Kubernetes API returned client error during TokenReview (status %s): %s",
            e.status,
            e.reason,
        )
        response_obj = InternalServerErrorResponse(
            response="Internal server error",
            cause=f"Kubernetes API request failed: {e.reason} (status {e.status})",
        )
        raise HTTPException(**response_obj.model_dump()) from e
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Unexpected error during TokenReview: %s", e)
        response_obj = InternalServerErrorResponse(
            response="Internal server error",
            cause=f"Unexpected error during TokenReview: {e}",
        )
        raise HTTPException(**response_obj.model_dump()) from e


def _populate_kube_admin_uid(
    user: kubernetes.client.V1UserInfo, start_time: float
) -> None:
    """Populate kube:admin UID from the cluster ID and record bounded failures."""
    if user.username != "kube:admin":
        return
    try:
        user.uid = K8sClientSingleton.get_cluster_id()
    except K8sAPIConnectionError as e:
        logger.error("Cannot connect to Kubernetes API: %s", e)
        record_auth_metrics(AUTH_MOD_K8S, "failure", "k8s_api_unavailable", start_time)
        response = ServiceUnavailableResponse(
            backend_name="Kubernetes API",
            cause=str(e),
        )
        raise HTTPException(**response.model_dump()) from e
    except K8sConfigurationError as e:
        logger.error("Cluster configuration error: %s", e)
        record_auth_metrics(AUTH_MOD_K8S, "failure", "k8s_config_error", start_time)
        response = InternalServerErrorResponse(
            response="Internal server error",
            cause=str(e),
        )
        raise HTTPException(**response.model_dump()) from e
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Unexpected error while resolving kube:admin cluster ID")
        record_auth_metrics(AUTH_MOD_K8S, "failure", "unexpected_error", start_time)
        response = InternalServerErrorResponse(
            response="Internal server error",
            cause=str(e),
        )
        raise HTTPException(**response.model_dump()) from e


def _create_subject_access_review(
    user: kubernetes.client.V1UserInfo, virtual_path: str, start_time: float
) -> kubernetes.client.V1SubjectAccessReview:
    """Create a Kubernetes SubjectAccessReview and record bounded failures."""
    try:
        authorization_api = K8sClientSingleton.get_authz_api()
    except Exception as e:
        logger.error("Failed to initialize Kubernetes authorization API: %s", e)
        record_auth_metrics(AUTH_MOD_K8S, "failure", "k8s_api_unavailable", start_time)
        response = ServiceUnavailableResponse(
            backend_name="Kubernetes API",
            cause=f"Unable to initialize Kubernetes client: {e}",
        )
        raise HTTPException(**response.model_dump()) from e

    try:
        sar = kubernetes.client.V1SubjectAccessReview(
            spec=kubernetes.client.V1SubjectAccessReviewSpec(
                user=user.username,
                groups=user.groups,
                non_resource_attributes=kubernetes.client.V1NonResourceAttributes(
                    path=virtual_path, verb="get"
                ),
            )
        )
        return cast(
            kubernetes.client.V1SubjectAccessReview,
            authorization_api.create_subject_access_review(sar),
        )
    except ApiException as e:
        record_auth_metrics(
            AUTH_MOD_K8S, "failure", "authorization_check_error", start_time
        )
        if e.status is None:
            logger.error(
                "Kubernetes API error during SubjectAccessReview with no status code: %s",
                e.reason,
            )
            response = ServiceUnavailableResponse(
                backend_name="Kubernetes API",
                cause=f"Failed to connect to Kubernetes API: {e.reason}",
            )
            raise HTTPException(**response.model_dump()) from e

        if (
            e.status >= HTTPStatus.INTERNAL_SERVER_ERROR
            or e.status == HTTPStatus.TOO_MANY_REQUESTS
        ):
            logger.error(
                "Kubernetes API unavailable during SubjectAccessReview (status %s): %s",
                e.status,
                e.reason,
            )
            response = ServiceUnavailableResponse(
                backend_name="Kubernetes API",
                cause=f"Kubernetes API unavailable: {e.reason} (status {e.status})",
            )
            raise HTTPException(**response.model_dump()) from e

        logger.error(
            "Kubernetes API returned client error during SubjectAccessReview (status %s): %s",
            e.status,
            e.reason,
        )
        response_obj = InternalServerErrorResponse(
            response="Internal server error",
            cause=f"Kubernetes API request failed: {e.reason} (status {e.status})",
        )
        raise HTTPException(**response_obj.model_dump()) from e
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Unexpected error during SubjectAccessReview")
        record_auth_metrics(AUTH_MOD_K8S, "failure", "unexpected_error", start_time)
        response = InternalServerErrorResponse(
            response="Internal server error",
            cause=str(e),
        )
        raise HTTPException(**response.model_dump()) from e


class K8SAuthDependency(AuthInterface):  # pylint: disable=too-few-public-methods
    """FastAPI dependency for Kubernetes (k8s) authentication and authorization.

    K8SAuthDependency is an authentication and authorization dependency for FastAPI endpoints,
    integrating with Kubernetes RBAC via SubjectAccessReview (SAR).

    This class extracts the user token from the request headers, retrieves user information,
    and performs a Kubernetes SAR to determine if the user is authorized.

    Raises:
        HTTPException: HTTP 403 if the token is invalid, expired, or the user is not authorized.

    """

    def __init__(self, virtual_path: str = DEFAULT_VIRTUAL_PATH) -> None:
        """Initialize the required allowed paths for authorization checks.

        Create a K8SAuthDependency configured for performing
        SubjectAccessReview checks on a specific virtual path.

        Parameters:
        ----------
            virtual_path (str): The request path used in SubjectAccessReview
            non-resource attributes; defaults to DEFAULT_VIRTUAL_PATH.

        Attributes set:
            virtual_path: Stored `virtual_path` value.
            skip_userid_check (bool): Flag indicating whether user ID checks
                                      should be skipped; initialized to False.
        """
        self.virtual_path = virtual_path
        self.skip_userid_check = False

    async def __call__(self, request: Request) -> tuple[str, str, bool, str]:
        """Validate FastAPI Requests for authentication and authorization.

        Parameters:
        ----------
            request: The FastAPI request object.

        Returns:
        -------
            The user's UID and username if authentication and authorization succeed
            user_id check should never be skipped with K8s authentication
            If user_id check should be skipped - always return False for k8s
            User's token

        Raises:
        ------
            HTTPException: If authentication or authorization fails.
        """
        start_time = time.monotonic()

        # LCORE-694: Config option to skip authorization for readiness and liveness probe
        if not request.headers.get("Authorization"):
            if configuration.authentication_configuration.skip_for_health_probes:
                if request.url.path in ("/readiness", "/liveness"):
                    record_auth_metrics(
                        AUTH_MOD_K8S, "skipped", "health_probe", start_time
                    )
                    return NO_AUTH_TUPLE
            # Skip auth for metrics endpoint when configured
            if configuration.authentication_configuration.skip_for_metrics:
                if request.url.path in ("/metrics",):
                    record_auth_metrics(AUTH_MOD_K8S, "skipped", "metrics", start_time)
                    return NO_AUTH_TUPLE

        try:
            token = extract_user_token(request.headers)
        except HTTPException:
            record_auth_metrics(AUTH_MOD_K8S, "failure", "missing_token", start_time)
            raise
        try:
            user_info = get_user_info(token)
        except HTTPException:
            record_auth_metrics(
                AUTH_MOD_K8S, "failure", "token_review_error", start_time
            )
            raise

        if user_info is None:
            record_auth_metrics(AUTH_MOD_K8S, "failure", "invalid_token", start_time)
            response = UnauthorizedResponse(cause="Invalid or expired Kubernetes token")
            raise HTTPException(**response.model_dump())

        # Cast user to proper type for type checking
        user = cast(kubernetes.client.V1UserInfo, user_info.user)

        _populate_kube_admin_uid(user, start_time)
        sar_response = _create_subject_access_review(
            user, self.virtual_path, start_time
        )

        sar_status = cast(
            kubernetes.client.V1SubjectAccessReviewStatus, sar_response.status
        )
        user_uid = cast(str, user.uid)
        username = cast(str, user.username)

        if not sar_status.allowed:
            record_auth_metrics(AUTH_MOD_K8S, "failure", "not_authorized", start_time)
            response = ForbiddenResponse.endpoint(user_id=user_uid)
            raise HTTPException(**response.model_dump())

        record_auth_metrics(AUTH_MOD_K8S, "success", "authenticated", start_time)
        return (
            user_uid,
            username,
            self.skip_userid_check,
            token,
        )
