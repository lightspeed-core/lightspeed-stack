"""Manage authentication flow for FastAPI endpoints with K8S/OCP."""

import logging
import os
from pathlib import Path
from typing import Optional, Self
from fastapi import Request, HTTPException

import kubernetes.client
from kubernetes.client.rest import ApiException
from kubernetes.config import ConfigException

from configuration import configuration
from auth.utils import extract_user_token
from auth.interface import AuthInterface
from constants import DEFAULT_VIRTUAL_PATH

logger = logging.getLogger(__name__)


CLUSTER_ID_LOCAL = "local"
RUNNING_IN_CLUSTER = (
    "KUBERNETES_SERVICE_HOST" in os.environ and "KUBERNETES_SERVICE_PORT" in os.environ
)


class ClusterIDUnavailableError(Exception):
    """Cluster ID is not available."""


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

    def __new__(cls: type[Self]) -> Self:
        """Create a new instance of the singleton, or returns the existing instance.

        This method initializes the Kubernetes API clients the first time it is called.
        and ensures that subsequent calls return the same instance.
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

                k8s_config.host = (
                    configuration.authentication_configuration.k8s_cluster_api
                    or k8s_config.host
                )
                k8s_config.verify_ssl = (
                    not configuration.authentication_configuration.skip_tls_verification
                )
                k8s_config.ssl_ca_cert = (
                    configuration.authentication_configuration.k8s_ca_cert_path
                    if configuration.authentication_configuration.k8s_ca_cert_path
                    not in {None, Path()}
                    else k8s_config.ssl_ca_cert
                )
                api_client = kubernetes.client.ApiClient(k8s_config)
                cls._api_client = api_client
                cls._custom_objects_api = kubernetes.client.CustomObjectsApi(api_client)
                cls._authn_api = kubernetes.client.AuthenticationV1Api(api_client)
                cls._authz_api = kubernetes.client.AuthorizationV1Api(api_client)
            except Exception as e:
                logger.info("Failed to initialize Kubernetes client: %s", e)
                raise
        return cls._instance

    @classmethod
    def get_authn_api(cls) -> kubernetes.client.AuthenticationV1Api:
        """Return the Authentication API client instance.

        Ensures the singleton is initialized before returning the Authentication API client.
        """
        if cls._instance is None or cls._authn_api is None:
            cls()
        return cls._authn_api

    @classmethod
    def get_authz_api(cls) -> kubernetes.client.AuthorizationV1Api:
        """Return the Authorization API client instance.

        Ensures the singleton is initialized before returning the Authorization API client.
        """
        if cls._instance is None or cls._authz_api is None:
            cls()
        return cls._authz_api

    @classmethod
    def get_custom_objects_api(cls) -> kubernetes.client.CustomObjectsApi:
        """Return the custom objects API instance.

        Ensures the singleton is initialized before returning the Authorization API client.
        """
        if cls._instance is None or cls._custom_objects_api is None:
            cls()
        return cls._custom_objects_api

    @classmethod
    def _get_cluster_id(cls) -> str:
        try:
            custom_objects_api = cls.get_custom_objects_api()
            version_data = custom_objects_api.get_cluster_custom_object(
                "config.openshift.io", "v1", "clusterversions", "version"
            )
            cluster_id = version_data["spec"]["clusterID"]
            cls._cluster_id = cluster_id
            return cluster_id
        except KeyError as e:
            logger.error(
                "Failed to get cluster_id from cluster, missing keys in version object"
            )
            raise ClusterIDUnavailableError("Failed to get cluster ID") from e
        except TypeError as e:
            logger.error(
                "Failed to get cluster_id, version object is: %s", version_data
            )
            raise ClusterIDUnavailableError("Failed to get cluster ID") from e
        except ApiException as e:
            logger.error("API exception during ClusterInfo: %s", e)
            raise ClusterIDUnavailableError("Failed to get cluster ID") from e
        except Exception as e:
            logger.error("Unexpected error during getting cluster ID: %s", e)
            raise ClusterIDUnavailableError("Failed to get cluster ID") from e

    @classmethod
    def get_cluster_id(cls) -> str:
        """Return the cluster ID."""
        if cls._instance is None:
            cls()
        if cls._cluster_id is None:
            if RUNNING_IN_CLUSTER:
                cls._cluster_id = cls._get_cluster_id()
            else:
                logger.debug("Not running in cluster, setting cluster_id to 'local'")
                cls._cluster_id = CLUSTER_ID_LOCAL
        return cls._cluster_id


def get_user_info(token: str) -> Optional[kubernetes.client.V1TokenReview]:
    """Perform a Kubernetes TokenReview to validate a given token.

    Args:
        token: The bearer token to be validated.

    Returns:
        The user information if the token is valid, None otherwise.
    """
    auth_api = K8sClientSingleton.get_authn_api()
    token_review = kubernetes.client.V1TokenReview(
        spec=kubernetes.client.V1TokenReviewSpec(token=token)
    )
    try:
        response = auth_api.create_token_review(token_review)
        if response.status.authenticated:
            return response.status
        return None
    except ApiException as e:
        logger.error("API exception during TokenReview: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error during TokenReview - Unauthorized: %s", e)
        raise HTTPException(
            status_code=500,
            detail={"response": "Forbidden: Unable to Review Token", "cause": str(e)},
        ) from e


def _extract_bearer_token(header: str) -> str:
    """Extract the bearer token from an HTTP authorization header.

    Args:
        header: The authorization header containing the token.

    Returns:
        The extracted token if present, else an empty string.
    """
    try:
        scheme, token = header.split(" ", 1)
        return token if scheme.lower() == "bearer" else ""
    except ValueError:
        return ""


class K8SAuthDependency(AuthInterface):  # pylint: disable=too-few-public-methods
    """No-op AuthDependency class that bypasses authentication and authorization checks."""

    def __init__(self, virtual_path: str = DEFAULT_VIRTUAL_PATH) -> None:
        """Initialize the required allowed paths for authorization checks."""
        self.virtual_path = virtual_path

    async def __call__(self, request: Request) -> tuple[str, str, str]:
        """Validate FastAPI Requests for authentication and authorization.

        Args:
            request: The FastAPI request object.

        Returns:
            The user's UID and username if authentication and authorization succeed
            user_id check is skipped with noop auth to allow consumers provide user_id
        """
        token = extract_user_token(request.headers)
        user_info = get_user_info(token)
        if user_info is None:
            raise HTTPException(
                status_code=403, detail="Forbidden: Invalid or expired token"
            )
        if user_info.user.username == "kube:admin":
            user_info.user.uid = K8sClientSingleton.get_cluster_id()
        authorization_api = K8sClientSingleton.get_authz_api()

        sar = kubernetes.client.V1SubjectAccessReview(
            spec=kubernetes.client.V1SubjectAccessReviewSpec(
                user=user_info.user.username,
                groups=user_info.user.groups,
                non_resource_attributes=kubernetes.client.V1NonResourceAttributes(
                    path=self.virtual_path, verb="get"
                ),
            )
        )
        try:
            response = authorization_api.create_subject_access_review(sar)
            if not response.status.allowed:
                raise HTTPException(
                    status_code=403, detail="Forbidden: User does not have access"
                )
        except ApiException as e:
            logger.error("API exception during SubjectAccessReview: %s", e)
            raise HTTPException(status_code=403, detail="Internal server error") from e

        return user_info.user.uid, user_info.user.username, token
